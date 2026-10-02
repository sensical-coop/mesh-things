"""The Kafka events registry publishes, and the keys consumers look them up by."""
import json
from unittest.mock import MagicMock

from registry.kafka_publisher import (
    KeyEventPublisher,
    device_intervals_kafka_key,
    gateway_kafka_key,
    measurement_alarms_kafka_key,
    node_rejection_kafka_key,
    postprocessing_kafka_key,
)
from registry.models import (
    Device,
    DeviceTelemetryVariant,
    Measurement,
    MeasurementType,
    Mesh,
    TelemetryVariant,
    TelemetryVariantMeasurement,
)

from .helpers import RegistryTestCase

KEYS_TOPIC = "mesh.keys.v1"
REJECTIONS_TOPIC = "mesh.node_rejections.v1"
QUALITY_CONFIG_TOPIC = "mesh.quality_config.v1"
POSTPROCESSING_CONFIG_TOPIC = "mesh.postprocessing_config.v1"


class KafkaContractTestCase(RegistryTestCase):
    """Real publisher, fake producer, so the bodies are what would go on the wire."""

    def setUp(self):
        super().setUp()
        self.owner = self.create_owner()
        self.mesh = Mesh.objects.create(
            channel_id="LongFast", psk_b64="AQ==", owner_id=self.owner["id"]
        )
        self.device = Device.objects.create(device_id=431637602, mesh=self.mesh, is_gateway=True)

        publisher = KeyEventPublisher.__new__(KeyEventPublisher)
        publisher._keys_topic = KEYS_TOPIC
        publisher._node_rejections_topic = REJECTIONS_TOPIC
        publisher._quality_config_topic = QUALITY_CONFIG_TOPIC
        publisher._postprocessing_config_topic = POSTPROCESSING_CONFIG_TOPIC
        publisher._producer = MagicMock()
        self.publisher = publisher

    def published(self):
        """(topic, key, event) of the single send made."""
        self.publisher._producer.send.assert_called_once()
        call = self.publisher._producer.send.call_args
        return call.args[0], call.kwargs["key"], call.kwargs["value"]


class GatewayKeyEventTests(KafkaContractTestCase):
    """Both decode paths key gateway state by the event key, then read psk_b64/mesh_id."""

    def test_upsert_carries_what_the_decoder_needs_to_decrypt(self):
        self.publisher.publish_gateway_upsert(self.device, self.mesh)

        topic, key, event = self.published()

        self.assertEqual(topic, KEYS_TOPIC)
        self.assertEqual(event["kind"], "gateway_key")
        self.assertEqual(event["op"], "upsert")
        # common/decode.py reads exactly these two out of the stored state.
        self.assertEqual(event["psk_b64"], "AQ==")
        self.assertEqual(event["mesh_id"], str(self.mesh.id))
        self.assertEqual(event["key"], key)

    def test_the_key_is_the_gateway_id_the_envelope_carries(self):
        """Looked up as gateway_state[ServiceEnvelope.gateway_id]: hex, not decimal."""
        self.publisher.publish_gateway_upsert(self.device, self.mesh)

        _, key, event = self.published()

        self.assertEqual(key, "!19ba4462")
        self.assertEqual(key, gateway_kafka_key(self.device))
        self.assertEqual(event["gateway_id"], key)

    def test_delete_is_a_same_key_tombstone(self):
        """A different key would leave the compacted topic serving the old PSK."""
        self.publisher.publish_gateway_upsert(self.device, self.mesh)
        _, upsert_key, _ = self.published()
        self.publisher._producer.send.reset_mock()

        self.publisher.publish_gateway_delete(self.device)
        _, delete_key, event = self.published()

        self.assertEqual(delete_key, upsert_key)
        self.assertEqual(event["op"], "delete")


class NodeRejectionEventTests(KafkaContractTestCase):
    def test_the_key_is_mesh_id_colon_device_id(self):
        """NODE_REJECTED_STATE is keyed by it; a node number alone is not unique."""
        node = Device.objects.create(device_id=7, mesh=self.mesh, is_gateway=False)

        self.publisher.publish_node_reject(node)
        topic, key, event = self.published()

        self.assertEqual(topic, REJECTIONS_TOPIC)
        self.assertEqual(key, f"{self.mesh.id}:7")
        self.assertEqual(key, node_rejection_kafka_key(node))
        self.assertEqual(event["kind"], "node_rejection")
        self.assertEqual(event["op"], "upsert")

    def test_unreject_tombstones_the_same_key(self):
        node = Device.objects.create(device_id=7, mesh=self.mesh, is_gateway=False)

        self.publisher.publish_node_unreject(node)
        _, key, event = self.published()

        self.assertEqual(key, node_rejection_kafka_key(node))
        self.assertEqual(event["op"], "delete")


