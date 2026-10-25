FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl
COPY . .
RUN pip install --require-hashes -r requirements.lock && pip install --no-deps ./mesh_things .

ENV PYTHONUNBUFFERED=1