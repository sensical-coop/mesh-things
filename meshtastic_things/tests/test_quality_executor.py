from datetime import datetime, timedelta, timezone

import pytest

from quality_worker.executor import (
    align_series,
    analyse_completeness,
    completeness_applies,
    derived_reading_interval,
    resolve_output_units,
    run_steps,
)

START = datetime(2026, 9, 1, tzinfo=timezone.utc)

def _series(values, interval_seconds=60, offset_seconds=0):
    return [
        (START + timedelta(seconds=offset_seconds + i * interval_seconds), v) for i, v in enumerate(values)
    ]


class TestAlignSeries:
    def test_single_channel_passes_through(self):
        rows = align_series({"a.x": _series([1.0, 2.0])}, 60)
        assert [r["a.x"] for r in rows] == [1.0, 2.0]

    def test_aligns_channels_sampled_at_slightly_different_instants(self):
        # Sensors in one device share a clock but not an exact sampling
        # instant, so an exact-timestamp join would drop everything.
        rows = align_series(
            {"a.x": _series([1.0, 2.0, 3.0]), "b.y": _series([10.0, 20.0, 30.0], offset_seconds=5)}, 60
        )
        assert len(rows) == 3
        assert [r["b.y"] for r in rows] == [10.0, 20.0, 30.0]

    def test_drops_rows_where_a_channel_has_no_nearby_sample(self):
        # A stale temperature would silently produce a wrong answer, which is
        # worse than producing nothing.
        rows = align_series(
            {"a.x": _series([1.0, 2.0, 3.0]), "b.y": [(START, 10.0), (START + timedelta(seconds=120), 30.0)]},
            60,
        )
        assert [r["a.x"] for r in rows] == [1.0, 3.0]

    def test_picks_the_nearest_sample_not_the_first(self):
        rows = align_series(
            {
                "a.x": [(START + timedelta(seconds=100), 1.0)],
                "b.y": [(START + timedelta(seconds=80), 10.0), (START + timedelta(seconds=105), 20.0)],
            },
            60,
        )
        assert rows[0]["b.y"] == 20.0

    def test_empty_inputs(self):
        assert align_series({}, 60) == []
        assert align_series({"a.x": []}, 60) == []


class TestRunSteps:
    def test_single_step_writes_its_declared_output_channel(self):
        rows = [{"time": START, "env.temperature": 20.0, "env.relative_humidity": 50.0}]
        steps = [
            {
                "order": 0,
                "function_name": "dew_point",
                "inputs": {"temperature": "env.temperature", "relative_humidity": "env.relative_humidity"},
                "params": {},
                "outputs": {"dew_point": "env.dew_point"},
            }
        ]

        outputs = run_steps(steps, rows)

        assert set(outputs) == {"env.dew_point"}
        assert outputs["env.dew_point"][0][1] == pytest.approx(9.25, abs=0.1)

    def test_later_step_consumes_an_earlier_steps_output(self):
        # The chaining case: ADC -> ppb -> ug/m3 as two steps.
        rows = [{"time": START, "ads.w": 300.0, "ads.a": 100.0, "env.temperature": 0.0}]
        steps = [
            {
                "order": 0,
                "function_name": "ec_sensor_ppb",
                "inputs": {"working": "ads.w", "auxiliary": "ads.a", "temperature": "env.temperature"},
                "params": {"sensitivity": 2.0},
                "outputs": {"concentration_ppb": "no2_ppb"},
            },
            {
                "order": 1,
                "function_name": "ppb_to_ugm3",
                "inputs": {"concentration_ppb": "no2_ppb", "temperature": "env.temperature"},
                "params": {"molecular_weight": 46.01},
                "outputs": {"concentration_ugm3": "no2_ugm3"},
            },
        ]

        outputs = run_steps(steps, rows)

        assert set(outputs) == {"no2_ppb", "no2_ugm3"}
        # temperature_coefficient defaults to 0, so aux is subtracted unscaled.
        assert outputs["no2_ppb"][0][1] == pytest.approx(100.0)
        assert outputs["no2_ugm3"][0][1] == pytest.approx(100.0 * 46.01 / 22.414)

    def test_steps_run_in_order_regardless_of_list_order(self):
        rows = [{"time": START, "ads.w": 300.0, "ads.a": 100.0, "env.temperature": 0.0}]
        steps = [
            {
                "order": 1,
                "function_name": "ppb_to_ugm3",
                "inputs": {"concentration_ppb": "no2_ppb", "temperature": "env.temperature"},
                "params": {"molecular_weight": 46.01},
                "outputs": {"concentration_ugm3": "no2_ugm3"},
            },
            {
                "order": 0,
                "function_name": "ec_sensor_ppb",
                "inputs": {"working": "ads.w", "auxiliary": "ads.a", "temperature": "env.temperature"},
                "params": {"sensitivity": 2.0},
                "outputs": {"concentration_ppb": "no2_ppb"},
            },
        ]

        outputs = run_steps(steps, rows)

        assert "no2_ugm3" in outputs

    def test_a_failing_row_is_skipped_not_fatal(self):
        rows = [
            {"time": START, "env.temperature": 20.0, "env.relative_humidity": 50.0},
            {"time": START + timedelta(seconds=60), "env.temperature": 20.0, "env.relative_humidity": 0.0},
        ]
        steps = [
            {
                "order": 0,
                "function_name": "dew_point",
                "inputs": {"temperature": "env.temperature", "relative_humidity": "env.relative_humidity"},
                "params": {},
                "outputs": {"dew_point": "env.dew_point"},
            }
        ]

        outputs = run_steps(steps, rows)

        assert len(outputs["env.dew_point"]) == 1

    def test_unknown_algorithm_is_skipped(self):
        rows = [{"time": START, "a.x": 1.0}]
        steps = [
            {"order": 0, "function_name": "gone_missing", "inputs": {"v": "a.x"}, "params": {}, "outputs": {"o": "y"}}
        ]

        assert run_steps(steps, rows) == {}

    def test_row_missing_an_upstream_channel_is_skipped(self):
        rows = [{"time": START}]
        steps = [
            {
                "order": 0,
                "function_name": "dew_point",
                "inputs": {"temperature": "env.temperature", "relative_humidity": "env.relative_humidity"},
                "params": {},
                "outputs": {"dew_point": "env.dew_point"},
            }
        ]

        assert run_steps(steps, rows) == {}


