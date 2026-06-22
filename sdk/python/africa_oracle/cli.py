"""afri-oracle — minimal CLI bound to the deployed API.

    afri-oracle health
    afri-oracle hunt --provider mtn --country GH
    afri-oracle quorum --min 2
"""

from __future__ import annotations

import argparse
import json
import sys

from . import Client, OracleError


def main() -> int:
    p = argparse.ArgumentParser(prog="afri-oracle", description=__doc__)
    p.add_argument("--url", help="Override AFRICA_ORACLE_URL")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")
    sub.add_parser("providers")

    h = sub.add_parser("hunt")
    h.add_argument("--provider", required=True)
    h.add_argument("--country", required=True)

    q = sub.add_parser("quorum")
    q.add_argument("--min", type=int, default=2)

    args = p.parse_args()
    client = Client(base_url=args.url) if args.url else Client()

    try:
        if args.cmd == "health":
            out = client.health()
        elif args.cmd == "providers":
            out = client.providers()
        elif args.cmd == "hunt":
            out = client.hunt(args.provider, args.country).__dict__
        elif args.cmd == "quorum":
            out = client.feeds_quorum(args.min).__dict__
        else:
            p.print_help()
            return 2
    except OracleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    json.dump(out, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
