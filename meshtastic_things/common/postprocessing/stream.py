"""Envelope glue between the Kafka topics and the engine.

Kept apart from the Flink job so it is testable without a PyFlink runtime.
Derived events are shaped like decoded ones (`payload_kind` "computed:derived",
payload {"derived": {field: value}}), so every consumer of decoded telemetry
reads them without special cases.
"""
from common.channels import DERIVED, DERIVED_KIND, channels_in, split_channel
from common.timestamps import resolve_timestamp

from .plan import ResolvedPlan
from .run import Observation


def device_key(mesh_id, node_id) -> str:
    """The key registry publishes plans under, and the stream is keyed by."""
    return f"{mesh_id}:{node_id}"


def observations_from_event(event: dict) -> list[Observation]:
    """Every numeric channel of a decoded event, at the time it is stored under."""
    if event.get("payload_kind") == DERIVED_KIND:
        # Derived events come back through their own topic, never this one.
        return []
    time, _ = resolve_timestamp(event)
    return [
        Observation(channel, float(time), float(value))
        for channel, value in channels_in(event.get("payload_kind"), event.get("payload") or {})
    ]


def plans_from_config(event: dict) -> list[ResolvedPlan]:
    """The plans a mesh.postprocessing_config.v1 event carries, none for a delete."""
    if event.get("op") == "delete":
        return []
    return [ResolvedPlan.from_dict(plan) for plan in event.get("plans") or []]


def derived_events(
    mesh_id: str, node_id: int, derived: list[Observation], plans: list[ResolvedPlan], backfill: bool = False
) -> list[dict]:
    """One event per postprocessing and timestamp, carrying every field it produced then.

    Backfilled events are marked, so the detectors leave recomputed history alone.
    """
    by_plan = {plan.id: plan for plan in plans}
    grouped: dict[tuple[str, float], dict[str, float]] = {}
    for obs in derived:
        measurement, field = split_channel(obs.channel)
        if measurement != DERIVED:
            continue
        grouped.setdefault((obs.plan_id, obs.time), {})[field] = obs.value

    events = []
    for (plan_id, time), fields in sorted(grouped.items(), key=lambda item: item[0][1]):
        plan = by_plan.get(plan_id)
        events.append(
            {
                "mesh_id": mesh_id,
                "node_id": node_id,
                "rx_time": int(time),
                "payload_kind": DERIVED_KIND,
                "payload": {DERIVED: fields},
                "postprocessing_id": plan_id,
                "blueprint_id": plan.blueprint_id if plan else None,
                "blueprint_version": plan.blueprint_version if plan else None,
                **({"backfill": True} if backfill else {}),
            }
        )
    return events
