"""Command line front end: iporigin 8.8.8.8"""

import argparse
import json
import sys

from . import __version__, classify, dataset_info
from .core import DatasetError


def _read_addresses(args):
    if args.ip:
        return args.ip
    # No arguments: read from stdin, so `cut -f1 access.log | iporigin` works.
    return (line.strip() for line in sys.stdin if line.strip())


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="iporigin",
        description="Classify IP addresses as hosting, CDN, VPN or unknown.",
    )
    parser.add_argument("ip", nargs="*", help="addresses to classify (default: stdin)")
    parser.add_argument("--json", action="store_true", help="output JSON lines")
    parser.add_argument(
        "--online",
        action="store_true",
        help="also query the free Unblock Master API (covers consumer VPNs)",
    )
    parser.add_argument(
        "--datacenter-only",
        action="store_true",
        help="print only addresses that are in a datacenter range",
    )
    parser.add_argument("--info", action="store_true", help="show dataset provenance")
    parser.add_argument("--version", action="version", version="iporigin " + __version__)
    args = parser.parse_args(argv)

    try:
        if args.info:
            print(json.dumps(dataset_info(), indent=2, sort_keys=True))
            return 0

        lookup = classify
        if args.online:
            from .online import classify_online as lookup  # noqa: N813

        exit_code = 0
        for raw in _read_addresses(args):
            try:
                origin = lookup(raw)
            except ValueError as exc:
                print("%s: %s" % (raw, exc), file=sys.stderr)
                exit_code = 2
                continue

            if args.datacenter_only and not origin.is_datacenter:
                continue

            if args.json:
                print(json.dumps({
                    "ip": origin.ip,
                    "kind": origin.kind,
                    "provider": origin.provider,
                    "source": origin.source,
                    "is_datacenter": origin.is_datacenter,
                }))
            else:
                print("%-40s %-9s %s" % (origin.ip, origin.kind, origin.provider))
        return exit_code

    except DatasetError as exc:
        print("iporigin: %s" % exc, file=sys.stderr)
        return 1
    except BrokenPipeError:
        # `iporigin < big.txt | head` is a normal thing to do.
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
