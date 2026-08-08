from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from homeassistant.components import mqtt
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC
@dataclass(frozen=True)
class CasambiSwitchDefinition:
    key: str; name: str; setting: str; icon: str
SWITCHES=(CasambiSwitchDefinition("web_interface","Web Interface","webinterface","mdi:web"),CasambiSwitchDefinition("smb_logging","SMB Logging","smb_logging","mdi:nas"),CasambiSwitchDefinition("tcp_logstream","TCP Logstream","tcp_logstream","mdi:console-network"),CasambiSwitchDefinition("auto_api_fetch","Auto API Fetch","auto_api_fetch","mdi:cloud-sync"),CasambiSwitchDefinition("websocket_live","WebSocket Live Updates","websocket_live","mdi:websocket"))
async def async_setup_entry(hass:HomeAssistant,entry:ConfigEntry,async_add_entities:AddEntitiesCallback)->None:
    base_topic=entry.data.get(CONF_BASE_TOPIC,DEFAULT_BASE_TOPIC).strip().strip("/"); async_add_entities(CasambiBridgeSwitch(entry,base_topic,d) for d in SWITCHES)
class CasambiBridgeSwitch(SwitchEntity):
    _attr_has_entity_name=True
    def __init__(self,entry:ConfigEntry,base_topic:str,definition:CasambiSwitchDefinition)->None:
        self._entry=entry; self._base_topic=base_topic; self._definition=definition; self._attr_unique_id=f"{entry.entry_id}_{definition.key}"; self.entity_description=SwitchEntityDescription(key=definition.key,name=definition.name,icon=definition.icon); self._attr_is_on=False; self._unsubscribe:Callable[[],None]|None=None
    @property
    def device_info(self)->DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id)},name=self._entry.title,manufacturer="Casambi Jungle",model="Android BLE Bridge")
    @property
    def command_topic(self)->str: return f"{self._base_topic}/settings/{self._definition.setting}/set"
    @property
    def state_topic(self)->str: return f"{self._base_topic}/settings/{self._definition.setting}/state"
    async def async_added_to_hass(self)->None:
        @callback
        def message_received(msg)->None:
            self._attr_is_on=str(msg.payload).strip().upper()=="ON"; self.async_write_ha_state()
        self._unsubscribe=await mqtt.async_subscribe(self.hass,self.state_topic,message_received,qos=0)
    async def async_turn_on(self,**kwargs)->None: await mqtt.async_publish(self.hass,self.command_topic,"ON",qos=0,retain=False)
    async def async_turn_off(self,**kwargs)->None: await mqtt.async_publish(self.hass,self.command_topic,"OFF",qos=0,retain=False)
    async def async_will_remove_from_hass(self)->None:
        if self._unsubscribe is not None: self._unsubscribe(); self._unsubscribe=None
