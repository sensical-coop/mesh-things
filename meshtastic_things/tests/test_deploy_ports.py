"""docker-compose.yml (the base file) must be safe to run on a public IP by itself Avoid
someone adding a service with a `ports:` entry bound to 0.0.0.0"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_ROOT = ROOT / "docker-compose.yml"
DEV = ROOT / "docker-compose.dev.yml"

# The only service allowed to bind a public interface: Caddy terminates TLS and
# is the single entry point. See docs/architecture.md#reverse-proxy.
PUBLIC_SERVICES = {"caddy"}


class _TagTolerantLoader(yaml.SafeLoader):
    """Compose's `!override` / `!reset` tags aren't YAML the safe loader knows."""


_TagTolerantLoader.add_multi_constructor(
    "!", lambda loader, suffix, node: loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode) else None
)

def _load(path):
    return yaml.load(path.read_text(), Loader=_TagTolerantLoader)

def _included_files():
    included = _load(COMPOSE_ROOT).get("include") or []
    return [ROOT / rel for rel in included]


BASE_FILES = _included_files()

def _services(paths):
    if isinstance(paths, Path):
        paths = [paths]
    merged = {}
    for path in paths:
        merged.update(_load(path).get("services") or {})
    return merged

def _compose_text(paths):
    if isinstance(paths, Path):
        paths = [paths]
    return "\n".join(path.read_text() for path in paths)

def _published(entry):
    if isinstance(entry, dict):
        return entry.get("host_ip", "0.0.0.0")
    parts = str(entry).split(":")
    return parts[0] if len(parts) >= 3 else "0.0.0.0"


BASE_SERVICES = _services(BASE_FILES)
BASE_EXPOSED = {name for name, svc in BASE_SERVICES.items() if svc.get("ports")}
DEV_SERVICES = _services(DEV)

def test_both_compose_files_exist():
    assert COMPOSE_ROOT.is_file() and DEV.is_file()
    assert BASE_FILES, "docker-compose.yml has no include: entries"
    assert all(f.is_file() for f in BASE_FILES), [f for f in BASE_FILES if not f.is_file()]

def test_the_base_file_actually_exposes_things():
    # If this ever becomes empty the checks below would pass vacuously.
    assert len(BASE_EXPOSED) > 5


@pytest.mark.parametrize("service", sorted(BASE_EXPOSED))
def test_only_caddy_binds_a_public_interface_by_default(service):
    """The base file alone is the production invocation now - nothing else layers on top to
    close ports the way docker-compose.prod.yml used to."""
    for entry in BASE_SERVICES[service].get("ports") or []:
        host_ip = _published(entry)
        if service in PUBLIC_SERVICES:
            continue
        assert host_ip == "127.0.0.1", (
            f"{service} binds {entry!r} to {host_ip} in the base file; "
            f"only {sorted(PUBLIC_SERVICES)} may be public by default."
        )

def test_caddy_still_serves_80_and_443():
    published = {str(e).split(":")[-2] for e in BASE_SERVICES["caddy"]["ports"]}

    assert {"80", "443"} <= published, "Caddy must keep 80 (ACME HTTP-01) and 443"

def test_mailhog_does_not_exist_outside_the_dev_overlay():
    """mailhog captures every owner's email-verification link - it must not be a container a
    production invocation (base file alone) can start at all, not just one whose ports
    happen to be closed."""
    assert "mailhog" not in BASE_SERVICES
    assert "mailhog" in DEV_SERVICES

def test_the_dev_overlay_uses_the_replacing_tag_not_a_plain_list():
    """Compose *concatenates* list-valued options across files."""
    raw = DEV.read_text()
    ports_blocks = len(re.findall(r"^\s+ports:", raw, re.M))
    overriding = raw.count("ports: !override")

    new_service_ports_blocks = 1

    assert ports_blocks - new_service_ports_blocks == overriding, (
        f"{overriding} of {ports_blocks - new_service_ports_blocks} overridden "
        f"`ports:` blocks use `!override`; a plain `ports:` list appends to the "
        f"base file's list instead of replacing it."
    )


CADDYFILE = ROOT / "Caddyfile"
CREDENTIALS_DIR = ROOT / "caddy" / "credentials"

# service name -> the Caddy site address variable fronting it
ADMIN_UIS = {
    "jobmanager": "CADDY_FLINK_ADDRESS",
    "kafbat-ui": "CADDY_KAFKAUI_ADDRESS",
    "influxdb": "CADDY_INFLUX_ADDRESS",
    "minio": "CADDY_MINIO_ADDRESS",
}


@pytest.mark.parametrize("service,address_var", sorted(ADMIN_UIS.items()))
def test_each_admin_ui_is_proxied_and_behind_auth(service, address_var):
    """Every admin UI must be reachable through Caddy *and* import the admin_ui snippet."""
    caddyfile = CADDYFILE.read_text()
    # Matches e.g. "{$CADDY_FLINK_ADDRESS::8181} {" through its closing brace.
    pattern = r"\{\$" + re.escape(address_var) + r"[^}]*\} \{(.*?)\n\}"
    block = re.search(pattern, caddyfile, re.S)

    assert block, f"no Caddy site block for {address_var}"
    body = block.group(1)
    # influxdb can't `import admin_ui`
    uses_admin_ui_snippet = "import admin_ui" in body
    uses_inline_basic_auth = "basic_auth" in body and "import /etc/caddy/credentials/" in body
    assert uses_admin_ui_snippet or uses_inline_basic_auth, f"{service} is proxied without basic auth"
    assert service in body, f"{address_var} block does not proxy {service}"

def test_the_admin_auth_snippet_reads_credentials_from_files_not_env():
    """Compose interpolates env_file values, eating the "$" segments of a password hash - which
    silently breaks auth and takes the whole gateway down on an invalid-credential parse
    error."""
    caddyfile = CADDYFILE.read_text()
    snippet = re.search(r"\(admin_ui\) \{(.*?)\n\}", caddyfile, re.S)

    assert snippet, "the admin_ui snippet is missing"
    body = snippet.group(1)
    assert "import /etc/caddy/credentials/" in body
    assert "CADDY_ADMIN_PASSWORD_HASH" not in caddyfile, "credentials must not come from the environment"

def test_basic_auth_pins_the_hash_algorithm():
    """One algorithm applies to every account in the block, so leaving it implicit invites a
    credential that parses and then never authenticates."""
    assert re.search(r"basic_auth\s+bcrypt\s*\{", CADDYFILE.read_text())

def test_a_locked_placeholder_credential_is_committed():
    """Caddy refuses to start with an empty basic_auth block, which would take the API down
    too."""
    locked = CREDENTIALS_DIR / "00-locked.txt"

    assert locked.is_file()
    creds = [ln.split() for ln in locked.read_text().splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    assert len(creds) == 1
    username, hashed = creds[0]
    assert username == "locked-placeholder"
    assert hashed.startswith("$2"), "placeholder must be a bcrypt hash"

def test_real_credentials_are_gitignored():
    gitignore = (ROOT / ".gitignore").read_text()

    assert "caddy/credentials/*" in gitignore
    assert "!caddy/credentials/00-locked.txt" in gitignore

def test_caddy_mounts_the_credentials_directory_read_only():
    caddy = _services(BASE_FILES)["caddy"]
    mounts = [m for m in caddy.get("volumes", []) if "credentials" in str(m)]

    assert mounts, "the credentials directory is not mounted into Caddy"
    assert all(str(m).endswith(":ro") for m in mounts), "credentials must be mounted read-only"

def test_the_admin_ui_ports_are_not_published_by_default():
    """The admin sites are extra ports on Caddy in docker-compose.dev.yml; in production (base
    file alone) they're hostnames on 443 instead, so those publications must not be part of
    the base file at all."""
    base_caddy_ports = {str(e).split(":")[-2] for e in BASE_SERVICES["caddy"]["ports"]}

    assert base_caddy_ports == {"80", "443"}


# These are one-shot: they submit detached and exit. Two properties have to
# hold together, and losing either silently reintroduces a real incident.

FLINK_SUBMITTERS = ["flink-job", "postprocessing-job", "pattern-detection-job", "absence-detection-job"]


@pytest.mark.parametrize("service", FLINK_SUBMITTERS)
def test_submitters_do_not_restart(service):
    """`restart: unless-stopped` on a submitter means every exit resubmits the job - which is
    how the stack used to accumulate duplicate jobs competing for slots."""
    assert _services(BASE_FILES)[service].get("restart") == "no", (
        f"{service} must be restart: \"no\" - it is a one-shot submitter"
    )


@pytest.mark.parametrize("service", FLINK_SUBMITTERS)
def test_submitters_go_through_the_idempotent_script(service):
    """Calling `flink run` directly loses both the detach and the already-running check."""
    command = _services(BASE_FILES)[service].get("command") or []

    assert command[0] == "./submit-job.sh", f"{service} bypasses submit-job.sh: {command}"
    assert len(command) == 3, f"{service} needs both a job file and a job name: {command}"


@pytest.mark.parametrize("service", FLINK_SUBMITTERS[1:])
def test_submitter_chain_waits_for_completion_not_start(service):
    """One-shot containers make `service_started` meaningless - it fires before the previous
    job was accepted by the cluster."""
    deps = _services(BASE_FILES)[service].get("depends_on") or {}
    upstream = {k: v for k, v in deps.items() if k in FLINK_SUBMITTERS}

    assert upstream, f"{service} should wait for the previous submitter"
    for name, cond in upstream.items():
        assert cond.get("condition") == "service_completed_successfully", (
            f"{service} waits on {name} with {cond} - should be service_completed_successfully"
        )

def test_submitted_job_names_match_what_the_jobs_register():
    """The already-running check compares against Flink's job name, so a typo here silently
    makes submission non-idempotent again."""
    import re as _re

    for service in FLINK_SUBMITTERS:
        _, job_file, job_name = _services(BASE_FILES)[service]["command"]
        source = (ROOT / "meshtastic_things" / "flink" / job_file).read_text()
        registered = _re.search(r'env\.execute\("([^"]+)"\)', source)

        assert registered, f"{job_file} has no env.execute(<name>)"
        assert registered.group(1) == job_name, (
            f"{service} submits '{job_name}' but {job_file} registers "
            f"'{registered.group(1)}' - the idempotency check would never match"
        )

def test_watchdog_watches_exactly_the_submitted_jobs():
    """A job missing here is never resubmitted after a jobmanager restart or a reboot."""
    services = _services(BASE_FILES)
    watchdog = services["flink-watchdog"]
    submitted = {
        f"{services[s]['command'][1]}:{services[s]['command'][2]}" for s in FLINK_SUBMITTERS
    }

    assert watchdog["command"][0] == "./watch-jobs.sh"
    assert set(watchdog["command"][1:]) == submitted
    assert watchdog.get("restart") == "unless-stopped", "the watchdog must come back with the host"
    last = (watchdog.get("depends_on") or {}).get(FLINK_SUBMITTERS[-1]) or {}
    assert last.get("condition") == "service_completed_successfully", (
        "the watchdog must start after the submitters, or both can submit the same job"
    )

def test_flink_jvm_sizes_are_pinned():
    """Left at the image defaults these are 1600m/1728m, ~800 MB more than this workload needs
    - the difference between an 8 GB and a 16 GB VPS."""
    compose = _compose_text(BASE_FILES)

    assert "jobmanager.memory.process.size:" in compose
    assert "taskmanager.memory.process.size:" in compose

def test_task_slots_leave_headroom_for_a_redeploy():
    """One slot per job at parallelism 1; a redeploy briefly needs one more while the old job
    still holds its own."""
    match = re.search(r"taskmanager\.numberOfTaskSlots:\s*(\d+)", _compose_text(BASE_FILES))

    assert match, "numberOfTaskSlots is not set"
    slots = int(match.group(1))
    assert slots > len(FLINK_SUBMITTERS), (
        f"{slots} slots for {len(FLINK_SUBMITTERS)} jobs leaves no room to resubmit"
    )


def test_every_service_has_a_memory_limit():
    """Without one, a leaking container drags the host into the kernel OOM killer, which
    chooses its victim by score - often something healthy."""
    unlimited = [name for name, svc in _services(BASE_FILES).items() if not svc.get("mem_limit")]

    assert not unlimited, f"no mem_limit on: {sorted(unlimited)}"

def test_flink_container_limits_exceed_their_configured_jvm_size():
    """A limit below the JVM's own budget is a guaranteed kill under load."""
    compose = _compose_text(BASE_FILES)
    services = _services(BASE_FILES)

    def mb(value):
        value = str(value).strip().lower()
        return int(value[:-1]) if value.endswith("m") else int(value)

    for daemon in ("jobmanager", "taskmanager"):
        configured = re.search(rf"{daemon}\.memory\.process\.size:\s*(\d+)m", compose)
        assert configured, f"{daemon}.memory.process.size is not pinned"
        assert mb(services[daemon]["mem_limit"]) > int(configured.group(1)), (
            f"{daemon} mem_limit is at or below its configured JVM size"
        )


