"""Monitor settings, read from MONITOR__* environment variables."""
from dataclasses import dataclass, field

from common.env import env_bool, env_int, env_list, env_str


class ConfigError(ValueError):
    pass


def _required(name: str) -> str:
    value = env_str(name)
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def split_host_port(value: str, default_port: int) -> tuple[str, int]:
    host, sep, port = value.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return value, default_port


@dataclass(frozen=True)
class Config:
    api_url: str
    api_key: str = ""
    channel_id: str = "LongFast"
    mesh_id: str = ""
    gateway_uuid: str = ""
    gateway_node_id: int = 0
    psk_b64: str = ""

    mqtt_broker: str = ""
    mqtt_port: int = 8883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    mqtt_ssl: bool = True
    mqtt_topic_prefix: str = ""

    sink_broker: str = ""
    sink_port: int = 8883
    sink_user: str = ""
    sink_pass: str = ""
    sink_topic: str = ""
    sink_ssl: bool = True

    interval_s: int = 300
    http_timeout_s: int = 10
    ingest_timeout_s: int = 180
    poll_s: int = 5
    failures_before_alert: int = 2
    reminder_hours: int = 6
    # Needs a superuser's API key, as it reads registry's email status.
    email_check: bool = True

    instance_name: str = ""
    alert_emails: list[str] = field(default_factory=list)
    email_host: str = ""
    email_port: int = 587
    email_user: str = ""
    email_password: str = ""
    email_use_tls: bool = True
    email_use_ssl: bool = False
    email_from: str = ""

    port: int = 8095
    run_token: str = ""
    run_min_interval_s: int = 30

    @property
    def sink_enabled(self) -> bool:
        return bool(self.sink_topic)

    @property
    def name(self) -> str:
        return self.instance_name or self.api_url

    @classmethod
    def from_env(cls) -> "Config":
        """Settings for `run`; raises ConfigError when a required one is missing."""
        sink_broker, sink_port = split_host_port(env_str("MONITOR__SINK_BROKER"), 8883)
        return cls(
            api_url=_required("MONITOR__API_URL").rstrip("/"),
            api_key=_required("MONITOR__API_KEY"),
            channel_id=env_str("MONITOR__CHANNEL_ID", "LongFast"),
            mesh_id=_required("MONITOR__MESH_ID"),
            gateway_uuid=_required("MONITOR__GATEWAY_UUID"),
            gateway_node_id=int(_required("MONITOR__GATEWAY_NODE_ID")),
            psk_b64=_required("MONITOR__PSK_B64"),
            mqtt_broker=_required("MONITOR__MQTT_BROKER"),
            mqtt_port=env_int("MONITOR__MQTT_PORT", 8883),
            mqtt_user=env_str("MONITOR__MQTT_USER"),
            mqtt_pass=env_str("MONITOR__MQTT_PASS"),
            mqtt_ssl=env_bool("MONITOR__MQTT_SSL", True),
            mqtt_topic_prefix=_required("MONITOR__MQTT_TOPIC_PREFIX").rstrip("/"),
            sink_broker=sink_broker,
            sink_port=sink_port,
            sink_user=env_str("MONITOR__SINK_USER"),
            sink_pass=env_str("MONITOR__SINK_PASS"),
            sink_topic=env_str("MONITOR__SINK_TOPIC"),
            sink_ssl=env_bool("MONITOR__SINK_SSL", True),
            interval_s=env_int("MONITOR__INTERVAL_SECONDS", 300),
            http_timeout_s=env_int("MONITOR__HTTP_TIMEOUT", 10),
            ingest_timeout_s=env_int("MONITOR__INGEST_TIMEOUT", 180),
            poll_s=env_int("MONITOR__POLL_SECONDS", 5),
            failures_before_alert=max(1, env_int("MONITOR__FAILURES_BEFORE_ALERT", 2)),
            reminder_hours=env_int("MONITOR__REMINDER_HOURS", 6),
            email_check=env_bool("MONITOR__EMAIL_CHECK", True),
            instance_name=env_str("MONITOR__INSTANCE_NAME"),
            alert_emails=env_list("MONITOR__ALERT_EMAILS"),
            email_host=env_str("MONITOR__EMAIL_HOST"),
            email_port=env_int("MONITOR__EMAIL_PORT", 587),
            email_user=env_str("MONITOR__EMAIL_HOST_USER"),
            email_password=env_str("MONITOR__EMAIL_HOST_PASSWORD"),
            email_use_tls=env_bool("MONITOR__EMAIL_USE_TLS", True),
            email_use_ssl=env_bool("MONITOR__EMAIL_USE_SSL", False),
            email_from=env_str("MONITOR__EMAIL_FROM"),
            port=env_int("MONITOR__PORT", 8095),
            run_token=env_str("MONITOR__RUN_TOKEN"),
            run_min_interval_s=env_int("MONITOR__RUN_MIN_INTERVAL_SECONDS", 30),
        )
