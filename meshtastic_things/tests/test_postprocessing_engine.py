import json

import pytest

from common.postprocessing import Calibration, Observation, ResolvedPlan, ResolvedStep, apply
from common.postprocessing.joiner import StepJoin, new_state

WORKING = "ads1115.channel_0"
AUXILIARY = "ads1115.channel_1"
TEMPERATURE = "environment_metrics.temperature"
HUMIDITY = "environment_metrics.relative_humidity"


def _no2_plan(calibrations=(Calibration(0.0, {"sensitivity": 2.0}),), tolerance=30.0) -> ResolvedPlan:
    """The motivating chain: two electrodes and a temperature to ppb, then to ug/m3."""
    return ResolvedPlan(
        id="pp-1",
        blueprint_id="bp-1",
        blueprint_version=1,
        tolerance_seconds=tolerance,
        steps=(
            ResolvedStep(
                key="ppb",
                function_name="ec_sensor_ppb",
                inputs={"working": WORKING, "auxiliary": AUXILIARY, "temperature": TEMPERATURE},
                outputs={"concentration_ppb": "derived.no2_ppb"},
                calibrations=tuple(calibrations),
            ),
            ResolvedStep(
                key="ugm3",
                function_name="ppb_to_ugm3",
                inputs={"concentration_ppb": "derived.no2_ppb", "temperature": TEMPERATURE},
                outputs={"concentration_ugm3": "derived.no2_ugm3"},
                params={"molecular_weight": 46.01},
            ),
        ),
    )


def _obs(channel, time, value):
    return Observation(channel, float(time), float(value))


def _by_channel(result):
    out = {}
    for obs in result.derived:
        out.setdefault(obs.channel, []).append((obs.time, obs.value))
    return out


class TestStepJoin:
    def _join(self, state=None, tolerance=10.0):
        return StepJoin(WORKING, (AUXILIARY, TEMPERATURE), tolerance, state or new_state())

    def test_row_waits_for_every_input(self):
        join = self._join()
        assert join.add(WORKING, 100, 300) == []
        assert join.add(AUXILIARY, 101, 100) == []
        rows = join.add(TEMPERATURE, 99, 20)
        assert rows == [{"time": 100, WORKING: 300, AUXILIARY: 100, TEMPERATURE: 20}]

    def test_row_is_timestamped_with_the_base_sample(self):
        join = self._join()
        join.add(AUXILIARY, 95, 1)
        join.add(TEMPERATURE, 105, 2)
        assert join.add(WORKING, 100, 3)[0]["time"] == 100

    def test_partner_outside_the_tolerance_is_not_used(self):
        join = self._join(tolerance=10.0)
        join.add(AUXILIARY, 50, 1)
        join.add(TEMPERATURE, 100, 2)
        assert join.add(WORKING, 100, 3) == []

    def test_nearest_partner_wins(self):
        join = self._join()
        join.add(AUXILIARY, 92, 1)
        join.add(AUXILIARY, 99, 2)
        join.add(AUXILIARY, 108, 3)
        join.add(TEMPERATURE, 100, 20)
        assert join.add(WORKING, 100, 0)[0][AUXILIARY] == 2

    def test_out_of_order_history_still_joins(self):
        # A device delivering a batch of history sends each channel in turn.
        join = self._join()
        rows = []
        for t in (0, 60, 120):
            rows += join.add(WORKING, t, t)
        for t in (0, 60, 120):
            rows += join.add(AUXILIARY, t + 1, 0)
        for t in (0, 60, 120):
            rows += join.add(TEMPERATURE, t - 1, 20)
        assert [r["time"] for r in rows] == [0, 60, 120]

    def test_channels_skewed_by_hours_still_join(self):
        join = self._join()
        rows = []
        for t in range(0, 36000, 600):
            rows += join.add(WORKING, t, 1)
        for t in range(0, 36000, 600):
            rows += join.add(AUXILIARY, t, 1)
            rows += join.add(TEMPERATURE, t, 20)
        assert len(rows) == 60

    def test_base_sample_is_dropped_once_a_partner_moves_past_it(self):
        join = self._join(tolerance=10.0)
        join.add(WORKING, 0, 1)
        join.add(WORKING, 100, 1)
        join.add(AUXILIARY, 50, 1)
        assert [p[0] for p in join.state["pending"]] == [100]

    def test_partner_samples_no_base_can_use_are_dropped(self):
        join = self._join(tolerance=10.0)
        join.add(AUXILIARY, 0, 1)
        join.add(TEMPERATURE, 0, 1)
        join.add(WORKING, 0, 1)
        join.add(AUXILIARY, 500, 1)
        join.add(WORKING, 500, 1)
        assert [s[0] for s in join.state["buffers"][AUXILIARY]] == [500]

    def test_single_input_step_emits_immediately(self):
        join = StepJoin(TEMPERATURE, (), 10.0, new_state())
        assert join.add(TEMPERATURE, 5, 20) == [{"time": 5, TEMPERATURE: 20}]
        assert join.state["buffers"] == {}

    def test_unrelated_channel_is_ignored(self):
        join = self._join()
        assert join.add("device_metrics.voltage", 1, 3.3) == []
        assert join.state == new_state()

    def test_state_survives_a_json_round_trip(self):
        # Flink keeps it as a serialised string between elements.
        join = self._join()
        join.add(WORKING, 100, 300)
        join.add(AUXILIARY, 100, 100)
        restored = self._join(state=json.loads(json.dumps(join.state)))
        assert restored.add(TEMPERATURE, 100, 20)[0][WORKING] == 300