# One project now, so one settings package for every Django service. The role
# each container plays is APP_ROLE, checked separately below.
DJANGO_SERVICES = {
    "registry_api": "api_project.settings",
    "registry_device_consumer": "api_project.settings",
    "registry_sensor_discovery_consumer": "api_project.settings",
    "registry_quality_alarms_consumer": "api_project.settings",
    "registry_data_lifecycle": "api_project.settings",
    "readings_api": "api_project.settings",
}

# APP_ROLE decides which URLs a container mounts and which database
# credentials it uses. Getting it wrong on readings_api would expose the
# registry's write routes on the read tier.
APP_ROLES = {
    "registry_api": "registry",
    "registry_device_consumer": "registry",
    "registry_sensor_discovery_consumer": "registry",
    "registry_quality_alarms_consumer": "registry",
    "registry_data_lifecycle": "registry",
    "readings_api": "readings",
}


@pytest.mark.parametrize("service,role", sorted(APP_ROLES.items()))
def test_every_django_service_states_its_role(service, role):
    env = BASE_SERVICES[service].get("environment") or {}

    assert env.get("APP_ROLE") == role, (
        f"{service} must set APP_ROLE={role!r}; without it the container falls "
        f"back to the registry role and mounts routes it should not serve"
    )

def test_the_read_tier_uses_its_own_database_credentials():
    """The guarantee that read load cannot exhaust the registry's connections, and that a
    compromised read tier holds no mesh keys, is the Postgres role - not anything in Python."""
    command = " ".join(BASE_SERVICES["readings_api"].get("command") or [])
    compose = _compose_text(BASE_FILES)

    assert "READINGS__DB_DSN" in compose or "env_file" in compose
    # The read tier must not run migrations: its role cannot write.
    assert "migrate" not in command


