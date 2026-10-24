# Generated from openapi.json by mesh_things.client._stubgen. Do not edit.
from typing import Any

class Algorithms:
    def list(self) -> Any:
        """List the functions available to postprocessing steps.

        Each entry declares the inputs it needs, the outputs it produces and the
        parameters it accepts.
        """

class DataDeletions:
    def list(self, *, mesh_id: str | None = None, status: str | None = None) -> Any:
        """List scheduled deletions of stored readings, newest first. Superusers only.

        A mesh's readings are scheduled for deletion when the mesh is deleted,
        moved off its source, or its source's terms lapse. They stay in place
        until `delete_after`, then are deleted from both the time-series store
        and the archive.

        Args:
            status: `pending`, the default, `cancelled`, `done`, or `all`.
            mesh_id: Restrict to one mesh.
        """

class Detectors:
    def list(self) -> Any:
        """List the alarm detectors and what each one needs to trigger.

        - `scope`: where a detector is switched on: `measurement` ones go in a
        channel's `enabled_detectors`, `device` ones in the device's own
        `absence_detection_enabled`.
        - `requires` is the config that must also be set before the
        detector can trigger in the first place.
        """

class Devices:
    def create(self, *, body: dict[str, Any]) -> Any:
        """Register a device on a mesh the caller owns.

        Registering a gateway authorizes its traffic to be decoded. A
        device can only move to another mesh once its current registration has
        been disallowed.
        """

    def delete(self, device_uuid: str) -> Any:
        """Delete a device registration.

        The device is deregistered from the decoder first, and the record is
        kept if that fails.
        """

    def get(self, device_uuid: str) -> Any:
        """Return one registered device.

        Rejected registrations are visible only to the mesh's owner.
        """

    def list(self, *, has_postprocessing: bool | None = None, is_allowed: bool | None = None, is_gateway: bool | None = None, mesh_id: str | None = None, telemetry_variant: str | None = None) -> Any:
        """List the devices the caller may read, or every device for a superuser.

        Alongside devices on their own meshes, this includes those on public
        meshes. Rejected registrations are shown only to the mesh's owner.

        Args:
            mesh_id: Restrict to devices on one mesh.
            is_gateway: Restrict to gateways, or to plain nodes when false.
            is_allowed: Restrict to allowed registrations, or to rejected ones
                when false.
            has_postprocessing: Restrict to devices with a postprocessing
                attached, or to those without one when false.
            telemetry_variant: Restrict by reported telemetry variants, as
                `has_any_of`, `has_all_of` or `has_none_of` followed by `:` and
                variant ids separated by `|`. Bare ids mean `has_any_of`.
        """

    def measurements_get(self, device_uuid: str, measurement_id: str) -> Any:
        """Return one of this device's measurement channels."""

    def measurements_list(self, device_uuid: str) -> Any:
        """List the measurement channels this device produces, measured and computed alike.

        Entries appear on their own as telemetry arrives. `enabled_detectors` is set by
        this device and may be null; `effective_detectors` is the result once
        the shared catalog default is applied.
        """

    def measurements_update(self, device_uuid: str, measurement_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Choose which detectors alarm on this channel, and the range they
        check against, for this device.

        Alarms are off until enabled. Sending `null` for enabled_detectors
        inherits whatever the shared catalog sets for the channel; sending an
        empty list silences it here regardless of that default. valid_min/
        valid_max have no catalog default: the range detector remains off
        until both are set here.

        Args:
            enabled_detectors: Detectors to run, or `null` to inherit.
            valid_min: Lower bound for the range detector. Must be provided together with valid_max.
            valid_max: Upper bound for the range detector. Must be provided together with valid_min.
        """

    def postprocessings_backfills_create(self, device_uuid: str, postprocessing_id: str, *, body: dict[str, Any]) -> Any:
        """Recompute a postprocessing's derived channels over stored history.

        Readings already stored between `start` and `stop` are run through the
        postprocessing with the calibration in force when each was taken, and
        the results replace any derived values stored for the same times.
        Backfilled values are stored and archived but never raise alarms. The
        request is queued and runs within about a minute; its progress is
        reported in `status`. The postprocessing must be runnable, although it
        does not need to be enabled.

        Args:
            start: Start of the range to recompute.
            stop: End of the range. Defaults to now. At most 90 days after `start`.
            include_dependants: Also recompute every enabled postprocessing that reads this one's outputs. Defaults
                to false.
        """

    def postprocessings_backfills_list(self, device_uuid: str, postprocessing_id: str) -> Any:
        """List the backfills requested for a postprocessing and how they went, oldest first."""

    def postprocessings_calibrations_create(self, device_uuid: str, postprocessing_id: str, *, body: dict[str, Any]) -> Any:
        """Record a calibration for one step, in force from `valid_from` onwards.

        History is kept: readings are processed with the calibration in force
        when they were taken, so recalibrating a sensor never rewrites the
        past. Every required calibration parameter of the step's algorithm
        must be given. Rolled back if the stream tier cannot be notified.

        Args:
            step_key: Step being calibrated.
            params: Calibration parameters of the step's algorithm.
            valid_from: When this calibration takes effect. Defaults to now.
        """

    def postprocessings_calibrations_delete(self, device_uuid: str, postprocessing_id: str, calibration_id: str) -> Any:
        """Delete a calibration recorded by mistake.

        Refused when it would leave an enabled postprocessing without a
        calibration it needs. To change a calibration from some point onwards,
        record a new one instead.
        """

    def postprocessings_calibrations_list(self, device_uuid: str, postprocessing_id: str) -> Any:
        """List the calibration history of a postprocessing, per step and oldest first."""

    def postprocessings_create(self, device_uuid: str, *, body: dict[str, Any] | None = None) -> Any:
        """Attach a blueprint to a device.

        Slots not given in `input_bindings` are bound to the device's channel
        named by their `default_channel` when it has one. The derived channels
        the blueprint produces are registered on the device straight away, so
        detectors and ranges can be configured on them before any data
        arrives. A postprocessing starts disabled unless `is_enabled` is set,
        and can only be enabled once every slot is bound and every step that
        needs one has a calibration. Changes are rolled back if the stream
        tier cannot be notified.

        Args:
            blueprint_id: Blueprint to attach, the caller's own or a public one. Required.
            blueprint_version: Version number. Defaults to the latest.
            input_bindings: {slot: measurement id of this device}.
            output_prefix: Prepended to every derived field name, so a blueprint can run twice on one device.
            tolerance_seconds: Maximum distance between samples joined into one row. Defaults to half the device's
                reading interval.
            is_enabled: Start running straight away. Defaults to false.
        """

    def postprocessings_delete(self, device_uuid: str, postprocessing_id: str) -> Any:
        """Detach a blueprint from a device.

        Its derived channels are removed from the device, while readings
        already stored remain queryable. Refused while another postprocessing
        on the device reads one of those channels.
        """

    def postprocessings_get(self, device_uuid: str, postprocessing_id: str) -> Any:
        """Return one blueprint attachment on a device."""

    def postprocessings_list(self, device_uuid: str) -> Any:
        """List the blueprints attached to a device, with their wiring, outputs and state.

        `problems` lists what keeps a postprocessing from being enabled, and is
        empty once it can run.
        """

    def postprocessings_update(self, device_uuid: str, postprocessing_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Rewire, move to another version, or enable or disable a postprocessing.

        Moving to another version keeps bindings for slots it still declares
        and calibrations for steps with the same key and algorithm. Derived
        channels the new wiring no longer produces are removed from the device,
        which is refused while another postprocessing reads them. Changes are
        rolled back if the stream tier cannot be notified.

        Args:
            blueprint_version: Version number of the same blueprint.
            input_bindings: {slot: measurement id of this device}. Null unbinds a slot. Slots not given keep
                their binding.
            output_prefix: Prepended to every derived field name.
            tolerance_seconds: Maximum distance between samples joined into one row. Null uses half the device's
                reading interval.
            is_enabled: Run or stop the postprocessing.
        """

    def telemetry_variants_list(self, device_uuid: str) -> Any:
        """List the telemetry types this device has been seen reporting.

        Entries appear on their own as telemetry arrives and cannot be edited here.
        """

    def update(self, device_uuid: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a registered device.

        Position and identity fields are filled in from what the device reports
        until they are set here, after which the values given take precedence.
        Disallowing a gateway stops its traffic being decoded.

        `archive_enabled` stores the device's readings in the Parquet archive from
        then on. It is accepted only on a mesh owned by an operator and on
        instances that run the archive. Turning it off stops storing new readings
        and keeps those already stored.

        Nothing in the request is applied if the pipeline cannot be told about a
        change to `archive_enabled` or `is_allowed`.
        """

class Health:
    def get(self) -> Any:
        """Report whether the service and its database are reachable."""

class Measurements:
    def create(self, *, body: dict[str, Any]) -> Any:
        """Add a measurement type to the shared catalog. Superusers only."""

    def delete(self, measurement_id: str) -> Any:
        """Remove a measurement type from the catalog. Superusers only."""

    def get(self, measurement_id: str) -> Any:
        """Return one measurement type."""

    def list(self, *, field_name: str | None = None, kind: str | None = None, payload_kind: str | None = None) -> Any:
        """List the shared catalog of measurement types and their units.

        Sensor fields are named `telemetry:<variant>`. Blueprint outputs from
        every postprocessing share `computed:derived`, and data quality metrics
        use `computed:quality`.

        Args:
            kind: Restrict to one namespace, one of `telemetry`, `device` or
                `computed`.
            payload_kind: Restrict to one exact payload kind, such as
                `telemetry:environment_metrics`.
            field_name: Restrict to one field name, such as `temperature`.
        """

    def update(self, measurement_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a measurement type. Its payload kind and field name are fixed. Superusers only."""

class Meshes:
    def create(self, *, body: dict[str, Any]) -> Any:
        """Create a mesh owned by the caller.

        A mesh on the default broker needs its mesh terms accepted, which are
        recorded with it. A mesh on a source is covered by the source's terms.

        Args:
            source_id: Source the mesh's traffic is bridged from, which must be
                one the caller created, or any source for a superuser. Leave
                unset for traffic on this instance's own broker.
            discover_gateways: Register gateways automatically once one of their
                packets decodes with this mesh's channel and pre-shared key.
                Defaults to `false`. Only an operator may switch it on for a mesh
                with a default or blank key.
            terms_version: The `version` of the mesh terms accepted. Required
                without a source, ignored with one, and ignored on an instance
                that does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def delete(self, mesh_id: str) -> Any:
        """Delete a mesh and every device registered on it.

        Its gateways are deregistered from the decoder first, and nothing is
        removed if that fails. The mesh's stored readings are deleted after the
        grace period, so export them first if they are needed.
        """

    def devices_list(self, mesh_id: str, *, telemetry_variant: str | None = None) -> Any:
        """List every device registered on this mesh, gateways and nodes alike.

        A public mesh's devices are readable without credentials. Rejected
        registrations and admin keys are shown only to the mesh's owner.

        Args:
            telemetry_variant: Restrict by reported telemetry variants, as
                `has_any_of`, `has_all_of` or `has_none_of` followed by `:` and
                variant ids separated by `|`. Bare ids mean `has_any_of`.
        """

    def get(self, mesh_id: str) -> Any:
        """Return one mesh.

        A public mesh is readable without credentials. The pre-shared key, the
        source and the terms status are included only for the mesh's owner.
        """

    def links_list(self, mesh_id: str, *, node_id: int | str | None = None, since: str | None = None) -> Any:
        """List the radio links heard on this mesh, longest first.

        A link is one node heard by another, as one source reports it:
        `traceroute` hops, `neighborinfo` reports, or `direct` receptions by a
        gateway with no hop in between. Each is directional, since the SNR is
        measured by the receiving node, so a pair heard both ways has two links.
        Direct links are added once an hour. Links not heard for 30 days are
        deleted. A public mesh's links are readable without credentials.

        Args:
            since: How far back a link must have been heard, one of `24h`, `7d`
                or `30d`. Defaults to `7d`.
            node_id: Only links to or from this node.
        """

    def list(self, *, owned: bool | None = None, source_id: str | None = None) -> Any:
        """List the meshes the caller may read, or every mesh for a superuser.

        Alongside their own, this includes public meshes. Without credentials,
        only public meshes are listed. The pre-shared key, the source and the
        terms status are included only for meshes the caller owns.

        Args:
            owned: Restrict to meshes the caller owns. Defaults to false.
            source_id: Restrict to meshes bridged from one source. Matches
                only meshes the caller owns, or any mesh for a superuser.
        """

    def terms_acceptance_create(self, mesh_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current mesh terms again, renewing the mesh. Its owner only.

        With a retention period configured, an acceptance lapses after that
        period and the mesh is paused: its gateways are deregistered and its
        readings are scheduled for deletion. Renewing resumes it and cancels the
        deletion, as long as the grace period has not ended. A mesh on a source
        is covered by the source's terms and answers `409`. Answers `404` on an
        instance that does not enforce terms.

        Args:
            terms_version: The `version` of the mesh terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def terms_get(self, *, locale: str | None = None) -> Any:
        """Return the terms an owner accepts to create a mesh on the default broker.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the mesh, or when moving a mesh from a
        source onto the default broker. The footnote states how long the mesh's
        data is kept. Answers `404` on an instance that does not enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

    def traceroutes_list(self, mesh_id: str, *, before: str | None = None, limit: int | None = None, node_id: int | str | None = None) -> Any:
        """List the traceroutes heard on this mesh, newest first.

        A traceroute heard by several gateways is listed once, with the most
        complete route any of them saw. `towards` runs from the node that started
        the traceroute to its target and `back` returns; each SNR is the one
        measured on arriving at the next node. A reply carries both directions,
        a request only the hops taken so far. Traceroutes are kept 30 days. A
        public mesh's traceroutes are readable without credentials.

        Args:
            limit: How many to return, up to 500. Defaults to 50.
            before: Only traceroutes heard before this time, as an ISO 8601
                timestamp. Pass the `heard_at` of the last one received to read
                the next page.
            node_id: Only traceroutes from, to or through this node.
        """

    def update(self, mesh_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a mesh.

        Changing the channel_id, the pre-shared key or the source redistributes
        them to every allowed gateway on the mesh, and the whole update is
        rolled back if that fails. Once the source changes, the mesh's gateways
        are only accepted through the new one.

        Args:
            source_id: Source to bridge the mesh's traffic from, which must be one
                the caller created, or any source for a superuser, and not paused.
                Null moves it to the default broker. Moving a mesh off a source
                schedules the readings stored until then for deletion after the
                grace period; moving it back within that period cancels it.
            discover_gateways: Register gateways automatically once one of their
                packets decodes with this mesh's channel and pre-shared key. A
                gateway is skipped when another mesh shares the same source,
                channel and key, when it is registered elsewhere, or when it was
                rejected on this mesh. Switching it off keeps the gateways
                already found. Only an operator may switch it on for a mesh with
                a default or blank key.
            terms_version: The `version` of the mesh terms accepted. Required when
                moving the mesh onto the default broker unless it already holds a
                current acceptance, or the instance does not enforce terms;
                ignored otherwise.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

class Metrics:
    def get(self) -> Any:
        """Return totals for registered owners, meshes, devices and active gateways."""

class OperatorRequests:
    def get(self, request_id: str) -> Any:
        """Return one operator request. Superusers only."""

    def list(self, *, status: str | None = None) -> Any:
        """List operator requests, newest first. Superusers only.

        Args:
            status: `pending`, the default, `approved`, `rejected`, or `all`.
        """

    def update(self, request_id: str, *, body: dict[str, Any]) -> Any:
        """Approve or reject a pending operator request. Superusers only.

        Approving makes the requester an operator. The requester is emailed
        the decision, and the decision stands even if that email fails.

        Args:
            decision: `approve` or `reject`. Required.
            note: Message to the requester, included in the email. Optional.
        """

class Owners:
    def create(self, *, body: dict[str, Any]) -> Any:
        """Register an owner, sign it in and return its API key.

        Signing up accepts the current account terms, which are recorded. The
        key is for scripts and is shown in this response only; it cannot be
        retrieved again afterwards. A browser uses the session cookie set by
        this response instead. A new owner stays inactive until its email
        address is verified, and until then can only reach its own account.

        Args:
            terms_version: The `version` of the account terms accepted, as
                served by the terms endpoint. Required, and refused once the
                terms have changed, unless the instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def csrf_cookie_get(self) -> Any:
        """Set the CSRF cookie a browser client needs before logging in."""

    def delete(self, owner_id: str) -> Any:
        """Remove an owner, along with their meshes, devices, blueprints and sinks. Superusers only.

        Their gateways are deregistered from the decoder and the credentials of
        their sinks revoked first, and nothing is removed if that fails.
        Blueprints other owners' devices still use are kept without an owner,
        editable by superusers only.
        """

    def get(self, owner_id: str) -> Any:
        """Return one owner.

        The full record comes back when the caller is the owner being requested, or
        a superuser. Everyone else gets the public fields only.
        """

    def list(self) -> Any:
        """List registered owners.

        A superuser sees the full record for every owner. Everyone else,
        including an authenticated owner reading their own row, gets the public
        fields only, so that the rows are all the same shape. Use the profile
        route to read your own record in full.
        """

    def login_create(self, *, body: dict[str, Any]) -> Any:
        """Sign in with email and password, returning the owner profile and a session cookie.

        An owner whose email is not verified yet is signed in too, with `is_active`
        false in the profile, and can only reach its own account until it verifies.
        Attempts are limited per email and source address; once the limit is
        reached even the correct password is refused with `429` for about a minute.
        """

    def logout_create(self) -> Any:
        """End the current session."""

    def me_change_password_create(self, *, body: dict[str, Any]) -> Any:
        """Change the authenticated owner's password, confirming the current one first."""

    def me_delete(self) -> Any:
        """Delete the authenticated owner, along with their meshes, devices, blueprints and sinks.

        Their gateways are deregistered from the decoder and the credentials of
        their sinks revoked first, and nothing is removed if that fails.
        Blueprints other owners' devices still use are kept without an owner,
        editable by superusers only.
        """

    def me_devices_get(self) -> Any:
        """List the devices the authenticated owner may access."""

    def me_get(self) -> Any:
        """Return the authenticated owner's own record, including their devices."""

    def me_operator_request_create(self, *, body: dict[str, Any]) -> Any:
        """Ask for the operator role, which lets an owner create sources.

        Every superuser is emailed and one of them approves or rejects the
        request. Only one request can be pending at a time, and an owner who
        is already an operator cannot file one. Limited to 3 requests a day.

        Args:
            reason: Why the role is needed. Shown to superusers. Required.
        """

    def me_operator_request_get(self) -> Any:
        """Return the caller's most recent operator request and its status."""

    def me_resend_verification_create(self) -> Any:
        """Send a fresh verification email to the authenticated owner."""

    def me_rotate_key_create(self) -> Any:
        """Issue a new API key and revoke the previous one immediately.

        The new key is shown in this response and cannot be retrieved again.
        """

    def me_terms_acceptance_create(self, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current account terms, when they have changed since signing up.

        Account terms never lapse, so this pauses and resumes nothing. Answers
        `404` on an instance that does not enforce terms.

        Args:
            terms_version: The `version` of the account terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def me_update(self, *, body: dict[str, Any] | None = None) -> Any:
        """Update the authenticated owner's name, email address, or email preferences.

        Changing the email address deactivates the account until the new one
        is verified, and sends a fresh verification email.

        Args:
            alarm_email_cooldown_seconds: Length of a device's alarm window,
                in seconds. The first alarm on a device is emailed straight
                away; any further alarms on that device during the window are
                sent as one summary when it ends. Accepts 0 (email on every
                alarm, no summaries) up to 2592000 (30 days). Leave unset or
                null to use the server default.
            status_alerts_enabled: Email me when a source I created stays
                disconnected, or a sink I created with meshes or devices
                attached has nobody connected. Defaults to false.
            source_rate_alerts_enabled: Email me when a source I created
                averages more messages per second over an hour than this
                instance allows. Defaults to false. Superusers are always
                emailed about busy sources.
        """

    def request_password_reset_create(self, *, body: dict[str, Any]) -> Any:
        """Email a password reset link.

        The response is the same whether or not the address is registered, so it
        cannot be used to discover accounts.
        """

    def reset_password_create(self, *, body: dict[str, Any]) -> Any:
        """Set a new password using the token from the password reset link.

        The token works once and expires after one hour by default. An invalid or
        expired token is refused with `400`; request a new link to try again.

        Args:
            token: The token from the password reset link. Required.
            new_password: The new password. Required.
        """

    def update(self, owner_id: str, *, body: dict[str, Any]) -> Any:
        """Change an owner's role. Superusers only.

        Args:
            role: `member`, the default, or `operator`, which may also manage
                sources and archive devices. Granting `operator` also approves any
                pending operator request from this owner, without emailing them.
                Taking it away stops archiving the owner's devices, and the role
                is kept if the pipeline cannot be told.
        """

    def verify_email_get(self, *, token: str) -> Any:
        """Confirm an owner's email address using the token from the verification link."""

class PostprocessingBackfills:
    def claim_create(self, backfill_id: str) -> Any:
        """Claim a pending backfill for processing and return everything needed to run it. Superusers only.

        Only one caller can claim a backfill. A backfill left running for over
        an hour is presumed abandoned and can be claimed again.
        """

    def list(self, *, status: str | None = None) -> Any:
        """List backfills across every device, oldest first. Superusers only.

        Args:
            status: Restrict to one status, such as `pending`.
        """

    def update(self, backfill_id: str, *, body: dict[str, Any]) -> Any:
        """Record how a claimed backfill finished. Superusers only.

        Args:
            status: `done` or `failed`.
            points_published: Derived values published.
            error: Why it failed.
        """

class PostprocessingBlueprints:
    def create(self, *, body: dict[str, Any]) -> Any:
        """Create a postprocessing blueprint together with its first version.

        A version declares the input slots it reads and an ordered list of
        steps. Each step runs one algorithm, takes its inputs from a slot or
        from an earlier step's output, and names the derived channels its
        outputs are stored as. Calibration parameters are not set here: each
        device supplies its own when the blueprint is attached to it.

        Args:
            name: Unique among the caller's blueprints.
            description: Free text.
            is_public: Lets any owner attach the blueprint to their devices. Defaults to false.
            inputs: Input slots, each with an optional `default_channel`.
            steps: Steps, each with a `key` that stays the same across versions.
            notes: Free text describing this version.
        """

    def delete(self, blueprint_id: str) -> Any:
        """Delete a blueprint and all of its versions.

        Refused while any device still uses one of its versions.
        """

    def get(self, blueprint_id: str) -> Any:
        """Return one postprocessing blueprint and its latest version."""

    def list(self, *, owned: bool | None = None) -> Any:
        """List the postprocessing blueprints the caller may use: their own and public ones.

        A superuser sees every blueprint.

        Args:
            owned: Restrict to the caller's own blueprints, excluding public ones.
        """

    def update(self, blueprint_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Rename or describe a blueprint, or change whether it is public.

        Steps cannot be changed here: create a new version instead. Making a
        blueprint private does not detach it from devices already using it.
        """

    def versions_create(self, blueprint_id: str, *, body: dict[str, Any]) -> Any:
        """Add a version of a blueprint.

        Versions are immutable, so this is how a blueprint's steps change.
        Devices keep running the version they use until they are moved to the
        new one. Keeping a step's `key` and algorithm lets a device keep its
        calibration when it moves.

        Args:
            inputs: Input slots, each with an optional `default_channel`.
            steps: Steps, each with a `key` that stays the same across versions.
            notes: Free text describing what changed.
        """

    def versions_get(self, blueprint_id: str, number: int) -> Any:
        """Return one version of a blueprint and its steps."""

    def versions_list(self, blueprint_id: str) -> Any:
        """List every version of a blueprint, oldest first."""

class Readings:
    def archive_meshes_credentials_create(self, mesh_id: str) -> Any:
        """Issue temporary S3 credentials that can read this mesh's archive and nothing else.

        Use them with DuckDB, pandas or any S3 client to query the archive as a
        partitioned dataset. The secret is shown in this response only. The
        credentials cannot be revoked and stay valid until `expires_at`, even if
        the caller loses access to the mesh in the meantime. Available to the
        mesh's owner while they are an operator, and to superusers.
        """

    def archive_meshes_get(self, mesh_id: str, *, start: str | None = None, stop: str | None = None) -> Any:
        """List the hourly Parquet files archived for a mesh, oldest first.

        Only devices whose archive is switched on are stored, from the moment it
        was switched on, so the list stays empty until one of them reports.
        Available to the mesh's owner while they are an operator, and to
        superusers.

        Args:
            start: Earliest day to include, as `YYYY-MM-DD`. Defaults to the first archived day.
            stop: Latest day to include, as `YYYY-MM-DD`. Defaults to the last archived day.
        """

    def archive_meshes_partitions_get(self, mesh_id: str, day: str, hour: int) -> Any:
        """Download one hour of a mesh's archive as a Parquet file.

        Answers with a redirect to a temporary link, valid for the same time as
        issued credentials, that any HTTP client can follow. The file does not
        carry `mesh_id` as a column. Available to the mesh's owner while they are
        an operator, and to superusers.
        """

    def devices_get(self, device_uuid: str, *, agg: str | None = None, channel: str | None = None, payload_kind: str | None = None, start: str | None = None, stop: str | None = None, window: str | None = None) -> Any:
        """Readings over a time range, addressed by the device's registration ID."""

    def devices_latest_get(self, device_uuid: str, *, lookback: str | None = None, payload_kind: str | None = None) -> Any:
        """Most recent readings, addressed by the device's registration ID.

        A device on a public mesh is readable without credentials. Rejected
        registrations are not.
        """

    def devices_quality_get(self, device_uuid: str, *, start: str | None = None, stop: str | None = None) -> Any:
        """Data-quality figures for a device, addressed by its registration ID."""

    def devices_traffic_get(self, device_uuid: str, *, range: str | None = None) -> Any:
        """A device's packets over a fixed range, addressed by its registration ID."""

    def exports_list(self) -> Any:
        """List the caller's exports of every mesh from the last 30 days, newest first.

        A ready export becomes `expired` 24 hours after it finished, when its file
        is deleted; request it again to rebuild it. Empty on an instance without
        object storage.
        """

    def meshes_exports_create(self, mesh_id: str, *, body: dict[str, Any]) -> Any:
        """Request a download of a mesh's readings over a range of days, as one zip.

        The zip is built in the background: poll the export until its status is
        `ready`, then download it from `url`. The owner is also emailed when it is
        ready or has failed. A CSV export reads every stored reading, a file per
        measurement and day with a column per field, plus `channels.csv` with each
        channel's unit. A Parquet export holds the hourly archive files, only for
        devices whose archive is on. Each owner has one export queued or running at a
        time, and repeating that same request returns it. Available to the mesh's
        owner and to superusers; Parquet also needs the operator role.

        Args:
            format: `csv` or `parquet`. Required.
            start: First day, as `YYYY-MM-DD` in UTC. Required.
            stop: Last day, included, as `YYYY-MM-DD` in UTC. Required. At most a year after `start`.
            node_ids: Node numbers to limit a CSV export to. Defaults to every device of the mesh.
        """

    def meshes_exports_get(self, mesh_id: str, export_id: str) -> Any:
        """Return one of the caller's exports: its status, progress in days and, once ready, a download link.

        The link is valid until `expires_at`, 24 hours after the export finished,
        and works for anyone who has it. The status then becomes `expired`.
        """

    def meshes_exports_list(self, mesh_id: str) -> Any:
        """List the caller's exports of a mesh from the last 30 days, newest first.

        A ready export becomes `expired` 24 hours after it finished, when its file
        is deleted. Available to the mesh's owner and to superusers.
        """

    def meshes_nodes_get(self, mesh_id: str, node_id: int | str, *, agg: str | None = None, channel: str | None = None, payload_kind: str | None = None, start: str | None = None, stop: str | None = None, window: str | None = None) -> Any:
        """Return a device's readings for one measurement over a time range.

        Downsampling covers numeric fields only, so text fields such as
        `timestamp_quality` are left out whenever `window` is set.

        Args:
            payload_kind: Family to read, for example `telemetry:environment_metrics`.
                Returns every channel in it. Required unless `channel` is given.
            channel: A single channel, for example `environment_metrics.temperature`.
                Takes precedence over `payload_kind`.
            start: Start of the range, as a relative duration such as `-24h`, a date
                such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
                Defaults to `-1h`.
            stop: End of the range, in the same forms as `start`, or `now()`.
                Defaults to `now()`.
            window: Bucket size to downsample into, for example `6h`. Off by default.
            agg: Aggregate applied to each bucket, one of `mean`, `max`, `min`,
                `last`, `first`, `sum` or `count`. Defaults to `mean` and applies
                only when `window` is set.
        """

    def meshes_nodes_latest_get(self, mesh_id: str, node_id: int | str, *, lookback: str | None = None, payload_kind: str | None = None) -> Any:
        """Return a device's most recent readings.

        Without `payload_kind`, every channel the device has reported comes back in
        one call, each annotated with its unit from the measurement catalog. A
        device on a public mesh is readable without credentials.

        Args:
            payload_kind: Restrict to one family, for example
                `telemetry:environment_metrics`. Defaults to every one.
            lookback: How far back to search for a value, as a relative duration, a
                date or a timestamp. Defaults to `-30d`.
        """

    def meshes_nodes_quality_get(self, mesh_id: str, node_id: int | str, *, start: str | None = None, stop: str | None = None) -> Any:
        """Return data-quality figures for a device over a time range.

        Covers the number of readings recorded, alarms raised per detector, the
        share of the hours the device reported in that stayed within its
        configured ranges, and how complete each channel was. Figures stay empty
        until the quality checks have run for the device.

        Alarms are kept one by one for 30 days. A range reaching further back is
        answered from daily counts, so it is rounded to whole days and does not
        include the current day.

        Args:
            start: Start of the range, as a relative duration such as `-24h`, a date
                such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
                Defaults to `-1h`.
            stop: End of the range, in the same forms as `start`, or `now()`.
                Defaults to `now()`.
        """

    def meshes_nodes_traffic_get(self, mesh_id: str, node_id: int | str, *, range: str | None = None) -> Any:
        """Return how much a node transmitted over a fixed range, and of which kinds of packet.

        Counts every packet the mesh's gateways heard from the node, including ones
        that could not be decrypted (`portnum` null). Kept per hour, so the range
        starts at `hourly_start`, the whole hour on or before its start. A device on
        a public mesh is readable without credentials.

        Args:
            range: Period to cover, ending now. One of `1h`, `24h`, `7d` or `30d`.
                Defaults to `24h`.
        """

    def meshes_stats_get(self, mesh_id: str, *, range: str | None = None) -> Any:
        """Return traffic and congestion figures for a mesh over a fixed range.

        Counts every packet the mesh's registered gateways hear, including text
        messages, routing traffic and packets that could not be decrypted. A packet
        heard by several gateways is one packet and several receptions. Packets from
        nodes the owner rejected count towards the totals but are never listed as
        nodes. Channel utilization and airtime are the figures the nodes report
        about themselves.

        Busiest nodes, gateways, hops, signal, gateway pairs, relays and activity
        are kept per hour, so they start at `hourly_start`, the whole hour on or
        before the start of the range. Figures from the last few minutes are still
        being counted and may grow.

        Gateway pairs compare gateways that heard the same packets. Relays say which
        nodes passed packets on to each gateway; the firmware reports only the last
        byte of a relay's node number, so each comes with the registered nodes it
        could be.

        Results are computed at most once a minute per mesh and range, so a repeated
        call within that minute returns the same figures. A public mesh is readable
        without credentials.

        Args:
            range: Period to cover, ending now. One of `1h`, `24h`, `7d` or `30d`.
                Defaults to `24h`.
        """

class Sinks:
    def create(self, *, body: dict[str, Any] | None = None) -> Any:
        """Create a sink and return the credentials its consumer subscribes with. Operators only.

        The consumer connects to `broker` over TLS as `username` with the returned
        password and subscribes under `topic_filter`, where each message is one
        reading or alarm as JSON. The password is shown in this response only.
        The caller must first accept the current sink terms. Nothing is kept if
        the broker or the pipeline cannot be set up, or if the broker does not
        yet keep sink topics private.

        Args:
            label: Name for the sink.
            streams: Which readings are sent: `decoded`, `derived` and `alarms`.
                Defaults to `decoded`. Derived readings are sent only by
                instances that run postprocessing, and alarms only by those that
                run quality checks.
            mesh_ids: Meshes whose every node is sent, including nodes that
                appear later. Each must be one the caller may edit, owned by an
                operator.
            device_ids: Registrations of single devices to send, under the same
                conditions.
            terms_version: The `version` of the sink terms the caller accepted.
                Required unless the instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def credentials_create(self, sink_id: str) -> Any:
        """Replace a sink's password and disconnect its consumers. Operators only, on the sinks they created.

        The new password is shown in this response only. The old one is kept if
        the broker cannot be told.
        """

    def delete(self, sink_id: str) -> Any:
        """Delete a sink, revoke its credentials and disconnect its consumers. Operators only.

        A sink with meshes or devices attached cannot be deleted. Nothing is
        removed if the broker cannot be told. Its terms acceptances are kept.
        """

    def get(self, sink_id: str) -> Any:
        """Return one sink and how many consumers are connected to it. Operators only.

        An operator can read only the sinks they created; a superuser can read
        any. The password is never included.
        """

    def list(self) -> Any:
        """List the sinks the caller created, or every sink for a superuser. Operators only.

        Each carries how many consumers are connected, null for all of them when
        the broker cannot be asked. Passwords are never included.
        """

    def terms_acceptance_create(self, sink_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current sink terms again, renewing the sink. Only the operator who created it.

        With a retention period configured, an acceptance lapses after that
        period and the sink is paused: nothing is sent and its consumers are
        refused. Renewing a paused sink resumes it with the same credentials.
        Answers `404` on an instance that does not enforce terms.

        Args:
            terms_version: The `version` of the sink terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def terms_get(self, *, locale: str | None = None) -> Any:
        """Return the terms an operator must accept to create a sink. Operators only.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the sink. Answers `404` on an instance that
        does not enforce terms or has no sinks.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

    def update(self, sink_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a sink. Operators only, on the sinks they created.

        Any subset of the create fields may be sent, except the terms. A list
        sent replaces the current one, so an empty `mesh_ids` detaches every
        mesh. Changes the pipeline cannot be told about are rolled back.
        """

class Sources:
    def create(self, *, body: dict[str, Any]) -> Any:
        """Create a source and start bridging its remote topic into this instance. Operators only.

        The caller must first accept the current source terms. The acceptance
        is recorded with the source. Nothing is kept if the bridge cannot be set
        up.

        Args:
            server: Remote broker as `host:port`. Cannot be this instance's own
                broker or one the server has blocked.
            ssl: Connect to the remote broker over TLS. Defaults to true.
            username: Remote broker username, if it requires one.
            password: Remote broker password. Accepted but never returned.
            topic: Remote topic filter, for example `msh/EU_868/2/e/MyChannel/#`.
                `$share`, `$SYS` and filters the server has blocked, such as `#`,
                are rejected.
            qos: 0 or 1. Defaults to 1.
            terms_version: The `version` of the source terms the caller accepted.
                Required, and refused once the terms have changed, unless the
                instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def delete(self, source_id: str) -> Any:
        """Delete a source and stop bridging it. Operators only, on the sources they created.

        A source with meshes attached cannot be deleted. Nothing is removed if
        the bridge cannot be torn down. Its terms acceptances are kept.
        """

    def get(self, source_id: str) -> Any:
        """Return one source and the live status of its bridge. Operators only.

        An operator can read only the sources they created; a superuser can read
        any. The status is `unknown` when the broker cannot be reached to check
        it, and `paused` once its terms have lapsed.
        """

    def list(self) -> Any:
        """List the sources the caller created, or every source for a superuser. Operators only.

        Each carries its bridge's status, `unknown` for all of them when the
        broker cannot be asked. Remote passwords are never included.
        """

    def terms_acceptance_create(self, source_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current source terms again, renewing the source. Only the operator who created it.

        With a retention period configured, an acceptance lapses after that
        period and the source is paused. Renewing a paused source restarts its
        bridge and cancels the deletion of its meshes' data, as long as the
        grace period has not ended. Answers `404` on an instance that does not
        enforce terms.

        Args:
            terms_version: The `version` of the source terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    def terms_get(self, *, locale: str | None = None) -> Any:
        """Return the terms an operator must accept to add a source. Operators only.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the source. The footnote states how long
        the source's data is kept. Answers `404` on an instance that does not
        enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

    def update(self, source_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a source and reconfigure its bridge. Operators only, on the sources they created.

        Any subset of the create fields may be sent. The update is rolled back
        if the bridge cannot be reconfigured. A paused source is updated
        without touching the broker. Send an empty `password` to remove it.
        """

class Status:
    def email_get(self) -> Any:
        """Report whether the instance's emails are being accepted by its mail server. Superusers only.

        Covers every email registry sends: alarms and their summaries, sign up,
        password resets, terms and status notices. `ok` is false while the most
        recent one failed to send, and turns true again with the next success.
        It says nothing about delivery beyond the mail server, such as spam
        filtering. Counts cover the last 24 hours and start empty after Redis is
        cleared.
        """

class TelemetryVariants:
    def delete(self, telemetry_variant_id: str) -> Any:
        """Delete a telemetry variant. Superusers only."""

    def get(self, telemetry_variant_id: str) -> Any:
        """Return one telemetry variant."""

    def list(self) -> Any:
        """List the known telemetry variants, such as device or environment metrics.

        Variants are registered automatically as devices report them, so there is
        no way to create one here.
        """

    def measurements_get(self, telemetry_variant_id: str, link_id: str) -> Any:
        """Return one measurement channel."""

    def measurements_list(self, telemetry_variant_id: str) -> Any:
        """List the measurement types reported under this telemetry variant."""

    def measurements_update(self, telemetry_variant_id: str, link_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Set which detectors run by default for a channel. Superusers only."""

    def update(self, telemetry_variant_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a telemetry variant. Its payload kind is fixed. Superusers only.

        The expected reading interval set here is used to judge whether devices
        reporting this variant are publishing as often as they should.
        """

class Terms:
    def get(self, *, locale: str | None = None) -> Any:
        """Return the account terms, which signing up accepts.

        They cover the account only (Terms of Use and Privacy Policy): signing up
        stores no mesh data. Creating a mesh on the default broker accepts the
        mesh terms instead. Every statement must be accepted. Send the returned
        `version` back as `terms_version` when signing up. They never lapse.
        Answers `404` on an instance that does not enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

class AsyncAlgorithms:
    async def list(self) -> Any:
        """List the functions available to postprocessing steps.

        Each entry declares the inputs it needs, the outputs it produces and the
        parameters it accepts.
        """

class AsyncDataDeletions:
    async def list(self, *, mesh_id: str | None = None, status: str | None = None) -> Any:
        """List scheduled deletions of stored readings, newest first. Superusers only.

        A mesh's readings are scheduled for deletion when the mesh is deleted,
        moved off its source, or its source's terms lapse. They stay in place
        until `delete_after`, then are deleted from both the time-series store
        and the archive.

        Args:
            status: `pending`, the default, `cancelled`, `done`, or `all`.
            mesh_id: Restrict to one mesh.
        """

class AsyncDetectors:
    async def list(self) -> Any:
        """List the alarm detectors and what each one needs to trigger.

        - `scope`: where a detector is switched on: `measurement` ones go in a
        channel's `enabled_detectors`, `device` ones in the device's own
        `absence_detection_enabled`.
        - `requires` is the config that must also be set before the
        detector can trigger in the first place.
        """

class AsyncDevices:
    async def create(self, *, body: dict[str, Any]) -> Any:
        """Register a device on a mesh the caller owns.

        Registering a gateway authorizes its traffic to be decoded. A
        device can only move to another mesh once its current registration has
        been disallowed.
        """

    async def delete(self, device_uuid: str) -> Any:
        """Delete a device registration.

        The device is deregistered from the decoder first, and the record is
        kept if that fails.
        """

    async def get(self, device_uuid: str) -> Any:
        """Return one registered device.

        Rejected registrations are visible only to the mesh's owner.
        """

    async def list(self, *, has_postprocessing: bool | None = None, is_allowed: bool | None = None, is_gateway: bool | None = None, mesh_id: str | None = None, telemetry_variant: str | None = None) -> Any:
        """List the devices the caller may read, or every device for a superuser.

        Alongside devices on their own meshes, this includes those on public
        meshes. Rejected registrations are shown only to the mesh's owner.

        Args:
            mesh_id: Restrict to devices on one mesh.
            is_gateway: Restrict to gateways, or to plain nodes when false.
            is_allowed: Restrict to allowed registrations, or to rejected ones
                when false.
            has_postprocessing: Restrict to devices with a postprocessing
                attached, or to those without one when false.
            telemetry_variant: Restrict by reported telemetry variants, as
                `has_any_of`, `has_all_of` or `has_none_of` followed by `:` and
                variant ids separated by `|`. Bare ids mean `has_any_of`.
        """

    async def measurements_get(self, device_uuid: str, measurement_id: str) -> Any:
        """Return one of this device's measurement channels."""

    async def measurements_list(self, device_uuid: str) -> Any:
        """List the measurement channels this device produces, measured and computed alike.

        Entries appear on their own as telemetry arrives. `enabled_detectors` is set by
        this device and may be null; `effective_detectors` is the result once
        the shared catalog default is applied.
        """

    async def measurements_update(self, device_uuid: str, measurement_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Choose which detectors alarm on this channel, and the range they
        check against, for this device.

        Alarms are off until enabled. Sending `null` for enabled_detectors
        inherits whatever the shared catalog sets for the channel; sending an
        empty list silences it here regardless of that default. valid_min/
        valid_max have no catalog default: the range detector remains off
        until both are set here.

        Args:
            enabled_detectors: Detectors to run, or `null` to inherit.
            valid_min: Lower bound for the range detector. Must be provided together with valid_max.
            valid_max: Upper bound for the range detector. Must be provided together with valid_min.
        """

    async def postprocessings_backfills_create(self, device_uuid: str, postprocessing_id: str, *, body: dict[str, Any]) -> Any:
        """Recompute a postprocessing's derived channels over stored history.

        Readings already stored between `start` and `stop` are run through the
        postprocessing with the calibration in force when each was taken, and
        the results replace any derived values stored for the same times.
        Backfilled values are stored and archived but never raise alarms. The
        request is queued and runs within about a minute; its progress is
        reported in `status`. The postprocessing must be runnable, although it
        does not need to be enabled.

        Args:
            start: Start of the range to recompute.
            stop: End of the range. Defaults to now. At most 90 days after `start`.
            include_dependants: Also recompute every enabled postprocessing that reads this one's outputs. Defaults
                to false.
        """

    async def postprocessings_backfills_list(self, device_uuid: str, postprocessing_id: str) -> Any:
        """List the backfills requested for a postprocessing and how they went, oldest first."""

    async def postprocessings_calibrations_create(self, device_uuid: str, postprocessing_id: str, *, body: dict[str, Any]) -> Any:
        """Record a calibration for one step, in force from `valid_from` onwards.

        History is kept: readings are processed with the calibration in force
        when they were taken, so recalibrating a sensor never rewrites the
        past. Every required calibration parameter of the step's algorithm
        must be given. Rolled back if the stream tier cannot be notified.

        Args:
            step_key: Step being calibrated.
            params: Calibration parameters of the step's algorithm.
            valid_from: When this calibration takes effect. Defaults to now.
        """

    async def postprocessings_calibrations_delete(self, device_uuid: str, postprocessing_id: str, calibration_id: str) -> Any:
        """Delete a calibration recorded by mistake.

        Refused when it would leave an enabled postprocessing without a
        calibration it needs. To change a calibration from some point onwards,
        record a new one instead.
        """

    async def postprocessings_calibrations_list(self, device_uuid: str, postprocessing_id: str) -> Any:
        """List the calibration history of a postprocessing, per step and oldest first."""

    async def postprocessings_create(self, device_uuid: str, *, body: dict[str, Any] | None = None) -> Any:
        """Attach a blueprint to a device.

        Slots not given in `input_bindings` are bound to the device's channel
        named by their `default_channel` when it has one. The derived channels
        the blueprint produces are registered on the device straight away, so
        detectors and ranges can be configured on them before any data
        arrives. A postprocessing starts disabled unless `is_enabled` is set,
        and can only be enabled once every slot is bound and every step that
        needs one has a calibration. Changes are rolled back if the stream
        tier cannot be notified.

        Args:
            blueprint_id: Blueprint to attach, the caller's own or a public one. Required.
            blueprint_version: Version number. Defaults to the latest.
            input_bindings: {slot: measurement id of this device}.
            output_prefix: Prepended to every derived field name, so a blueprint can run twice on one device.
            tolerance_seconds: Maximum distance between samples joined into one row. Defaults to half the device's
                reading interval.
            is_enabled: Start running straight away. Defaults to false.
        """

    async def postprocessings_delete(self, device_uuid: str, postprocessing_id: str) -> Any:
        """Detach a blueprint from a device.

        Its derived channels are removed from the device, while readings
        already stored remain queryable. Refused while another postprocessing
        on the device reads one of those channels.
        """

    async def postprocessings_get(self, device_uuid: str, postprocessing_id: str) -> Any:
        """Return one blueprint attachment on a device."""

    async def postprocessings_list(self, device_uuid: str) -> Any:
        """List the blueprints attached to a device, with their wiring, outputs and state.

        `problems` lists what keeps a postprocessing from being enabled, and is
        empty once it can run.
        """

    async def postprocessings_update(self, device_uuid: str, postprocessing_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Rewire, move to another version, or enable or disable a postprocessing.

        Moving to another version keeps bindings for slots it still declares
        and calibrations for steps with the same key and algorithm. Derived
        channels the new wiring no longer produces are removed from the device,
        which is refused while another postprocessing reads them. Changes are
        rolled back if the stream tier cannot be notified.

        Args:
            blueprint_version: Version number of the same blueprint.
            input_bindings: {slot: measurement id of this device}. Null unbinds a slot. Slots not given keep
                their binding.
            output_prefix: Prepended to every derived field name.
            tolerance_seconds: Maximum distance between samples joined into one row. Null uses half the device's
                reading interval.
            is_enabled: Run or stop the postprocessing.
        """

    async def telemetry_variants_list(self, device_uuid: str) -> Any:
        """List the telemetry types this device has been seen reporting.

        Entries appear on their own as telemetry arrives and cannot be edited here.
        """

    async def update(self, device_uuid: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a registered device.

        Position and identity fields are filled in from what the device reports
        until they are set here, after which the values given take precedence.
        Disallowing a gateway stops its traffic being decoded.

        `archive_enabled` stores the device's readings in the Parquet archive from
        then on. It is accepted only on a mesh owned by an operator and on
        instances that run the archive. Turning it off stops storing new readings
        and keeps those already stored.

        Nothing in the request is applied if the pipeline cannot be told about a
        change to `archive_enabled` or `is_allowed`.
        """

class AsyncHealth:
    async def get(self) -> Any:
        """Report whether the service and its database are reachable."""

class AsyncMeasurements:
    async def create(self, *, body: dict[str, Any]) -> Any:
        """Add a measurement type to the shared catalog. Superusers only."""

    async def delete(self, measurement_id: str) -> Any:
        """Remove a measurement type from the catalog. Superusers only."""

    async def get(self, measurement_id: str) -> Any:
        """Return one measurement type."""

    async def list(self, *, field_name: str | None = None, kind: str | None = None, payload_kind: str | None = None) -> Any:
        """List the shared catalog of measurement types and their units.

        Sensor fields are named `telemetry:<variant>`. Blueprint outputs from
        every postprocessing share `computed:derived`, and data quality metrics
        use `computed:quality`.

        Args:
            kind: Restrict to one namespace, one of `telemetry`, `device` or
                `computed`.
            payload_kind: Restrict to one exact payload kind, such as
                `telemetry:environment_metrics`.
            field_name: Restrict to one field name, such as `temperature`.
        """

    async def update(self, measurement_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a measurement type. Its payload kind and field name are fixed. Superusers only."""

class AsyncMeshes:
    async def create(self, *, body: dict[str, Any]) -> Any:
        """Create a mesh owned by the caller.

        A mesh on the default broker needs its mesh terms accepted, which are
        recorded with it. A mesh on a source is covered by the source's terms.

        Args:
            source_id: Source the mesh's traffic is bridged from, which must be
                one the caller created, or any source for a superuser. Leave
                unset for traffic on this instance's own broker.
            discover_gateways: Register gateways automatically once one of their
                packets decodes with this mesh's channel and pre-shared key.
                Defaults to `false`. Only an operator may switch it on for a mesh
                with a default or blank key.
            terms_version: The `version` of the mesh terms accepted. Required
                without a source, ignored with one, and ignored on an instance
                that does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def delete(self, mesh_id: str) -> Any:
        """Delete a mesh and every device registered on it.

        Its gateways are deregistered from the decoder first, and nothing is
        removed if that fails. The mesh's stored readings are deleted after the
        grace period, so export them first if they are needed.
        """

    async def devices_list(self, mesh_id: str, *, telemetry_variant: str | None = None) -> Any:
        """List every device registered on this mesh, gateways and nodes alike.

        A public mesh's devices are readable without credentials. Rejected
        registrations and admin keys are shown only to the mesh's owner.

        Args:
            telemetry_variant: Restrict by reported telemetry variants, as
                `has_any_of`, `has_all_of` or `has_none_of` followed by `:` and
                variant ids separated by `|`. Bare ids mean `has_any_of`.
        """

    async def get(self, mesh_id: str) -> Any:
        """Return one mesh.

        A public mesh is readable without credentials. The pre-shared key, the
        source and the terms status are included only for the mesh's owner.
        """

    async def links_list(self, mesh_id: str, *, node_id: int | str | None = None, since: str | None = None) -> Any:
        """List the radio links heard on this mesh, longest first.

        A link is one node heard by another, as one source reports it:
        `traceroute` hops, `neighborinfo` reports, or `direct` receptions by a
        gateway with no hop in between. Each is directional, since the SNR is
        measured by the receiving node, so a pair heard both ways has two links.
        Direct links are added once an hour. Links not heard for 30 days are
        deleted. A public mesh's links are readable without credentials.

        Args:
            since: How far back a link must have been heard, one of `24h`, `7d`
                or `30d`. Defaults to `7d`.
            node_id: Only links to or from this node.
        """

    async def list(self, *, owned: bool | None = None, source_id: str | None = None) -> Any:
        """List the meshes the caller may read, or every mesh for a superuser.

        Alongside their own, this includes public meshes. Without credentials,
        only public meshes are listed. The pre-shared key, the source and the
        terms status are included only for meshes the caller owns.

        Args:
            owned: Restrict to meshes the caller owns. Defaults to false.
            source_id: Restrict to meshes bridged from one source. Matches
                only meshes the caller owns, or any mesh for a superuser.
        """

    async def terms_acceptance_create(self, mesh_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current mesh terms again, renewing the mesh. Its owner only.

        With a retention period configured, an acceptance lapses after that
        period and the mesh is paused: its gateways are deregistered and its
        readings are scheduled for deletion. Renewing resumes it and cancels the
        deletion, as long as the grace period has not ended. A mesh on a source
        is covered by the source's terms and answers `409`. Answers `404` on an
        instance that does not enforce terms.

        Args:
            terms_version: The `version` of the mesh terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def terms_get(self, *, locale: str | None = None) -> Any:
        """Return the terms an owner accepts to create a mesh on the default broker.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the mesh, or when moving a mesh from a
        source onto the default broker. The footnote states how long the mesh's
        data is kept. Answers `404` on an instance that does not enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

    async def traceroutes_list(self, mesh_id: str, *, before: str | None = None, limit: int | None = None, node_id: int | str | None = None) -> Any:
        """List the traceroutes heard on this mesh, newest first.

        A traceroute heard by several gateways is listed once, with the most
        complete route any of them saw. `towards` runs from the node that started
        the traceroute to its target and `back` returns; each SNR is the one
        measured on arriving at the next node. A reply carries both directions,
        a request only the hops taken so far. Traceroutes are kept 30 days. A
        public mesh's traceroutes are readable without credentials.

        Args:
            limit: How many to return, up to 500. Defaults to 50.
            before: Only traceroutes heard before this time, as an ISO 8601
                timestamp. Pass the `heard_at` of the last one received to read
                the next page.
            node_id: Only traceroutes from, to or through this node.
        """

    async def update(self, mesh_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a mesh.

        Changing the channel_id, the pre-shared key or the source redistributes
        them to every allowed gateway on the mesh, and the whole update is
        rolled back if that fails. Once the source changes, the mesh's gateways
        are only accepted through the new one.

        Args:
            source_id: Source to bridge the mesh's traffic from, which must be one
                the caller created, or any source for a superuser, and not paused.
                Null moves it to the default broker. Moving a mesh off a source
                schedules the readings stored until then for deletion after the
                grace period; moving it back within that period cancels it.
            discover_gateways: Register gateways automatically once one of their
                packets decodes with this mesh's channel and pre-shared key. A
                gateway is skipped when another mesh shares the same source,
                channel and key, when it is registered elsewhere, or when it was
                rejected on this mesh. Switching it off keeps the gateways
                already found. Only an operator may switch it on for a mesh with
                a default or blank key.
            terms_version: The `version` of the mesh terms accepted. Required when
                moving the mesh onto the default broker unless it already holds a
                current acceptance, or the instance does not enforce terms;
                ignored otherwise.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

class AsyncMetrics:
    async def get(self) -> Any:
        """Return totals for registered owners, meshes, devices and active gateways."""

class AsyncOperatorRequests:
    async def get(self, request_id: str) -> Any:
        """Return one operator request. Superusers only."""

    async def list(self, *, status: str | None = None) -> Any:
        """List operator requests, newest first. Superusers only.

        Args:
            status: `pending`, the default, `approved`, `rejected`, or `all`.
        """

    async def update(self, request_id: str, *, body: dict[str, Any]) -> Any:
        """Approve or reject a pending operator request. Superusers only.

        Approving makes the requester an operator. The requester is emailed
        the decision, and the decision stands even if that email fails.

        Args:
            decision: `approve` or `reject`. Required.
            note: Message to the requester, included in the email. Optional.
        """

class AsyncOwners:
    async def create(self, *, body: dict[str, Any]) -> Any:
        """Register an owner, sign it in and return its API key.

        Signing up accepts the current account terms, which are recorded. The
        key is for scripts and is shown in this response only; it cannot be
        retrieved again afterwards. A browser uses the session cookie set by
        this response instead. A new owner stays inactive until its email
        address is verified, and until then can only reach its own account.

        Args:
            terms_version: The `version` of the account terms accepted, as
                served by the terms endpoint. Required, and refused once the
                terms have changed, unless the instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def csrf_cookie_get(self) -> Any:
        """Set the CSRF cookie a browser client needs before logging in."""

    async def delete(self, owner_id: str) -> Any:
        """Remove an owner, along with their meshes, devices, blueprints and sinks. Superusers only.

        Their gateways are deregistered from the decoder and the credentials of
        their sinks revoked first, and nothing is removed if that fails.
        Blueprints other owners' devices still use are kept without an owner,
        editable by superusers only.
        """

    async def get(self, owner_id: str) -> Any:
        """Return one owner.

        The full record comes back when the caller is the owner being requested, or
        a superuser. Everyone else gets the public fields only.
        """

    async def list(self) -> Any:
        """List registered owners.

        A superuser sees the full record for every owner. Everyone else,
        including an authenticated owner reading their own row, gets the public
        fields only, so that the rows are all the same shape. Use the profile
        route to read your own record in full.
        """

    async def login_create(self, *, body: dict[str, Any]) -> Any:
        """Sign in with email and password, returning the owner profile and a session cookie.

        An owner whose email is not verified yet is signed in too, with `is_active`
        false in the profile, and can only reach its own account until it verifies.
        Attempts are limited per email and source address; once the limit is
        reached even the correct password is refused with `429` for about a minute.
        """

    async def logout_create(self) -> Any:
        """End the current session."""

    async def me_change_password_create(self, *, body: dict[str, Any]) -> Any:
        """Change the authenticated owner's password, confirming the current one first."""

    async def me_delete(self) -> Any:
        """Delete the authenticated owner, along with their meshes, devices, blueprints and sinks.

        Their gateways are deregistered from the decoder and the credentials of
        their sinks revoked first, and nothing is removed if that fails.
        Blueprints other owners' devices still use are kept without an owner,
        editable by superusers only.
        """

    async def me_devices_get(self) -> Any:
        """List the devices the authenticated owner may access."""

    async def me_get(self) -> Any:
        """Return the authenticated owner's own record, including their devices."""

    async def me_operator_request_create(self, *, body: dict[str, Any]) -> Any:
        """Ask for the operator role, which lets an owner create sources.

        Every superuser is emailed and one of them approves or rejects the
        request. Only one request can be pending at a time, and an owner who
        is already an operator cannot file one. Limited to 3 requests a day.

        Args:
            reason: Why the role is needed. Shown to superusers. Required.
        """

    async def me_operator_request_get(self) -> Any:
        """Return the caller's most recent operator request and its status."""

    async def me_resend_verification_create(self) -> Any:
        """Send a fresh verification email to the authenticated owner."""

    async def me_rotate_key_create(self) -> Any:
        """Issue a new API key and revoke the previous one immediately.

        The new key is shown in this response and cannot be retrieved again.
        """

    async def me_terms_acceptance_create(self, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current account terms, when they have changed since signing up.

        Account terms never lapse, so this pauses and resumes nothing. Answers
        `404` on an instance that does not enforce terms.

        Args:
            terms_version: The `version` of the account terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def me_update(self, *, body: dict[str, Any] | None = None) -> Any:
        """Update the authenticated owner's name, email address, or email preferences.

        Changing the email address deactivates the account until the new one
        is verified, and sends a fresh verification email.

        Args:
            alarm_email_cooldown_seconds: Length of a device's alarm window,
                in seconds. The first alarm on a device is emailed straight
                away; any further alarms on that device during the window are
                sent as one summary when it ends. Accepts 0 (email on every
                alarm, no summaries) up to 2592000 (30 days). Leave unset or
                null to use the server default.
            status_alerts_enabled: Email me when a source I created stays
                disconnected, or a sink I created with meshes or devices
                attached has nobody connected. Defaults to false.
            source_rate_alerts_enabled: Email me when a source I created
                averages more messages per second over an hour than this
                instance allows. Defaults to false. Superusers are always
                emailed about busy sources.
        """

    async def request_password_reset_create(self, *, body: dict[str, Any]) -> Any:
        """Email a password reset link.

        The response is the same whether or not the address is registered, so it
        cannot be used to discover accounts.
        """

    async def reset_password_create(self, *, body: dict[str, Any]) -> Any:
        """Set a new password using the token from the password reset link.

        The token works once and expires after one hour by default. An invalid or
        expired token is refused with `400`; request a new link to try again.

        Args:
            token: The token from the password reset link. Required.
            new_password: The new password. Required.
        """

    async def update(self, owner_id: str, *, body: dict[str, Any]) -> Any:
        """Change an owner's role. Superusers only.

        Args:
            role: `member`, the default, or `operator`, which may also manage
                sources and archive devices. Granting `operator` also approves any
                pending operator request from this owner, without emailing them.
                Taking it away stops archiving the owner's devices, and the role
                is kept if the pipeline cannot be told.
        """

    async def verify_email_get(self, *, token: str) -> Any:
        """Confirm an owner's email address using the token from the verification link."""

class AsyncPostprocessingBackfills:
    async def claim_create(self, backfill_id: str) -> Any:
        """Claim a pending backfill for processing and return everything needed to run it. Superusers only.

        Only one caller can claim a backfill. A backfill left running for over
        an hour is presumed abandoned and can be claimed again.
        """

    async def list(self, *, status: str | None = None) -> Any:
        """List backfills across every device, oldest first. Superusers only.

        Args:
            status: Restrict to one status, such as `pending`.
        """

    async def update(self, backfill_id: str, *, body: dict[str, Any]) -> Any:
        """Record how a claimed backfill finished. Superusers only.

        Args:
            status: `done` or `failed`.
            points_published: Derived values published.
            error: Why it failed.
        """

class AsyncPostprocessingBlueprints:
    async def create(self, *, body: dict[str, Any]) -> Any:
        """Create a postprocessing blueprint together with its first version.

        A version declares the input slots it reads and an ordered list of
        steps. Each step runs one algorithm, takes its inputs from a slot or
        from an earlier step's output, and names the derived channels its
        outputs are stored as. Calibration parameters are not set here: each
        device supplies its own when the blueprint is attached to it.

        Args:
            name: Unique among the caller's blueprints.
            description: Free text.
            is_public: Lets any owner attach the blueprint to their devices. Defaults to false.
            inputs: Input slots, each with an optional `default_channel`.
            steps: Steps, each with a `key` that stays the same across versions.
            notes: Free text describing this version.
        """

    async def delete(self, blueprint_id: str) -> Any:
        """Delete a blueprint and all of its versions.

        Refused while any device still uses one of its versions.
        """

    async def get(self, blueprint_id: str) -> Any:
        """Return one postprocessing blueprint and its latest version."""

    async def list(self, *, owned: bool | None = None) -> Any:
        """List the postprocessing blueprints the caller may use: their own and public ones.

        A superuser sees every blueprint.

        Args:
            owned: Restrict to the caller's own blueprints, excluding public ones.
        """

    async def update(self, blueprint_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Rename or describe a blueprint, or change whether it is public.

        Steps cannot be changed here: create a new version instead. Making a
        blueprint private does not detach it from devices already using it.
        """

    async def versions_create(self, blueprint_id: str, *, body: dict[str, Any]) -> Any:
        """Add a version of a blueprint.

        Versions are immutable, so this is how a blueprint's steps change.
        Devices keep running the version they use until they are moved to the
        new one. Keeping a step's `key` and algorithm lets a device keep its
        calibration when it moves.

        Args:
            inputs: Input slots, each with an optional `default_channel`.
            steps: Steps, each with a `key` that stays the same across versions.
            notes: Free text describing what changed.
        """

    async def versions_get(self, blueprint_id: str, number: int) -> Any:
        """Return one version of a blueprint and its steps."""

    async def versions_list(self, blueprint_id: str) -> Any:
        """List every version of a blueprint, oldest first."""

class AsyncReadings:
    async def archive_meshes_credentials_create(self, mesh_id: str) -> Any:
        """Issue temporary S3 credentials that can read this mesh's archive and nothing else.

        Use them with DuckDB, pandas or any S3 client to query the archive as a
        partitioned dataset. The secret is shown in this response only. The
        credentials cannot be revoked and stay valid until `expires_at`, even if
        the caller loses access to the mesh in the meantime. Available to the
        mesh's owner while they are an operator, and to superusers.
        """

    async def archive_meshes_get(self, mesh_id: str, *, start: str | None = None, stop: str | None = None) -> Any:
        """List the hourly Parquet files archived for a mesh, oldest first.

        Only devices whose archive is switched on are stored, from the moment it
        was switched on, so the list stays empty until one of them reports.
        Available to the mesh's owner while they are an operator, and to
        superusers.

        Args:
            start: Earliest day to include, as `YYYY-MM-DD`. Defaults to the first archived day.
            stop: Latest day to include, as `YYYY-MM-DD`. Defaults to the last archived day.
        """

    async def archive_meshes_partitions_get(self, mesh_id: str, day: str, hour: int) -> Any:
        """Download one hour of a mesh's archive as a Parquet file.

        Answers with a redirect to a temporary link, valid for the same time as
        issued credentials, that any HTTP client can follow. The file does not
        carry `mesh_id` as a column. Available to the mesh's owner while they are
        an operator, and to superusers.
        """

    async def devices_get(self, device_uuid: str, *, agg: str | None = None, channel: str | None = None, payload_kind: str | None = None, start: str | None = None, stop: str | None = None, window: str | None = None) -> Any:
        """Readings over a time range, addressed by the device's registration ID."""

    async def devices_latest_get(self, device_uuid: str, *, lookback: str | None = None, payload_kind: str | None = None) -> Any:
        """Most recent readings, addressed by the device's registration ID.

        A device on a public mesh is readable without credentials. Rejected
        registrations are not.
        """

    async def devices_quality_get(self, device_uuid: str, *, start: str | None = None, stop: str | None = None) -> Any:
        """Data-quality figures for a device, addressed by its registration ID."""

    async def devices_traffic_get(self, device_uuid: str, *, range: str | None = None) -> Any:
        """A device's packets over a fixed range, addressed by its registration ID."""

    async def exports_list(self) -> Any:
        """List the caller's exports of every mesh from the last 30 days, newest first.

        A ready export becomes `expired` 24 hours after it finished, when its file
        is deleted; request it again to rebuild it. Empty on an instance without
        object storage.
        """

    async def meshes_exports_create(self, mesh_id: str, *, body: dict[str, Any]) -> Any:
        """Request a download of a mesh's readings over a range of days, as one zip.

        The zip is built in the background: poll the export until its status is
        `ready`, then download it from `url`. The owner is also emailed when it is
        ready or has failed. A CSV export reads every stored reading, a file per
        measurement and day with a column per field, plus `channels.csv` with each
        channel's unit. A Parquet export holds the hourly archive files, only for
        devices whose archive is on. Each owner has one export queued or running at a
        time, and repeating that same request returns it. Available to the mesh's
        owner and to superusers; Parquet also needs the operator role.

        Args:
            format: `csv` or `parquet`. Required.
            start: First day, as `YYYY-MM-DD` in UTC. Required.
            stop: Last day, included, as `YYYY-MM-DD` in UTC. Required. At most a year after `start`.
            node_ids: Node numbers to limit a CSV export to. Defaults to every device of the mesh.
        """

    async def meshes_exports_get(self, mesh_id: str, export_id: str) -> Any:
        """Return one of the caller's exports: its status, progress in days and, once ready, a download link.

        The link is valid until `expires_at`, 24 hours after the export finished,
        and works for anyone who has it. The status then becomes `expired`.
        """

    async def meshes_exports_list(self, mesh_id: str) -> Any:
        """List the caller's exports of a mesh from the last 30 days, newest first.

        A ready export becomes `expired` 24 hours after it finished, when its file
        is deleted. Available to the mesh's owner and to superusers.
        """

    async def meshes_nodes_get(self, mesh_id: str, node_id: int | str, *, agg: str | None = None, channel: str | None = None, payload_kind: str | None = None, start: str | None = None, stop: str | None = None, window: str | None = None) -> Any:
        """Return a device's readings for one measurement over a time range.

        Downsampling covers numeric fields only, so text fields such as
        `timestamp_quality` are left out whenever `window` is set.

        Args:
            payload_kind: Family to read, for example `telemetry:environment_metrics`.
                Returns every channel in it. Required unless `channel` is given.
            channel: A single channel, for example `environment_metrics.temperature`.
                Takes precedence over `payload_kind`.
            start: Start of the range, as a relative duration such as `-24h`, a date
                such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
                Defaults to `-1h`.
            stop: End of the range, in the same forms as `start`, or `now()`.
                Defaults to `now()`.
            window: Bucket size to downsample into, for example `6h`. Off by default.
            agg: Aggregate applied to each bucket, one of `mean`, `max`, `min`,
                `last`, `first`, `sum` or `count`. Defaults to `mean` and applies
                only when `window` is set.
        """

    async def meshes_nodes_latest_get(self, mesh_id: str, node_id: int | str, *, lookback: str | None = None, payload_kind: str | None = None) -> Any:
        """Return a device's most recent readings.

        Without `payload_kind`, every channel the device has reported comes back in
        one call, each annotated with its unit from the measurement catalog. A
        device on a public mesh is readable without credentials.

        Args:
            payload_kind: Restrict to one family, for example
                `telemetry:environment_metrics`. Defaults to every one.
            lookback: How far back to search for a value, as a relative duration, a
                date or a timestamp. Defaults to `-30d`.
        """

    async def meshes_nodes_quality_get(self, mesh_id: str, node_id: int | str, *, start: str | None = None, stop: str | None = None) -> Any:
        """Return data-quality figures for a device over a time range.

        Covers the number of readings recorded, alarms raised per detector, the
        share of the hours the device reported in that stayed within its
        configured ranges, and how complete each channel was. Figures stay empty
        until the quality checks have run for the device.

        Alarms are kept one by one for 30 days. A range reaching further back is
        answered from daily counts, so it is rounded to whole days and does not
        include the current day.

        Args:
            start: Start of the range, as a relative duration such as `-24h`, a date
                such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
                Defaults to `-1h`.
            stop: End of the range, in the same forms as `start`, or `now()`.
                Defaults to `now()`.
        """

    async def meshes_nodes_traffic_get(self, mesh_id: str, node_id: int | str, *, range: str | None = None) -> Any:
        """Return how much a node transmitted over a fixed range, and of which kinds of packet.

        Counts every packet the mesh's gateways heard from the node, including ones
        that could not be decrypted (`portnum` null). Kept per hour, so the range
        starts at `hourly_start`, the whole hour on or before its start. A device on
        a public mesh is readable without credentials.

        Args:
            range: Period to cover, ending now. One of `1h`, `24h`, `7d` or `30d`.
                Defaults to `24h`.
        """

    async def meshes_stats_get(self, mesh_id: str, *, range: str | None = None) -> Any:
        """Return traffic and congestion figures for a mesh over a fixed range.

        Counts every packet the mesh's registered gateways hear, including text
        messages, routing traffic and packets that could not be decrypted. A packet
        heard by several gateways is one packet and several receptions. Packets from
        nodes the owner rejected count towards the totals but are never listed as
        nodes. Channel utilization and airtime are the figures the nodes report
        about themselves.

        Busiest nodes, gateways, hops, signal, gateway pairs, relays and activity
        are kept per hour, so they start at `hourly_start`, the whole hour on or
        before the start of the range. Figures from the last few minutes are still
        being counted and may grow.

        Gateway pairs compare gateways that heard the same packets. Relays say which
        nodes passed packets on to each gateway; the firmware reports only the last
        byte of a relay's node number, so each comes with the registered nodes it
        could be.

        Results are computed at most once a minute per mesh and range, so a repeated
        call within that minute returns the same figures. A public mesh is readable
        without credentials.

        Args:
            range: Period to cover, ending now. One of `1h`, `24h`, `7d` or `30d`.
                Defaults to `24h`.
        """

class AsyncSinks:
    async def create(self, *, body: dict[str, Any] | None = None) -> Any:
        """Create a sink and return the credentials its consumer subscribes with. Operators only.

        The consumer connects to `broker` over TLS as `username` with the returned
        password and subscribes under `topic_filter`, where each message is one
        reading or alarm as JSON. The password is shown in this response only.
        The caller must first accept the current sink terms. Nothing is kept if
        the broker or the pipeline cannot be set up, or if the broker does not
        yet keep sink topics private.

        Args:
            label: Name for the sink.
            streams: Which readings are sent: `decoded`, `derived` and `alarms`.
                Defaults to `decoded`. Derived readings are sent only by
                instances that run postprocessing, and alarms only by those that
                run quality checks.
            mesh_ids: Meshes whose every node is sent, including nodes that
                appear later. Each must be one the caller may edit, owned by an
                operator.
            device_ids: Registrations of single devices to send, under the same
                conditions.
            terms_version: The `version` of the sink terms the caller accepted.
                Required unless the instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def credentials_create(self, sink_id: str) -> Any:
        """Replace a sink's password and disconnect its consumers. Operators only, on the sinks they created.

        The new password is shown in this response only. The old one is kept if
        the broker cannot be told.
        """

    async def delete(self, sink_id: str) -> Any:
        """Delete a sink, revoke its credentials and disconnect its consumers. Operators only.

        A sink with meshes or devices attached cannot be deleted. Nothing is
        removed if the broker cannot be told. Its terms acceptances are kept.
        """

    async def get(self, sink_id: str) -> Any:
        """Return one sink and how many consumers are connected to it. Operators only.

        An operator can read only the sinks they created; a superuser can read
        any. The password is never included.
        """

    async def list(self) -> Any:
        """List the sinks the caller created, or every sink for a superuser. Operators only.

        Each carries how many consumers are connected, null for all of them when
        the broker cannot be asked. Passwords are never included.
        """

    async def terms_acceptance_create(self, sink_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current sink terms again, renewing the sink. Only the operator who created it.

        With a retention period configured, an acceptance lapses after that
        period and the sink is paused: nothing is sent and its consumers are
        refused. Renewing a paused sink resumes it with the same credentials.
        Answers `404` on an instance that does not enforce terms.

        Args:
            terms_version: The `version` of the sink terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def terms_get(self, *, locale: str | None = None) -> Any:
        """Return the terms an operator must accept to create a sink. Operators only.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the sink. Answers `404` on an instance that
        does not enforce terms or has no sinks.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

    async def update(self, sink_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a sink. Operators only, on the sinks they created.

        Any subset of the create fields may be sent, except the terms. A list
        sent replaces the current one, so an empty `mesh_ids` detaches every
        mesh. Changes the pipeline cannot be told about are rolled back.
        """

class AsyncSources:
    async def create(self, *, body: dict[str, Any]) -> Any:
        """Create a source and start bridging its remote topic into this instance. Operators only.

        The caller must first accept the current source terms. The acceptance
        is recorded with the source. Nothing is kept if the bridge cannot be set
        up.

        Args:
            server: Remote broker as `host:port`. Cannot be this instance's own
                broker or one the server has blocked.
            ssl: Connect to the remote broker over TLS. Defaults to true.
            username: Remote broker username, if it requires one.
            password: Remote broker password. Accepted but never returned.
            topic: Remote topic filter, for example `msh/EU_868/2/e/MyChannel/#`.
                `$share`, `$SYS` and filters the server has blocked, such as `#`,
                are rejected.
            qos: 0 or 1. Defaults to 1.
            terms_version: The `version` of the source terms the caller accepted.
                Required, and refused once the terms have changed, unless the
                instance does not enforce terms.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def delete(self, source_id: str) -> Any:
        """Delete a source and stop bridging it. Operators only, on the sources they created.

        A source with meshes attached cannot be deleted. Nothing is removed if
        the bridge cannot be torn down. Its terms acceptances are kept.
        """

    async def get(self, source_id: str) -> Any:
        """Return one source and the live status of its bridge. Operators only.

        An operator can read only the sources they created; a superuser can read
        any. The status is `unknown` when the broker cannot be reached to check
        it, and `paused` once its terms have lapsed.
        """

    async def list(self) -> Any:
        """List the sources the caller created, or every source for a superuser. Operators only.

        Each carries its bridge's status, `unknown` for all of them when the
        broker cannot be asked. Remote passwords are never included.
        """

    async def terms_acceptance_create(self, source_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Accept the current source terms again, renewing the source. Only the operator who created it.

        With a retention period configured, an acceptance lapses after that
        period and the source is paused. Renewing a paused source restarts its
        bridge and cancels the deletion of its meshes' data, as long as the
        grace period has not ended. Answers `404` on an instance that does not
        enforce terms.

        Args:
            terms_version: The `version` of the source terms accepted. Required.
            terms_locale: Locale the terms were shown in, `en` or `es`. Defaults
                to `en`.
        """

    async def terms_get(self, *, locale: str | None = None) -> Any:
        """Return the terms an operator must accept to add a source. Operators only.

        Every statement must be accepted. Send the returned `version` back as
        `terms_version` when creating the source. The footnote states how long
        the source's data is kept. Answers `404` on an instance that does not
        enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

    async def update(self, source_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a source and reconfigure its bridge. Operators only, on the sources they created.

        Any subset of the create fields may be sent. The update is rolled back
        if the bridge cannot be reconfigured. A paused source is updated
        without touching the broker. Send an empty `password` to remove it.
        """

class AsyncStatus:
    async def email_get(self) -> Any:
        """Report whether the instance's emails are being accepted by its mail server. Superusers only.

        Covers every email registry sends: alarms and their summaries, sign up,
        password resets, terms and status notices. `ok` is false while the most
        recent one failed to send, and turns true again with the next success.
        It says nothing about delivery beyond the mail server, such as spam
        filtering. Counts cover the last 24 hours and start empty after Redis is
        cleared.
        """

class AsyncTelemetryVariants:
    async def delete(self, telemetry_variant_id: str) -> Any:
        """Delete a telemetry variant. Superusers only."""

    async def get(self, telemetry_variant_id: str) -> Any:
        """Return one telemetry variant."""

    async def list(self) -> Any:
        """List the known telemetry variants, such as device or environment metrics.

        Variants are registered automatically as devices report them, so there is
        no way to create one here.
        """

    async def measurements_get(self, telemetry_variant_id: str, link_id: str) -> Any:
        """Return one measurement channel."""

    async def measurements_list(self, telemetry_variant_id: str) -> Any:
        """List the measurement types reported under this telemetry variant."""

    async def measurements_update(self, telemetry_variant_id: str, link_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Set which detectors run by default for a channel. Superusers only."""

    async def update(self, telemetry_variant_id: str, *, body: dict[str, Any] | None = None) -> Any:
        """Update a telemetry variant. Its payload kind is fixed. Superusers only.

        The expected reading interval set here is used to judge whether devices
        reporting this variant are publishing as often as they should.
        """

class AsyncTerms:
    async def get(self, *, locale: str | None = None) -> Any:
        """Return the account terms, which signing up accepts.

        They cover the account only (Terms of Use and Privacy Policy): signing up
        stores no mesh data. Creating a mesh on the default broker accepts the
        mesh terms instead. Every statement must be accepted. Send the returned
        `version` back as `terms_version` when signing up. They never lapse.
        Answers `404` on an instance that does not enforce terms.

        Args:
            locale: `en` or `es`. Defaults to `en`, which is also used for any
                other value.
        """

class SyncNamespaces:
    algorithms: Algorithms
    data_deletions: DataDeletions
    detectors: Detectors
    devices: Devices
    health: Health
    measurements: Measurements
    meshes: Meshes
    metrics: Metrics
    operator_requests: OperatorRequests
    owners: Owners
    postprocessing_backfills: PostprocessingBackfills
    postprocessing_blueprints: PostprocessingBlueprints
    readings: Readings
    sinks: Sinks
    sources: Sources
    status: Status
    telemetry_variants: TelemetryVariants
    terms: Terms

class AsyncNamespaces:
    algorithms: AsyncAlgorithms
    data_deletions: AsyncDataDeletions
    detectors: AsyncDetectors
    devices: AsyncDevices
    health: AsyncHealth
    measurements: AsyncMeasurements
    meshes: AsyncMeshes
    metrics: AsyncMetrics
    operator_requests: AsyncOperatorRequests
    owners: AsyncOwners
    postprocessing_backfills: AsyncPostprocessingBackfills
    postprocessing_blueprints: AsyncPostprocessingBlueprints
    readings: AsyncReadings
    sinks: AsyncSinks
    sources: AsyncSources
    status: AsyncStatus
    telemetry_variants: AsyncTelemetryVariants
    terms: AsyncTerms
