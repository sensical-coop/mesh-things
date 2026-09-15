"""Offset handling shared by the registry's Kafka consumers.

poll() advances the fetch position, so committing past a record that failed for
a transient reason loses it silently. Bad data must still be skipped, though,
or one unparseable record blocks the partition forever.
"""
from unittest.mock import MagicMock

from django.db import IntegrityError, OperationalError
from django.test import SimpleTestCase

from registry.consumer_loop import consume_batch


class _Record:
    def __init__(self, offset, value=b"{}"):
        self.offset = offset
        self.value = value


class _Partition:
    def __init__(self, partition=0):
        self.topic = "mesh.devices.v1"
        self.partition = partition


class ConsumeBatchTests(SimpleTestCase):
    def setUp(self):
        self.consumer = MagicMock()
        self.tp = _Partition()

    def _run(self, records, handle):
        return consume_batch(self.consumer, {self.tp: records}, handle, "upsert thing")

    def test_clean_batch_commits_and_does_not_rewind(self):
        handled = []
        rewound = self._run([_Record(10), _Record(11)], handled.append)

        self.assertFalse(rewound)
        self.assertEqual(len(handled), 2)
        self.consumer.commit.assert_called_once()
        self.consumer.seek.assert_not_called()

    def test_database_outage_rewinds_to_the_failed_record(self):
        def handle(value):
            raise OperationalError("could not connect to server")

        rewound = self._run([_Record(10), _Record(11)], handle)

        self.assertTrue(rewound)
        self.consumer.seek.assert_called_once_with(self.tp, 10)
        self.consumer.commit.assert_called_once()

    def test_outage_stops_reading_the_partition_at_the_failure(self):
        seen = []

        def handle(value):
            seen.append(value)
            if len(seen) == 2:
                raise OperationalError("server closed the connection")

        self._run([_Record(10), _Record(11), _Record(12)], handle)

        # Record 12 must not be handled ahead of 11, which is about to be retried.
        self.assertEqual(len(seen), 2)
        self.consumer.seek.assert_called_once_with(self.tp, 11)

    def test_bad_data_is_skipped_not_retried(self):
        seen = []

        def handle(value):
            seen.append(value)
            if len(seen) == 1:
                raise ValueError("not json")

        rewound = self._run([_Record(10), _Record(11)], handle)

        self.assertFalse(rewound)
        self.assertEqual(len(seen), 2)  # kept going
        self.consumer.commit.assert_called_once()
        self.consumer.seek.assert_not_called()

    def test_integrity_error_is_not_retried(self):
        # A constraint violation fails identically on every retry, so rewinding
        # onto it would block the partition forever.
        def handle(value):
            raise IntegrityError("duplicate key value violates unique constraint")

        rewound = self._run([_Record(10)], handle)

        self.assertFalse(rewound)
        self.consumer.seek.assert_not_called()
        self.consumer.commit.assert_called_once()

    def test_a_tombstone_is_ignored(self):
        handled = []
        self._run([_Record(10, value=None), _Record(11)], handled.append)

        self.assertEqual(len(handled), 1)
        self.consumer.commit.assert_called_once()

    def test_only_the_failing_partition_is_rewound(self):
        other = _Partition(1)

        def handle(value):
            if value == b"boom":
                raise OperationalError("down")

        messages = {
            self.tp: [_Record(10), _Record(11, value=b"boom")],
            other: [_Record(40)],
        }
        rewound = consume_batch(self.consumer, messages, handle, "upsert thing")

        self.assertTrue(rewound)
        self.consumer.seek.assert_called_once_with(self.tp, 11)
        self.consumer.commit.assert_called_once()