@pytest.mark.parametrize("service,package", sorted(DJANGO_SERVICES.items()))
def test_base_compose_selects_the_prod_settings_module(service, package):
    """The base file is the production invocation now - it must never silently fall back to dev
    settings (ALLOWED_HOSTS='*', DEBUG on, email to a mailhog container that doesn't even
    exist in this file)."""
    env = BASE_SERVICES[service].get("environment") or {}

    assert env.get("DJANGO_SETTINGS_MODULE") == f"{package}.prod", (
        f"{service} must name a settings module explicitly; pointing at the "
        f"package itself leaves Django with empty settings"
    )


@pytest.mark.parametrize("service,package", sorted(DJANGO_SERVICES.items()))
def test_dev_overlay_switches_to_dev_settings(service, package):
    env = (DEV_SERVICES.get(service) or {}).get("environment") or {}

    assert env.get("DJANGO_SETTINGS_MODULE") == f"{package}.dev", (
        f"{service} still runs prod settings under docker-compose.dev.yml"
    )


# 19 services build from 4 Dockerfiles. Without an explicit `image:`, Compose
# derives a tag per *service*, so `docker compose build <one>` left the other
# siblings on stale code - which silently broke sensor discovery for a day.

WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"

def _building_services():
    return {n: s for n, s in _services(BASE_FILES).items() if s.get("build") or s.get("<<")}

