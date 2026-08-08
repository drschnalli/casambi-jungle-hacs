Repository: https://github.com/drschnalli/casambi-jungle-hacs
Issues: https://github.com/drschnalli/casambi-jungle-hacs/issues

# Casambi Jungle Bridge for Home Assistant

HACS Custom Integration **v1.2.3** for the Android Casambi Jungle Bridge.

## New in v1.2.3

- Fixes dynamic scene detection from Android v0.6.0 MQTT payload format.
- Supports both scene payload formats:
  - `[ {"id": 1, "name": "An"} ]`
  - `{ "scenes": [ {"id": 1, "name": "An"} ] }`
- Dynamically creates scene buttons after updates on `casambi_bridge/scenes`.
- Adds a dedicated Home Assistant device: **Casambi Scenes**.
- Scene buttons expose attributes:
  - `scene_id`
  - `scene_name`
  - `active`
- Active Scene is tracked by:
  - `casambi_bridge/diagnostics/active_scene`
  - `casambi_bridge/diagnostics/active_scene_id`
- Uses an exact 256x256 PNG as `custom_components/casambi_jungle/icon.png`.

## Required Android Bridge

Use Android Bridge v0.6.0 or newer.

Android should publish retained:

```text
casambi_bridge/scenes
```

Payload:

```json
{
  "scenes": [
    {"id": 1, "name": "An"},
    {"id": 2, "name": "Aus"},
    {"id": 3, "name": "Testszene"}
  ]
}
```

Scene buttons publish commands to:

```text
casambi_bridge/scene/<id>/set
```

Payload:

```text
PRESS
```
