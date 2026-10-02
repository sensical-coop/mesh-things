"""Registry of postprocessing algorithms, discovered by name.

A blueprint step names one of these functions and binds its `inputs` to
channels; a device attaching the blueprint supplies the step's calibration
parameters. See docs/architecture.md#postprocessing-blueprints. Writing a new
algorithm means dropping a decorated function into a module in this package;
nothing else needs editing.

Parameters come in two kinds, declared with `Param`:
  - configuration describes the recipe (a molecular weight) and is set on the
    blueprint step.
  - calibration describes one physical sensor (an electrode's sensitivity) and
    is set per device, so one blueprint can serve many units of the same build.

A parameter's default is read from the function signature and never restated;
a parameter without one is required.

`mode` decides where an algorithm can run:
  - "pointwise": one aligned sample at a time, no history. Runs in the stream
    tier and in backfills.
  - "windowed": needs a whole series. Declarable, but nothing runs it yet, so
    registry rejects blueprints that use one.
"""
import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from common.units import quantity_kind_for

log = structlog.get_logger()

POINTWISE = "pointwise"
WINDOWED = "windowed"
_VALID_MODES = (POINTWISE, WINDOWED)

# An output_units value of "@value" means "whatever unit the channel bound to
# the `value` input carries". Some algorithms are unit-preserving - a
# temperature correction returns the same quantity it was given, so the only
# honest declaration is a reference to its input, not a literal.
INHERIT = "@"

_NO_DEFAULT = inspect.Parameter.empty


@dataclass(frozen=True)
class Param:
    """One keyword argument of an algorithm."""

    name: str
    calibration: bool = False
    # Free text for documentation, e.g. "mV/ppb". Calibration units are rarely
    # catalog units, so they are not checked against common.units.
    unit: str | None = None
    doc: str = ""
    default: Any = _NO_DEFAULT

    @property
    def required(self) -> bool:
        return self.default is _NO_DEFAULT

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "calibration": self.calibration,
            "required": self.required,
            "default": None if self.required else self.default,
            "unit": self.unit,
            "doc": self.doc,
        }


@dataclass(frozen=True)
class AlgorithmSpec:
    """What a step needs to know to call an algorithm without importing it."""

    name: str
    func: Callable
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    params: tuple[Param, ...] = ()
    mode: str = POINTWISE
    doc: str = ""
    # {output_name: unit}, where a unit may be "@<input_name>" - see INHERIT.
    # A derived channel has no protobuf field to inherit a unit from, so the
    # algorithm is the only thing that can say what it emits.
    output_units: dict[str, str] = field(default_factory=dict)

    @property
    def config_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if not p.calibration)

    @property
    def calibration_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if p.calibration)

    def unit_for(self, output_name: str, input_units: dict[str, str | None]) -> str | None:
        """This output's unit, resolving an "@<input>" reference against the
        units of the channels actually bound to this step's inputs.

        Returns None when undeclared, or when an inherited unit can't be
        resolved because the upstream channel has no unit itself.
        """
        declared = self.output_units.get(output_name)
        if not declared:
            return None
        if declared.startswith(INHERIT):
            return input_units.get(declared[len(INHERIT):])
        return declared

    def call(self, inputs: dict, params: dict) -> dict:
        """Invoke with inputs and params as keyword args, normalising the
        return to {output_name: value}. A single-output algorithm may return a
        bare value instead of a dict."""
        result = self.func(**inputs, **params)
        if isinstance(result, dict):
            return result
        if len(self.outputs) == 1:
            return {self.outputs[0]: result}
        raise TypeError(
            f"Algorithm {self.name!r} declares {len(self.outputs)} outputs "
            f"so it must return a dict, got {type(result).__name__}"
        )

    def as_dict(self) -> dict:
        """Serializable form returned by GET /algorithms."""
        return {
            "name": self.name,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "params": [p.as_dict() for p in self.params],
            "mode": self.mode,
            "doc": self.doc,
            "output_units": dict(self.output_units),
        }


REGISTRY: dict[str, AlgorithmSpec] = {}


