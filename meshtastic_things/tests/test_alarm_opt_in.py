"""Alarms tests"""
import pytest

from common import detectors
from common.detectors import (
    COMPLETENESS,
    FLAT_VALUE,
    MEASUREMENT_DETECTORS,
    PLAUSIBILITY,
    enabled_detectors_for,
)


class TestResolution:
    def test_null_inherits_the_catalog_default(self):
        assert enabled_detectors_for(None, [PLAUSIBILITY]) == {PLAUSIBILITY}

    def test_an_empty_list_silences_despite_the_default(self):
        assert enabled_detectors_for([], [PLAUSIBILITY, FLAT_VALUE]) == set()

    def test_the_device_list_replaces_the_default_rather_than_merging(self):
        assert enabled_detectors_for([FLAT_VALUE], [PLAUSIBILITY]) == {FLAT_VALUE}

    def test_nothing_configured_anywhere_means_no_alarms(self):
        assert enabled_detectors_for(None, None) == set()
        assert enabled_detectors_for(None, []) == set()

    def test_the_motivating_case(self):
        """Stable pressure: no flat_value, but still range-checked."""
        enabled = enabled_detectors_for([PLAUSIBILITY, COMPLETENESS], None)

        assert FLAT_VALUE not in enabled
        assert PLAUSIBILITY in enabled


class TestFlatValueGate:
    """The one detector that fired unconditionally before."""

    FLAT = [1.0] * 10

    def test_it_still_triggers_on_its_own_terms(self):
        assert detectors.stuck_value_triggered(self.FLAT, window=5)

    @pytest.mark.parametrize("enabled,fires", [(None, False), ([], False),
                                               ([PLAUSIBILITY], False), ([FLAT_VALUE], True)])
    def test_only_an_enabled_measurement_alarms(self, enabled, fires):
        triggered = detectors.stuck_value_triggered(self.FLAT, window=5)
        assert (FLAT_VALUE in enabled_detectors_for(enabled, None) and triggered) is fires


class TestDetectorNames:
    def test_the_per_measurement_set_is_what_the_jobs_gate_on(self):
        assert set(MEASUREMENT_DETECTORS) == {FLAT_VALUE, PLAUSIBILITY, COMPLETENESS}

    def test_absence_is_not_per_measurement(self):
        """It has no channel, so it hangs off Device.alarms_enabled instead."""
        assert detectors.ABSENCE not in MEASUREMENT_DETECTORS