def test_every_building_service_names_its_image_explicitly():
    """An implicit tag is per-service, which is what lets siblings drift."""
    compose = _compose_text(BASE_FILES)
    anchors = set(re.findall(r"^x-([\w-]+)-image:\s*&", compose, re.M))

    assert anchors, "no shared image anchors defined"
    for name in anchors:
        assert re.search(rf"^\s+image:\s+meshtastic-things/[\w-]+:latest\n", compose, re.M), (
            f"x-{name}-image does not pin an image name"
        )

def test_services_sharing_a_dockerfile_share_one_image():
    """The property that actually prevents drift: one image ID behind every service built from
    the same Dockerfile."""
    compose = _compose_text(BASE_FILES)
    # service name -> the anchor it merges. Some services merge a role anchor
    # that itself merges the image one, so match any anchor, not just *-image.
    merged = dict(re.findall(r"^  ([A-Za-z0-9_.-]+):\n(?:.*\n)*?    <<: \*([\w-]+)\n", compose, re.M))

    assert len(merged) >= 15, f"only {len(merged)} services use a shared anchor"

    # The decisive check: no *service* may declare its own `build:`. Only the
    # top-level x-*-image anchors do. A service that reopens one gets a
    # per-service tag again and can drift from its siblings - and it would
    # otherwise pass unnoticed, since it simply drops out of `merged`.
    in_services = compose.split("\nservices:\n", 1)[1]
    own_builds = re.findall(r"^  ([A-Za-z0-9_.-]+):\n(?:(?:    .*|)\n)*?    build:", in_services, re.M)

    assert not own_builds, (
        f"these services declare their own build: instead of a shared image "
        f"anchor, so Compose gives each its own tag: {sorted(set(own_builds))}"
    )


