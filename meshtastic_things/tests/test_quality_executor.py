from datetime import datetime, timedelta, timezone

import pytest

from common.postprocessing import Calibration, ResolvedPlan, ResolvedStep
from quality_worker.executor import (
    analyse_completeness,
    backfill_batches,
    backfill_channels,
    completeness_applies,
    derived_reading_interval,
)

START = datetime(2026, 9, 1, tzinfo=timezone.utc)

def _series(values, interval_seconds=60, offset_seconds=0):
    return [
        (START + timedelta(seconds=offset_seconds + i * interval_seconds), v) for i, v in enumerate(values)
    ]


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


TEMPERATURE = "environment_metrics.temperature"
HUMIDITY = "environment_metrics.relative_humidity"


def _dew_plan() -> ResolvedPlan:
    return ResolvedPlan(
        id="pp-dew",
        blueprint_id="bp",
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


def _offset_plan() -> ResolvedPlan:
    """Reads the dew plan's output, and was recalibrated one hour in."""
    return ResolvedPlan(
        id="pp-offset",
        blueprint_id="bp",
        blueprint_version=1,
        tolerance_seconds=30.0,
        steps=(
            ResolvedStep(
                key="cal",
                function_name="offset_scale",
                inputs={"value": "derived.dew_point"},
                outputs={"calibrated": "derived.dew_point_offset"},
                calibrations=(
                    Calibration(START.timestamp(), {"offset": 1.0}),
                    Calibration(START.timestamp() + 3600, {"offset": 2.0}),
                ),
            ),
        ),
    )


class TestBackfill:
    def _run(self, plans, series, batch_size=5000):
        events, failures = [], {}
        for batch, batch_failures in backfill_batches(plans, series, "mesh", 7, batch_size=batch_size):
            events.extend(batch)
            failures.update(batch_failures)
        return events, failures

    def test_reads_only_what_the_plans_do_not_produce(self):
        assert backfill_channels([_dew_plan(), _offset_plan()]) == {TEMPERATURE, HUMIDITY}
        assert backfill_channels([_offset_plan()]) == {"derived.dew_point"}

    def test_history_is_joined_across_channels_and_marked_as_backfill(self):
        series = {
            TEMPERATURE: _series([20.0, 21.0, 22.0], interval_seconds=600),
            HUMIDITY: _series([50.0, 50.0, 50.0], interval_seconds=600, offset_seconds=5),
        }

        events, failures = self._run([_dew_plan()], series)

        assert failures == {}
        assert [e["rx_time"] for e in events] == [int(START.timestamp()) + i * 600 for i in range(3)]
        assert all(e["backfill"] is True for e in events)
        assert all(e["postprocessing_id"] == "pp-dew" for e in events)

    def test_dependants_run_on_the_backfilled_output_with_the_calibration_of_the_time(self):
        series = {
            TEMPERATURE: _series([20.0, 20.0], interval_seconds=7200),
            HUMIDITY: _series([50.0, 50.0], interval_seconds=7200),
        }

        events, _ = self._run([_dew_plan(), _offset_plan()], series)

        dew = [e["payload"]["derived"]["dew_point"] for e in events if e["postprocessing_id"] == "pp-dew"]
        offset = [e["payload"]["derived"]["dew_point_offset"] for e in events if e["postprocessing_id"] == "pp-offset"]
        assert offset == [pytest.approx(dew[0] + 1.0), pytest.approx(dew[1] + 2.0)]

    def test_join_state_carries_across_batches(self):
        # Batches of one: every temperature is paired with a humidity from the next batch.
        series = {
            TEMPERATURE: _series([20.0, 21.0], interval_seconds=600),
            HUMIDITY: _series([50.0, 50.0], interval_seconds=600, offset_seconds=5),
        }

        events, _ = self._run([_dew_plan()], series, batch_size=1)

        assert len(events) == 2

    def test_no_history_publishes_nothing(self):
        assert self._run([_dew_plan()], {TEMPERATURE: [], HUMIDITY: []}) == ([], {})
