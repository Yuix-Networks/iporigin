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


# ---------------------------------------------------------------------------
# Community aggregations
#
# Some providers publish no machine-readable range feed at all — Hetzner and
# OVH are the two that matter most, since a large share of abusive traffic
# comes from them. Consumer VPN exits and crawler ranges have the same
# problem for a different reason: nobody has an interest in publishing them.
#
# These come from two community repos instead. Both are CC0, which is why
# these two and not the half-dozen others that cover the same ground:
# redistributing an unlicensed list inside an MIT package is not something a
# dependency should ask of the people who install it.
#
#   rezmoss/cloud-provider-ip-addresses  CC0-1.0
#   lord-alfred/ipranges                 CC0-1.0
#
# They are second-hand by definition, so they are labelled as such in the
# README rather than presented as the provider's own word.
# ---------------------------------------------------------------------------

REZMOSS = "https://raw.githubusercontent.com/rezmoss/cloud-provider-ip-addresses/main/%s/%s_ips_v%d.txt"
LORD_ALFRED = "https://raw.githubusercontent.com/lord-alfred/ipranges/main/%s/ipv%d_merged.txt"


def _plain_cidr_lines(url, required=True):
    try:
        text = _get_text(url)
    except Exception:
        if required:
            raise
        return
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "/" in line:
            yield line


def _rezmoss(slug):
    def fetch():
        yield from _plain_cidr_lines(REZMOSS % (slug, slug, 4))
        # Not every provider has a v6 file with content; a missing one must
        # not lose the v4 ranges we already collected.
        yield from _plain_cidr_lines(REZMOSS % (slug, slug, 6), required=False)

    return fetch


def _lord_alfred(slug):
    def fetch():
        yield from _plain_cidr_lines(LORD_ALFRED % (slug, 4))
        yield from _plain_cidr_lines(LORD_ALFRED % (slug, 6), required=False)

    return fetch


def _optional_rezmoss(slug):
    """Like _rezmoss, but a missing upstream file is logged and skipped,
    not raised. Use for community slugs whose availability is not certain."""
    def fetch():
        url = REZMOSS % (slug, slug, 4)
        try:
            text = _get_text(url)
        except Exception as exc:
            print("  !! %-18s skipped: %s" % (slug, exc), file=__import__("sys").stderr)
            return
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "/" in line:
                yield line
    return fetch


def _optional_lord_alfred(slug):
    """Like _lord_alfred, but a missing upstream file is logged and skipped."""
    def fetch():
        url = LORD_ALFRED % (slug, 4)
        try:
            text = _get_text(url)
        except Exception as exc:
            print("  !! %-18s skipped: %s" % (slug, exc), file=__import__("sys").stderr)
            return
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "/" in line:
                yield line
    return fetch


COMMUNITY = {
    # Hosting with no official feed.
    "Hetzner": ("hosting", _rezmoss("hetzner")),
    "OVHcloud": ("hosting", _rezmoss("ovhcloud")),
    "Scaleway": ("hosting", _rezmoss("scaleway")),
    "Alibaba Cloud": ("hosting", _rezmoss("alibaba")),
    "Leaseweb": ("hosting", _rezmoss("leaseweb")),
    "UpCloud": ("hosting", _rezmoss("upcloud")),
    "IBM Cloud": ("hosting", _rezmoss("ibmcloud")),
    "Huawei Cloud": ("hosting", _rezmoss("huawei")),
    "Tencent Cloud": ("hosting", _rezmoss("tencent")),
    "Rackspace": ("hosting", _rezmoss("rackspace")),
    # CDN.
    "Akamai": ("cdn", _rezmoss("akamai")),
    "Gcore": ("cdn", _rezmoss("gcore")),
    # Consumer VPN exits — the thing no provider feed can give us.
    "Mullvad": ("vpn", _rezmoss("mullvad")),
    "ProtonVPN": ("vpn", _lord_alfred("protonvpn")),
    "Apple Private Relay": ("vpn", _rezmoss("apple_private_relay")),
    # Tor is its own thing: not a VPN, not a datacenter, and a caller
    # usually wants to treat it differently from both.
    "Tor": ("tor", _rezmoss("tor")),
    # Declared crawlers. Separate from hosting because "a bot" and "someone
    # on a server" call for different handling — you rate-limit one and
    # block the other.
    "Googlebot": ("bot", _rezmoss("googlebot")),
    "Bingbot": ("bot", _rezmoss("bingbot")),
    "GPTBot": ("bot", _rezmoss("gptbot")),
    "ClaudeBot": ("bot", _rezmoss("claudebot")),
    "PerplexityBot": ("bot", _rezmoss("perplexitybot")),
    "DuckDuckBot": ("bot", _rezmoss("duckduckbot")),
    "Amazonbot": ("bot", _rezmoss("amazonbot")),
    "Applebot": ("bot", _rezmoss("applebot")),
    "Common Crawl": ("bot", _rezmoss("commoncrawl")),
    "Internet Archive": ("bot", _rezmoss("internetarchive")),
    "OpenAI": ("bot", _optional_lord_alfred("openai")),
    "Perplexity AI": ("bot", _optional_lord_alfred("perplexity")),
    "DuckAssistBot": ("bot", _optional_lord_alfred("duckassistbot")),
    "Apple Intelligence Proxy": ("bot", _optional_lord_alfred("apple-proxy")),
    "Meta": ("bot", _optional_rezmoss("meta")),
}

