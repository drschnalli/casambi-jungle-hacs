# Casambi Jungle Bridge for Home Assistant

HACS Custom Integration **v2.2.0** for the Android Casambi Jungle Bridge.

## New in v2.2.0

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
