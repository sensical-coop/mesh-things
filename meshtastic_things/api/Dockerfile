FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./

# Shared code
COPY common/ ./common/

# REGISTRY__SECRET_KEY has no runtime fallback
RUN REGISTRY__SECRET_KEY=build-time-only-unused python manage.py collectstatic --noinput

ENV PYTHONUNBUFFERED=1

# Non-root user
RUN useradd --create-home --uid 1000 api && chown -R api:api /app
USER api

# "readings" connects read-only and must not migrate nor seed; it overrides this CMD.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py provision_read_role && python manage.py seed_measurement_catalog && python manage.py seed_from_env && gunicorn api_project.wsgi:application --bind 0.0.0.0:8090 --workers 2"]
