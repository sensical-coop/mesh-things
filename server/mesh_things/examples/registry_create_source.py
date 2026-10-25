#!/usr/bin/env python3
"""Create a source: a remote MQTT broker whose traffic this instance brings in.

Creating one accepts the current source terms on your behalf, so please read them
first with --show-terms. It needs the operator role. A superuser can grant the role in
the same step with --grant-operator. The script prints a SOURCE_ID to use with
registry_attach_mesh_to_source.py.
"""
import argparse
import os
import sys

from mesh_things.client import MeshThings, terms_fields

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def print_terms(terms: dict) -> None:
    print(f"{terms['title']} ({terms['version']})\n\n{terms['description']}\n")
    for statement in terms["statements"]:
        print(f"  [{statement['id']}] {statement['text']}")
    print(f"\n{terms['footnote']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"), help="an operator's key")
    parser.add_argument("--server", help="remote broker as host:port")
    parser.add_argument("--topic", help="remote topic filter, e.g. msh/EU_868/2/e/MyChannel/#")
    parser.add_argument("--locale", choices=("en", "es"), default="en", help="language of the terms")
    parser.add_argument("--show-terms", action="store_true", help="print the source terms and exit")
    parser.add_argument("--accept-terms", action="store_true", help="accept every statement of the source terms")
    parser.add_argument("--no-ssl", action="store_true", help="connect to the remote broker without TLS")
    parser.add_argument("--username")
    parser.add_argument("--password", help="write-only: never returned by the API")
    parser.add_argument("--qos", type=int, choices=(0, 1), default=1)
    parser.add_argument("--label")
    parser.add_argument("--grant-operator", metavar="OWNER_ID", help="make this owner an operator first")
    parser.add_argument("--superuser-api-key", default=os.environ.get("SUPERUSER_API_KEY"))
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Please pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py).")
    if args.grant_operator and not args.superuser_api_key:
        sys.exit("Please pass --superuser-api-key or set SUPERUSER_API_KEY to use --grant-operator.")

    api = MeshThings(API_URL, args.api_key)
    terms = api.get_terms("sources", locale=args.locale)
    if args.show_terms and terms is None:
        print("This instance does not ask for terms.")
        return
    if args.show_terms:
        print_terms(terms)
        return
    if terms is not None and not args.accept_terms:
        sys.exit("Please read the terms with --show-terms, then pass --accept-terms to create the source.")
    if not args.server or not args.topic:
        sys.exit("Please pass --server and --topic to create a source.")

    # Only once the create is known to be valid, so a terms-only or invalid run changes no role.
    if args.grant_operator:
        owner = MeshThings(API_URL, args.superuser_api_key).owners.update(args.grant_operator, body={"role": "operator"})
        print(f"{owner['email']} is now {owner['role']}")

    source = api.sources.create(body={
        **terms_fields(terms),
        "server": args.server,
        "topic": args.topic,
        "ssl": not args.no_ssl,
        "username": args.username,
        "password": args.password,
        "qos": args.qos,
        "label": args.label,
    })
    print(f"Created source {source['id']}: {source['server']} {source['topic']}")
    # An unreachable remote is not an error; it stays disconnected until it connects.
    print(f"  bridge status: {source['status']}")
    print(f"\nexport SOURCE_ID={source['id']}")


if __name__ == "__main__":
    main()
