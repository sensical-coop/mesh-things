FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY quality_worker/requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# The shared package, installed before the code so it is cached apart.
COPY mesh_things/ /tmp/mesh_things/
RUN pip install --no-cache-dir --no-deps /tmp/mesh_things && rm -rf /tmp/mesh_things

COPY quality_worker/ ./quality_worker/
COPY common/ ./common/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN useradd --create-home --uid 1000 worker && chown -R worker:worker /app
USER worker

CMD ["celery", "-A", "quality_worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
