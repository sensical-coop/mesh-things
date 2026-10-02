import pytest

from common import algorithms
from common.algorithms import POINTWISE, AlgorithmSpec, Param, discover, get, validate_calibration, validate_step


@pytest.fixture(autouse=True)
def _restore_registry():
    """Tests that register throwaway algorithms must not leak into the real registry, which
    other tests (and registry's validation) read from."""
    discover()
    original = dict(algorithms.REGISTRY)
    yield
    algorithms.REGISTRY.clear()
    algorithms.REGISTRY.update(original)

def _spec(**overrides) -> AlgorithmSpec:
    defaults = dict(name="t", func=lambda x: x, inputs=("x",), outputs=("y",))
    return AlgorithmSpec(**{**defaults, **overrides})

def test_discover_finds_the_shipped_algorithms():
    registry = discover(force=True)
    assert "ec_sensor_ppb" in registry
    assert "dew_point" in registry
    assert "ppb_to_ugm3" in registry

def test_spec_declares_multi_sensor_inputs():
    # The motivating case: one algorithm spanning two ADC channels + temperature.
    spec = get("ec_sensor_ppb")
    assert spec.inputs == ("working", "auxiliary", "temperature")
    assert spec.outputs == ("concentration_ppb",)
    assert "sensitivity" in {p.name for p in spec.calibration_params}
    assert spec.mode == POINTWISE

def test_call_wraps_a_bare_return_for_single_output_algorithms():
    spec = get("dew_point")
    result = spec.call({"temperature": 20.0, "relative_humidity": 50.0}, {})
    assert set(result) == {"dew_point"}
    assert result["dew_point"] == pytest.approx(9.25, abs=0.1)

def test_call_rejects_a_bare_return_when_several_outputs_are_declared():
    spec = _spec(outputs=("a", "b"), func=lambda x: 1.0)
    with pytest.raises(TypeError, match="must return a dict"):
        spec.call({"x": 1.0}, {})

def test_duplicate_algorithm_name_is_rejected():
    algorithms.algorithm(name="dupe", inputs=("x",), outputs=("y",))(lambda x: x)
    with pytest.raises(ValueError, match="Duplicate algorithm name"):
        algorithms.algorithm(name="dupe", inputs=("x",), outputs=("y",))(lambda x: x)

def test_invalid_mode_is_rejected_at_decoration_time():
    with pytest.raises(ValueError, match="mode must be one of"):
        algorithms.algorithm(name="bad", inputs=("x",), outputs=("y",), mode="streaming")

def test_param_declared_twice_is_rejected():
    with pytest.raises(ValueError, match="declared twice"):

        @algorithms.algorithm(name="_twice", inputs=("x",), outputs=("y",), params=("p", Param("p")))
        def _f(x, *, p):
            return x

def test_inputs_must_match_the_positional_arguments():
    with pytest.raises(ValueError, match="positional arguments"):

        @algorithms.algorithm(name="_bad_inputs", inputs=("x", "z"), outputs=("y",))
        def _f(x):
            return x

def test_params_must_match_the_keyword_only_arguments():
    with pytest.raises(ValueError, match="keyword-only arguments"):

        @algorithms.algorithm(name="_bad_params", inputs=("x",), outputs=("y",), params=("gain",))
        def _f(x, *, offset=0.0):
            return x

def test_defaults_are_read_from_the_signature():
    params = {p.name: p for p in get("ec_sensor_ppb").params}
    assert params["sensitivity"].required
    assert not params["working_zero"].required
    assert params["working_zero"].default == 0.0
    assert params["reference_temperature"].default == 20.0

def test_param_metadata_is_exposed_for_introspection():
    params = {p["name"]: p for p in get("ec_sensor_ppb").as_dict()["params"]}
    assert params["sensitivity"] == {
        "name": "sensitivity",
        "calibration": True,
        "required": True,
        "default": None,
        "unit": "mV/ppb",
        "doc": "Working electrode response per ppb, non-zero.",
    }
    assert params["reference_temperature"]["calibration"] is False

def test_validate_step_accepts_a_well_formed_step():
    errors = validate_step(
        "ec_sensor_ppb",
        {"working": "ads.chan0", "auxiliary": "ads.chan1", "temperature": "environment_metrics.temperature"},
        {"temperature_coefficient": 0.01},
        {"concentration_ppb": "no2_ppb"},
    )
    assert errors == []

def test_validate_step_rejects_calibration_params():
    # They describe one physical sensor, so they belong to the device.
    errors = validate_step(
        "ec_sensor_ppb", {"working": "a", "auxiliary": "b", "temperature": "c"}, {"sensitivity": 0.42}
    )
    assert any("calibration parameters, set per device" in e and "sensitivity" in e for e in errors)