def _bind_params(name: str, func: Callable, inputs: tuple[str, ...], declared: tuple) -> tuple[Param, ...]:
    """Check the declaration against the signature and fill defaults from it.

    Inputs must be the positional arguments and params the keyword-only ones,
    so a declaration can never drift from what the function actually accepts.
    """
    signature = inspect.signature(func)
    positional = [
        p.name for p in signature.parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    keyword = {p.name: p for p in signature.parameters.values() if p.kind == p.KEYWORD_ONLY}

    if set(positional) != set(inputs):
        raise ValueError(
            f"Algorithm {name!r}: inputs {sorted(inputs)} don't match the function's "
            f"positional arguments {sorted(positional)}"
        )
    params = tuple(p if isinstance(p, Param) else Param(p) for p in declared)
    names = [p.name for p in params]
    if len(set(names)) != len(names):
        raise ValueError(f"Algorithm {name!r}: a param is declared twice in {names}")
    if set(names) != set(keyword):
        raise ValueError(
            f"Algorithm {name!r}: params {sorted(names)} don't match the function's "
            f"keyword-only arguments {sorted(keyword)}"
        )
    return tuple(
        Param(p.name, calibration=p.calibration, unit=p.unit, doc=p.doc, default=keyword[p.name].default)
        for p in params
    )


def algorithm(
    *,
    name: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    params: tuple[Param | str, ...] = (),
    mode: str = POINTWISE,
    output_units: dict[str, str] | None = None,
):
    """Register a function as a named, introspectable algorithm.

    Args:
        name: Name steps refer to the algorithm by.
        inputs: Channel-bound arguments, the function's positional arguments.
        outputs: Names this produces, each bound to a derived channel by a step.
        params: Keyword-only arguments, as `Param` or a bare name for a
            configuration parameter. Defaults come from the signature.
        mode: `POINTWISE` or `WINDOWED`.
        output_units: {output: unit}, the unit being a literal ("degC") or
            "@<input>" for a unit-preserving algorithm.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"Algorithm {name!r}: mode must be one of {_VALID_MODES}, got {mode!r}")
    if not inputs:
        raise ValueError(f"Algorithm {name!r}: must declare at least one input")
    if not outputs:
        raise ValueError(f"Algorithm {name!r}: must declare at least one output")

    units = dict(output_units or {})
    if unknown := set(units) - set(outputs):
        raise ValueError(f"Algorithm {name!r}: output_units names {sorted(unknown)}, which aren't outputs")
    for output_name, unit in units.items():
        if unit.startswith(INHERIT):
            source = unit[len(INHERIT):]
            if source not in inputs:
                raise ValueError(
                    f"Algorithm {name!r}: output {output_name!r} inherits its unit from {source!r}, "
                    f"which isn't one of its inputs {sorted(inputs)}"
                )
        elif quantity_kind_for(unit) is None:
            # Caught at import time rather than silently writing an
            # unclassifiable unit into the catalog months later.
            raise ValueError(
                f"Algorithm {name!r}: output {output_name!r} declares unit {unit!r}, which isn't in "
                f"common.units.QUANTITY_KIND_BY_UNIT - add it there first"
            )

    def decorator(func: Callable) -> Callable:
        if name in REGISTRY and REGISTRY[name].func is not func:
            raise ValueError(f"Duplicate algorithm name {name!r} - already registered by {REGISTRY[name].func!r}")
        REGISTRY[name] = AlgorithmSpec(
            name=name,
            func=func,
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            params=_bind_params(name, func, tuple(inputs), tuple(params)),
            mode=mode,
            doc=(func.__doc__ or "").strip(),
            output_units=units,
        )
        return func

    return decorator


_discovered = False


def discover(force: bool = False) -> dict[str, AlgorithmSpec]:
    """Import every module in this package so its decorators run.

    Import failures are logged and skipped rather than raised: registry imports
    this purely to validate step config, and one algorithm module growing a
    dependency registry doesn't have shouldn't take the whole API down. The
    affected algorithms simply won't validate as known names, which surfaces
    as a clear 400 on the step that uses them.
    """
    global _discovered
    if _discovered and not force:
        return REGISTRY
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{module.name}")
        except Exception as e:
            log.warning("algorithm_module_import_failed", module=module.name, error=str(e))
    _discovered = True
    return REGISTRY


def get(function_name: str) -> AlgorithmSpec | None:
    discover()
    return REGISTRY.get(function_name)


def _unknown(function_name: str) -> list[str]:
    known = ", ".join(sorted(REGISTRY)) or "none registered"
    return [f"Unknown algorithm {function_name!r}. Available: {known}"]


def validate_step(
    function_name: str, inputs: dict | None, params: dict | None, outputs: dict | None = None
) -> list[str]:
    """Check a blueprint step against the algorithm's declaration.

    Returns human-readable errors, empty when valid. Calibration parameters
    are rejected here because they belong to each device, not to the recipe.
    """
    spec = get(function_name)
    if spec is None:
        return _unknown(function_name)

    errors = []
    given_inputs = set(inputs or {})
    expected_inputs = set(spec.inputs)
    if missing := expected_inputs - given_inputs:
        errors.append(f"{function_name!r} requires input(s) {sorted(missing)}")
    if extra := given_inputs - expected_inputs:
        errors.append(f"{function_name!r} does not accept input(s) {sorted(extra)}")

    given_params = set(params or {})
    config = {p.name: p for p in spec.config_params}
    calibration = {p.name for p in spec.calibration_params}
    if missing := {n for n, p in config.items() if p.required} - given_params:
        errors.append(f"{function_name!r} requires param(s) {sorted(missing)}")
    if misplaced := given_params & calibration:
        errors.append(
            f"{function_name!r} param(s) {sorted(misplaced)} are calibration parameters, set per device"
        )
    if extra := given_params - set(config) - calibration:
        errors.append(f"{function_name!r} does not accept param(s) {sorted(extra)}")

    if outputs is not None:
        if not outputs:
            errors.append(f"{function_name!r} step must bind at least one output")
        elif extra := set(outputs) - set(spec.outputs):
            errors.append(f"{function_name!r} has no output(s) {sorted(extra)}, only {list(spec.outputs)}")
    return errors


def validate_calibration(function_name: str, params: dict | None, *, complete: bool = True) -> list[str]:
    """Check one step's per-device calibration against the declaration.

    With `complete`, every required calibration parameter must be present,
    which is what enabling a postprocessing needs.
    """
    spec = get(function_name)
    if spec is None:
        return _unknown(function_name)

    errors = []
    given = set(params or {})
    calibration = {p.name: p for p in spec.calibration_params}
    config = {p.name for p in spec.config_params}
    if misplaced := given & config:
        errors.append(
            f"{function_name!r} param(s) {sorted(misplaced)} are configuration, set on the blueprint step"
        )
    if extra := given - set(calibration) - config:
        errors.append(f"{function_name!r} does not accept param(s) {sorted(extra)}")
    if complete and (missing := {n for n, p in calibration.items() if p.required} - given):
        errors.append(f"{function_name!r} requires calibration param(s) {sorted(missing)}")
    return errors
