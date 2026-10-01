FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY monitor/ ./monitor/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN useradd --create-home --uid 1000 monitor && chown -R monitor:monitor /app
USER monitor

CMD ["python", "-m", "monitor", "run"]
