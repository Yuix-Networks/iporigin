"""Where the address ranges come from.

Every source here is the provider's own published feed, so the dataset is
reproducible: anyone can re-run tools/build_dataset.py and get the same
thing. That matters more than coverage — a bundled blob nobody can verify
is a blob nobody should trust.

A source that fails is skipped with a warning rather than failing the
build. These are ten third-party endpoints; on any given day one of them
is having a bad time, and that must not block a release.
"""

import csv
import io
import json
import re
import urllib.request

USER_AGENT = "iporigin-dataset-builder/1.0 (+https://github.com/Yuix-Networks/iporigin)"
TIMEOUT = 60


def _get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def _get_json(url):
    return json.loads(_get(url))


def _get_text(url):
    return _get(url).decode("utf-8", "replace")


def aws():
    data = _get_json("https://ip-ranges.amazonaws.com/ip-ranges.json")
    for row in data.get("prefixes", []):
        yield row["ip_prefix"]
    for row in data.get("ipv6_prefixes", []):
        yield row["ipv6_prefix"]


def gcp():
    data = _get_json("https://www.gstatic.com/ipranges/cloud.json")
    for row in data.get("prefixes", []):
        prefix = row.get("ipv4Prefix") or row.get("ipv6Prefix")
        if prefix:
            yield prefix


def google():
    # cloud.json is only the ranges Google Cloud hands to customers.
    # goog.json is every range Google announces, which is what covers
    # things like 8.8.8.8 — so both are needed, and they overlap.
    data = _get_json("https://www.gstatic.com/ipranges/goog.json")
    for row in data.get("prefixes", []):
        prefix = row.get("ipv4Prefix") or row.get("ipv6Prefix")
        if prefix:
            yield prefix


def azure():
    # Microsoft publishes a dated JSON behind a download page and changes the
    # filename every week, so the URL has to be discovered rather than pinned.
    page = _get_text("https://www.microsoft.com/en-us/download/details.aspx?id=56519")
    match = re.search(
        r"https://download\.microsoft\.com/download/[^\"']*?ServiceTags_Public_\d+\.json",
        page,
    )
    if not match:
        raise RuntimeError("could not find the ServiceTags JSON link on the page")
    data = _get_json(match.group(0))
    for value in data.get("values", []):
        for prefix in value.get("properties", {}).get("addressPrefixes", []):
            yield prefix


def digitalocean():
    text = _get_text("https://www.digitalocean.com/geo/google.csv")
    for row in csv.reader(io.StringIO(text)):
        if row and "/" in row[0]:
            yield row[0]


def linode():
    # RFC 8805 geofeed: "prefix,country,region,city,postcode", # for comments.
    for line in _get_text("https://geoip.linode.com/").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        prefix = line.split(",")[0].strip()
        if "/" in prefix:
            yield prefix


def vultr():
    data = _get_json("https://geofeed.constant.com/?json")
    for row in data.get("subnets", []):
        prefix = row.get("ip_prefix")
        if prefix:
            yield prefix


def oracle():
    data = _get_json("https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json")
    for region in data.get("regions", []):
        for cidr in region.get("cidrs", []):
            prefix = cidr.get("cidr")
            if prefix:
                yield prefix


def cloudflare():
    for url in ("https://www.cloudflare.com/ips-v4", "https://www.cloudflare.com/ips-v6"):
        for line in _get_text(url).splitlines():
            line = line.strip()
            if "/" in line:
                yield line


def fastly():
    data = _get_json("https://api.fastly.com/public-ip-list")
    for key in ("addresses", "ipv6_addresses"):
        for prefix in data.get(key, []):
            yield prefix


def github():
    data = _get_json("https://api.github.com/meta")
    seen = set()
    for key, values in data.items():
        if key in ("verifiable_password_authentication", "ssh_key_fingerprints", "domains"):
            continue
        if not isinstance(values, list):
            continue
        for prefix in values:
            if isinstance(prefix, str) and "/" in prefix and prefix not in seen:
                seen.add(prefix)
                yield prefix


# name -> (kind, fetcher). "kind" is what the range means to a caller:
# hosting is a machine in a datacenter, cdn is edge infrastructure that
# fronts other people's sites and says nothing about who the visitor is.
SOURCES = {
    "Amazon AWS": ("hosting", aws),
    "Google Cloud": ("hosting", gcp),
    "Google": ("hosting", google),
    "Microsoft Azure": ("hosting", azure),
    "DigitalOcean": ("hosting", digitalocean),
    "Linode": ("hosting", linode),
    "Vultr": ("hosting", vultr),
    "Oracle Cloud": ("hosting", oracle),
    "GitHub": ("hosting", github),
    "Cloudflare": ("cdn", cloudflare),
    "Fastly": ("cdn", fastly),
}