# lite/full split (docs/done.md#0): decode now has two mutually exclusive
# runtimes, one per tier, so a typo'd or missing profile tag can silently
# drop decode from both, or run it twice.

KNOWN_PROFILES = {"full", "lite", "quality", "bridge-pool", "minio", "sinks", "monitor"}

def test_profiles_are_known_values():
    """A typo'd profile name silently drops a service from every real invocation - Compose
    doesn't validate profile names itself."""
    for name, svc in BASE_SERVICES.items():
        for profile in svc.get("profiles") or []:
            assert profile in KNOWN_PROFILES, f"{name} has unknown profile {profile!r}"

def test_decode_runtimes_are_mutually_exclusive_per_tier():
    """flink-job (full, exactly-once) and decode_consumer (lite, at-least-once) both consume
    the raw topic - running both under the same profile would double-decode every packet."""
    flink_profiles = set(BASE_SERVICES["flink-job"].get("profiles") or [])
    consumer_profiles = set(BASE_SERVICES["decode_consumer"].get("profiles") or [])

    assert flink_profiles and consumer_profiles, "both decode runtimes must be tier-tagged"
    assert not (flink_profiles & consumer_profiles), (
        "flink-job and decode_consumer share a profile - double decode"
    )

def test_sinks_are_opt_in_on_lite():
    """A plain lite install must not gain a service publishing readings for third parties."""
    assert set(BASE_SERVICES["sink_dispatcher"]["profiles"]) == {"full", "sinks"}

def test_ci_publishes_every_image_compose_builds():
    """A Dockerfile that compose builds but CI never pushes means a registry deployment
    silently runs an older copy of that component - which is how quality_worker went
    unpublished."""
    compose_dockerfiles = set(re.findall(r"dockerfile:\s*(\S+)", _compose_text(BASE_FILES)))
    compose_dockerfiles.add("Dockerfile")  # the root one, referenced as `build: ./meshtastic_things`

    ci = WORKFLOW.read_text()
    ci_dockerfiles = {p.split("meshtastic_things/")[-1] for p in re.findall(r"dockerfile:\s*(\S+)", ci)}

    missing = compose_dockerfiles - ci_dockerfiles
    assert not missing, f"built by compose but never published by CI: {sorted(missing)}"


# The broker keeps one session per client id and holds that member's messages
# while it is away. That is what makes a restart lossless, and it is also why a
# duplicated or vanishing id silently swallows traffic - see known-gaps.md.

def _bridge_services():
    return {n: s for n, s in BASE_SERVICES.items() if n.startswith("mqtt_kafka_bridge")}

def test_every_bridge_member_declares_its_own_client_id():
    missing = [n for n, s in _bridge_services().items() if not (s.get("environment") or {}).get("MQTT_BRIDGE__CLIENT_ID")]

    assert _bridge_services(), "no bridge services found"
    assert not missing, (
        f"these bridge members have no MQTT_BRIDGE__CLIENT_ID: {sorted(missing)}. "
        f"Without one the id falls back to a shared default and the members "
        f"disconnect each other in a loop"
    )

