from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_BASE_TOPIC,
    CONF_WEB_URL,
    CONF_TRANSPORT,
    DEFAULT_BASE_TOPIC,
    DEFAULT_WEB_URL,
    DEFAULT_TRANSPORT,
    FRONTEND_CARD_REPO,
)
from .direct_api import direct_available, direct_get_json


@dataclass(frozen=True)
class D:
    key: str
    name: str
    topic: str | None
    icon: str
    static: str | None = None


SENSORS = (
    D("availability", "Availability", "availability", "mdi:server-network"),
    D("bridge_status", "Bridge Status", "status/bridge", "mdi:bridge"),
    D("ble_status", "BLE Status", "status/ble", "mdi:bluetooth"),
    D("bridge_version", "Bridge Version", "diagnostics/bridge_version", "mdi:cellphone-cog"),
    D("last_sync", "Last API Sync", "diagnostics/last_sync", "mdi:cloud-sync"),
    D("active_scene", "Active Scene", "diagnostics/active_scene", "mdi:palette"),
    D("web_interface_url", "Web Interface URL", None, "mdi:web", CONF_WEB_URL),
    D("transport_mode", "Transport Mode", None, "mdi:transit-connection-variant", CONF_TRANSPORT),
    D("direct_api_url", "Direct API URL", None, "mdi:api", "direct_api_url"),
    D("frontend_card_repository", "Frontend Card Repository", None, "mdi:cards", "card_repo"),
)


class CasambiDirectStatusPoller:
    """Shared REST poller per config entry.

    v2.2.0 subscribed to MQTT topics for Bridge/BLE status. That leaves stale retained
    values when MQTT is turned off. This poller makes Direct/Hybrid entries use the
    Android Bridge REST API as the primary source of truth.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.status: dict[str, Any] = {}
        self.info: dict[str, Any] = {}
        self._unsub = None
        self._listeners: set[CasambiBridgeSensor] = set()

    def add_listener(self, sensor: "CasambiBridgeSensor") -> None:
        self._listeners.add(sensor)

    def remove_listener(self, sensor: "CasambiBridgeSensor") -> None:
        self._listeners.discard(sensor)

    async def async_start(self) -> None:
        if not direct_available(self.entry):
            return
        await self.async_refresh(None)
        self._unsub = async_track_time_interval(self.hass, self.async_refresh, timedelta(seconds=2))

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def async_refresh(self, _now) -> None:
        if not direct_available(self.entry):
            return
        status = await direct_get_json(self.hass, self.entry, "/api/status")
        info = await direct_get_json(self.hass, self.entry, "/api/info")
        if isinstance(status, dict) and status.get("ok") is not False:
            self.status = status
        if isinstance(info, dict) and info.get("ok") is not False:
            self.info = info
        for sensor in list(self._listeners):
            sensor.update_from_direct()

    def transport_mode(self) -> str:
        mode = str(self.info.get("mode") or "").strip().lower()
        if mode in {"direct", "hybrid", "mqtt"}:
            return mode
        mqtt_enabled = self.info.get("mqtt_enabled")
        direct_enabled = self.info.get("direct_enabled")
        if direct_enabled is True and mqtt_enabled is True:
            return "hybrid"
        if direct_enabled is True and mqtt_enabled is False:
            return "direct"
        if mqtt_enabled is True:
            return "mqtt"
        return str(self.entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT) or DEFAULT_TRANSPORT)

    def value_for(self, key: str) -> str | int | None:
        status = self.status
        info = self.info
        if key == "availability":
            return "online" if status else None
        if key == "bridge_status":
            value = status.get("bridge")
            return str(value) if value is not None else ("online" if status else None)
        if key == "ble_status":
            value = status.get("ble")
            if isinstance(value, bool):
                return "connected" if value else "disconnected"
            return str(value) if value is not None else None
        if key == "bridge_version":
            return str(status.get("version") or info.get("version") or "") or None
        if key == "last_sync":
            text = status.get("lastSyncText")
            if text:
                return str(text)
            millis = int(status.get("lastSync") or 0)
            return "never" if millis <= 0 else str(millis)
        if key == "active_scene":
            return str(status.get("lastSceneName") or "none")
        if key == "transport_mode":
            return self.transport_mode()
        return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    base = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/")
    poller = CasambiDirectStatusPoller(hass, entry)
    hass.data[DOMAIN][entry.entry_id].direct_status_poller = poller
    entities = [CasambiBridgeSensor(entry, base, d, poller) for d in SENSORS]
    async_add_entities(entities)
    await poller.async_start()


class CasambiBridgeSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, base: str, d: D, poller: CasambiDirectStatusPoller) -> None:
        self._entry = entry
        self._base = base
        self._d = d
        self._poller = poller
        self._attr_unique_id = f"{entry.entry_id}_{d.key}"
        self.entity_description = SensorEntityDescription(key=d.key, name=d.name, icon=d.icon)
        self._attr_native_value = None
        self._unsubscribe = None

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Casambi Jungle",
            model="Android BLE Bridge",
        )

    async def async_added_to_hass(self):
        self._poller.add_listener(self)
        if self._d.static is not None:
            self._apply_static_value()
            self.update_from_direct()
            self.async_write_ha_state()
            return
        if self._d.topic:
            @callback
            def received(msg):
                # MQTT stays as fallback/legacy source. Direct polling overwrites this
                # shortly afterwards if a Direct API URL is configured.
                self._attr_native_value = msg.payload
                self.async_write_ha_state()
            self._unsubscribe = await mqtt.async_subscribe(self.hass, f"{self._base}/{self._d.topic}", received, qos=0)
        self.update_from_direct()
        self.async_write_ha_state()

    def _apply_static_value(self) -> None:
        if self._d.static == CONF_WEB_URL:
            self._attr_native_value = self._entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL) or "not configured"
        elif self._d.static == CONF_TRANSPORT:
            self._attr_native_value = self._entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
        elif self._d.static == "direct_api_url":
            url = self._entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL) or ""
            self._attr_native_value = f"{url.rstrip('/')}/api/info" if url else "not configured"
        elif self._d.static == "card_repo":
            self._attr_native_value = FRONTEND_CARD_REPO

    def update_from_direct(self) -> None:
        if not direct_available(self._entry):
            return
        if self._d.key == "direct_api_url":
            self._apply_static_value()
        elif self._d.key == "web_interface_url":
            self._apply_static_value()
        elif self._d.key == "frontend_card_repository":
            self._apply_static_value()
        else:
            value = self._poller.value_for(self._d.key)
            if value not in (None, ""):
                self._attr_native_value = value
        if self.hass:
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self):
        self._poller.remove_listener(self)
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
