from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components import mqtt, persistent_notification
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_SCENES, DEFAULT_BASE_TOPIC, DEFAULT_WEB_URL
from .direct_api import direct_available, direct_get_json


@dataclass(frozen=True)
class CasambiButtonDefinition:
    key: str
    name: str
    command_suffix: str | None
    payload: str | None
    icon: str
    kind: str = "mqtt"


BRIDGE_BUTTONS = (
    CasambiButtonDefinition("api_fetch", "API Fetch", "button/api_fetch/set", "PRESS", "mdi:cloud-download"),
    CasambiButtonDefinition("restart_bridge", "Restart Bridge", "button/restart/set", "PRESS", "mdi:restart"),
    CasambiButtonDefinition("open_web_ui", "Open Jungle Control Center", None, None, "mdi:web", "web_link"),
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/")
    async_add_entities(CasambiBridgeButton(entry, base_topic, definition) for definition in BRIDGE_BUTTONS)
    manager = CasambiSceneButtonManager(hass, entry, base_topic, async_add_entities)
    hass.data[DOMAIN][entry.entry_id].scene_button_manager = manager
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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._definition.kind == "web_link":
            return {"url": self._entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL) or "not configured"}
        return {}

    async def async_press(self) -> None:
        if self._definition.kind == "web_link":
            url = self._entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL) or ""
            if url:
                persistent_notification.async_create(
                    self.hass,
                    f"[Jungle Control Center öffnen]({url})",
                    title="Casambi Jungle Bridge",
                    notification_id=f"{DOMAIN}_web_ui_link_{self._entry.entry_id}",
                )
            else:
                persistent_notification.async_create(
                    self.hass,
                    "Keine Webinterface URL konfiguriert. Bitte Integrationseintrag bearbeiten und Webinterface URL setzen.",
                    title="Casambi Jungle Bridge",
                    notification_id=f"{DOMAIN}_web_ui_link_{self._entry.entry_id}",
                )
            return
        if self._definition.command_suffix and self._definition.payload is not None:
            if direct_available(self._entry):
                if self._definition.key == "api_fetch":
                    await direct_get_json(self.hass, self._entry, "/fetch-api")
                    return
                if self._definition.key == "restart_bridge":
                    await direct_get_json(self.hass, self._entry, "/api/restart")
                    return
            await mqtt.async_publish(
                self.hass,
                f"{self._base_topic}/{self._definition.command_suffix}",
                self._definition.payload,
                qos=0,
                retain=False,
            )


class CasambiSceneButtonManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, base_topic: str, async_add_entities: AddEntitiesCallback) -> None:
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

        self._unsubscribe_scenes = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/scenes", scenes_received, qos=0)
        self._unsubscribe_active = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/diagnostics/active_scene", active_received, qos=0)
        self._unsubscribe_active_id = await mqtt.async_subscribe(self.hass, f"{self.base_topic}/diagnostics/active_scene_id", active_id_received, qos=0)

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

    def __init__(self, entry: ConfigEntry, base_topic: str, scene_id: int, scene_name: str, active_scene: str = "", active_scene_id: int = -1) -> None:
        self._entry = entry
        self._base_topic = base_topic
        self._scene_id = scene_id
        self._scene_name = scene_name
        self._active_scene = active_scene
        self._active_scene_id = active_scene_id
        self._attr_unique_id = f"{entry.entry_id}_scene_{scene_id}"
        self.entity_description = ButtonEntityDescription(key=f"scene_{scene_id}", name=scene_name, icon="mdi:palette")

    @property
    def icon(self) -> str | None:
        return "mdi:check-decagram" if self.is_active else "mdi:palette-outline"

    @property
    def is_active(self) -> bool:
        active_by_id = self._active_scene_id == self._scene_id
        active_by_name = self._active_scene.strip().lower() == self._scene_name.strip().lower()
        return active_by_id or active_by_name

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
        return {
            "scene_id": self._scene_id,
            "scene_name": self._scene_name,
            "active": self.is_active,
            "active_scene": self._active_scene,
            "active_scene_id": self._active_scene_id,
        }

    def set_active_scene(self, active_scene: str, active_scene_id: int = -1) -> None:
        self._active_scene = active_scene
        self._active_scene_id = active_scene_id
        if self.enabled:
            self.async_write_ha_state()

    def update_name(self, scene_name: str) -> None:
        if scene_name == self._scene_name:
            return
        self._scene_name = scene_name
        self.entity_description = ButtonEntityDescription(key=f"scene_{self._scene_id}", name=scene_name, icon="mdi:palette")
        if self.enabled:
            self.async_write_ha_state()

    async def async_press(self) -> None:
        if direct_available(self._entry):
            await direct_get_json(self.hass, self._entry, f"/api/scene/{self._scene_id}")
            return
        await mqtt.async_publish(self.hass, f"{self._base_topic}/scene/{self._scene_id}/set", "PRESS", qos=0, retain=False)
