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
from .button import normalize_scene_payload
from .light import normalize_units_payload
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    base=entry.data.get(CONF_BASE_TOPIC,DEFAULT_BASE_TOPIC).strip().strip('/')
    sm=CasambiSceneActiveManager(hass,entry,base,async_add_entities); um=CasambiUnitOnlineManager(hass,entry,base,async_add_entities)
    hass.data[DOMAIN][entry.entry_id].scene_active_manager=sm; hass.data[DOMAIN][entry.entry_id].unit_online_manager=um
    await sm.async_start(); await um.async_start()
class CasambiSceneActiveManager:
    def __init__(self,hass,entry,base,add): self.hass=hass;self.entry=entry;self.base=base;self.add=add;self._entities={};self._active='';self._active_id=-1
    async def async_start(self):
        self._add(normalize_scene_payload(self.entry.data.get(CONF_SCENES,[])))
        @callback
        def scenes(msg): self._add(normalize_scene_payload(msg.payload))
        @callback
        def active(msg): self._active=str(msg.payload or ''); self._update()
        @callback
        def active_id(msg):
            try: self._active_id=int(str(msg.payload).strip())
            except Exception: self._active_id=-1
            self._update()
        await mqtt.async_subscribe(self.hass,f'{self.base}/scenes',scenes,qos=0); await mqtt.async_subscribe(self.hass,f'{self.base}/diagnostics/active_scene',active,qos=0); await mqtt.async_subscribe(self.hass,f'{self.base}/diagnostics/active_scene_id',active_id,qos=0)
    def _add(self,scenes):
        new=[]
        for item in scenes:
            sid=int(item.get('id')); name=str(item.get('name') or f'Scene {sid}')
            if sid in self._entities: self._entities[sid].update_name(name); continue
            e=SceneActiveSensor(self.entry,sid,name,self._active,self._active_id); self._entities[sid]=e; new.append(e)
        if new: self.add(new); self._update()
    def _update(self):
        for e in self._entities.values(): e.set_active_scene(self._active,self._active_id)
class CasambiUnitOnlineManager:
    def __init__(self,hass,entry,base,add): self.hass=hass;self.entry=entry;self.base=base;self.add=add;self._entities={}
    async def async_start(self):
        self._add(normalize_units_payload(self.entry.data.get(CONF_UNITS,[])) or [{'id':1,'name':'Casambi Unit 1'}])
        @callback
        def units(msg):
            u=normalize_units_payload(msg.payload)
            if u: self._add(u)
        await mqtt.async_subscribe(self.hass,f'{self.base}/discovery',units,qos=0); await mqtt.async_subscribe(self.hass,f'{self.base}/units',units,qos=0)
    def _add(self,units):
        new=[]
        for item in units:
            uid=int(item.get('id')); name=str(item.get('name') or f'Casambi Unit {uid}')
            if uid in self._entities: self._entities[uid].update_unit_name(name); continue
            e=UnitOnlineSensor(self.entry,self.base,uid,name); self._entities[uid]=e; new.append(e)
        if new: self.add(new)
class SceneActiveSensor(BinarySensorEntity):
    _attr_has_entity_name=True
    def __init__(self,entry,sid,name,active='',active_id=-1): self._entry=entry;self._sid=sid;self._name=name;self._active=active;self._active_id=active_id;self._attr_unique_id=f'{entry.entry_id}_scene_{sid}_active';self._attr_name=f'{name} Active';self._attr_icon='mdi:check-circle-outline'
    @property
    def is_on(self): return self._active_id==self._sid or self._active.strip().lower()==self._name.strip().lower()
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id,'scenes')},name='Casambi Scenes',manufacturer='Casambi Jungle',model='Scene Collection',via_device=(DOMAIN,self._entry.entry_id))
    @property
    def extra_state_attributes(self): return {'scene_id':self._sid,'scene_name':self._name,'active_scene':self._active,'active_scene_id':self._active_id}
    def set_active_scene(self,active,active_id=-1): self._active=active;self._active_id=active_id; self.async_write_ha_state() if self.enabled else None
    def update_name(self,name): self._name=name;self._attr_name=f'{name} Active'; self.async_write_ha_state() if self.enabled else None
class UnitOnlineSensor(BinarySensorEntity):
    _attr_has_entity_name=True
    def __init__(self,entry,base,uid,name): self._entry=entry;self._base=base;self._uid=uid;self._name=name;self._attr_unique_id=f'{entry.entry_id}_unit_{uid}_online';self._attr_name='Online';self._attr_icon='mdi:connection';self._is_on=False;self._unsubscribe=None
    @property
    def is_on(self): return self._is_on
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id,f'unit_{self._uid}')},name=self._name,manufacturer='Casambi',model='Casambi Unit',via_device=(DOMAIN,self._entry.entry_id))
    @property
    def extra_state_attributes(self): return {'unit_id':self._uid,'unit_name':self._name,'mqtt_state_topic':f'{self._base}/light/{self._uid}/state'}
    async def async_added_to_hass(self):
        @callback
        def received(msg):
            try: data=json.loads(msg.payload)
            except Exception: data={}
            if data.get('unit_name'): self.update_unit_name(str(data.get('unit_name')))
            self._is_on=data.get('online') if isinstance(data.get('online'),bool) else str(data.get('state','OFF')).upper() in {'ON','OFF'}
            self.async_write_ha_state()
        self._unsubscribe=await mqtt.async_subscribe(self.hass,f'{self._base}/light/{self._uid}/state',received,qos=0)
    def update_unit_name(self,name): self._name=name; self.async_write_ha_state() if self.enabled else None
    async def async_will_remove_from_hass(self):
        if self._unsubscribe: self._unsubscribe(); self._unsubscribe=None
