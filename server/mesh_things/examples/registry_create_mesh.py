#!/usr/bin/env python3
"""Register a Mesh on the default broker under the authenticated owner, accepting its
mesh terms (read them first with --show-terms). Needs a Gateway too before decoding
starts - see docs/architecture.md#registered-gateways-only-gate."""
import argparse
import os
import sys

from mesh_things.client import MeshThings, terms_fields

API_URL = os.environ.get("MESH_THINGS_URL", "http://localhost")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.environ.get("MESH_THINGS_API_KEY"))
    parser.add_argument("--channel-id", default="LongFast")
    parser.add_argument("--psk-b64", default="", help="base64 channel PSK; empty string for a plaintext-only mesh")
    parser.add_argument("--label", default=None)
    parser.add_argument("--locale", choices=("en", "es"), default="en")
    parser.add_argument("--show-terms", action="store_true", help="print the mesh terms and exit")
    parser.add_argument("--accept-terms", action="store_true", help="accept every statement of the mesh terms")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("No API key - pass --api-key or set MESH_THINGS_API_KEY (see registry_create_owner.py)")

    api = MeshThings(API_URL, args.api_key)
    terms = api.get_terms("meshes", locale=args.locale)
    if args.show_terms and terms is None:
        print("This instance does not ask for terms.")
        return
    if args.show_terms:
        print(f"{terms['title']} ({terms['version']})\n\n{terms['description']}\n")
        for statement in terms["statements"]:
            print(f"  [{statement['id']}] {statement['text']}")
        print(f"\n{terms['footnote']}")
        return
    if terms is not None and not args.accept_terms:
        sys.exit("Read the terms with --show-terms, then pass --accept-terms to create the mesh")

    mesh = api.meshes.create(body={
        "channel_id": args.channel_id, "psk_b64": args.psk_b64, "label": args.label, **terms_fields(terms),
    })
    print(f"Registered mesh on channel {mesh['channel_id']!r}")
    print(f"  id={mesh['id']}  owner_id={mesh['owner_id']}")
    print("Export it to register a gateway against this mesh:")
    print(f"  export MESH_ID={mesh['id']}")


if __name__ == "__main__":
    main()