def test_validate_step_rejects_unknown_output():
    errors = validate_step("dew_point", {"temperature": "a", "relative_humidity": "b"}, {}, {"dewpoint": "x"})
    assert any("has no output(s)" in e for e in errors)

def test_validate_step_requires_an_output_binding():
    errors = validate_step("dew_point", {"temperature": "a", "relative_humidity": "b"}, {}, {})
    assert any("at least one output" in e for e in errors)

def test_validate_calibration_requires_every_required_calibration_param():
    errors = validate_calibration("ec_sensor_ppb", {"working_zero": 220.0})
    assert any("requires calibration param(s)" in e and "sensitivity" in e for e in errors)

def test_validate_calibration_allows_an_incomplete_draft():
    assert validate_calibration("ec_sensor_ppb", {"working_zero": 220.0}, complete=False) == []

def test_validate_calibration_rejects_configuration_params():
    errors = validate_calibration("ec_sensor_ppb", {"sensitivity": 1.0, "reference_temperature": 25.0})
    assert any("are configuration, set on the blueprint step" in e for e in errors)

def test_validate_calibration_rejects_unknown_params():
    errors = validate_calibration("offset_scale", {"gain": 2.0})
    assert any("does not accept param(s)" in e and "gain" in e for e in errors)

def test_validate_step_rejects_unknown_function():
    errors = validate_step("does_not_exist", {}, {})
    assert len(errors) == 1
    assert "Unknown algorithm" in errors[0]

def test_validate_step_rejects_missing_input():
    errors = validate_step("ec_sensor_ppb", {"working": "a"}, {})
    assert any("requires input(s)" in e and "auxiliary" in e for e in errors)

def test_validate_step_rejects_unexpected_input():
    errors = validate_step(
        "ec_sensor_ppb",
        {"working": "a", "auxiliary": "b", "temperature": "c", "pressure": "d"},
        {},
    )
    assert any("does not accept input(s)" in e and "pressure" in e for e in errors)

def test_validate_step_rejects_missing_required_param():
    errors = validate_step("ppb_to_ugm3", {"concentration_ppb": "a", "temperature": "b"}, {})
    assert any("requires param(s)" in e and "molecular_weight" in e for e in errors)

def test_validate_step_rejects_unknown_param():
    errors = validate_step(
        "ec_sensor_ppb",
        {"working": "a", "auxiliary": "b", "temperature": "c"},
        {"nonsense": 3},
    )
    assert any("does not accept param(s)" in e and "nonsense" in e for e in errors)

def test_ec_sensor_subtracts_the_auxiliary_electrode():
    spec = get("ec_sensor_ppb")
    # working 300, auxiliary 100, no zeros, no temp coefficient, sensitivity 2
    # -> (300 - 100) / 2 = 100
    result = spec.call(
        {"working": 300.0, "auxiliary": 100.0, "temperature": 20.0}, {"sensitivity": 2.0}
    )
    assert result["concentration_ppb"] == pytest.approx(100.0)

def test_ec_sensor_zero_sensitivity_raises():
    spec = get("ec_sensor_ppb")
    with pytest.raises(ZeroDivisionError):
        spec.call({"working": 1.0, "auxiliary": 0.0, "temperature": 20.0}, {"sensitivity": 0.0})

def test_ppb_to_ugm3_at_reference_conditions():
    spec = get("ppb_to_ugm3")
    # NO2 at 0 degC / 1013.25 hPa: molar volume is exactly 22.414 l/mol
    result = spec.call({"concentration_ppb": 100.0, "temperature": 0.0}, {"molecular_weight": 46.01})
    assert result["concentration_ugm3"] == pytest.approx(100.0 * 46.01 / 22.414)

def test_ppb_to_ugm3_is_temperature_dependent():
    spec = get("ppb_to_ugm3")
    cold = spec.call({"concentration_ppb": 100.0, "temperature": 0.0}, {"molecular_weight": 46.01})
    warm = spec.call({"concentration_ppb": 100.0, "temperature": 30.0}, {"molecular_weight": 46.01})
    # Warmer air is less dense, so the same mixing ratio is less mass per m3.
    assert warm["concentration_ugm3"] < cold["concentration_ugm3"]

def test_linear_temperature_correction_is_identity_at_reference():
    spec = get("linear_temperature_correction")
    result = spec.call({"value": 50.0, "temperature": 20.0}, {"coefficient": 0.01})
    assert result["corrected"] == pytest.approx(50.0)

def test_linear_temperature_correction_undoes_a_known_drift():
    spec = get("linear_temperature_correction")
    # +1%/degC, 10 degC above reference -> reading inflated by 10%
    result = spec.call({"value": 110.0, "temperature": 30.0}, {"coefficient": 0.01})
    assert result["corrected"] == pytest.approx(100.0)

