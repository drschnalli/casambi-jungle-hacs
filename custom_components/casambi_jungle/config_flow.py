from __future__ import annotations
import json
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_UNITS, CONF_SCENES, CONF_TRANSPORT, DEFAULT_BASE_TOPIC, DEFAULT_NAME, DEFAULT_WEB_URL, DEFAULT_TRANSPORT

def _decode_properties(raw) -> dict:
    props = getattr(raw, "properties", raw) if raw is not None else {}
    data = {}
    if isinstance(props, dict):
        for key, value in props.items():
            k = key.decode() if isinstance(key, bytes) else str(key)
            if isinstance(value, bytes):
                try: data[k] = value.decode()
                except Exception: data[k] = str(value)
            else: data[k] = str(value)
    return data
class CasambiJungleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self) -> None:
        self._discovered_name = DEFAULT_NAME; self._discovered_base_topic = DEFAULT_BASE_TOPIC; self._discovered_web_url = DEFAULT_WEB_URL
        self._discovered_host = ""; self._discovered_port = 0; self._discovered_transport = DEFAULT_TRANSPORT
        self._discovered_units: list[dict] = []; self._discovered_scenes: list[dict] = []
    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None: return await self._create_entry_from_data(user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(CONF_NAME, default=DEFAULT_NAME): str, vol.Required(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str, vol.Optional(CONF_WEB_URL, default=DEFAULT_WEB_URL): str}), errors={})
    async def async_step_mqtt(self, discovery_info) -> FlowResult:
        payload = getattr(discovery_info, "payload", None); topic = getattr(discovery_info, "topic", None)
        if isinstance(discovery_info, dict): payload = discovery_info.get("payload", payload); topic = discovery_info.get("topic", topic)
        data = {}
        if payload:
            try: data = json.loads(payload)
            except Exception: data = {}
        base_topic = str(data.get(CONF_BASE_TOPIC) or data.get("baseTopic") or DEFAULT_BASE_TOPIC).strip().strip("/")
        if not base_topic and topic: base_topic = str(topic).split("/", 1)[0]
        self._discovered_name = str(data.get(CONF_NAME) or data.get("name") or DEFAULT_NAME).strip() or DEFAULT_NAME
        self._discovered_base_topic = base_topic
        self._discovered_web_url = str(data.get(CONF_WEB_URL) or data.get("web_ui") or data.get("webUrl") or DEFAULT_WEB_URL).strip()
        self._discovered_transport = "mqtt"; self._discovered_units = data.get(CONF_UNITS) or []; self._discovered_scenes = data.get(CONF_SCENES) or []
        await self.async_set_unique_id(base_topic); self._abort_if_unique_id_configured(); return await self._show_confirm()
    async def async_step_zeroconf(self, discovery_info) -> FlowResult:
        props = _decode_properties(discovery_info)
        host = getattr(discovery_info, "host", "") or getattr(discovery_info, "hostname", "") or ""
        port = int(getattr(discovery_info, "port", 0) or props.get("port", 0) or 0)
        name = props.get("name") or getattr(discovery_info, "name", None) or DEFAULT_NAME
        base_topic = props.get(CONF_BASE_TOPIC) or props.get("baseTopic") or DEFAULT_BASE_TOPIC
        web_url = props.get(CONF_WEB_URL) or props.get("web_url") or ""
        if not web_url and host and port: web_url = f"http://{host}:{port}"
        info_data = {}
        if web_url:
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(f"{web_url.rstrip('/')}/api/info", timeout=5) as resp:
                    if resp.status < 400: info_data = await resp.json(content_type=None)
            except Exception: info_data = {}
        name = info_data.get("name") or name
        base_topic = info_data.get(CONF_BASE_TOPIC) or info_data.get("baseTopic") or base_topic
        self._discovered_name = str(name).replace("._casambi-jungle._tcp.local.", "").strip() or DEFAULT_NAME
        self._discovered_base_topic = str(base_topic).strip().strip("/") or DEFAULT_BASE_TOPIC
        self._discovered_web_url = web_url; self._discovered_host = str(host); self._discovered_port = port; self._discovered_transport = str(info_data.get("mode") or props.get("mode") or "hybrid").strip().lower() or "hybrid"
        if self._discovered_transport not in {"mqtt", "direct", "hybrid"}:
            mqtt_enabled = info_data.get("mqtt_enabled")
            direct_enabled = info_data.get("direct_enabled")
            self._discovered_transport = "direct" if direct_enabled is True and mqtt_enabled is False else "hybrid"
        units = info_data.get(CONF_UNITS) or []; scenes = info_data.get(CONF_SCENES) or []
        self._discovered_units = list(units) if isinstance(units, list) else []
        self._discovered_scenes = list(scenes) if isinstance(scenes, list) else []
        await self.async_set_unique_id(self._discovered_base_topic); self._abort_if_unique_id_configured(); return await self._show_confirm()
    async def _show_confirm(self) -> FlowResult:
        self.context.update({"title_placeholders": {"name": self._discovered_name}})
        return self.async_show_form(step_id="confirm_discovery", description_placeholders={"name": self._discovered_name, "base_topic": self._discovered_base_topic, "web_url": self._discovered_web_url or "not provided"}, data_schema=vol.Schema({}), errors={})
    async def async_step_confirm_discovery(self, user_input: dict | None = None) -> FlowResult:
        return await self._create_entry_from_data({CONF_NAME: self._discovered_name, CONF_BASE_TOPIC: self._discovered_base_topic, CONF_WEB_URL: self._discovered_web_url, CONF_HOST: self._discovered_host, CONF_PORT: self._discovered_port, CONF_TRANSPORT: self._discovered_transport, CONF_UNITS: self._discovered_units, CONF_SCENES: self._discovered_scenes})
    async def _create_entry_from_data(self, user_input: dict) -> FlowResult:
        name = user_input.get(CONF_NAME, DEFAULT_NAME).strip() or DEFAULT_NAME; base_topic = user_input.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/") or DEFAULT_BASE_TOPIC
        web_url = user_input.get(CONF_WEB_URL, DEFAULT_WEB_URL).strip(); host = user_input.get(CONF_HOST, ""); port = int(user_input.get(CONF_PORT, 0) or 0); transport = user_input.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
        await self.async_set_unique_id(base_topic); self._abort_if_unique_id_configured()
        return self.async_create_entry(title=name, data={CONF_NAME: name, CONF_BASE_TOPIC: base_topic, CONF_WEB_URL: web_url, CONF_HOST: host, CONF_PORT: port, CONF_TRANSPORT: transport, CONF_UNITS: list(user_input.get(CONF_UNITS, [])), CONF_SCENES: list(user_input.get(CONF_SCENES, []))})
