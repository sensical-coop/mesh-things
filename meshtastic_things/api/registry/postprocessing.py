"""Device postprocessing: wiring blueprint versions to devices and publishing the result.

A blueprint version says what to compute from abstract input slots. A
`DevicePostprocessing` binds those slots to the device's own channels, carries
the device's calibration, and owns the derived `Measurement` rows its outputs
land in. What the stream job receives is the resolved form, one message per
device with every enabled plan in dependency order.
"""
import re

import structlog
from django.db.models import Prefetch, RestrictedError

from common.algorithms import POINTWISE, get as get_algorithm
from common.channels import DERIVED_KIND, channel_name
from common.postprocessing import Calibration, ResolvedPlan, ResolvedStep
from common.units import quantity_kind_for

from .kafka_publisher import get_publisher
from .models import (
    BlueprintVersion,
    Device,
    DevicePostprocessing,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    PostprocessingBlueprint,
    PostprocessingInputBinding,
    TelemetryVariant,
)

log = structlog.get_logger()

# Used when neither the postprocessing nor the device sets an interval.
DEFAULT_TOLERANCE_SECONDS = 30
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
PREFIX_PATTERN = re.compile(r"^[a-z0-9_]*$")
SLOT_REF = "slot:"
STEP_REF = "step:"


class PostprocessingError(Exception):
    """A change that would leave a postprocessing inconsistent."""

    def __init__(self, errors: list[str], conflict: bool = False):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.conflict = conflict


def validate_version(inputs: list[dict], steps: list[dict]) -> list[str]:
    """Check how a version's steps reference its slots and each other.

    Each step on its own is checked against its algorithm by the serializer;
    this covers what only makes sense across steps.
    """
    errors = []
    slots = [entry.get("slot") for entry in inputs]
    for slot in slots:
        if not isinstance(slot, str) or not NAME_PATTERN.match(slot):
            errors.append(f"Input slot {slot!r} must be lowercase letters, digits and underscores")
    if len(set(slots)) != len(slots):
        errors.append("Input slot names must be unique")

    keys, produced, fields, used_slots = set(), set(), set(), set()
    for step in sorted(steps, key=lambda s: s["order"]):
        key = step["key"]
        if not NAME_PATTERN.match(key):
            errors.append(f"Step key {key!r} must be lowercase letters, digits and underscores")
        if key in keys:
            errors.append(f"Step key {key!r} is used twice")
        spec = get_algorithm(step["function_name"])
        if spec is not None and spec.mode != POINTWISE:
            errors.append(f"Step {key!r}: {spec.name!r} is {spec.mode}, only pointwise algorithms can run")
        for arg, ref in (step.get("inputs") or {}).items():
            if isinstance(ref, str) and ref.startswith(SLOT_REF) and ref[len(SLOT_REF):] in slots:
                used_slots.add(ref[len(SLOT_REF):])
            elif isinstance(ref, str) and ref.startswith(STEP_REF) and ref[len(STEP_REF):] in produced:
                continue
            else:
                errors.append(
                    f"Step {key!r} input {arg!r} must be \"slot:<declared slot>\" or "
                    f"\"step:<earlier step key>.<output>\", got {ref!r}"
                )
        for output, field in (step.get("outputs") or {}).items():
            if not isinstance(field, str) or not NAME_PATTERN.match(field):
                errors.append(f"Step {key!r} output field {field!r} must be lowercase letters, digits and underscores")
            elif field in fields:
                errors.append(f"Output field {field!r} is produced twice")
            fields.add(field)
            produced.add(f"{key}.{output}")
        keys.add(key)
    if unused := [s for s in slots if s not in used_slots]:
        errors.append(f"Input slot(s) {unused} are not used by any step")
    return errors


def visible_blueprints(owner):
    """Blueprints the owner may read and attach: their own and public ones."""
    if owner.is_superuser:
        return PostprocessingBlueprint.objects.all()
    return PostprocessingBlueprint.objects.filter(owner_id=owner.id) | PostprocessingBlueprint.objects.filter(
        is_public=True
    )


