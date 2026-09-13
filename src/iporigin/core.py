"""Classify an IP address by where it is hosted."""

import ipaddress
from dataclasses import dataclass

from ._data import DatasetError, dataset  # noqa: F401 — re-exported

# What a result can be. Deliberately small: a caller should be able to
# switch on this exhaustively.
HOSTING = "hosting"      # a machine in a cloud or hosting provider
CDN = "cdn"              # edge infrastructure fronting other people's sites
VPN = "vpn"              # a consumer VPN or private relay exit
TOR = "tor"              # a Tor exit node
BOT = "bot"              # a declared crawler (Googlebot, GPTBot, ...)
RESERVED = "reserved"    # private, loopback, link-local, documentation...
UNKNOWN = "unknown"      # in no list we have — most often a residential ISP

#: Kinds that mean "this address is a machine, not somebody's home line".
#: A person browsing through Mullvad is at home, but the address they arrive
#: from is still a server — this is about the address, not the human.
DATACENTER_KINDS = frozenset({HOSTING, CDN, VPN, TOR, BOT})

#: Kinds that mean "whoever is behind this is deliberately hidden".
#: A different decision from DATACENTER_KINDS: you might rate-limit a cloud
#: IP but refuse a payment from an anonymised one, or the exact reverse.
ANONYMIZER_KINDS = frozenset({VPN, TOR})


@dataclass(frozen=True)
class Origin:
    """What we know about an address.

    ``kind`` is always set. ``provider`` is empty when we did not match a
    known range — absence of evidence, so do not read UNKNOWN as
    "residential", only as "not in our data".
    """

    ip: str
    kind: str
    provider: str = ""
    source: str = "local"

    @property
    def is_datacenter(self):
        return self.kind in DATACENTER_KINDS

    def __bool__(self):
        # Guard against `if classify(ip):` reading as "is a datacenter".
        # An Origin is always a result, so make the truthiness meaningless
        # rather than misleading.
        return True


def _parse(ip):
    if isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return ip
    try:
        return ipaddress.ip_address(str(ip).strip())
    except ValueError as exc:
        raise ValueError("%r is not an IP address" % (ip,)) from exc


def classify(ip):
    """Classify one address against the bundled dataset.

    >>> classify("1.1.1.1").provider
    'Cloudflare'

    Raises ValueError if ``ip`` is not an address. Never makes a network
    request — see iporigin.online for that.
    """
    address = _parse(ip)

    # A reserved address is not "unknown", and answering "hosting: no" for
    # 127.0.0.1 would be technically true and completely useless.
    if not address.is_global:
        return Origin(str(address), RESERVED)

    found = dataset().find(int(address), address.version)
    if found is None:
        return Origin(str(address), UNKNOWN)

    provider, kind = found
    return Origin(str(address), kind, provider)


def is_datacenter(ip):
    """True when the address belongs to a known hosting, CDN or VPN range.

    False means "not in our data", which is not the same as "residential" —
    our coverage is the published feeds listed in tools/sources.py.
    """
    return classify(ip).is_datacenter


def classify_many(ips):
    """Classify an iterable of addresses, yielding Origin objects.

    Loads the dataset once for the whole batch, so this is the right call
    for scanning a log file.
    """
    dataset()
    for ip in ips:
        yield classify(ip)


def dataset_info():
    """Provenance of the bundled data: when it was built and how big it is."""
    data = dataset()
    return {
        "built_at": data.built_at,
        "ranges": len(data),
        "ipv4_ranges": len(data.v4_starts),
        "ipv6_ranges": len(data.v6_starts),
        "providers": sorted({provider for provider, _ in data.labels}),
    }
