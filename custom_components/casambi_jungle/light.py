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
from .direct_api import direct_available, direct_get_json
def normalize_units_payload(payload:Any)->list[dict[str,Any]]:
    if payload is None: return []
    if isinstance(payload,str):
        try: payload=json.loads(payload)
        except Exception: return []
    units=payload.get('units',[]) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
    out=[]
    for item in units if isinstance(units,list) else []:
        if not isinstance(item,dict): continue
        unit_id=item.get('id') or item.get('unit_id') or item.get('deviceID') or item.get('address')
        try: unit_id=int(unit_id)
        except Exception: continue
        out.append({'id':unit_id,'name':str(item.get('name') or item.get('unit_name') or item.get('label') or f'Casambi Unit {unit_id}')})
    return out
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    base=entry.data.get(CONF_BASE_TOPIC,DEFAULT_BASE_TOPIC).strip().strip('/')
    manager=CasambiUnitLightManager(hass,entry,base,async_add_entities); hass.data[DOMAIN][entry.entry_id].light_manager=manager; await manager.async_start()
class CasambiUnitLightManager:
    def __init__(self,hass,entry,base,add): self.hass=hass;self.entry=entry;self.base=base;self.add=add;self._lights={};self._u1=None;self._u2=None
    async def async_start(self):
        initial=normalize_units_payload(self.entry.data.get(CONF_UNITS,[])) or [{'id':1,'name':'Casambi Unit 1'}]; self._add_units(initial)
        @callback
        def received(msg):
            units=normalize_units_payload(msg.payload)
            if units: self._add_units(units)
        self._u1=await mqtt.async_subscribe(self.hass,f'{self.base}/discovery',received,qos=0); self._u2=await mqtt.async_subscribe(self.hass,f'{self.base}/units',received,qos=0)
    def _add_units(self,units):
        new=[]
        for item in units:
            unit_id=int(item.get('id')); name=str(item.get('name') or f'Casambi Unit {unit_id}')
            if unit_id in self._lights: self._lights[unit_id].update_unit_name(name); continue
            e=CasambiUnitLight(self.entry,self.base,unit_id,name); self._lights[unit_id]=e; new.append(e)
        if new: self.add(new)
class CasambiUnitLight(LightEntity):
    _attr_supported_color_modes={ColorMode.BRIGHTNESS}; _attr_color_mode=ColorMode.BRIGHTNESS
    def __init__(self,entry,base,unit_id,unit_name):
        self._entry=entry;self._base=base;self._unit_id=unit_id;self._unit_name=unit_name;self._attr_unique_id=f'{entry.entry_id}_unit_{unit_id}_light';self._attr_name=unit_name;self._is_on=False;self._brightness=0;self._online=None;self._raw=None;self._unsubscribe=None;self._unsub_poll=None
    @property
    def name(self): return self._unit_name
    @property
    def is_on(self): return self._is_on
    @property
    def brightness(self): return self._brightness
    @property
    def extra_state_attributes(self): return {'unit_id':self._unit_id,'unit_name':self._unit_name,'online':self._online,'raw_state':self._raw,'mqtt_state_topic':f'{self._base}/light/{self._unit_id}/state','mqtt_command_topic':f'{self._base}/light/{self._unit_id}/set'}
    @property
    def device_identifiers(self): return (DOMAIN,self._entry.entry_id,f'unit_{self._unit_id}')
    @property
    def device_info(self): return DeviceInfo(identifiers={self.device_identifiers},name=self._unit_name,manufacturer='Casambi',model='Casambi Unit',via_device=(DOMAIN,self._entry.entry_id))
    async def async_added_to_hass(self):
        @callback
        def received(msg):
            try: data=json.loads(msg.payload)
            except Exception: data={}
            self._apply_state(data); self.async_write_ha_state()
        self._unsubscribe=await mqtt.async_subscribe(self.hass,f'{self._base}/light/{self._unit_id}/state',received,qos=0)
        if direct_available(self._entry):
            from datetime import timedelta
            from homeassistant.helpers.event import async_track_time_interval
            self._unsub_poll=async_track_time_interval(self.hass,self._poll_direct_status,timedelta(seconds=2)); await self._poll_direct_status(None)
    def _apply_state(self,data):
        if data.get('unit_name') or data.get('unitName'): self.update_unit_name(str(data.get('unit_name') or data.get('unitName')))
        try: self._brightness=max(0,min(255,int(data.get('brightness',0) or 0)))
        except Exception: self._brightness=0
        state=str(data.get('state','OFF')).upper(); self._is_on=state=='ON' and self._brightness>0; self._online=data.get('online'); self._raw=data.get('raw_state') or data.get('raw')
    async def _poll_direct_status(self,now):
        if not direct_available(self._entry): return
        data=await direct_get_json(self.hass,self._entry,'/api/status')
        if isinstance(data,dict) and data.get('ok') is not False: self._apply_state(data); self.async_write_ha_state()
    def update_unit_name(self,name):
        if not name or name==self._unit_name: return
        self._unit_name=name; self._attr_name=name
        if self.hass:
            reg=dr.async_get(self.hass); dev=reg.async_get_device({self.device_identifiers})
            if dev: reg.async_update_device(dev.id,name=name)
            if self.enabled: self.async_write_ha_state()
    async def async_turn_on(self,**kwargs):
        brightness=kwargs.get(ATTR_BRIGHTNESS); payload={'state':'ON'}
        if brightness is not None: payload['brightness']=int(brightness)
        elif self._brightness>0: payload['brightness']=self._brightness
        if direct_available(self._entry):
            params={'state':'ON'}
            if 'brightness' in payload: params['brightness']=payload['brightness']
            await direct_get_json(self.hass,self._entry,f'/api/light/{self._unit_id}',params); await self._poll_direct_status(None); return
        await mqtt.async_publish(self.hass,f'{self._base}/light/{self._unit_id}/set',json.dumps(payload),qos=0,retain=False)
    async def async_turn_off(self,**kwargs):
        if direct_available(self._entry): await direct_get_json(self.hass,self._entry,f'/api/light/{self._unit_id}',{'state':'OFF'}); await self._poll_direct_status(None); return
        await mqtt.async_publish(self.hass,f'{self._base}/light/{self._unit_id}/set',json.dumps({'state':'OFF'}),qos=0,retain=False)
    async def async_will_remove_from_hass(self):
        if self._unsubscribe: self._unsubscribe(); self._unsubscribe=None
        if self._unsub_poll: self._unsub_poll(); self._unsub_poll=None
