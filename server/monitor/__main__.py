"""`python -m monitor [run]` starts the monitor; `python -m monitor setup` provisions it."""
import argparse
import asyncio
import os
import sys

import structlog
from aiohttp import web
from mesh_things.client import ApiError

from monitor.checks import Checker
from monitor.config import Config, ConfigError
from monitor.server import build_app
from monitor.service import Monitor
from monitor.setup import setup

log = structlog.get_logger()


async def serve(config: Config) -> None:
    monitor = Monitor(config, Checker(config))
    runner = web.AppRunner(build_app(monitor))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.port).start()
    log.info("monitor_started", port=config.port, checks=monitor.names, on_demand=bool(config.run_token))
    await monitor.loop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="monitor", description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="run the checks and serve the status API (default)")
    setup_parser = commands.add_parser("setup", help="create the monitor's mesh, gateway and optional sink")
    setup_parser.add_argument("--api-url", default=os.environ.get("MONITOR__API_URL"))
    setup_parser.add_argument("--api-key", default=os.environ.get("MONITOR__API_KEY"), help="a verified owner's key")
    setup_parser.add_argument("--channel-id", default=os.environ.get("MONITOR__CHANNEL_ID") or "LongFast")
    setup_parser.add_argument("--accept-terms", action="store_true", help="accept the mesh (and sink) terms")
    setup_parser.add_argument("--sink", action="store_true", help="also create a sink; needs the operator role")
    args = parser.parse_args()

    if args.command == "setup":
        if not args.api_url or not args.api_key:
            sys.exit("Pass --api-url and --api-key, or set MONITOR__API_URL and MONITOR__API_KEY")
        try:
            setup(args.api_url, args.api_key, args.channel_id, args.accept_terms, args.sink)
        except ApiError as e:
            sys.exit(f"Registry refused: {e}")
        return

    try:
        config = Config.from_env()
    except ConfigError as e:
        sys.exit(f"{e}; run `python -m monitor setup` first")
    asyncio.run(serve(config))


if __name__ == "__main__":
    main()
