"""The resolved form of one device postprocessing.

Registry resolves a device's attachment (blueprint version, input bindings,
calibration history) into a `ResolvedPlan` and publishes it; the stream job
and backfills only ever execute one. Everything here is concrete: channels,
not slots, and parameters already split into blueprint configuration and
per-device calibration.
"""
import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass, field

from common.algorithms import get as get_algorithm


@dataclass(frozen=True)
class Calibration:
    """Calibration parameters in force from `valid_from` (epoch seconds) onwards."""

    valid_from: float
    params: dict


@dataclass(frozen=True)
class ResolvedStep:
    key: str
    function_name: str
    # {algorithm input: channel}
    inputs: dict[str, str]
    # {algorithm output: channel}
    outputs: dict[str, str]
    # Blueprint configuration.
    params: dict = field(default_factory=dict)
    calibrations: tuple[Calibration, ...] = ()

    def __post_init__(self):
        ordered = tuple(sorted(self.calibrations, key=lambda c: c.valid_from))
        object.__setattr__(self, "calibrations", ordered)

    def params_at(self, time: float) -> dict:
        """Configuration merged with the calibration in force at `time`.

        A sample older than every calibration gets none, so the algorithm's
        signature defaults apply or it fails for a missing required value.
        """
        index = bisect_right([c.valid_from for c in self.calibrations], time) - 1
        if index < 0:
            return dict(self.params)
        return {**self.params, **self.calibrations[index].params}

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "function_name": self.function_name,
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "params": dict(self.params),
            "calibrations": [{"valid_from": c.valid_from, "params": dict(c.params)} for c in self.calibrations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedStep":
        calibrations = [
            Calibration(float(c["valid_from"]), dict(c.get("params") or {})) for c in data.get("calibrations") or []
        ]
        return cls(
            key=data["key"],
            function_name=data["function_name"],
            inputs=dict(data.get("inputs") or {}),
            outputs=dict(data.get("outputs") or {}),
            params=dict(data.get("params") or {}),
            calibrations=tuple(calibrations),
        )


@dataclass(frozen=True)
class ResolvedPlan:
    # The device postprocessing this plan executes.
    id: str
    blueprint_id: str
    blueprint_version: int
    # Two samples belong to the same row when they are at most this far apart.
    tolerance_seconds: float
    steps: tuple[ResolvedStep, ...]

    @property
    def input_channels(self) -> set[str]:
        """Channels the plan reads that none of its own steps produce."""
        produced = self.output_channels
        return {c for step in self.steps for c in step.inputs.values()} - produced

    @property
    def output_channels(self) -> set[str]:
        return {c for step in self.steps for c in step.outputs.values()}

    def fingerprint(self) -> str:
        """Changes whenever anything that affects a join changes, so stream
        state built for an older plan is discarded rather than reused."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def resolve_output_units(self, channel_units: dict[str, str | None]) -> dict[str, str | None]:
        """{output channel: unit}, chaining "@<input>" units through the steps
        in order. An unresolvable unit is None rather than a guess."""
        known = dict(channel_units)
        resolved: dict[str, str | None] = {}
        for step in self.steps:
            spec = get_algorithm(step.function_name)
            if spec is None:
                continue
            input_units = {arg: known.get(channel) for arg, channel in step.inputs.items()}
            for output_name, channel in step.outputs.items():
                unit = spec.unit_for(output_name, input_units)
                resolved[channel] = unit
                if unit:
                    known[channel] = unit
        return resolved

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "blueprint_id": self.blueprint_id,
            "blueprint_version": self.blueprint_version,
            "tolerance_seconds": self.tolerance_seconds,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedPlan":
        return cls(
            id=str(data["id"]),
            blueprint_id=str(data["blueprint_id"]),
            blueprint_version=int(data["blueprint_version"]),
            tolerance_seconds=float(data["tolerance_seconds"]),
            steps=tuple(ResolvedStep.from_dict(s) for s in data.get("steps") or []),
        )