class TestAnalyseCompleteness:
    def test_full_history_scores_one(self):
        series = _series([1.0] * 24, interval_seconds=3600)
        stats = analyse_completeness(series, window_seconds=86400, reading_interval_seconds=3600)
        assert stats["ratio"] == 1.0
        assert stats["largest_gap_seconds"] == 3600

    def test_patchy_history_scores_below_one(self):
        # 12 readings where 24 were expected - the device published, but its
        # history has holes.
        series = _series([1.0] * 12, interval_seconds=3600)
        stats = analyse_completeness(series, window_seconds=86400, reading_interval_seconds=3600)
        assert stats["ratio"] == pytest.approx(0.5)
        assert stats["observed"] == 12
        assert stats["expected"] == 24

    def test_largest_gap_is_reported_even_when_the_ratio_looks_healthy(self):
        # 23 of 24 readings, but not evenly spread: hourly readings up to
        # t=11h, then nothing until t=17h - a 6h hole the ratio alone hides.
        series = _series([1.0] * 12, interval_seconds=3600) + _series(
            [1.0] * 11, interval_seconds=3600, offset_seconds=17 * 3600
        )
        stats = analyse_completeness(series, window_seconds=86400, reading_interval_seconds=3600)
        assert stats["ratio"] > 0.9
        assert stats["largest_gap_seconds"] == pytest.approx(6 * 3600)

    def test_no_data_scores_zero(self):
        stats = analyse_completeness([], window_seconds=86400, reading_interval_seconds=3600)
        assert stats["ratio"] == 0.0
        assert stats["largest_gap_seconds"] == 0

    def test_more_samples_than_expected_is_capped_not_over_one(self):
        # A device reading faster than configured isn't a completeness fault.
        series = _series([1.0] * 48, interval_seconds=1800)
        stats = analyse_completeness(series, window_seconds=86400, reading_interval_seconds=3600)
        assert stats["ratio"] == 1.0


def _step(order, function_name, inputs, outputs, params=None):
    return {
        "order": order,
        "function_name": function_name,
        "inputs": inputs,
        "outputs": outputs,
        "params": params or {},
    }

def test_resolve_output_units_reads_the_algorithms_declaration():
    steps = [
        _step(0, "dew_point",
              {"temperature": "environment_metrics.temperature",
               "relative_humidity": "environment_metrics.relative_humidity"},
              {"dew_point": "dew_point"})
    ]

    assert resolve_output_units(steps, {}) == {"dew_point": "degC"}

