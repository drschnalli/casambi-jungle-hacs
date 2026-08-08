from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_UNITS, CONF_SCENES, CONF_HOST, CONF_PORT, CONF_TRANSPORT, DEFAULT_BASE_TOPIC, DEFAULT_WEB_URL, DEFAULT_TRANSPORT
@dataclass
class CasambiJungleBridgeData:
    name: str
    base_topic: str
    web_url: str
    host: str = ""
    port: int = 0
    transport: str = DEFAULT_TRANSPORT
    units: list[dict[str, Any]] = field(default_factory=list)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    light_manager: Any | None = None
    scene_button_manager: Any | None = None
    scene_active_manager: Any | None = None
    unit_online_manager: Any | None = None
    direct_status_poller: Any | None = None
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = CasambiJungleBridgeData(
        name=entry.title,
        base_topic=entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/"),
        web_url=entry.data.get(CONF_WEB_URL, DEFAULT_WEB_URL).strip(),
        host=entry.data.get(CONF_HOST, ""),
        port=int(entry.data.get(CONF_PORT, 0) or 0),
        transport=entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT),
        units=list(entry.data.get(CONF_UNITS, [])),
        scenes=list(entry.data.get(CONF_SCENES, [])),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if data and getattr(data, "direct_status_poller", None):
        await data.direct_status_poller.async_stop()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
