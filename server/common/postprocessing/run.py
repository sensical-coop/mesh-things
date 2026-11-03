"""Execute a device's resolved plans over incoming samples.

Every derived sample is fed back in as an ordinary observation, so a step can
consume an earlier step's output, and a plan another plan's output, exactly
like a raw channel. Registry rejects dependency cycles; the depth guard here
only keeps a malformed plan from looping forever.
"""
from dataclasses import dataclass, field

import structlog

from common.algorithms import POINTWISE, get as get_algorithm

from .joiner import StepJoin, new_state
from .plan import ResolvedPlan

log = structlog.get_logger()


@dataclass(frozen=True)
class Observation:
    channel: str
    # Epoch seconds.
    time: float
    value: float
    # The plan that produced it, None for a raw sample.
    plan_id: str | None = None


@dataclass
class RunResult:
    derived: list[Observation] = field(default_factory=list)
    # "<plan id>:<step key>" -> (rows skipped, first error message)
    failures: dict[str, tuple[int, str]] = field(default_factory=dict)

    def record_failure(self, plan: ResolvedPlan, step_key: str, error: str) -> None:
        key = f"{plan.id}:{step_key}"
        count, first = self.failures.get(key, (0, error))
        self.failures[key] = (count + 1, first)


def _plan_state(plan: ResolvedPlan, state: dict) -> dict:
    """This plan's join state, reset whenever the plan itself changed."""
    fingerprint = plan.fingerprint()
    current = state.get(plan.id)
    if current is None or current.get("fingerprint") != fingerprint:
        current = {"fingerprint": fingerprint, "steps": {}}
        state[plan.id] = current
    return current


def apply(plans: list[ResolvedPlan], state: dict, observations) -> RunResult:
    """Feed samples through every plan and return what they derive.

    Args:
        plans: One device's plans, in dependency order.
        state: The device's join state, keyed by plan id, mutated in place.
            State for plans no longer present is dropped.
        observations: Raw samples for that device.
    """
    for stale in set(state) - {plan.id for plan in plans}:
        del state[stale]
    plan_states = {plan.id: _plan_state(plan, state) for plan in plans}

    result = RunResult()
    max_depth = sum(len(plan.steps) for plan in plans) + 1
    queue = [(obs, 0) for obs in observations]
    while queue:
        obs, depth = queue.pop(0)
        if depth > max_depth:
            log.warning("postprocessing_depth_exceeded", channel=obs.channel, plan_id=obs.plan_id)
            continue
        for plan in plans:
            for step in plan.steps:
                if obs.channel not in step.inputs.values():
                    continue
                for derived in _run_step(plan, step, plan_states[plan.id], obs, result):
                    result.derived.append(derived)
                    queue.append((derived, depth + 1))
    return result


def _run_step(plan: ResolvedPlan, step, plan_state: dict, obs: Observation, result: RunResult):
    spec = get_algorithm(step.function_name)
    if spec is None or spec.mode != POINTWISE:
        result.record_failure(plan, step.key, f"{step.function_name!r} is unknown or not pointwise")
        return

    spec_inputs = [step.inputs[arg] for arg in spec.inputs]
    join = StepJoin(
        base=spec_inputs[0],
        others=tuple(spec_inputs[1:]),
        tolerance=plan.tolerance_seconds,
        state=plan_state["steps"].setdefault(step.key, new_state()),
    )
    for row in join.add(obs.channel, obs.time, obs.value):
        inputs = {arg: row[channel] for arg, channel in step.inputs.items()}
        try:
            values = spec.call(inputs, step.params_at(row["time"]))
        except Exception as e:
            result.record_failure(plan, step.key, f"{type(e).__name__}: {e}")
            continue
        for output_name, channel in step.outputs.items():
            value = values.get(output_name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                yield Observation(channel, row["time"], float(value), plan.id)