def test_bridge_client_ids_are_unique():
    ids = [(n, (s.get("environment") or {})["MQTT_BRIDGE__CLIENT_ID"]) for n, s in _bridge_services().items()]
    seen = {}
    for name, client_id in ids:
        assert client_id not in seen, (
            f"{name} and {seen[client_id]} share client id {client_id!r}; MQTT allows "
            f"one connection per id, so they would kick each other off repeatedly"
        )
        seen[client_id] = name

def test_no_bridge_member_uses_replicas():
    """`deploy.replicas` gives each replica a fresh container and no stable identity, so every
    restart stranded a session that kept taking a share of the messages."""
    scaled = [n for n, s in _bridge_services().items() if (s.get("deploy") or {}).get("replicas")]

    assert not scaled, (
        f"{sorted(scaled)} use deploy.replicas; scale by adding a named member "
        f"with its own MQTT_BRIDGE__CLIENT_ID instead"
    )

def test_the_dev_overlay_separates_every_bridge_member_from_prod():
    """Members of one `$share` group get a share of the
    topic each, so a dev bridge on prod's group takes traffic away from prod."""
    without = [
        name
        for name in _bridge_services()
        if not ((DEV_SERVICES.get(name) or {}).get("environment") or {}).get("MQTT_BRIDGE__INSTANCE_SUFFIX")
    ]

    assert not without, (
        f"these bridge members have no MQTT_BRIDGE__INSTANCE_SUFFIX in "
        f"docker-compose.dev.yml: {sorted(without)}. Without it they join prod's "
        f"$share group and consume prod's messages"
    )

def test_the_dev_overlay_keeps_dev_connectors_apart_from_prod():
    """registry_api names the EMQX bridges and sinks, the bridges read what sources
    republish, and sink_dispatcher publishes sink topics. On a shared EMQX, a dev stack in
    prod's namespace would reconcile away prod's bridges and sinks and read prod's traffic."""
    services = [*_bridge_services(), "registry_api", "sink_dispatcher"]
    namespaces = {
        name: ((DEV_SERVICES.get(name) or {}).get("environment") or {}).get("MQTT_CONNECTORS__NAMESPACE")
        for name in services
    }

    assert all(ns and ns != "mt-sources" for ns in namespaces.values()), namespaces
    assert len(set(namespaces.values())) == 1, f"registry and bridges disagree: {namespaces}"


