"""Registry of postprocessing algorithms, discovered by name.

A `PostprocessingStep` (registry) names one of these functions, binds its
`inputs` to channel names, and supplies `params` - see
docs/architecture.md#postprocessing-blueprints. Writing a new algorithm means
dropping a decorated function into a module in this package; nothing else
needs editing.

Same name-dispatch shape as common/calibration.py's CALIBRATION_FUNCTIONS and
common/detectors.py's DETECTORS, but with declared metadata (inputs/outputs/
params/mode) so registry can reject a misconfigured step at write time instead
of failing deep inside a worker hours later.

`mode` decides *where* an algorithm can run:
  - "pointwise": one aligned sample at a time, no history. Runnable by the
    batch executor row-by-row AND (once wired) by Flink per-point.
  - "windowed": needs a whole series (rolling baselines, drift, resampling).
    Batch only - a stream tier would have to buffer, which is what the batch
    tier is already for.
"""
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable

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


@dataclass(frozen=True)
class AlgorithmSpec:
    """What a step needs to know to call an algorithm without importing it."""

    name: str
    func: Callable
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()
    mode: str = POINTWISE
    doc: str = ""
    # {output_name: unit}, where a unit may be "@<input_name>" - see INHERIT.
    # Declared here because the algorithm is the only thing that knows: a
    # channel produced by a blueprint has no protobuf field to inherit a unit
    # from, so without this its catalog row is created bare and every consumer
    # downstream (readings' /latest decoration, any plot axis) has nothing to
    # label it with.
    output_units: dict[str, str] = field(default_factory=dict)

    def unit_for(self, output_name: str, input_units: dict[str, str | None]) -> str | None:
        """This output's unit, resolving an "@<input>" reference against the
        units of the channels actually bound to this step's inputs.

        Returns None when undeclared, or when an inherited unit can't be
        resolved because the upstream channel has no unit itself - unknown is
        recorded as unknown rather than guessed.
        """
        declared = self.output_units.get(output_name)
        if not declared:
            return None
        if declared.startswith(INHERIT):
            return input_units.get(declared[len(INHERIT):])
        return declared

    def call(self, inputs: dict, params: dict) -> dict:
        """Invoke with inputs+params as keyword args, normalising the return
        to {output_name: value}. A single-output algorithm may return a bare
        value instead of a dict - the common case, and not worth the ceremony."""
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
        """Serializable form - what GET /algorithms returns."""
        return {
            "name": self.name,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "params": list(self.params),
            "optional_params": list(self.optional_params),
            "mode": self.mode,
            "doc": self.doc,
            "output_units": dict(self.output_units),
        }


REGISTRY: dict[str, AlgorithmSpec] = {}


def algorithm(
    *,
    name: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    params: tuple[str, ...] = (),
    optional_params: tuple[str, ...] = (),
    mode: str = POINTWISE,
    output_units: dict[str, str] | None = None,
):
    """Register a function as a named, introspectable algorithm.

    inputs           - channel-bound arguments (a step maps each to a channel name)
    outputs          - names this produces (a step maps each to a derived channel name)
    params           - required scalar configuration
    optional_params  - configuration with a default in the function signature
    output_units     - {output: unit}, unit being a literal ("degC") or
                       "@<input>" for a unit-preserving algorithm
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"Algorithm {name!r}: mode must be one of {_VALID_MODES}, got {mode!r}")
    if not inputs:
        raise ValueError(f"Algorithm {name!r}: must declare at least one input")
    if not outputs:
        raise ValueError(f"Algorithm {name!r}: must declare at least one output")
    overlap = set(params) & set(optional_params)
    if overlap:
        raise ValueError(f"Algorithm {name!r}: {sorted(overlap)} declared both required and optional")

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
            params=tuple(params),
            optional_params=tuple(optional_params),
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


def validate_step(function_name: str, inputs: dict | None, params: dict | None) -> list[str]:
    """Check a step's config against the declared spec, returning human-readable
    errors (empty list = valid). Used by registry's serializer so bad config fails
    at write time - see PostprocessingStepSerializer."""
    spec = get(function_name)
    if spec is None:
        known = ", ".join(sorted(REGISTRY)) or "none registered"
        return [f"Unknown algorithm {function_name!r}. Available: {known}"]

    errors = []
    given_inputs = set(inputs or {})
    expected_inputs = set(spec.inputs)
    if missing := expected_inputs - given_inputs:
        errors.append(f"{function_name!r} requires input(s) {sorted(missing)}")
    if extra := given_inputs - expected_inputs:
        errors.append(f"{function_name!r} does not accept input(s) {sorted(extra)}")

    given_params = set(params or {})
    allowed_params = set(spec.params) | set(spec.optional_params)
    if missing := set(spec.params) - given_params:
        errors.append(f"{function_name!r} requires param(s) {sorted(missing)}")
    if extra := given_params - allowed_params:
        errors.append(f"{function_name!r} does not accept param(s) {sorted(extra)}")
    return errors