SOURCES.update(COMMUNITY)


# ---------------------------------------------------------------------------
# Sources used with the upstream maintainers' permission
#
# These repositories carry no licence file, which normally means "all rights
# reserved" and rules them out of an MIT package. They are included because
# permission was obtained from each maintainer directly — see NOTICE.
#
# Only what is actually additive is taken. Two well-known lists were measured
# and left out rather than included for the sake of it:
#
#   jhassine/server-ip-addresses  52,772 prefixes, 227M addresses, and every
#                                 one of 211,616 sampled addresses already
#                                 covered — it is a subset of the provider
#                                 feeds it was itself built from.
#   Pymmdrza/Datacenter_List...   1,280 new addresses over what Hetzner's
#                                 other sources already give.
#
# A source that adds nothing is not free: it is another endpoint that can
# break the weekly rebuild.
# ---------------------------------------------------------------------------

JJCK = "https://raw.githubusercontent.com/123jjck/cdn-ip-ranges/main/%s/%s_plain_ipv4.txt"


def _jjck(slug):
    # IPv4 only; this repo publishes no v6 files.
    return lambda: _plain_cidr_lines(JJCK % (slug, slug))


def akamai_secops():
    yield from _plain_cidr_lines(
        "https://raw.githubusercontent.com/SecOps-Institute/"
        "Akamai-ASN-and-IPs-List/master/akamai_ip_cidr_blocks.lst"
    )


BY_PERMISSION = {
    # Networks with no feed anywhere else. Measured additions over the
    # CC0 tier, largest first.
    "Cogent": ("hosting", _jjck("cogent")),          # +36.2M addresses
    "DataCamp": ("cdn", _jjck("datacamp")),          # +1.07M
    "Contabo": ("hosting", _jjck("contabo")),        # +603k
    "Vercel": ("hosting", _jjck("vercel")),          # +134k
    "CDN77": ("cdn", _jjck("cdn77")),                # +128k
    "GleSYS": ("hosting", _jjck("glesys")),          # +158k
    "Scalaxy": ("hosting", _jjck("scalaxy")),        # +105k
    "GTHost": ("hosting", _jjck("gthost")),          # +89k
    "Melbicom": ("hosting", _jjck("melbicom")),      # +63k
    "BuyVM": ("hosting", _jjck("buyvm")),            # +32k
    "BunnyCDN": ("cdn", _jjck("bunny")),             # +4k
}

# Akamai already has a CC0 source; this one adds ~309k addresses on top, so
# it feeds the same label rather than creating a second Akamai entry.
_akamai_cc0 = COMMUNITY["Akamai"][1]


def akamai_combined():
    yield from _akamai_cc0()
    yield from akamai_secops()


COMMUNITY["Akamai"] = ("cdn", akamai_combined)

SOURCES.update(BY_PERMISSION)