def can_attach(owner, blueprint: PostprocessingBlueprint, device: Device) -> bool:
    """A device may run its mesh owner's blueprints and public ones."""
    return owner.is_superuser or blueprint.is_public or blueprint.owner_id == device.mesh.owner_id


def with_relations(queryset):
    """Everything resolving a postprocessing touches, in a fixed number of queries."""
    return queryset.select_related("device__mesh", "blueprint_version__blueprint").prefetch_related(
        "blueprint_version__steps",
        "calibrations",
        Prefetch(
            "input_bindings",
            queryset=PostprocessingInputBinding.objects.select_related(
                "measurement__measurement_type", "measurement__produced_by"
            ),
        ),
        Prefetch("outputs", queryset=Measurement.objects.select_related("measurement_type")),
    )


def tolerance_for(dp: DevicePostprocessing) -> float:
    if dp.tolerance_seconds:
        return float(dp.tolerance_seconds)
    if dp.device.reading_interval_seconds:
        return dp.device.reading_interval_seconds / 2
    return float(DEFAULT_TOLERANCE_SECONDS)


def measurement_channel(measurement: Measurement) -> str:
    return channel_name(measurement.measurement_type.payload_kind, measurement.measurement_type.field_name)


def derived_channel(field: str) -> str:
    return channel_name(DERIVED_KIND, field)


def slots_of(version: BlueprintVersion) -> list[str]:
    return [entry["slot"] for entry in version.inputs]


def output_fields(dp: DevicePostprocessing) -> dict[str, str]:
    """{"<step key>.<output>": derived field name on this device}."""
    return {
        f"{step.key}.{output}": f"{dp.output_prefix}{field}"
        for step in dp.blueprint_version.steps.all()
        for output, field in step.outputs.items()
    }


def build_plan(dp: DevicePostprocessing) -> ResolvedPlan:
    """The resolved form of one postprocessing. Unbound slots resolve to a
    placeholder channel, which nothing produces."""
    bound = {b.slot: measurement_channel(b.measurement) for b in dp.input_bindings.all()}
    fields = output_fields(dp)
    calibrations = list(dp.calibrations.all())
    steps = []
    for step in dp.blueprint_version.steps.all():
        inputs = {}
        for arg, ref in step.inputs.items():
            if ref.startswith(SLOT_REF):
                slot = ref[len(SLOT_REF):]
                inputs[arg] = bound.get(slot, f"unbound.{slot}")
            else:
                inputs[arg] = derived_channel(fields[ref[len(STEP_REF):]])
        steps.append(
            ResolvedStep(
                key=step.key,
                function_name=step.function_name,
                inputs=inputs,
                outputs={o: derived_channel(fields[f"{step.key}.{o}"]) for o in step.outputs},
                params=dict(step.params),
                calibrations=tuple(
                    Calibration(c.valid_from.timestamp(), dict(c.params))
                    for c in calibrations
                    if c.step_key == step.key and c.function_name == step.function_name
                ),
            )
        )
    return ResolvedPlan(
        id=str(dp.id),
        blueprint_id=str(dp.blueprint_version.blueprint_id),
        blueprint_version=dp.blueprint_version.number,
        tolerance_seconds=tolerance_for(dp),
        steps=tuple(steps),
    )


