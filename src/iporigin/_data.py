"""Loading and querying the packed range table.

The table is loaded once, lazily, on the first lookup — importing iporigin
must stay cheap for a program that imports it and never calls it.

Lookups are a bisect over a sorted column of range starts. Ranges never
overlap within the merged table, so the candidate found by bisect is the
only one that can contain the address: one comparison decides it.
"""

import bisect
import struct
from array import array
from pathlib import Path

MAGIC = b"IPORIGIN"
SUPPORTED_VERSION = 1

DATA_FILE = Path(__file__).parent / "data" / "ranges.bin"

_HEADER = struct.Struct("<8sHQHII")
_V4_RECORD = struct.Struct("<IIH")
_V6_RECORD = struct.Struct("<16s16sH")


class DatasetError(RuntimeError):
    """The bundled dataset is missing or unreadable."""


class _Dataset:
    __slots__ = (
        "built_at", "labels",
        "v4_starts", "v4_ends", "v4_labels",
        "v6_starts", "v6_ends", "v6_labels",
    )

    def __init__(self, blob):
        magic, version, built_at, n_labels, n_v4, n_v6 = _HEADER.unpack_from(blob, 0)
        if magic != MAGIC:
            raise DatasetError("not an iporigin dataset")
        if version != SUPPORTED_VERSION:
            raise DatasetError(
                "dataset format v%d, this build understands v%d — upgrade iporigin"
                % (version, SUPPORTED_VERSION)
            )

        self.built_at = built_at
        offset = _HEADER.size

        self.labels = []
        for _ in range(n_labels):
            (length,) = struct.unpack_from("<H", blob, offset)
            offset += 2
            provider, _, kind = blob[offset:offset + length].decode("utf-8").partition("\t")
            self.labels.append((provider, kind))
            offset += length

        # Parallel arrays rather than tuples: 21k ranges as Python tuples is
        # several MB of objects, as arrays it is a few hundred KB.
        self.v4_starts = array("L")
        self.v4_ends = array("L")
        self.v4_labels = array("H")
        for _ in range(n_v4):
            start, end, label = _V4_RECORD.unpack_from(blob, offset)
            self.v4_starts.append(start)
            self.v4_ends.append(end)
            self.v4_labels.append(label)
            offset += _V4_RECORD.size

        # IPv6 addresses do not fit a machine word, so these stay Python ints.
        self.v6_starts = []
        self.v6_ends = []
        self.v6_labels = array("H")
        for _ in range(n_v6):
            start, end, label = _V6_RECORD.unpack_from(blob, offset)
            self.v6_starts.append(int.from_bytes(start, "big"))
            self.v6_ends.append(int.from_bytes(end, "big"))
            self.v6_labels.append(label)
            offset += _V6_RECORD.size

    def find(self, value, version):
        """Return (provider, kind) for an address, or None."""
        if version == 4:
            starts, ends, labels = self.v4_starts, self.v4_ends, self.v4_labels
        else:
            starts, ends, labels = self.v6_starts, self.v6_ends, self.v6_labels

        index = bisect.bisect_right(starts, value) - 1
        if index < 0 or value > ends[index]:
            return None
        return self.labels[labels[index]]

    def __len__(self):
        return len(self.v4_starts) + len(self.v6_starts)


_loaded = None


def dataset():
    global _loaded
    if _loaded is None:
        try:
            blob = DATA_FILE.read_bytes()
        except OSError as exc:
            raise DatasetError(
                "bundled dataset missing at %s — reinstall iporigin, or run "
                "tools/build_dataset.py if you are working from a checkout"
                % DATA_FILE
            ) from exc
        _loaded = _Dataset(blob)
    return _loaded
