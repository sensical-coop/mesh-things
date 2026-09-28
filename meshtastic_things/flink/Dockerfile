FROM flink:1.19.2-scala_2.12-java17

USER root

# The base image's Java 17 runtime (JAVA_HOME=/opt/java/openjdk) runs Flink and
# PyFlink; nothing here is compiled, so no JDK or build toolchain is needed.
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends python3 python3-venv && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/bin/python3 /usr/bin/python

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-kafka/3.3.0-1.19/flink-connector-kafka-3.3.0-1.19.jar && \
    wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.19/flink-sql-connector-kafka-3.3.0-1.19.jar && \
    wget -P /opt/flink/lib/ https://repo.maven.apache.org/maven2/org/apache/kafka/kafka-clients/3.2.3/kafka-clients-3.2.3.jar

# Dependencies are installed before the source is copied, so a code change
# does not reinstall PyFlink.
WORKDIR /build
COPY flink/requirements-flink.txt flink/
RUN pip install --no-cache-dir -r flink/requirements-flink.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir --no-deps .

RUN mkdir -p /opt/flink/checkpoints /opt/flink/savepoints && chown -R flink:flink /opt/flink/checkpoints /opt/flink/savepoints

WORKDIR /opt/flink/usrlib
COPY flink/decode_job.py flink/postprocessing_job.py flink/pattern_detection_job.py flink/absence_detection_job.py .
# Detached submission and the watchdog - see the scripts.
COPY --chmod=0755 flink/submit-job.sh flink/watch-jobs.sh .

USER flink