class TestApply:
    def test_chains_steps_within_one_pass(self):
        state = {}
        result = apply(
            [_no2_plan()],
            state,
            [_obs(WORKING, 100, 300), _obs(AUXILIARY, 100, 100), _obs(TEMPERATURE, 100, 0)],
        )
        derived = _by_channel(result)
        assert derived["derived.no2_ppb"] == [(100.0, pytest.approx(100.0))]
        # At 0 degC and standard pressure the molar volume is exactly 22.414 l/mol.
        assert derived["derived.no2_ugm3"] == [(100.0, pytest.approx(100.0 * 46.01 / 22.414))]
        assert all(obs.plan_id == "pp-1" for obs in result.derived)

    def test_join_state_persists_across_calls(self):
        state = {}
        plan = _no2_plan()
        apply([plan], state, [_obs(WORKING, 100, 300), _obs(AUXILIARY, 100, 100)])
        result = apply([plan], state, [_obs(TEMPERATURE, 100, 0)])
        assert "derived.no2_ppb" in _by_channel(result)

    def test_calibration_in_force_at_the_sample_time_applies(self):
        # Recalibrated at t=1000: backfills must use the old sensitivity before it.
        plan = _no2_plan(
            calibrations=(Calibration(0.0, {"sensitivity": 2.0}), Calibration(1000.0, {"sensitivity": 4.0}))
        )
        samples = []
        for t in (500, 1500):
            samples += [_obs(WORKING, t, 300), _obs(AUXILIARY, t, 100), _obs(TEMPERATURE, t, 20)]
        derived = _by_channel(apply([plan], {}, samples))
        assert derived["derived.no2_ppb"] == [(500.0, pytest.approx(100.0)), (1500.0, pytest.approx(50.0))]

    def test_sample_before_any_calibration_fails_the_row_not_the_run(self):
        plan = _no2_plan(calibrations=(Calibration(1000.0, {"sensitivity": 2.0}),))
        samples = [_obs(WORKING, 500, 300), _obs(AUXILIARY, 500, 100), _obs(TEMPERATURE, 500, 20)]
        result = apply([plan], {}, samples)
        assert result.derived == []
        count, message = result.failures["pp-1:ppb"]
        assert count == 1
        assert "sensitivity" in message

    def test_raising_algorithm_skips_the_row_and_counts_it(self):
        plan = _no2_plan(calibrations=(Calibration(0.0, {"sensitivity": 0.0}),))
        samples = []
        for t in (0, 60):
            samples += [_obs(WORKING, t, 300), _obs(AUXILIARY, t, 100), _obs(TEMPERATURE, t, 20)]
        result = apply([plan], {}, samples)
        assert result.failures["pp-1:ppb"][0] == 2
        assert result.failures["pp-1:ppb"][1].startswith("ZeroDivisionError")

    def test_one_plan_consumes_another_plans_output(self):
        dew = ResolvedPlan(
            id="pp-dew",
            blueprint_id="bp-dew",
            blueprint_version=1,
            tolerance_seconds=30.0,
            steps=(
                ResolvedStep(
                    key="dew",
                    function_name="dew_point",
                    inputs={"temperature": TEMPERATURE, "relative_humidity": HUMIDITY},
                    outputs={"dew_point": "derived.dew_point"},
                ),
            ),
        )
        offset = ResolvedPlan(
            id="pp-offset",
            blueprint_id="bp-offset",
            blueprint_version=1,
            tolerance_seconds=30.0,
            steps=(
                ResolvedStep(
                    key="cal",
                    function_name="offset_scale",
                    inputs={"value": "derived.dew_point"},
                    outputs={"calibrated": "derived.dew_point_calibrated"},
                    calibrations=(Calibration(0.0, {"offset": 1.0}),),
                ),
            ),
        )
        derived = _by_channel(apply([dew, offset], {}, [_obs(TEMPERATURE, 0, 20), _obs(HUMIDITY, 0, 50)]))
        (_, dew_point), = derived["derived.dew_point"]
        assert derived["derived.dew_point_calibrated"] == [(0.0, pytest.approx(dew_point + 1.0))]

    def test_changed_plan_discards_its_old_join_state(self):
        state = {}
        apply([_no2_plan()], state, [_obs(WORKING, 100, 300), _obs(AUXILIARY, 100, 100)])
        recalibrated = _no2_plan(calibrations=(Calibration(0.0, {"sensitivity": 3.0}),))
        result = apply([recalibrated], state, [_obs(TEMPERATURE, 100, 0)])
        assert result.derived == []

    def test_state_for_a_removed_plan_is_dropped(self):
        state = {}
        apply([_no2_plan()], state, [_obs(WORKING, 100, 300)])
        apply([], state, [])
        assert state == {}

    def test_cycle_does_not_loop_forever(self):
        loop = ResolvedPlan(
            id="pp-loop",
            blueprint_id="bp",
            blueprint_version=1,
            tolerance_seconds=10.0,
            steps=(
                ResolvedStep(
                    key="loop",
                    function_name="offset_scale",
                    inputs={"value": "derived.x"},
                    outputs={"calibrated": "derived.x"},
                ),
            ),
        )
        result = apply([loop], {}, [_obs("derived.x", 0, 1)])
        assert 0 < len(result.derived) <= 3

    def test_windowed_or_unknown_algorithm_is_reported(self):
        plan = ResolvedPlan(
            id="pp-x",
            blueprint_id="bp",
            blueprint_version=1,
            tolerance_seconds=10.0,
            steps=(ResolvedStep(key="s", function_name="nope", inputs={"value": TEMPERATURE}, outputs={}),),
        )
        result = apply([plan], {}, [_obs(TEMPERATURE, 0, 1)])
        assert "pp-x:s" in result.failures


