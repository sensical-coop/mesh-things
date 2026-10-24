# mesh-things

Shared vocabulary and Meshtastic protocol helpers for the meshtastic-things API: channel
and payload-kind naming, node ids, units, query validation, detector names, and the
telemetry catalog derived from the Meshtastic protobufs.

```bash
pip install mesh-things              # vocabulary only, no dependencies
pip install mesh-things[protobuf]    # catalog and portnum names, from the Meshtastic protobufs
pip install mesh-things[codec]       # MQTT envelope parsing and channel decryption
```
