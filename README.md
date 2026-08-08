# Casambi Jungle Bridge for Home Assistant

HACS Custom Integration **v2.2.1** for the Android Casambi Jungle Bridge.

## New in v2.2.1

- Adds a Frontend Card repository link entity and button.
- Keeps Direct REST control, MQTT mode, Hybrid mode, mDNS discovery and branding.
- Recommended companion frontend card: https://github.com/drschnalli/casambi-jungle-card

## Companion Lovelace Card

Install the separate Dashboard/Frontend repository in HACS:

```text
https://github.com/drschnalli/casambi-jungle-card
```

Use card type:

```yaml
type: custom:casambi-jungle-card
light: light.your_casambi_light
active_scene: sensor.casambi_jungle_bridge_active_scene
scenes:
  - button.an
  - button.aus
```


### Fix in v2.2.1

- Direct REST status is now the primary source for Bridge Status, BLE Status, Active Scene, Availability, Bridge Version, Last Sync and Transport Mode when a Web URL is configured.
- MQTT retained status values can no longer leave Direct-only setups showing stale `stopped` or `disconnected` values.
- Zeroconf discovery now stores `direct`, `hybrid` or `mqtt` from `/api/info` instead of always storing `hybrid`.