class TestResolvedPlan:
    def test_round_trips_through_its_published_form(self):
        plan = _no2_plan(
            calibrations=(Calibration(1000.0, {"sensitivity": 4.0}), Calibration(0.0, {"sensitivity": 2.0}))
        )
        restored = ResolvedPlan.from_dict(json.loads(json.dumps(plan.to_dict())))
        assert restored == plan
        assert restored.fingerprint() == plan.fingerprint()

    def test_calibrations_are_sorted_when_loaded(self):
        step = ResolvedStep.from_dict(
            {
                "key": "s",
                "function_name": "offset_scale",
                "calibrations": [
                    {"valid_from": 100, "params": {"offset": 2}},
                    {"valid_from": 0, "params": {"offset": 1}},
                ],
            }
        )
        assert step.params_at(50) == {"offset": 1}
        assert step.params_at(150) == {"offset": 2}

    def test_calibration_overrides_nothing_but_calibration(self):
        step = _no2_plan().steps[0]
        assert step.params_at(10) == {"sensitivity": 2.0}
        assert _no2_plan().steps[1].params_at(10) == {"molecular_weight": 46.01}

    def test_fingerprint_changes_with_calibration(self):
        assert _no2_plan().fingerprint() != _no2_plan(calibrations=(Calibration(0.0, {"sensitivity": 3.0}),)).fingerprint()

    def test_input_channels_exclude_what_the_plan_produces(self):
        assert _no2_plan().input_channels == {WORKING, AUXILIARY, TEMPERATURE}
        assert _no2_plan().output_channels == {"derived.no2_ppb", "derived.no2_ugm3"}

    def test_output_units_chain_through_the_steps(self):
        units = _no2_plan().resolve_output_units({TEMPERATURE: "degC"})
        assert units == {"derived.no2_ppb": "ppb", "derived.no2_ugm3": "ug/m3"}

    def test_inherited_unit_follows_the_bound_channel(self):
        plan = ResolvedPlan(
            id="p",
            blueprint_id="b",
            blueprint_version=1,
            tolerance_seconds=1.0,
            steps=(
                ResolvedStep(
                    key="s", function_name="offset_scale", inputs={"value": TEMPERATURE}, outputs={"calibrated": "derived.t"}
                ),
            ),
        )
        assert plan.resolve_output_units({TEMPERATURE: "degC"}) == {"derived.t": "degC"}
        assert plan.resolve_output_units({}) == {"derived.t": None}
