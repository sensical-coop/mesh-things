"""The envelope glue postprocessing_job.py runs, and the contract its output keeps."""
import json

import pytest

from common.channels import DERIVED_KIND, channels_in
from common.postprocessing import Calibration, Observation, ResolvedPlan, ResolvedStep, apply
from common.postprocessing.stream import derived_events, device_key, observations_from_event, plans_from_config
from common.timestamps import MIN_FEASIBLE_TIME

MESH_ID = "11111111-2222-3333-4444-555555555555"
NODE_ID = 431637602
RX_TIME = 1790000000


def _decoded(payload, rx_time=RX_TIME):
    return {
        "mesh_id": MESH_ID,
        "node_id": NODE_ID,
        "packet_id": 1,
        "rx_time": rx_time,
        "payload_kind": "telemetry:environment_metrics",
        "payload": payload,
    }


def _offset_plan(plan_id="pp-1") -> ResolvedPlan:
    return ResolvedPlan(
        id=plan_id,
        blueprint_id="bp-1",
        blueprint_version=2,
        tolerance_seconds=30.0,
        steps=(
            ResolvedStep(
                key="cal",
                function_name="offset_scale",
                inputs={"value": "environment_metrics.temperature"},
                outputs={"calibrated": "derived.temperature_calibrated"},
                calibrations=(Calibration(0.0, {"offset": -0.5}),),
            ),
        ),
    )


def _config_event(plans, op="upsert"):
    return {
        "kind": "postprocessing_plans",
        "key": device_key(MESH_ID, NODE_ID),
        "plans": [plan.to_dict() for plan in plans],
        "op": op,
    }


class TestObservations:
    def test_every_numeric_channel_becomes_an_observation(self):
        observations = observations_from_event(
            _decoded({"environment_metrics": {"temperature": 21.5, "relative_humidity": 40}})
        )

        assert {(o.channel, o.value) for o in observations} == {
            ("environment_metrics.temperature", 21.5),
            ("environment_metrics.relative_humidity", 40.0),
        }
        assert all(o.time == RX_TIME for o in observations)

    def test_payload_time_wins_like_it_does_in_storage(self):
        # A device delivering stored history: derived points must land on the
        # same timestamp as the raw point they came from.
        taken = MIN_FEASIBLE_TIME + 1000
        observations = observations_from_event(
            _decoded({"time": taken, "environment_metrics": {"temperature": 20.0}})
        )

        assert [o.time for o in observations] == [taken]

    def test_derived_events_are_never_fed_back(self):
        event = {**_decoded({}), "payload_kind": DERIVED_KIND, "payload": {"derived": {"x": 1.0}}}

        assert observations_from_event(event) == []


class TestConfig:
    def test_plans_round_trip_through_the_config_event(self):
        plan = _offset_plan()

        assert plans_from_config(json.loads(json.dumps(_config_event([plan])))) == [plan]

    def test_delete_carries_no_plans(self):
        assert plans_from_config(_config_event([], op="delete")) == []


class TestDerivedEvents:
    def _run(self, payload, plans=None):
        plans = plans or [_offset_plan()]
        result = apply(plans, {}, observations_from_event(_decoded(payload)))
        return derived_events(MESH_ID, NODE_ID, result.derived, plans)

    def test_end_to_end_from_decoded_event_to_derived_event(self):
        [event] = self._run({"environment_metrics": {"temperature": 21.5}})

        assert event == {
            "mesh_id": MESH_ID,
            "node_id": NODE_ID,
            "rx_time": RX_TIME,
            "payload_kind": DERIVED_KIND,
            "payload": {"derived": {"temperature_calibrated": pytest.approx(21.0)}},
            "postprocessing_id": "pp-1",
            "blueprint_id": "bp-1",
            "blueprint_version": 2,
        }

    def test_one_event_per_plan_and_timestamp(self):
        observations = [
            Observation("derived.a", 10.0, 1.0, "pp-1"),
            Observation("derived.b", 10.0, 2.0, "pp-1"),
            Observation("derived.a", 20.0, 3.0, "pp-1"),
            Observation("derived.c", 10.0, 4.0, "pp-2"),
        ]

        events = derived_events(MESH_ID, NODE_ID, observations, [_offset_plan("pp-1"), _offset_plan("pp-2")])

        assert [(e["postprocessing_id"], e["rx_time"], e["payload"]["derived"]) for e in events] == [
            ("pp-1", 10, {"a": 1.0, "b": 2.0}),
            ("pp-2", 10, {"c": 4.0}),
            ("pp-1", 20, {"a": 3.0}),
        ]

    def test_pattern_detection_sees_derived_channels_by_their_catalog_name(self):
        # ExplodeFields runs channels_in over every event it reads, so a range
        # set on derived.<field> in registry matches what the detector sees.
        [event] = self._run({"environment_metrics": {"temperature": 21.5}})

        channels = [channel for channel, _ in channels_in(event["payload_kind"], event["payload"])]

        assert channels == ["derived.temperature_calibrated"]
