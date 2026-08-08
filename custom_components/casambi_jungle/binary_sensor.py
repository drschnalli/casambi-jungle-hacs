from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_BASE_TOPIC, CONF_SCENES, CONF_UNITS, DEFAULT_BASE_TOPIC
from .light import normalize_units_payload


def normalize_scene_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return []
    if isinstance(payload, dict):
        scenes = payload.get("scenes", [])
    elif isinstance(payload, list):
        scenes = payload
    else:
        return []
    out: list[dict[str, Any]] = []
    if not isinstance(scenes, list):
        return out
    for item in scenes:
        if not isinstance(item, dict):
            continue
        scene_id = item.get("id") or item.get("sceneID") or item.get("scene_id")
        scene_name = item.get("name") or item.get("sceneName") or item.get("scene_name")
        try:
            scene_id_int = int(scene_id)
        except Exception:
            continue
        out.append({"id": scene_id_int, "name": str(scene_name or f"Scene {scene_id_int}")})
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/")
    scene_manager = CasambiSceneActiveManager(hass, entry, base_topic, async_add_entities)
    unit_manager = CasambiUnitOnlineManager(hass, entry, base_topic, async_add_entities)
    hass.data[DOMAIN][entry.entry_id].scene_active_manager = scene_manager
    hass.data[DOMAIN][entry.entry_id].unit_online_manager = unit_manager
    await scene_manager.async_start()
    await unit_manager.async_start()


class CasambiSceneActiveManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, base_topic: str, async_add_entities: AddEntitiesCallback) -> None:
        self.hass = hass
        self.entry = entry
        self.base_topic = base_topic
        self.async_add_entities = async_add_entities
        self._entities: dict[int, CasambiSceneActiveBinarySensor] = {}
        self._active_scene = ""
        self._active_scene_id = -1
        self._unsubscribe_scenes: Callable[[], None] | None = None
        self._unsubscribe_active: Callable[[], None] | None = None
        self._unsubscribe_active_id: Callable[[], None] | None = None

    async def async_start(self) -> None:
        self._add_scenes(normalize_scene_payload(self.entry.data.get(CONF_SCENES, [])))

        @callback
        def scenes_received(msg) -> None:
            self._add_scenes(normalize_scene_payload(msg.payload))

        @callback
        def active_received(msg) -> None:
            self._active_scene = str(msg.payload or "")
            self._update_active()

        @callback
        def active_id_received(msg) -> None:
            try:
                self._active_scene_id = int(str(msg.payload).strip())
            except Exception:
                self._active_scene_id = -1
            self._update_active()

        self._unsubscribe_scenes = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/scenes", scenes_received, qos=0)
        self._unsubscribe_active = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/diagnostics/active_scene", active_received, qos=0)
        self._unsubscribe_active_id = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/diagnostics/active_scene_id", active_id_received, qos=0)

    def _add_scenes(self, scenes: list[dict[str, Any]]) -> None:
        new: list[CasambiSceneActiveBinarySensor] = []
        for item in scenes:
            try:
                scene_id = int(item.get("id"))
            except Exception:
                continue
            name = str(item.get("name") or f"Scene {scene_id}")
            if scene_id in self._entities:
                self._entities[scene_id].update_name(name)
                continue
            entity = CasambiSceneActiveBinarySensor(self.entry, scene_id, name, self._active_scene, self._active_scene_id)
            self._entities[scene_id] = entity
            new.append(entity)
        if new:
            self.async_add_entities(new)
            self._update_active()

    def _update_active(self) -> None:
        for entity in self._entities.values():
            entity.set_active_scene(self._active_scene, self._active_scene_id)


