from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_BASE_TOPIC, CONF_UNITS, DEFAULT_BASE_TOPIC


def _normalize_units_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize Android discovery/unit payload into a list of units."""
    if payload is None:
        return []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return []
    if isinstance(payload, dict):
        units = payload.get("units", [])
    elif isinstance(payload, list):
        units = payload
    else:
        return []
    out: list[dict[str, Any]] = []
    if not isinstance(units, list):
        return out
    for item in units:
        if not isinstance(item, dict):
            continue
        unit_id = item.get("id") or item.get("unit_id") or item.get("deviceID") or item.get("address")
        unit_name = item.get("name") or item.get("unit_name") or item.get("label")
        try:
            unit_id_int = int(unit_id)
        except Exception:
            continue
        out.append({"id": unit_id_int, "name": str(unit_name or f"Casambi Unit {unit_id_int}")})
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/")
    manager = CasambiUnitLightManager(hass, entry, base_topic, async_add_entities)
    hass.data[DOMAIN][entry.entry_id].light_manager = manager
    await manager.async_start()


class CasambiUnitLightManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, base_topic: str, async_add_entities: AddEntitiesCallback) -> None:
        self.hass = hass
        self.entry = entry
        self.base_topic = base_topic
        self.async_add_entities = async_add_entities
        self._lights: dict[int, CasambiUnitLight] = {}
        self._unsubscribe_discovery: Callable[[], None] | None = None

    async def async_start(self) -> None:
        initial = _normalize_units_payload(self.entry.data.get(CONF_UNITS, []))
        if not initial:
            initial = [{"id": 1, "name": "Casambi Unit 1"}]
        self._add_units(initial)

        @callback
        def discovery_received(msg) -> None:
            units = _normalize_units_payload(msg.payload)
            if units:
                self._add_units(units)

        self._unsubscribe_discovery = await mqtt.async_subscribe(
            self.hass,
            f"{self.base_topic}/discovery",
            discovery_received,
            qos=0,
        )

    def _add_units(self, units: list[dict[str, Any]]) -> None:
        new_entities: list[CasambiUnitLight] = []
        for item in units:
            try:
                unit_id = int(item.get("id"))
            except Exception:
                continue
            name = str(item.get("name") or f"Casambi Unit {unit_id}")
            if unit_id in self._lights:
                self._lights[unit_id].update_unit_name(name)
                continue
            entity = CasambiUnitLight(self.entry, self.base_topic, unit_id, name)
            self._lights[unit_id] = entity
            new_entities.append(entity)
        if new_entities:
            self.async_add_entities(new_entities)


class CasambiUnitLight(LightEntity):
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, entry: ConfigEntry, base_topic: str, unit_id: int, unit_name: str) -> None:
        self._entry = entry
        self._base_topic = base_topic
        self._unit_id = unit_id
        self._unit_name = unit_name
        self._attr_unique_id = f"{entry.entry_id}_unit_{unit_id}_light"
        self._attr_name = unit_name
        self._is_on = False
        self._brightness = 0
        self._online: bool | None = None
        self._unsubscribe: Callable[[], None] | None = None

    @property
    def name(self) -> str | None:
        return self._unit_name

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int:
        return self._brightness

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"unit_id": self._unit_id, "unit_name": self._unit_name, "online": self._online}

    @property
    def device_identifiers(self) -> tuple[str, str, str]:
        return (DOMAIN, self._entry.entry_id, f"unit_{self._unit_id}")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={self.device_identifiers},
            name=self._unit_name,
            manufacturer="Casambi",
            model="Casambi Unit",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    async def async_added_to_hass(self) -> None:
        topic = f"{self._base_topic}/light/{self._unit_id}/state"

        @callback
        def message_received(msg) -> None:
            try:
                data = json.loads(msg.payload)
            except Exception:
                data = {}
            unit_name = data.get("unit_name")
            if unit_name:
                self.update_unit_name(str(unit_name))
            state = str(data.get("state", "OFF")).upper()
            try:
                brightness = int(data.get("brightness", 0) or 0)
            except Exception:
                brightness = 0
            self._brightness = max(0, min(255, brightness))
            self._is_on = state == "ON" and self._brightness > 0
            self._online = data.get("online")
            self.async_write_ha_state()

        self._unsubscribe = await mqtt.async_subscribe(self.hass, topic, message_received, qos=0)

    def update_unit_name(self, unit_name: str) -> None:
        if not unit_name or unit_name == self._unit_name:
            return
        self._unit_name = unit_name
        self._attr_name = unit_name
        if self.hass is not None:
            registry = dr.async_get(self.hass)
            device = registry.async_get_device({self.device_identifiers})
            if device is not None:
                registry.async_update_device(device.id, name=unit_name)
            if self.enabled:
                self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        payload: dict[str, Any] = {"state": "ON"}
        if brightness is not None:
            payload["brightness"] = int(brightness)
        elif self._brightness > 0:
            payload["brightness"] = self._brightness
        await mqtt.async_publish(self.hass, f"{self._base_topic}/light/{self._unit_id}/set", json.dumps(payload), qos=0, retain=False)

    async def async_turn_off(self, **kwargs) -> None:
        await mqtt.async_publish(self.hass, f"{self._base_topic}/light/{self._unit_id}/set", json.dumps({"state": "OFF"}), qos=0, retain=False)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
