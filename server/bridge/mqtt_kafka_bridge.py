import asyncio
import os
import sys
import argparse
from bridge.mqtt_handler import MQTTHandler, retire_session, subscription_filters
from tools.env import get_bool_env
from dotenv import load_dotenv

import structlog
log = structlog.get_logger()

async def create_tasks(mqtt_handler):

    topics = subscription_filters(os.environ['MQTT_BRIDGE__TOPIC'])
    await asyncio.to_thread(mqtt_handler.load_gateway_sources)
    log.info('Creating bridge tasks...')
    async with asyncio.TaskGroup() as tg:
        tg.create_task(mqtt_handler.bridge_mqtt_kafka(topics=topics, shared_sub=get_bool_env('MQTT_BRIDGE__SHARED_SUBS')))
        tg.create_task(mqtt_handler.follow_gateway_sources())
        tg.create_task(mqtt_handler.monitor_publish())
        tg.create_task(mqtt_handler.start_health_server())
        tg.create_task(mqtt_handler.producer_health.monitor())

        log.info("Looping forever...")

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--local", default=False, dest='local', action='store_true', help="Local development mode"
    )
    parser.add_argument(
        "--retire-session",
        metavar="CLIENT_ID",
        help=(
            "Delete this client id's session on the broker and exit. Use when "
            "removing a member from the shared group: its session otherwise "
            "keeps taking a share of the messages and queueing them forever."
        ),
    )

    args = parser.parse_args()

    if args.retire_session:
        if args.local:
            load_dotenv("../.env")
        asyncio.run(retire_session(os.environ['MQTT_BRIDGE__BROKER'], args.retire_session))
        return

    if args.local:
        load_dotenv("../.env")
        kafka_bootstrap_server=os.environ['KAFKA_BOOTSTRAP_LOCAL']
        log.warn('Local development mode')
    else:
        log.warn("Set environment file manually")
        kafka_bootstrap_server=os.environ['KAFKA_BOOTSTRAP']

    mqtt_handler = MQTTHandler(broker=os.environ['MQTT_BRIDGE__BROKER'], kafka_bootstrap_server=kafka_bootstrap_server)

    log.info("Starting MQTT bridge...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(create_tasks(mqtt_handler))
    except KeyboardInterrupt:
        log.info("Program interrupted by user")
        sys.exit(0)