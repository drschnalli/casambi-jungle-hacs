## Casambi Jungle Bridge v2.2.1

Adds companion frontend card metadata.

Frontend Card Repository: https://github.com/drschnalli/casambi-jungle-card


### Fix in v2.2.1

- Direct REST status is now the primary source for Bridge Status, BLE Status, Active Scene, Availability, Bridge Version, Last Sync and Transport Mode when a Web URL is configured.
- MQTT retained status values can no longer leave Direct-only setups showing stale `stopped` or `disconnected` values.
- Zeroconf discovery now stores `direct`, `hybrid` or `mqtt` from `/api/info` instead of always storing `hybrid`.