def test_units_chain_through_steps_the_same_way_values_do():
    """A correction step reading an earlier step's output inherits its unit -
    the catalog has no row for a channel that didn't exist until this run."""
    steps = [
        _step(0, "ec_sensor_ppb",
              {"working": "adc.working", "auxiliary": "adc.auxiliary",
               "temperature": "environment_metrics.temperature"},
              {"concentration_ppb": "no2_ppb"},
              {"sensitivity": 0.3}),
        _step(1, "linear_temperature_correction",
              {"value": "no2_ppb", "temperature": "environment_metrics.temperature"},
              {"corrected": "no2_ppb_corrected"},
              {"coefficient": 0.01}),
        _step(2, "ppb_to_ugm3",
              {"concentration_ppb": "no2_ppb_corrected", "temperature": "environment_metrics.temperature"},
              {"concentration_ugm3": "no2_ugm3"},
              {"molecular_weight": 46.01}),
    ]

    assert resolve_output_units(steps, {}) == {
        "no2_ppb": "ppb",
        "no2_ppb_corrected": "ppb",  # inherited through the correction
        "no2_ugm3": "ug/m3",
    }

def test_inherited_unit_comes_from_the_existing_catalog_when_the_input_is_raw():
    steps = [
        _step(0, "linear_temperature_correction",
              {"value": "environment_metrics.temperature", "temperature": "environment_metrics.temperature"},
              {"corrected": "temperature_corrected"},
              {"coefficient": 0.01}),
    ]

    catalog = {"environment_metrics.temperature": "degC"}
    assert resolve_output_units(steps, catalog) == {"temperature_corrected": "degC"}

def test_unknown_upstream_unit_resolves_to_none_rather_than_being_guessed():
    steps = [
        _step(0, "linear_temperature_correction",
              {"value": "adc.raw", "temperature": "environment_metrics.temperature"},
              {"corrected": "raw_corrected"},
              {"coefficient": 0.01}),
    ]

    assert resolve_output_units(steps, {}) == {"raw_corrected": None}

def test_unknown_algorithm_is_skipped_not_fatal():
    # Same fail-soft convention as run_steps: a step naming a since-removed
    # algorithm shouldn't stop the others' units being resolved.
    steps = [
        _step(0, "no_such_algorithm", {"a": "x.y"}, {"b": "gone"}),
        _step(1, "dew_point",
              {"temperature": "environment_metrics.temperature",
               "relative_humidity": "environment_metrics.relative_humidity"},
              {"dew_point": "dew_point"}),
    ]

    assert resolve_output_units(steps, {}) == {"dew_point": "degC"}

def test_steps_are_resolved_in_execution_order_not_list_order():
    steps = [
        _step(1, "linear_temperature_correction",
              {"value": "dew_point", "temperature": "environment_metrics.temperature"},
              {"corrected": "dew_point_corrected"},
              {"coefficient": 0.01}),
        _step(0, "dew_point",
              {"temperature": "environment_metrics.temperature",
               "relative_humidity": "environment_metrics.relative_humidity"},
              {"dew_point": "dew_point"}),
    ]

    assert resolve_output_units(steps, {})["dew_point_corrected"] == "degC"


@pytest.mark.parametrize(
    "measurement_type, applies",
    [
        ({"origin": "measured", "payload_kind": "telemetry:environment_metrics"}, True),
        ({"origin": "computed", "payload_kind": "computed:derived"}, True),
        ({"origin": "computed", "payload_kind": "computed:quality"}, False),
        ({"origin": "device", "payload_kind": "device:position"}, False),
    ],
)
def test_completeness_covers_sensor_and_derived_channels(measurement_type, applies):
    assert completeness_applies(measurement_type) is applies


class TestDerivedReadingInterval:
    ROWS = {
        "temp": {"id": "temp", "produced_by": None, "measurement_type": {"payload_kind": "telemetry:environment_metrics"}},
        "adc": {"id": "adc", "produced_by": None, "measurement_type": {"payload_kind": "telemetry:ads1115"}},
        "ppb": {"id": "ppb", "produced_by": "pp-no2", "measurement_type": {"payload_kind": "computed:derived"}},
    }
    INTERVALS = {"telemetry:environment_metrics": 300, "telemetry:ads1115": 60}

    def _interval(self, produced_by, bindings):
        return derived_reading_interval(produced_by, self.ROWS, bindings, self.INTERVALS.get)

    def test_the_slowest_input_sets_the_pace(self):
        assert self._interval("pp-no2", {"pp-no2": {"working": "adc", "temperature": "temp"}}) == 300

    def test_chained_postprocessings_are_followed(self):
        bindings = {"pp-no2": {"working": "adc"}, "pp-cal": {"value": "ppb"}}
        assert self._interval("pp-cal", bindings) == 60

    def test_unknown_intervals_give_none(self):
        assert self._interval("pp-no2", {"pp-no2": {"value": "missing"}}) is None

    def test_a_cycle_does_not_recurse_forever(self):
        rows = {"x": {"id": "x", "produced_by": "pp-a", "measurement_type": {"payload_kind": "computed:derived"}}}
        assert derived_reading_interval("pp-a", rows, {"pp-a": {"v": "x"}}, self.INTERVALS.get) is None
