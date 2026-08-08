from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_HOST, CONF_PORT, CONF_TRANSPORT, DEFAULT_BASE_TOPIC, DEFAULT_WEB_URL, DEFAULT_TRANSPORT

@dataclass(frozen=True)
class CasambiBridgeSensorDefinition:
    key: str
    name: str
    topic_suffix: str | None
    icon: str
    parser: Callable[[str], Any] | None = None
    static_key: str | None = None

def _plain(payload: str) -> str:
    return payload

SENSORS = (
    CasambiBridgeSensorDefinition("availability", "Availability", "availability", "mdi:server-network", _plain),
    CasambiBridgeSensorDefinition("bridge_status", "Bridge Status", "status/bridge", "mdi:bridge", _plain),
    CasambiBridgeSensorDefinition("ble_status", "BLE Status", "status/ble", "mdi:bluetooth", _plain),
    CasambiBridgeSensorDefinition("bridge_version", "Bridge Version", "diagnostics/bridge_version", "mdi:cellphone-cog", _plain),
    CasambiBridgeSensorDefinition("last_sync", "Last API Sync", "diagnostics/last_sync", "mdi:cloud-sync", _plain),
    CasambiBridgeSensorDefinition("active_scene", "Active Scene", "diagnostics/active_scene", "mdi:palette", _plain),
    CasambiBridgeSensorDefinition("web_interface_url", "Web Interface URL", None, "mdi:web", static_key=CONF_WEB_URL),
    CasambiBridgeSensorDefinition("transport_mode", "Transport Mode", None, "mdi:transit-connection-variant", static_key=CONF_TRANSPORT),
    CasambiBridgeSensorDefinition("direct_api_url", "Direct API URL", None, "mdi:api", static_key="direct_api_url"),
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/")
    async_add_entities(CasambiBridgeSensor(entry, base_topic, description) for description in SENSORS)

class CasambiBridgeSensor(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, entry: ConfigEntry, base_topic: str, definition: CasambiBridgeSensorDefinition) -> None:
        self._entry = entry
        self._base_topic = base_topic
        self._definition = definition
        self._attr_unique_id = f"{entry.entry_id}_{definition.key}"
        self.entity_description = SensorEntityDescription(key=definition.key, name=definition.name, icon=definition.icon)
        self._attr_native_value: Any = None
        self._unsubscribe: Callable[[], None] | None = None
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)}, name=self._entry.title, manufacturer="Casambi Jungle", model="Android BLE Bridge")
    async def async_added_to_hass(self) -> None:
        if self._definition.static_key is not None:
            if self._definition.static_key == CONF_WEB_URL:
                self._attr_native_value = self._entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL) or "not configured"
            elif self._definition.static_key == CONF_TRANSPORT:
                self._attr_native_value = self._entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
            elif self._definition.static_key == "direct_api_url":
                web_url = self._entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL) or ""
                self._attr_native_value = f"{web_url}/api/info" if web_url else "not configured"
            else:
                self._attr_native_value = "unknown"
            self.async_write_ha_state()
            return
        topic = f"{self._base_topic}/{self._definition.topic_suffix}"
        @callback
        def message_received(msg) -> None:
            self._attr_native_value = (self._definition.parser or _plain)(msg.payload)
            self.async_write_ha_state()
        self._unsubscribe = await mqtt.async_subscribe(self.hass, topic, message_received, qos=0)
    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
