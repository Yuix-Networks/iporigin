"""Tell a datacenter IP from a home connection, offline.

    >>> import iporigin
    >>> iporigin.classify("52.95.110.1")
    Origin(ip='52.95.110.1', kind='hosting', provider='Amazon AWS', source='local')
    >>> iporigin.is_datacenter("8.8.8.8")
    True

No network calls, no API key: the answer comes from a table compiled from
the providers' own published feeds. See iporigin.online for the optional
live lookup that also covers consumer VPN exit nodes.
"""

from ._data import DatasetError
from .core import (
    ANONYMIZER_KINDS,
    BOT,
    CDN,
    DATACENTER_KINDS,
    HOSTING,
    RESERVED,
    TOR,
    UNKNOWN,
    VPN,
    Origin,
    classify,
    classify_many,
    dataset_info,
    is_datacenter,
)

__version__ = "1.0.0"

__all__ = [
    "ANONYMIZER_KINDS",
    "BOT",
    "CDN",
    "DATACENTER_KINDS",
    "DatasetError",
    "HOSTING",
    "Origin",
    "RESERVED",
    "TOR",
    "UNKNOWN",
    "VPN",
    "classify",
    "classify_many",
    "dataset_info",
    "is_datacenter",
    "__version__",
]