def test_absolute_humidity_rises_with_temperature_at_fixed_rh():
    spec = get("absolute_humidity")
    cool = spec.call({"temperature": 10.0, "relative_humidity": 50.0}, {})
    warm = spec.call({"temperature": 30.0, "relative_humidity": 50.0}, {})
    assert warm["absolute_humidity"] > cool["absolute_humidity"]

def test_offset_scale_applies_scale_then_offset():
    result = get("offset_scale").call({"value": 10.0}, {"scale": 2.0, "offset": 1.0})
    assert result["calibrated"] == pytest.approx(21.0)

def test_offset_scale_defaults_to_identity():
    assert get("offset_scale").call({"value": 10.0}, {})["calibrated"] == pytest.approx(10.0)

def test_lookup_table_interpolates_and_clamps():
    spec = get("lookup_table")
    points = [[10, 100], [0, 0]]
    assert spec.call({"value": 5.0}, {"points": points})["calibrated"] == pytest.approx(50.0)
    assert spec.call({"value": -5.0}, {"points": points})["calibrated"] == pytest.approx(0.0)
    assert spec.call({"value": 50.0}, {"points": points})["calibrated"] == pytest.approx(100.0)

def test_lookup_table_needs_a_point():
    with pytest.raises(ValueError, match="at least one"):
        get("lookup_table").call({"value": 1.0}, {"points": []})

def test_calibration_curves_preserve_the_input_unit():
    assert get("offset_scale").unit_for("calibrated", {"value": "degC"}) == "degC"
    assert get("lookup_table").unit_for("calibrated", {"value": "ppb"}) == "ppb"

def test_dew_point_rejects_zero_humidity():
    spec = get("dew_point")
    with pytest.raises(ValueError, match="relative_humidity"):
        spec.call({"temperature": 20.0, "relative_humidity": 0.0}, {})


# A derived channel has no protobuf field behind it, so the algorithm is the
# only thing that can say what its output is measured in. Without this the
# catalog row is created bare and nothing downstream can label the series.

def test_every_shipped_algorithm_declares_a_unit_for_every_output():
    """Guards the next algorithm added, not the current five - an undeclared output silently
    produces an unlabelled channel."""
    for spec in discover().values():
        for output in spec.outputs:
            assert output in spec.output_units, f"{spec.name} declares no unit for output {output!r}"

def test_literal_unit_is_returned_as_declared():
    assert get("dew_point").unit_for("dew_point", {}) == "degC"
    assert get("ppb_to_ugm3").unit_for("concentration_ugm3", {}) == "ug/m3"

def test_unit_preserving_algorithm_inherits_from_its_input():
    # A temperature correction returns the same quantity it was given, so the
    # only honest declaration is a reference to the input.
    spec = get("linear_temperature_correction")
    assert spec.unit_for("corrected", {"value": "ppb", "temperature": "degC"}) == "ppb"
    assert spec.unit_for("corrected", {"value": "ug/m3", "temperature": "degC"}) == "ug/m3"

def test_unresolvable_inherited_unit_is_none_not_a_guess():
    # The upstream channel has no unit itself. Unknown must stay unknown - a
    # wrong unit in the catalog is worse than an absent one.
    spec = get("linear_temperature_correction")
    assert spec.unit_for("corrected", {"value": None}) is None
    assert spec.unit_for("corrected", {}) is None

def test_output_units_are_exposed_for_introspection():
    assert get("dew_point").as_dict()["output_units"] == {"dew_point": "degC"}

def test_declaring_a_unit_for_something_that_isnt_an_output_is_rejected():
    with pytest.raises(ValueError, match="which aren't outputs"):

        @algorithms.algorithm(
            name="_bad_output_name", inputs=("a",), outputs=("b",), output_units={"typo": "degC"}
        )
        def _f(a):
            return a

def test_inheriting_from_something_that_isnt_an_input_is_rejected():
    with pytest.raises(ValueError, match="isn't one of its inputs"):

        @algorithms.algorithm(
            name="_bad_inherit", inputs=("a",), outputs=("b",), output_units={"b": "@nonexistent"}
        )
        def _f(a):
            return a

def test_unclassifiable_unit_is_rejected_at_import_time():
    """Caught here rather than silently writing a unit the catalog can't classify into a
    quantity_kind months later."""
    with pytest.raises(ValueError, match="common.units"):

        @algorithms.algorithm(
            name="_bad_unit", inputs=("a",), outputs=("b",), output_units={"b": "furlongs/fortnight"}
        )
        def _f(a):
            return a
