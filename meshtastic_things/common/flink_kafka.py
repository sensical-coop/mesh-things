"""Kafka source helpers for the Flink jobs."""


def committed_or_latest():
    """Resume from the group's committed offsets, or start at the end of a topic
    the group has never read.

    PyFlink's `committed_offsets` hands Java the OffsetResetStrategy shaded
    into the SQL connector jar, which the connector's method does not accept,
    so the unshaded enum from kafka-clients is passed through the gateway.
    """
    from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer
    from pyflink.java_gateway import get_gateway

    jvm = get_gateway().jvm
    initializer = jvm.org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer
    strategy = jvm.org.apache.kafka.clients.consumer.OffsetResetStrategy.LATEST
    return KafkaOffsetsInitializer(initializer.committedOffsets(strategy))