def _env_example() -> dict[str, str]:
    values = {}
    for line in (ROOT / "env.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values

def test_env_example_passes_the_prod_allowed_hosts_guard():
    """compose runs the prod settings, which refuse to start on `*`."""
    for name in ("REGISTRY__ALLOWED_HOSTS", "READINGS__ALLOWED_HOSTS"):
        value = _env_example()[name]
        assert value, f"{name} is empty; prod settings require hostnames"
        assert "*" not in value, (
            f"{name}={value!r} is rejected at startup by api_project/settings/prod.py"
        )

def test_env_example_does_not_point_smtp_at_the_local_mail_catcher():
    """The other prod guard: the SMTP backend with EMAIL_HOST=mailhog raises."""
    values = _env_example()
    if values.get("REGISTRY__EMAIL_BACKEND", "").endswith("smtp.EmailBackend"):
        assert values.get("REGISTRY__EMAIL_HOST") not in ("", "mailhog", "localhost"), (
            "SMTP backend with a local mail host is rejected by prod settings"
        )


# These read the workflows the same way the port tests read compose: the
# failures they catch are invisible locally, where the dev stack is already
# running everything the tests need.

PR_WORKFLOW = ROOT / ".github" / "workflows" / "pr-checks.yml"

def _pr_workflow() -> dict:
    return yaml.load(PR_WORKFLOW.read_text(), Loader=_TagTolerantLoader)

def _job_text(job: str) -> str:
    return yaml.dump(_pr_workflow()["jobs"][job])

def test_ci_starts_redis_wherever_it_runs_the_django_tests():
    """The bearer-auth rate limiter writes to the cache on every request, so a CI job with
    postgres but no redis errors 276 of 312 tests."""
    for name, job in _pr_workflow()["jobs"].items():
        text = yaml.dump(job)
        if "manage.py test" not in text:
            continue
        assert re.search(r"up -d --wait[^\n]*\bredis\b", text), (
            f"job {name!r} runs the Django tests without starting redis"
        )

def test_ci_pins_compose_file_so_env_example_cannot_swap_in_the_dev_overlay():
    """env.example sets COMPOSE_FILE to include docker-compose.dev.yml, and CI copies it to
    .env."""
    workflow = _pr_workflow()
    pinned = (workflow.get("env") or {}).get("COMPOSE_FILE")

    assert pinned == "docker-compose.yml", (
        "pr-checks.yml must pin COMPOSE_FILE to the base file; env.example "
        f"would otherwise select the dev overlay (got {pinned!r})"
    )

def test_env_example_still_points_compose_file_at_the_dev_overlay():
    """The pin above only matters while this holds."""
    line = next(
        (l for l in (ROOT / "env.example").read_text().splitlines() if l.startswith("COMPOSE_FILE=")),
        None,
    )

    assert line and "docker-compose.dev.yml" in line, (
        "env.example no longer selects the dev overlay; re-check the "
        "COMPOSE_FILE pin in pr-checks.yml and the local-run docs"
    )

def test_ci_builds_every_dockerfile_on_the_pr():
    """A broken Dockerfile in any component other than the api used to reach main and fail in
    the deploy workflow, after review had already passed."""
    compose_dockerfiles = set(re.findall(r"dockerfile:\s*(\S+)", _compose_text(BASE_FILES)))
    compose_dockerfiles.add("Dockerfile")
    built = set(_pr_workflow()["jobs"]["images"]["strategy"]["matrix"]["dockerfile"])

    missing = compose_dockerfiles - built
    assert not missing, f"not built on the PR: {sorted(missing)}"


BASE_YML = ROOT / "compose" / "base.yml"

def test_every_topic_created_at_startup_is_actually_used():
    """kafka-topics-init creates a topic per env var, and a deleted producer or consumer leaves
    its topic behind: created on every deploy, compacted forever, read by nothing."""
    init = BASE_YML.read_text().split("kafka-topics-init:", 1)[1].split("\n  influxdb:", 1)[0]
    topic_vars = set(re.findall(r"\$\$\{?([A-Z0-9_]+)", init))
    sources = "\n".join(
        path.read_text()
        for path in (ROOT / "meshtastic_things").rglob("*.py")
        if "/build/" not in str(path) and "__pycache__" not in str(path)
    )

    assert topic_vars, "no topic variables found - the parsing above has drifted"
    unused = sorted(name for name in topic_vars if name not in sources)
    assert not unused, (
        f"these topics are created at startup but no code reads the variable: {unused}"
    )


def test_the_read_tier_gets_only_the_environment_it_needs():
    """readings_api must not load the whole .env: that hands the read tier the MinIO root
    credential, registry's database password and the EMQX keys."""
    readings = BASE_SERVICES["readings_api"]
    env = readings.get("environment") or {}

    assert "env_file" not in readings
    leaked = sorted(k for k in env if k.startswith(("S3_WRITER__", "REGISTRY__", "POSTGRES_", "MQTT_")))
    assert not leaked, f"readings_api receives {leaked}"
    assert "READINGS__DB_DSN" in env and "INFLUX__TOKEN" in env


def test_the_archive_writer_runs_without_the_bundled_minio():
    """With the archive on an external S3 the minio profile is off, so the writer may not
    require it."""
    minio = BASE_SERVICES["s3_writer"]["depends_on"]["minio"]

    assert minio.get("required") is False
    assert BASE_SERVICES["minio"]["profiles"] == ["minio"]
    assert BASE_SERVICES["minio_init"]["profiles"] == ["minio"]


def test_the_s3_api_is_proxied_without_basic_auth():
    """S3 clients sign every request and cannot send a second Authorization header."""
    caddyfile = CADDYFILE.read_text()
    block = re.search(r"\{\$CADDY_S3_ADDRESS[^}]*\} \{(.*?)\n\}", caddyfile, re.S)

    assert block, "no Caddy site block for CADDY_S3_ADDRESS"
    assert "reverse_proxy minio:9000" in block.group(1)
    assert "admin_ui" not in block.group(1) and "basic_auth" not in block.group(1)