class QualityConfigEventTests(KafkaContractTestCase):
    """One topic, two key shapes, told apart by `kind`."""

    def test_variant_config_is_keyed_by_channel(self):
        """Looked up by the channel computed from a reading, so "<measurement>.<field>"."""
        variant = TelemetryVariant.objects.create(
            payload_kind="telemetry:environment_metrics", default_reading_interval_seconds=900
        )
        measurement_type = MeasurementType.objects.create(
            payload_kind="telemetry:environment_metrics", field_name="temperature"
        )
        link = TelemetryVariantMeasurement.objects.create(
            telemetry_variant=variant, measurement_type=measurement_type
        )

        self.publisher.publish_variant_measurement_config(link)
        topic, key, event = self.published()

        self.assertEqual(topic, QUALITY_CONFIG_TOPIC)
        self.assertEqual(key, "environment_metrics.temperature")
        self.assertEqual(event["kind"], "variant_config")
        # The value pattern_detection_job reads off this entry
        self.assertEqual(event["default_reading_interval_seconds"], 900)

    def test_a_computed_channels_config_keys_the_same_way(self):
        """The namespace is dropped, so every kind yields the same key shape."""
        variant = TelemetryVariant.objects.create(payload_kind="computed:quality")
        measurement_type = MeasurementType.objects.create(
            payload_kind="computed:quality", field_name="completeness_ratio"
        )
        link = TelemetryVariantMeasurement.objects.create(
            telemetry_variant=variant, measurement_type=measurement_type
        )

        self.publisher.publish_variant_measurement_config(link)
        _, key, _ = self.published()

        self.assertEqual(key, "quality.completeness_ratio")

    def test_device_intervals_are_keyed_by_mesh_and_device(self):
        """absence_detection_job does state.get(f"{mesh_id}:{device_id}")."""
        self.device.reading_interval_seconds = 300
        self.device.publish_interval_seconds = 900
        self.device.save()

        self.publisher.publish_device_intervals(self.device)
        topic, key, event = self.published()

        self.assertEqual(topic, QUALITY_CONFIG_TOPIC)
        self.assertEqual(key, f"{self.mesh.id}:{self.device.device_id}")
        self.assertEqual(key, device_intervals_kafka_key(self.device))
        self.assertEqual(event["kind"], "device_intervals")
        self.assertEqual(event["reading_interval_seconds"], 300)
        self.assertEqual(event["publish_interval_seconds"], 900)

    def test_the_three_key_shapes_never_collide(self):
        """They share one compacted topic."""
        channel_key = "environment_metrics.temperature"
        device_key = device_intervals_kafka_key(self.device)
        measurement_key = measurement_alarms_kafka_key(self.device, channel_key)

        self.assertNotIn(":", channel_key)
        self.assertNotIn(".", device_key)
        self.assertEqual(measurement_key.count(":"), 2)
        self.assertIn(".", measurement_key)
        self.assertEqual(len({channel_key, device_key, measurement_key}), 3)

    def test_the_catalog_alarm_default_rides_on_the_variant_config(self):
        variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")
        measurement_type = MeasurementType.objects.create(
            payload_kind="telemetry:environment_metrics", field_name="barometric_pressure"
        )
        link = TelemetryVariantMeasurement.objects.create(
            telemetry_variant=variant, measurement_type=measurement_type,
            default_enabled_detectors=["range"],
        )

        self.publisher.publish_variant_measurement_config(link)
        _, _, event = self.published()

        self.assertEqual(event["default_enabled_detectors"], ["range"])

    def test_the_absence_switch_rides_on_the_device_intervals(self):
        """absence has no channel, so it cannot use the per-measurement key."""
        self.device.absence_detection_enabled = True
        self.device.publish_interval_seconds = 900
        self.device.save()

        self.publisher.publish_device_intervals(self.device)
        _, _, event = self.published()

        self.assertTrue(event["absence_detection_enabled"])

    def test_clearing_both_intervals_tombstones_the_entry(self):
        self.device.reading_interval_seconds = None
        self.device.publish_interval_seconds = None
        self.device.save()

        self.publisher.publish_device_intervals(self.device)
        _, _, event = self.published()

        self.assertEqual(event["op"], "delete")


