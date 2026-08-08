from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_TRANSPORT, DEFAULT_BASE_TOPIC, DEFAULT_WEB_URL, DEFAULT_TRANSPORT, FRONTEND_CARD_REPO
@dataclass(frozen=True)
class D:
    key:str; name:str; topic:str|None; icon:str; static:str|None=None
SENSORS=(D('availability','Availability','availability','mdi:server-network'),D('bridge_status','Bridge Status','status/bridge','mdi:bridge'),D('ble_status','BLE Status','status/ble','mdi:bluetooth'),D('bridge_version','Bridge Version','diagnostics/bridge_version','mdi:cellphone-cog'),D('last_sync','Last API Sync','diagnostics/last_sync','mdi:cloud-sync'),D('active_scene','Active Scene','diagnostics/active_scene','mdi:palette'),D('web_interface_url','Web Interface URL',None,'mdi:web',CONF_WEB_URL),D('transport_mode','Transport Mode',None,'mdi:transit-connection-variant',CONF_TRANSPORT),D('direct_api_url','Direct API URL',None,'mdi:api','direct_api_url'),D('frontend_card_repository','Frontend Card Repository',None,'mdi:cards','card_repo'))
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    base=entry.data.get(CONF_BASE_TOPIC,DEFAULT_BASE_TOPIC).strip().strip('/')
    async_add_entities(CasambiBridgeSensor(entry,base,d) for d in SENSORS)
class CasambiBridgeSensor(SensorEntity):
    _attr_has_entity_name=True
    def __init__(self,entry,base,d):
        self._entry=entry;self._base=base;self._d=d;self._attr_unique_id=f'{entry.entry_id}_{d.key}';self.entity_description=SensorEntityDescription(key=d.key,name=d.name,icon=d.icon);self._attr_native_value=None;self._unsubscribe=None
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id)},name=self._entry.title,manufacturer='Casambi Jungle',model='Android BLE Bridge')
    async def async_added_to_hass(self):
        if self._d.static is not None:
            if self._d.static==CONF_WEB_URL: self._attr_native_value=self._entry.data.get(CONF_WEB_URL,DEFAULT_WEB_URL) or 'not configured'
            elif self._d.static==CONF_TRANSPORT: self._attr_native_value=self._entry.data.get(CONF_TRANSPORT,DEFAULT_TRANSPORT)
            elif self._d.static=='direct_api_url':
                url=self._entry.data.get(CONF_WEB_URL,DEFAULT_WEB_URL) or ''; self._attr_native_value=f'{url}/api/info' if url else 'not configured'
            elif self._d.static=='card_repo': self._attr_native_value=FRONTEND_CARD_REPO
            self.async_write_ha_state();return
        @callback
        def received(msg): self._attr_native_value=msg.payload; self.async_write_ha_state()
        self._unsubscribe=await mqtt.async_subscribe(self.hass,f'{self._base}/{self._d.topic}',received,qos=0)
    async def async_will_remove_from_hass(self):
        if self._unsubscribe: self._unsubscribe(); self._unsubscribe=None
