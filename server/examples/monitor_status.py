#!/usr/bin/env python3
"""Show the server monitor's latest results, or run its checks now with --run.

See docs/monitoring.md.
"""
import argparse
import os
import sys

import requests

MONITOR_URL = os.environ.get("MONITOR_URL", "http://localhost:8095")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", nargs="?", const="", metavar="CHECK", help="run every check now, or only CHECK")
    parser.add_argument("--timeout", type=float, help="seconds to wait for the probe, with --run")
    parser.add_argument("--token", default=os.environ.get("MONITOR_RUN_TOKEN"), help="MONITOR__RUN_TOKEN, for --run")
    args = parser.parse_args()

    if args.run is None:
        resp = requests.get(f"{MONITOR_URL}/status", timeout=10)
    else:
        if not args.token:
            sys.exit("--run needs a token - pass --token or set MONITOR_RUN_TOKEN")
        path = f"/run/{args.run}" if args.run else "/run"
        params = {"timeout": args.timeout} if args.timeout else {}
        resp = requests.post(
            f"{MONITOR_URL}{path}", headers={"Authorization": f"Bearer {args.token}"}, params=params, timeout=300
        )
    if resp.status_code not in (200, 503):
        resp.raise_for_status()

    body = resp.json()
    cached = " (cached)" if body.get("cached") else ""
    print(f"{'OK' if body['ok'] else 'FAILING'}{cached}, checked at {body['checked_at']}, alerting={body['alerting']}")
    for name, check in body["checks"].items():
        latency = f"{check['latency_s']:.1f}s" if check["latency_s"] is not None else "-"
        print(f"  {'ok ' if check['ok'] else 'BAD'} {name:<18} {latency:>7}  {check['detail']}")


if __name__ == "__main__":
    main()
