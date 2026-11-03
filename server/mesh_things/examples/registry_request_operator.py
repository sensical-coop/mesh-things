#!/usr/bin/env python3
"""Ask for the operator role, or check on your request.

Every superuser is emailed your request, and you are emailed the decision. You can
have one pending request at a time.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings, NotFound

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--reason", help="file a request with this reason")
    action.add_argument("--status", action="store_true", help="show the latest request")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")
    api = MeshThings(API_URL, args.api_key)

    if args.reason:
        request = api.owners.me_operator_request_create(body={"reason": args.reason})
        print(f"Operator request {request['id']} filed, superusers have been emailed")
        return

    try:
        request = api.owners.me_operator_request_get()
    except NotFound:
        print("No operator request filed yet")
        return
    print(f"Operator request {request['id']}: {request['status']}")
    if request["decision_note"]:
        print(f"  note: {request['decision_note']}")


if __name__ == "__main__":
    main()
