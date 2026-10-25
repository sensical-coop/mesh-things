#!/usr/bin/env python3
"""Create an MQTT sink, change what it delivers, or renew its password.

A sink lets a service of your choice subscribe to the readings of the meshes and
devices you attach to it, on this instance's broker. Please read the sink terms with
--show-terms, then pass --accept-terms when you create the sink. The script prints the
credentials, which are shown only once. It needs the operator role.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings, ServerError, terms_fields

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def print_terms(terms: dict) -> None:
    print(f"{terms['title']} ({terms['version']})\n\n{terms['description']}\n")
    for statement in terms["statements"]:
        print(f"  [{statement['id']}] {statement['text']}")
    print(f"\n{terms['footnote']}")


def print_credentials(sink: dict) -> None:
    print(f"  broker:       {sink['broker']} (TLS)")
    print(f"  username:     {sink['username']}")
    print(f"  password:     {sink['password']}   <- shown once")
    print(f"  topic filter: {sink['topic_filter']}")
    print(f"\nexport SINK_ID={sink['id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="an operator's key")
    parser.add_argument("--locale", choices=("en", "es"), default="en", help="language of the terms")
    parser.add_argument("--show-terms", action="store_true", help="print the sink terms and exit")
    parser.add_argument("--accept-terms", action="store_true", help="accept every statement of the sink terms")
    parser.add_argument("--label")
    parser.add_argument(
        "--stream", action="append", choices=("decoded", "derived", "alarms"),
        help="repeat for several; defaults to decoded on create",
    )
    parser.add_argument("--mesh-id", action="append", help="send every node of this mesh; repeat for several")
    parser.add_argument("--device-uuid", action="append", help="send this one device; repeat for several")
    parser.add_argument("--update", metavar="SINK_ID", help="replace the given fields of an existing sink")
    parser.add_argument("--rotate", metavar="SINK_ID", help="issue a new password and disconnect the consumer")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")
    api = MeshThings(API_URL, args.api_key)

    if args.rotate:
        print(f"New credentials for sink {args.rotate}:")
        print_credentials(api.sinks.credentials_create(args.rotate))
        return

    fields = {}
    if args.label is not None:
        fields["label"] = args.label
    if args.stream:
        fields["streams"] = args.stream
    # An empty value sends an empty list, detaching them all.
    if args.mesh_id is not None:
        fields["mesh_ids"] = [m for m in args.mesh_id if m]
    if args.device_uuid is not None:
        fields["device_ids"] = [d for d in args.device_uuid if d]

    if args.update:
        # A list sent replaces the sink's current one; omitted fields stay as they are.
        sink = api.sinks.update(args.update, body=fields)
        print(f"Updated sink {sink['id']}: streams {sink['streams']}, meshes {sink['mesh_ids']}, devices {sink['device_ids']}")
        return

    terms = api.get_terms("sinks", locale=args.locale)
    if args.show_terms and terms is None:
        print("This instance does not ask for terms.")
        return
    if args.show_terms:
        print_terms(terms)
        return
    if terms is not None and not args.accept_terms:
        sys.exit("Please read the terms with --show-terms, then pass --accept-terms to create the sink.")

    try:
        sink = api.sinks.create(body={**fields, **terms_fields(terms)})
    except ServerError as e:
        sys.exit(f"The broker could not be set up: {e.detail}")
    print(f"Created sink {sink['id']}: streams {sink['streams']}, meshes {sink['mesh_ids']}, devices {sink['device_ids']}")
    print_credentials(sink)


if __name__ == "__main__":
    main()