def problems(dp: DevicePostprocessing) -> list[str]:
    """What keeps this postprocessing from being enabled."""
    found = []
    bindings = list(dp.input_bindings.all())
    bound = {b.slot for b in bindings}
    for slot in slots_of(dp.blueprint_version):
        if slot not in bound:
            found.append(f"Input slot {slot!r} is not bound to a channel")
    calibrated = {(c.step_key, c.function_name) for c in dp.calibrations.all()}
    for step in dp.blueprint_version.steps.all():
        spec = get_algorithm(step.function_name)
        if spec is None:
            found.append(f"Step {step.key!r} uses {step.function_name!r}, which is no longer available")
            continue
        required = sorted(p.name for p in spec.calibration_params if p.required)
        if required and (step.key, step.function_name) not in calibrated:
            found.append(f"Step {step.key!r} needs a calibration setting {required}")
    for binding in bindings:
        producer = binding.measurement.produced_by
        if producer is not None and not producer.is_enabled:
            found.append(
                f"Input slot {binding.slot!r} reads {measurement_channel(binding.measurement)}, "
                f"which comes from a disabled postprocessing"
            )
    return found


def _device_measurement(device: Device, measurement_id) -> Measurement:
    try:
        return Measurement.objects.select_related("measurement_type", "produced_by").get(
            pk=measurement_id, device_telemetry_variant__device=device
        )
    except (Measurement.DoesNotExist, ValueError, TypeError):
        raise PostprocessingError([f"Measurement {measurement_id} is not a channel of this device"])


def _check_no_cycle(dp: DevicePostprocessing, bindings: dict[str, Measurement]) -> None:
    graph = {
        other.id: {b.measurement.produced_by_id for b in other.input_bindings.all() if b.measurement.produced_by_id}
        for other in DevicePostprocessing.objects.filter(device_id=dp.device_id).prefetch_related(
            "input_bindings__measurement"
        )
    }
    graph[dp.id] = {m.produced_by_id for m in bindings.values() if m.produced_by_id}
    stack, seen = list(graph[dp.id]), set()
    while stack:
        current = stack.pop()
        if current == dp.id:
            raise PostprocessingError(["These bindings would make this postprocessing depend on its own output"])
        if current not in seen:
            seen.add(current)
            stack.extend(graph.get(current, ()))


def set_bindings(dp: DevicePostprocessing, requested: dict, auto_bind: bool = True) -> None:
    """Apply {slot: measurement id or None} over the current bindings.

    Slots the version no longer declares are dropped. With `auto_bind`, a slot
    left unbound takes the device's channel named by its `default_channel`.
    """
    slots = slots_of(dp.blueprint_version)
    if unknown := sorted(set(requested) - set(slots)):
        raise PostprocessingError([f"Unknown input slot(s) {unknown}, this version declares {slots}"])

    bindings = {
        b.slot: b.measurement
        for b in dp.input_bindings.select_related("measurement__measurement_type", "measurement__produced_by")
        if b.slot in slots
    }
    for slot, measurement_id in requested.items():
        if measurement_id is None:
            bindings.pop(slot, None)
        else:
            bindings[slot] = _device_measurement(dp.device, measurement_id)

    if auto_bind:
        defaults = {e["slot"]: e.get("default_channel") for e in dp.blueprint_version.inputs}
        by_channel = {
            measurement_channel(m): m
            for m in Measurement.objects.filter(device_telemetry_variant__device=dp.device).select_related(
                "measurement_type", "produced_by"
            )
        }
        for slot in slots:
            if slot not in bindings and slot not in requested and defaults.get(slot) in by_channel:
                bindings[slot] = by_channel[defaults[slot]]

    for measurement in bindings.values():
        if measurement.produced_by_id == dp.id:
            raise PostprocessingError(["A postprocessing cannot read its own output"])
    _check_no_cycle(dp, bindings)

    dp.input_bindings.all().delete()
    PostprocessingInputBinding.objects.bulk_create(
        [PostprocessingInputBinding(device_postprocessing=dp, slot=s, measurement=m) for s, m in bindings.items()]
    )


def _derived_variant(device: Device) -> DeviceTelemetryVariant:
    variant, _ = TelemetryVariant.objects.get_or_create(payload_kind=DERIVED_KIND)
    dtv, _ = DeviceTelemetryVariant.objects.get_or_create(device=device, telemetry_variant=variant)
    return dtv


