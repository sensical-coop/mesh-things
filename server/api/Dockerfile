FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The shared package, installed before the code so it is cached apart.
COPY mesh_things/ /tmp/mesh_things/
RUN pip install --no-cache-dir "/tmp/mesh_things[codec]" && rm -rf /tmp/mesh_things

COPY api/ ./

# Server-only shared code
COPY common/ ./common/

# REGISTRY__SECRET_KEY has no runtime fallback
RUN REGISTRY__SECRET_KEY=build-time-only-unused python manage.py collectstatic --noinput

ENV PYTHONUNBUFFERED=1

# Non-root user
RUN useradd --create-home --uid 1000 api && chown -R api:api /app
USER api

# "readings" connects read-only and must not migrate nor seed; it overrides this CMD.
# Workers are recycled because their memory grows about 18MiB an hour (issue #56);
# the access log is there to find which requests cause it.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py provision_read_role && python manage.py seed_measurement_catalog && python manage.py seed_from_env && gunicorn api_project.wsgi:application --bind 0.0.0.0:8090 --workers 2 --max-requests 1000 --max-requests-jitter 100 --access-logfile -"]
