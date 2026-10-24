# Repository tools

The API examples moved into the package, at
[../mesh_things/examples/](../mesh_things/examples/README.md). What is left here talks
to something other than the API:

- `source_publish_fake.py` publishes fake, encrypted environment readings to a source's
  broker, as a Meshtastic gateway would. It uses `mesh_things.codec` for the encryption.
- `sink_consume.py` and `sink_count.py` subscribe to an MQTT sink, to print or to count
  what it delivers.
- `monitor_status.py` reads the server monitor's own status API.
- `*.http` files are request collections for an HTTP client such as VS Code's REST Client.

```bash
pip install -r requirements.txt
```

## Server monitor

The monitor has its own small API, separate from the registry and readings (see
[../../docs/monitoring.md](../../docs/monitoring.md)). `MONITOR_URL` defaults to
`http://localhost:8095`.

```bash
# The latest result of every check
python3 monitor_status.py

# Run every check now, or one; needs MONITOR__RUN_TOKEN
export MONITOR_RUN_TOKEN=...
python3 monitor_status.py --run
python3 monitor_status.py --run ingestion --timeout 60
```
