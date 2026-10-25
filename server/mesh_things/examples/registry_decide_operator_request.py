#!/usr/bin/env python3
"""List operator requests and approve or reject them, with a superuser key.

Approving makes the requester an operator, and the requester is emailed either
decision. See docs/api-reference.md#requesting-the-role.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("SUPERUSER_API_KEY"))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", nargs="?", const="pending", metavar="STATUS",
                        help="pending (default), approved, rejected or all")
    action.add_argument("--approve", metavar="REQUEST_ID")
    action.add_argument("--reject", metavar="REQUEST_ID")
    parser.add_argument("--note", default="", help="message to the requester")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("No API key - pass --api-key or set SUPERUSER_API_KEY")
    api = MeshThings(API_URL, args.api_key)

    if args.list:
        for request in api.operator_requests.list(status=args.list):
            print(f"{request['id']}  {request['status']:<8}  {request['owner_name']} <{request['owner_email']}>")
            print(f"    {request['reason']}")
        return

    decision, request_id = ("approve", args.approve) if args.approve else ("reject", args.reject)
    request = api.operator_requests.update(request_id, body={"decision": decision, "note": args.note})
    # The decision stands even if the email fails to send.
    print(f"Operator request {request['id']} {request['status']}; the requester is emailed the decision")


if __name__ == "__main__":
    main()
