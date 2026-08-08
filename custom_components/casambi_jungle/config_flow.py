from __future__ import annotations

import json
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_UNITS, CONF_SCENES, DEFAULT_BASE_TOPIC, DEFAULT_NAME, DEFAULT_WEB_URL


class CasambiJungleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_name = DEFAULT_NAME
        self._discovered_base_topic = DEFAULT_BASE_TOPIC
        self._discovered_web_url = DEFAULT_WEB_URL
        self._discovered_units: list[dict] = []
        self._discovered_scenes: list[dict] = []

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return await self._create_entry_from_data(user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str,
                vol.Optional(CONF_WEB_URL, default=DEFAULT_WEB_URL): str,
            }),
            errors={},
        )

    async def async_step_mqtt(self, discovery_info) -> FlowResult:
        payload = getattr(discovery_info, "payload", None)
        topic = getattr(discovery_info, "topic", None)
        if isinstance(discovery_info, dict):
            payload = discovery_info.get("payload", payload)
            topic = discovery_info.get("topic", topic)
        data: dict = {}
        if payload:
            try:
                data = json.loads(payload)
            except Exception:
                data = {}
        base_topic = str(data.get(CONF_BASE_TOPIC) or data.get("baseTopic") or DEFAULT_BASE_TOPIC).strip().strip("/")
        if not base_topic and topic:
            base_topic = str(topic).split("/", 1)[0]
        name = str(data.get(CONF_NAME) or data.get("name") or DEFAULT_NAME).strip() or DEFAULT_NAME
        web_url = str(data.get(CONF_WEB_URL) or data.get("web_ui") or data.get("webUrl") or DEFAULT_WEB_URL).strip()
        self._discovered_name = name
        self._discovered_base_topic = base_topic
        self._discovered_web_url = web_url
        self._discovered_units = data.get(CONF_UNITS) or []
        self._discovered_scenes = data.get(CONF_SCENES) or []
        await self.async_set_unique_id(base_topic)
        self._abort_if_unique_id_configured()
        self.context.update({"title_placeholders": {"name": name}})
        return self.async_show_form(
            step_id="confirm_discovery",
            description_placeholders={"name": name, "base_topic": base_topic},
            data_schema=vol.Schema({}),
            errors={},
        )

    async def async_step_confirm_discovery(self, user_input: dict | None = None) -> FlowResult:
        return await self._create_entry_from_data({
            CONF_NAME: self._discovered_name,
            CONF_BASE_TOPIC: self._discovered_base_topic,
            CONF_WEB_URL: self._discovered_web_url,
            CONF_UNITS: self._discovered_units,
            CONF_SCENES: self._discovered_scenes,
        })

    async def _create_entry_from_data(self, user_input: dict) -> FlowResult:
        name = user_input.get(CONF_NAME, DEFAULT_NAME).strip() or DEFAULT_NAME
        base_topic = user_input.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip().strip("/") or DEFAULT_BASE_TOPIC
        web_url = user_input.get(CONF_WEB_URL, DEFAULT_WEB_URL).strip()
        units = list(user_input.get(CONF_UNITS, []))
        scenes = list(user_input.get(CONF_SCENES, []))
        await self.async_set_unique_id(base_topic)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=name, data={CONF_NAME: name, CONF_BASE_TOPIC: base_topic, CONF_WEB_URL: web_url, CONF_UNITS: units, CONF_SCENES: scenes})