class MeasurementAlarmEventTests(KafkaContractTestCase):
    """The per-device override pattern_detection_job looks up alongside the channel config."""

    def _measurement(self, enabled_detectors, valid_min=None, valid_max=None):
        variant = TelemetryVariant.objects.create(payload_kind="telemetry:environment_metrics")
        measurement_type = MeasurementType.objects.create(
            payload_kind="telemetry:environment_metrics", field_name="wind_speed"
        )
        dtv = DeviceTelemetryVariant.objects.create(device=self.device, telemetry_variant=variant)
        return Measurement.objects.create(
            device_telemetry_variant=dtv, measurement_type=measurement_type,
            enabled_detectors=enabled_detectors, valid_min=valid_min, valid_max=valid_max,
        )

    def test_the_key_is_mesh_device_and_channel(self):
        measurement = self._measurement(["range"])

        self.publisher.publish_measurement_alarms(self.device, measurement)
        topic, key, event = self.published()

        self.assertEqual(topic, QUALITY_CONFIG_TOPIC)
        self.assertEqual(key, f"{self.mesh.id}:{self.device.device_id}:environment_metrics.wind_speed")
        self.assertEqual(key, measurement_alarms_kafka_key(self.device, "environment_metrics.wind_speed"))
        self.assertEqual(event["kind"], "measurement_alarms")
        self.assertEqual(event["enabled_detectors"], ["range"])
        self.assertEqual(event["op"], "upsert")

    def test_an_empty_list_is_published_rather_than_tombstoned(self):
        """[] silences the channel, which the job has to be told about"""
        measurement = self._measurement([])

        self.publisher.publish_measurement_alarms(self.device, measurement)
        _, _, event = self.published()

        self.assertEqual(event["op"], "upsert")
        self.assertEqual(event["enabled_detectors"], [])

    def test_valid_min_and_valid_max_are_published(self):
        """Range has no catalog default - this event is the only place they come from."""
        measurement = self._measurement(["range"], valid_min=-40, valid_max=85)

        self.publisher.publish_measurement_alarms(self.device, measurement)
        _, _, event = self.published()

        self.assertEqual(event["valid_min"], -40)
        self.assertEqual(event["valid_max"], 85)
        self.assertEqual(event["op"], "upsert")

    def test_a_range_set_without_enabled_detectors_still_upserts(self):
        """Regression: a device inheriting the catalog default
        while also having its own range configured must not lose it."""
        measurement = self._measurement(None, valid_min=-40, valid_max=85)

        self.publisher.publish_measurement_alarms(self.device, measurement)
        _, _, event = self.published()

        self.assertEqual(event["op"], "upsert")
        self.assertEqual(event["valid_min"], -40)

    def test_clearing_everything_tombstones_the_entry(self):
        measurement = self._measurement(None, valid_min=None, valid_max=None)

        self.publisher.publish_measurement_alarms(self.device, measurement)
        _, _, event = self.published()

        self.assertEqual(event["op"], "delete")

    def test_clearing_the_override_tombstones_it_back_to_the_default(self):
        measurement = self._measurement(None)

        self.publisher.publish_measurement_alarms(self.device, measurement)
        _, _, event = self.published()

        self.assertEqual(event["op"], "delete")


class PostprocessingPlansEventTests(KafkaContractTestCase):
    """The stream job holds one entry per device and replaces it whole."""

    PLAN = {"id": "pp", "blueprint_id": "bp", "blueprint_version": 1, "tolerance_seconds": 30.0, "steps": []}

    def test_plans_are_keyed_by_mesh_and_device(self):
        self.publisher.publish_postprocessing_plans(self.device, [self.PLAN])

        topic, key, event = self.published()
        self.assertEqual(topic, POSTPROCESSING_CONFIG_TOPIC)
        self.assertEqual(key, f"{self.mesh.id}:{self.device.device_id}")
        self.assertEqual(key, postprocessing_kafka_key(self.device))
        self.assertEqual(event["kind"], "postprocessing_plans")
        self.assertEqual(event["op"], "upsert")
        self.assertEqual(event["plans"], [self.PLAN])
        self.assertEqual(event["device_id"], self.device.device_id)

    def test_no_plans_tombstones_the_entry(self):
        self.publisher.publish_postprocessing_plans(self.device, [])

        _, _, event = self.published()
        self.assertEqual(event["op"], "delete")
        self.assertEqual(event["plans"], [])

    def test_the_event_round_trips_through_json(self):
        self.publisher.publish_postprocessing_plans(self.device, [self.PLAN])

        _, _, event = self.published()
        self.assertEqual(json.loads(json.dumps(event))["plans"][0]["id"], "pp")


class WireVocabularyTests(KafkaContractTestCase):
    """The API's uuid/node_id rename deliberately did not reach the wire format."""

    def test_events_speak_device_id_not_the_apis_node_id(self):
        for publish in (
            lambda: self.publisher.publish_gateway_upsert(self.device, self.mesh),
            lambda: self.publisher.publish_gateway_delete(self.device),
            lambda: self.publisher.publish_device_intervals(self.device),
            lambda: self.publisher.publish_postprocessing_plans(self.device, []),
        ):
            with self.subTest(publish=publish):
                self.publisher._producer.send.reset_mock()
                publish()
                _, _, event = self.published()
                self.assertIn("device_id", event)
                self.assertNotIn("node_id", event)
                self.assertNotIn("uuid", event)

    def test_every_event_is_json_serialisable(self):
        """A UUID that slips in raises only at publish time, inside the request."""
        self.publisher.publish_gateway_upsert(self.device, self.mesh)
        _, _, event = self.published()

        json.dumps(event)  # would raise on a non-serialisable value
        self.assertIsInstance(event["mesh_id"], str)