class CasambiUnitOnlineManager:
    """Create one online binary sensor per Casambi unit."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, base_topic: str, async_add_entities: AddEntitiesCallback) -> None:
        self.hass = hass
        self.entry = entry
        self.base_topic = base_topic
        self.async_add_entities = async_add_entities
        self._entities: dict[int, CasambiUnitOnlineBinarySensor] = {}
        self._unsubscribe_discovery: Callable[[], None] | None = None
        self._unsubscribe_units: Callable[[], None] | None = None

    async def async_start(self) -> None:
        initial = normalize_units_payload(self.entry.data.get(CONF_UNITS, []))
        if not initial:
            initial = [{"id": 1, "name": "Casambi Unit 1"}]
        self._add_units(initial)

        @callback
        def units_payload_received(msg) -> None:
            units = normalize_units_payload(msg.payload)
            if units:
                self._add_units(units)

        self._unsubscribe_discovery = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/discovery", units_payload_received, qos=0)
        self._unsubscribe_units = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/units", units_payload_received, qos=0)

    def _add_units(self, units: list[dict[str, Any]]) -> None:
        new: list[CasambiUnitOnlineBinarySensor] = []
        for item in units:
            try:
                unit_id = int(item.get("id"))
            except Exception:
                continue
            name = str(item.get("name") or f"Casambi Unit {unit_id}")
            if unit_id in self._entities:
                self._entities[unit_id].update_unit_name(name)
                continue
            entity = CasambiUnitOnlineBinarySensor(self.entry, self.base_topic, unit_id, name)
            self._entities[unit_id] = entity
            new.append(entity)
        if new:
            self.async_add_entities(new)


class CasambiSceneActiveBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, scene_id: int, scene_name: str, active_scene: str = "", active_scene_id: int = -1) -> None:
        self._entry = entry
        self._scene_id = scene_id
        self._scene_name = scene_name
        self._active_scene = active_scene
        self._active_scene_id = active_scene_id
        self._attr_unique_id = f"{entry.entry_id}_scene_{scene_id}_active"
        self._attr_name = f"{scene_name} Active"
        self._attr_icon = "mdi:check-circle-outline"

    @property
    def is_on(self) -> bool:
        return self._active_scene_id == self._scene_id or self._active_scene.strip().lower() == self._scene_name.strip().lower()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id, "scenes")},
            name="Casambi Scenes",
            manufacturer="Casambi Jungle",
            model="Scene Collection",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"scene_id": self._scene_id, "scene_name": self._scene_name, "active_scene": self._active_scene, "active_scene_id": self._active_scene_id}

    def set_active_scene(self, active_scene: str, active_scene_id: int = -1) -> None:
        self._active_scene = active_scene
        self._active_scene_id = active_scene_id
        if self.enabled:
            self.async_write_ha_state()

    def update_name(self, scene_name: str) -> None:
        if scene_name == self._scene_name:
            return
        self._scene_name = scene_name
        self._attr_name = f"{scene_name} Active"
        if self.enabled:
            self.async_write_ha_state()


class CasambiUnitOnlineBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, base_topic: str, unit_id: int, unit_name: str) -> None:
        self._entry = entry
        self._base_topic = base_topic
        self._unit_id = unit_id
        self._unit_name = unit_name
        self._attr_unique_id = f"{entry.entry_id}_unit_{unit_id}_online"
        self._attr_name = "Online"
        self._attr_icon = "mdi:connection"
        self._is_on = False
        self._unsubscribe: Callable[[], None] | None = None

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id, f"unit_{self._unit_id}")},
            name=self._unit_name,
            manufacturer="Casambi",
            model="Casambi Unit",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"unit_id": self._unit_id, "unit_name": self._unit_name, "mqtt_state_topic": f"{self._base_topic}/light/{self._unit_id}/state"}

    async def async_added_to_hass(self) -> None:
        @callback
        def message_received(msg) -> None:
            try:
                data = json.loads(msg.payload)
            except Exception:
                data = {}
            unit_name = data.get("unit_name")
            if unit_name:
                self.update_unit_name(str(unit_name))
            online = data.get("online")
            if isinstance(online, bool):
                self._is_on = online
            else:
                state = str(data.get("state", "OFF")).upper()
                self._is_on = state in {"ON", "OFF"}
            self.async_write_ha_state()

        self._unsubscribe = await mqtt.async_subscribe(self.hass, f"{self._base_topic}/light/{self._unit_id}/state", message_received, qos=0)

    def update_unit_name(self, unit_name: str) -> None:
        if not unit_name or unit_name == self._unit_name:
            return
        self._unit_name = unit_name
        if self.enabled:
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
