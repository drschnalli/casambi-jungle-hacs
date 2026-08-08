# Casambi Jungle Bridge

Home Assistant companion integration for the Android Casambi Jungle Bridge.

This package includes local brand assets in `brand/` and `custom_components/casambi_jungle/brand/`.


Adds Zeroconf/mDNS discovery foundation for Android Bridge v0.7.0.


## New in v2.1.0

- Adds Direct REST control for lights and scenes when the entry was discovered via Zeroconf/hybrid mode.
- MQTT Mode, Direct Mode and Network Discovery switches are available.
- Direct API is used for light/scene/API Fetch/Restart when `web_url` is available.
- MQTT remains supported and is still used for normal MQTT entries.