def sync_outputs(dp: DevicePostprocessing) -> list[Measurement]:
    """Create, adopt or remove the derived Measurement rows this postprocessing
    owns, and record their units. Returns the rows removed."""
    dp = with_relations(DevicePostprocessing.objects.filter(pk=dp.pk)).get()
    plan = build_plan(dp)
    input_units = {
        measurement_channel(b.measurement): b.measurement.measurement_type.native_unit for b in dp.input_bindings.all()
    }
    units = plan.resolve_output_units(input_units)
    wanted = set(output_fields(dp).values())
    dtv = _derived_variant(dp.device)

    errors = []
    for field in sorted(wanted):
        measurement_type, _ = MeasurementType.objects.get_or_create(payload_kind=DERIVED_KIND, field_name=field)
        unit = units.get(derived_channel(field))
        if unit and measurement_type.native_unit and measurement_type.native_unit != unit:
            errors.append(
                f"Output {field!r} would be in {unit}, but the catalog records {derived_channel(field)} "
                f"in {measurement_type.native_unit}. Set an output_prefix to give it another name"
            )
            continue
        if unit and not measurement_type.native_unit:
            measurement_type.native_unit = unit
            measurement_type.quantity_kind = measurement_type.quantity_kind or quantity_kind_for(unit)
            measurement_type.save(update_fields=["native_unit", "quantity_kind"])
        measurement, created = Measurement.objects.get_or_create(
            device_telemetry_variant=dtv, measurement_type=measurement_type, defaults={"produced_by": dp}
        )
        if created or measurement.produced_by_id == dp.id:
            continue
        if measurement.produced_by_id is None:
            measurement.produced_by = dp
            measurement.save(update_fields=["produced_by"])
        else:
            errors.append(
                f"Output {derived_channel(field)} is already produced on this device by another postprocessing. "
                f"Set an output_prefix to give it another name"
            )
    if errors:
        raise PostprocessingError(errors)

    stale = list(Measurement.objects.filter(produced_by=dp).exclude(measurement_type__field_name__in=wanted))
    delete_outputs(stale)
    return stale


def delete_outputs(measurements: list[Measurement]) -> None:
    """Delete derived rows, refusing while another postprocessing reads them."""
    if not measurements:
        return
    try:
        Measurement.objects.filter(pk__in=[m.pk for m in measurements]).delete()
    except RestrictedError as e:
        consumers = sorted({str(obj.device_postprocessing_id) for obj in e.restricted_objects})
        raise PostprocessingError(
            [f"Another postprocessing reads these outputs ({', '.join(consumers)}). Rebind or remove it first"],
            conflict=True,
        )


def device_plans(device: Device) -> list[ResolvedPlan]:
    """Every enabled plan on the device, each after the plans it reads from."""
    enabled = list(with_relations(DevicePostprocessing.objects.filter(device=device, is_enabled=True)))
    by_id = {dp.id: dp for dp in enabled}
    ordered, visiting, done = [], set(), set()

    def visit(dp):
        if dp.id in done or dp.id in visiting:
            return
        visiting.add(dp.id)
        for binding in dp.input_bindings.all():
            producer = by_id.get(binding.measurement.produced_by_id)
            if producer is not None:
                visit(producer)
        visiting.discard(dp.id)
        done.add(dp.id)
        ordered.append(dp)

    for dp in sorted(enabled, key=lambda d: d.created_at):
        visit(dp)
    return [build_plan(dp) for dp in ordered]


def publish_device(device: Device) -> None:
    """Send the device's current plans to the stream job. Raises on failure."""
    get_publisher().publish_postprocessing_plans(device, [plan.to_dict() for plan in device_plans(device)])


def unpublish_devices(devices) -> None:
    """Best-effort removal of plans for devices about to be deleted."""
    for device in devices:
        try:
            get_publisher().publish_postprocessing_plans(device, [])
        except Exception as e:
            log.warning("postprocessing_unpublish_failed", device_id=str(device.id), error=str(e))
