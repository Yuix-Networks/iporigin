#!/usr/bin/env python3
"""Compile the published provider feeds into src/iporigin/data/ranges.bin.

Run it by hand or let .github/workflows/update-data.yml do it weekly:

    python tools/build_dataset.py

Format (all integers little-endian):

    magic     8s   b"IPORIGIN"
    version   H    format version, currently 1
    built_at  Q    unix timestamp of the build
    n_labels  H
    n_v4      I
    n_v6      I
    labels         n_labels x (H length + utf-8 "provider\\tkind")
    v4 table       n_v4 x (I start, I end, H label)
    v6 table       n_v6 x (16s start, 16s end, H label)

Ranges are stored as inclusive start/end integers rather than CIDR prefixes
because a lookup is then one bisect over a sorted column, with no prefix
arithmetic at query time. They are sorted by start and merged where a
provider's own feed overlaps itself, which the cloud feeds do constantly.
"""

import ipaddress
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sources import SOURCES  # noqa: E402

MAGIC = b"IPORIGIN"
VERSION = 1
OUT = Path(__file__).parent.parent / "src" / "iporigin" / "data" / "ranges.bin"


def collect():
    """Fetch every source. Returns (v4, v6) lists of (start, end, label)."""
    v4, v6 = [], []
    for name, (kind, fetch) in SOURCES.items():
        label = "%s\t%s" % (name, kind)
        count = 0
        try:
            for prefix in fetch():
                try:
                    net = ipaddress.ip_network(prefix.strip(), strict=False)
                except ValueError:
                    continue
                record = (
                    int(net.network_address),
                    int(net.broadcast_address),
                    label,
                )
                (v4 if net.version == 4 else v6).append(record)
                count += 1
        except Exception as exc:  # noqa: BLE001 — see module docstring
            print("  !! %-18s skipped: %s" % (name, exc), file=sys.stderr)
            continue
        print("  %-18s %6d prefixes" % (name, count))
    return v4, v6


def flatten(records):
    """Turn overlapping ranges into a disjoint, sorted table.

    Two things make this necessary rather than a nicety:

    * Feeds overlap each other. GitHub runs on Azure and AWS, so its
      prefixes sit inside theirs; Google publishes goog.json and cloud.json
      which share space.
    * The lookup is a bisect that inspects exactly one candidate — the last
      range whose start is <= the address. With overlapping ranges that
      candidate can be a narrow range that ends before the address while a
      wider range still contains it, and the lookup returns "unknown" for an
      address that is plainly in the table.

    Where ranges overlap, the narrowest one wins: GitHub inside Azure should
    answer GitHub, which is the more specific truth.
    """
    import heapq

    if not records:
        return []

    events = []
    for index, (start, end, label) in enumerate(records):
        events.append((start, 0, index))        # range opens
        events.append((end + 1, 1, index))      # range closes
    events.sort()

    active = []           # heap of (width, index)
    ends = {}
    for index, (start, end, _) in enumerate(records):
        ends[index] = end

    segments = []
    position = events[0][0]
    event_index = 0
    total = len(events)

    while event_index < total:
        point = events[event_index][0]

        # Emit the segment that ends where this event begins.
        if point > position:
            while active and ends[active[0][1]] < position:
                heapq.heappop(active)
            if active:
                _, winner = active[0]
                segments.append((position, point - 1, records[winner][2]))
            position = point

        while event_index < total and events[event_index][0] == point:
            _, kind, index = events[event_index]
            if kind == 0:
                start, end, _ = records[index]
                heapq.heappush(active, (end - start, index))
            event_index += 1

        # Closing events are handled lazily by the pop above; pushing the
        # close event only serves to create a segment boundary here.

    # Coalesce neighbours that ended up with the same label.
    merged = []
    for start, end, label in segments:
        if merged and merged[-1][2] == label and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end), label)
        else:
            merged.append((start, end, label))
    return merged


def pack(v4, v6):
    labels = []
    index = {}
    for _, _, label in v4 + v6:
        if label not in index:
            index[label] = len(labels)
            labels.append(label)

    out = bytearray()
    out += struct.pack("<8sHQHII", MAGIC, VERSION, int(time.time()), len(labels), len(v4), len(v6))
    for label in labels:
        raw = label.encode("utf-8")
        out += struct.pack("<H", len(raw)) + raw
    for start, end, label in v4:
        out += struct.pack("<IIH", start, end, index[label])
    for start, end, label in v6:
        out += struct.pack("<16s16sH",
                           start.to_bytes(16, "big"), end.to_bytes(16, "big"), index[label])
    return bytes(out)


#: Refuse to replace the dataset if it shrinks by more than this. A source
#: that starts answering 200 with an empty body, or quietly changes its JSON
#: shape, looks exactly like a provider giving up its address space — and
#: nothing else in the pipeline would notice.
MAX_SHRINK = 0.20


def existing_range_count():
    """How many ranges the committed dataset holds, or None if there is none."""
    if not OUT.exists():
        return None
    try:
        blob = OUT.read_bytes()
        magic, _version, _built, _labels, n_v4, n_v6 = struct.unpack_from("<8sHQHII", blob, 0)
    except Exception:
        return None
    if magic != MAGIC:
        return None
    return n_v4 + n_v6


def shrink_complaint(previous, current, max_shrink=None):
    """Why this build must not replace the committed one, or None.

    A source that starts answering 200 with an empty body, or quietly
    changes its JSON shape, looks exactly like a provider giving up its
    address space. Nothing else in the pipeline notices, and since the
    refresh now commits straight to main there is no review that would.
    """
    limit = MAX_SHRINK if max_shrink is None else max_shrink
    if not previous or current >= previous * (1 - limit):
        return None
    return (
        "Refusing to write: %d ranges is %.0f%% below the %d already "
        "committed. Either several sources failed at once, or one changed "
        "shape and is now parsing to nothing. Check the per-source counts "
        "above, then override with --allow-shrink if it is genuine."
        % (current, 100 * (1 - current / previous), previous)
    )


def main(allow_shrink=False):
    print("Fetching provider feeds...")
    v4, v6 = collect()
    if not v4:
        # Every source failing at once means something is wrong with the
        # runner, not with ten providers. Refuse to ship an empty dataset
        # over a good one.
        print("No IPv4 ranges collected; refusing to write an empty dataset.", file=sys.stderr)
        return 1

    before = len(v4) + len(v6)
    v4, v6 = flatten(v4), flatten(v6)
    blob = pack(v4, v6)

    # The last line of defence now that nothing downstream reviews this.
    complaint = None if allow_shrink else shrink_complaint(
        existing_range_count(), len(v4) + len(v6)
    )
    if complaint:
        print(complaint, file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(blob)

    print("\n%d prefixes -> %d ranges (%d v4, %d v6), %.1f KB"
          % (before, len(v4) + len(v6), len(v4), len(v6), len(blob) / 1024))
    print("written to %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(allow_shrink="--allow-shrink" in sys.argv))
