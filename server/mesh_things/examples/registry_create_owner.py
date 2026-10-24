#!/usr/bin/env python3
"""Create a new owner ("sign up"), accepting the account terms. Save the returned
api_key - it is never shown again. Read the terms first with --show-terms. See
../../../docs/api-reference.md#owners."""
import argparse
import getpass
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
    parser.add_argument("--name")
    parser.add_argument("--email")
    parser.add_argument("--locale", choices=("en", "es"), default="en")
    parser.add_argument("--show-terms", action="store_true", help="print the account terms and exit")
    parser.add_argument("--accept-terms", action="store_true", help="accept every statement of the account terms")
    args = parser.parse_args()

    api = MeshThings(API_URL, api_key="")  # signing up needs no key
    terms = api.get_terms("account", locale=args.locale)
    if args.show_terms:
        if terms is None:
            print("This instance does not ask for terms.")
        else:
            print_terms(terms)
        return
    if terms is not None and not args.accept_terms:
        sys.exit("Read the terms with --show-terms, then pass --accept-terms to sign up")
    if not args.name or not args.email:
        sys.exit("--name and --email are required to sign up")

    owner = api.owners.create(body={
        "name": args.name, "email": args.email, "password": getpass.getpass("Password: "), **terms_fields(terms),
    })
    print(f"Created owner {owner['id']} ({owner['email']})")
    print("Save this API key - it is never shown again. Export it for the other examples:")
    print(f"  export MESH_THINGS_API_KEY={owner['api_key']}")


if __name__ == "__main__":
    main()
