Repository: https://github.com/drschnalli/casambi-jungle-hacs
Issues: https://github.com/drschnalli/casambi-jungle-hacs/issues

# Casambi Jungle Bridge for Home Assistant

HACS Custom Integration **v2.1.0** for the Android Casambi Jungle Bridge.

## New in v2.1.0

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


## Branding in v2.1.0

This release adds Home Assistant / HACS brand assets in both locations used by current and newer Home Assistant installations:

```text
brand/
  icon.png
  dark_icon.png
  icon@2x.png
  dark_icon@2x.png
  logo.png
  dark_logo.png
  logo@2x.png
  dark_logo@2x.png

custom_components/casambi_jungle/brand/
  icon.png
  dark_icon.png
  icon@2x.png
  dark_icon@2x.png
  logo.png
  dark_logo.png
  logo@2x.png
  dark_logo@2x.png
```

The direct legacy files remain available as well:

```text
icon.png
logo.png
custom_components/casambi_jungle/icon.png
custom_components/casambi_jungle/logo.png
```

If Home Assistant still shows `icon not available`, clear the HACS cache/reload the repository and restart Home Assistant after installing this version.
