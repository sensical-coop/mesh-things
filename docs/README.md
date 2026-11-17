# Documentation

Meshtastic Things is a fleet and telemetry platform for [Meshtastic](https://meshtastic.org/) meshes. Packets arrive over MQTT, are decoded into structured events, stored as time series, and exposed through a HTTP API.

| Document | Contents |
| --- | --- |
| [product.md](product.md) | What the product is for, who uses it, and how data flows |
| [architecture.md](architecture.md) | Services this repository declares, profiles, and Kafka topics |
| [data-model.md](data-model.md) | Relational model, time-series layout, and object archive |
| [data-model.dbml](data-model.dbml) | Same Postgres schema in [DBML](https://dbml.dbdiagram.io/docs) |
| [features.md](features.md) | Product features and the services that implement them |

The live HTTP contract is served by the registry role at `/schema` (OpenAPI) and `/docs` (Swagger UI).
