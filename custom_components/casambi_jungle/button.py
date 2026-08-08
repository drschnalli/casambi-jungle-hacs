from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_BASE_TOPIC, CONF_SCENES, DEFAULT_BASE_TOPIC


@dataclass(frozen=True)
class CasambiButtonDefinition:
    key: str
    name: str
    command_suffix: str
    payload: str
    icon: str


BRIDGE_BUTTONS = (
    CasambiButtonDefinition("api_fetch", "API Fetch", "button/api_fetch/set", "PRESS", "mdi:cloud-download"),
    CasambiButtonDefinition("restart_bridge", "Restart Bridge", "button/restart/set", "PRESS", "mdi:restart"),
)


def _normalize_scene_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize Android scene payload into a list of scene dictionaries."""
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
        name = str(scene_name or f"Scene {scene_id_int}")
        out.append({"id": scene_id_int, "name": name})
    return out


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/")
    async_add_entities(CasambiBridgeButton(entry, base_topic, definition) for definition in BRIDGE_BUTTONS)
    manager = CasambiSceneButtonManager(hass, entry, base_topic, async_add_entities)
    await manager.async_start()


class CasambiBridgeButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, base_topic: str, definition: CasambiButtonDefinition) -> None:
        self._entry = entry
        self._base_topic = base_topic
        self._definition = definition
        self._attr_unique_id = f"{entry.entry_id}_{definition.key}"
        self.entity_description = ButtonEntityDescription(key=definition.key, name=definition.name, icon=definition.icon)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Casambi Jungle",
            model="Android BLE Bridge",
        )

    async def async_press(self) -> None:
        await mqtt.async_publish(
            self.hass,
            f"{self._base_topic}/{self._definition.command_suffix}",
            self._definition.payload,
            qos=0,
            retain=False,
        )


class CasambiSceneButtonManager:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        base_topic: str,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.base_topic = base_topic
        self.async_add_entities = async_add_entities
        self._scene_buttons: dict[int, CasambiSceneButton] = {}
        self._unsubscribe_scenes: Callable[[], None] | None = None
        self._unsubscribe_active: Callable[[], None] | None = None
        self._unsubscribe_active_id: Callable[[], None] | None = None
        self._active_scene = ""
        self._active_scene_id = -1

    async def async_start(self) -> None:
        initial = _normalize_scene_payload(self.entry.data.get(CONF_SCENES, []))
        self._add_scenes(initial)

        @callback
        def scenes_received(msg) -> None:
            scenes = _normalize_scene_payload(msg.payload)
            self._add_scenes(scenes)

        @callback
        def active_received(msg) -> None:
            self._active_scene = str(msg.payload or "")
            self._update_active_state()

        @callback
        def active_id_received(msg) -> None:
            try:
                self._active_scene_id = int(str(msg.payload).strip())
            except Exception:
                self._active_scene_id = -1
            self._update_active_state()

        self._unsubscribe_scenes = await mqtt.async_subscribe(
            self.hass,
            f"{self.base_topic}/scenes",
            scenes_received,
            qos=0,
        )
        self._unsubscribe_active = await mqtt.async_subscribe(
            self.hass,
            f"{self.base_topic}/diagnostics/active_scene",
            active_received,
            qos=0,
        )
        self._unsubscribe_active_id = await mqtt.async_subscribe(
            self.hass,
            f"{self.base_topic}/diagnostics/active_scene_id",
            active_id_received,
            qos=0,
        )

    def _add_scenes(self, scenes: list[dict[str, Any]]) -> None:
        new_entities: list[CasambiSceneButton] = []
        for item in scenes:
            try:
                scene_id = int(item.get("id"))
            except Exception:
                continue
            name = str(item.get("name") or f"Scene {scene_id}")
            if scene_id in self._scene_buttons:
                self._scene_buttons[scene_id].update_name(name)
                continue
            entity = CasambiSceneButton(self.entry, self.base_topic, scene_id, name, self._active_scene, self._active_scene_id)
            self._scene_buttons[scene_id] = entity
            new_entities.append(entity)
        if new_entities:
            self.async_add_entities(new_entities)
            self._update_active_state()

    def _update_active_state(self) -> None:
        for button in self._scene_buttons.values():
            button.set_active_scene(self._active_scene, self._active_scene_id)


class CasambiSceneButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        base_topic: str,
        scene_id: int,
        scene_name: str,
        active_scene: str = "",
        active_scene_id: int = -1,
    ) -> None:
        self._entry = entry
        self._base_topic = base_topic
        self._scene_id = scene_id
        self._scene_name = scene_name
        self._active_scene = active_scene
        self._active_scene_id = active_scene_id
        self._attr_unique_id = f"{entry.entry_id}_scene_{scene_id}"
        self.entity_description = ButtonEntityDescription(key=f"scene_{scene_id}", name=scene_name, icon="mdi:palette")

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
        active_by_id = self._active_scene_id == self._scene_id
        active_by_name = self._active_scene.strip().lower() == self._scene_name.strip().lower()
        return {
            "scene_id": self._scene_id,
            "scene_name": self._scene_name,
            "active": active_by_id or active_by_name,
            "active_scene": self._active_scene,
            "active_scene_id": self._active_scene_id,
        }

    def set_active_scene(self, active_scene: str, active_scene_id: int = -1) -> None:
        self._active_scene = active_scene
        self._active_scene_id = active_scene_id
        self.async_write_ha_state()

    def update_name(self, scene_name: str) -> None:
        self._scene_name = scene_name
        self.entity_description = ButtonEntityDescription(key=f"scene_{self._scene_id}", name=scene_name, icon="mdi:palette")
        self.async_write_ha_state()

    async def async_press(self) -> None:
        await mqtt.async_publish(
            self.hass,
            f"{self._base_topic}/scene/{self._scene_id}/set",
            "PRESS",
            qos=0,
            retain=False,
        )
