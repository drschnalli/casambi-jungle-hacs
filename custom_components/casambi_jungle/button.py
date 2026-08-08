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
from .const import DOMAIN, CONF_BASE_TOPIC, CONF_WEB_URL, CONF_SCENES, DEFAULT_BASE_TOPIC, DEFAULT_WEB_URL, FRONTEND_CARD_REPO
from .direct_api import direct_available, direct_get_json
@dataclass(frozen=True)
class Def: key:str; name:str; topic:str|None; payload:str|None; icon:str; kind:str='mqtt'
BRIDGE=(Def('api_fetch','API Fetch','button/api_fetch/set','PRESS','mdi:cloud-download'),Def('restart_bridge','Restart Bridge','button/restart/set','PRESS','mdi:restart'),Def('open_web_ui','Open Jungle Control Center',None,None,'mdi:web','web'),Def('open_card_repo','Open Jungle Card Repository',None,None,'mdi:cards','card_repo'))
def normalize_scene_payload(payload:Any)->list[dict[str,Any]]:
    if payload is None: return []
    if isinstance(payload,str):
        try: payload=json.loads(payload)
        except Exception: return []
    scenes=payload.get('scenes',[]) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
    out=[]
    for item in scenes if isinstance(scenes,list) else []:
        if not isinstance(item,dict): continue
        scene_id=item.get('id') or item.get('sceneID') or item.get('scene_id')
        try: scene_id=int(scene_id)
        except Exception: continue
        out.append({'id':scene_id,'name':str(item.get('name') or item.get('sceneName') or item.get('scene_name') or f'Scene {scene_id}')})
    return out
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    base=entry.data.get(CONF_BASE_TOPIC,DEFAULT_BASE_TOPIC).strip().strip('/')
    async_add_entities(CasambiBridgeButton(entry,base,d) for d in BRIDGE)
    mgr=CasambiSceneButtonManager(hass,entry,base,async_add_entities); hass.data[DOMAIN][entry.entry_id].scene_button_manager=mgr; await mgr.async_start()
class CasambiBridgeButton(ButtonEntity):
    _attr_has_entity_name=True
    def __init__(self,entry,base,d): self._entry=entry;self._base=base;self._d=d;self._attr_unique_id=f'{entry.entry_id}_{d.key}';self.entity_description=ButtonEntityDescription(key=d.key,name=d.name,icon=d.icon)
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id)},name=self._entry.title,manufacturer='Casambi Jungle',model='Android BLE Bridge')
    @property
    def extra_state_attributes(self):
        if self._d.kind=='web': return {'url':self._entry.data.get(CONF_WEB_URL,DEFAULT_WEB_URL) or 'not configured'}
        if self._d.kind=='card_repo': return {'url':FRONTEND_CARD_REPO}
        return {}
    async def async_press(self):
        if self._d.kind=='web':
            url=self._entry.data.get(CONF_WEB_URL,DEFAULT_WEB_URL) or ''
            persistent_notification.async_create(self.hass,f'[Jungle Control Center öffnen]({url})' if url else 'Keine Webinterface URL konfiguriert.',title='Casambi Jungle Bridge',notification_id=f'{DOMAIN}_web_ui_{self._entry.entry_id}'); return
        if self._d.kind=='card_repo':
            persistent_notification.async_create(self.hass,f'[Casambi Jungle Card Repository öffnen]({FRONTEND_CARD_REPO})',title='Casambi Jungle Card',notification_id=f'{DOMAIN}_card_repo_{self._entry.entry_id}'); return
        if self._d.topic and self._d.payload:
            if direct_available(self._entry):
                if self._d.key=='api_fetch': await direct_get_json(self.hass,self._entry,'/fetch-api'); return
                if self._d.key=='restart_bridge': await direct_get_json(self.hass,self._entry,'/api/restart'); return
            await mqtt.async_publish(self.hass,f'{self._base}/{self._d.topic}',self._d.payload,qos=0,retain=False)
class CasambiSceneButtonManager:
    def __init__(self,hass,entry,base,add): self.hass=hass;self.entry=entry;self.base=base;self.add=add;self._buttons={};self._active='';self._active_id=-1;self._u=[]
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
        self._u.append(await mqtt.async_subscribe(self.hass,f'{self.base}/scenes',scenes,qos=0)); self._u.append(await mqtt.async_subscribe(self.hass,f'{self.base}/diagnostics/active_scene',active,qos=0)); self._u.append(await mqtt.async_subscribe(self.hass,f'{self.base}/diagnostics/active_scene_id',active_id,qos=0))
    def _add(self,scenes):
        new=[]
        for item in scenes:
            sid=int(item.get('id')); name=str(item.get('name') or f'Scene {sid}')
            if sid in self._buttons: self._buttons[sid].update_name(name); continue
            b=CasambiSceneButton(self.entry,self.base,sid,name,self._active,self._active_id); self._buttons[sid]=b; new.append(b)
        if new: self.add(new); self._update()
    def _update(self):
        for b in self._buttons.values(): b.set_active_scene(self._active,self._active_id)
class CasambiSceneButton(ButtonEntity):
    _attr_has_entity_name=True
    def __init__(self,entry,base,sid,name,active='',active_id=-1): self._entry=entry;self._base=base;self._sid=sid;self._name=name;self._active=active;self._active_id=active_id;self._attr_unique_id=f'{entry.entry_id}_scene_{sid}';self.entity_description=ButtonEntityDescription(key=f'scene_{sid}',name=name,icon='mdi:palette')
    @property
    def icon(self): return 'mdi:check-decagram' if self.is_active else 'mdi:palette-outline'
    @property
    def is_active(self): return self._active_id==self._sid or self._active.strip().lower()==self._name.strip().lower()
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id,'scenes')},name='Casambi Scenes',manufacturer='Casambi Jungle',model='Scene Collection',via_device=(DOMAIN,self._entry.entry_id))
    @property
    def extra_state_attributes(self): return {'scene_id':self._sid,'scene_name':self._name,'active':self.is_active,'active_scene':self._active,'active_scene_id':self._active_id}
    def set_active_scene(self,active,active_id=-1): self._active=active;self._active_id=active_id; self.async_write_ha_state() if self.enabled else None
    def update_name(self,name): self._name=name; self.entity_description=ButtonEntityDescription(key=f'scene_{self._sid}',name=name,icon='mdi:palette'); self.async_write_ha_state() if self.enabled else None
    async def async_press(self):
        if direct_available(self._entry): await direct_get_json(self.hass,self._entry,f'/api/scene/{self._sid}'); return
        await mqtt.async_publish(self.hass,f'{self._base}/scene/{self._sid}/set','PRESS',qos=0,retain=False)
