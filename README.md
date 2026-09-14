# iporigin

Tell a datacenter IP from a home connection — offline, with no API key.

```python
>>> import iporigin
>>> iporigin.classify("52.95.110.1")
Origin(ip='52.95.110.1', kind='hosting', provider='Amazon AWS', source='local')
>>> iporigin.is_datacenter("8.8.8.8")
True
>>> iporigin.is_datacenter("127.0.0.1")
False
```

No network calls. No signup. No runtime dependencies. The answer comes from
a bundled table of 38,000 ranges covering 48 hosting providers, CDNs,
consumer VPNs, Tor and declared crawlers.

## Install

```
pip install iporigin
```

## Why

"Is this visitor on a server or on a home connection?" comes up constantly —
scoring signups, filtering scrapers out of analytics, deciding whether an
abuse report is worth acting on, flagging logins from hosting ranges. The
usual answers are a paid API or a hand-maintained list of CIDRs that goes
stale in a month.

This is a third option: the providers publish their own ranges, so the list
can be compiled from source and rebuilt on a schedule. You get a local
lookup in microseconds, and you can verify every byte of the data by
re-running the build script.

## Use

### Classify one address

```python
import iporigin

origin = iporigin.classify("140.82.121.4")
origin.kind          # 'hosting'
origin.provider      # 'GitHub'
origin.is_datacenter # True
```

`kind` is one of:

| kind | meaning | examples |
| --- | --- | --- |
| `hosting` | a machine in a cloud or hosting provider | AWS, Hetzner, OVHcloud |
| `cdn` | edge infrastructure fronting other people's sites | Cloudflare, Akamai |
| `vpn` | a consumer VPN or private relay exit | Mullvad, ProtonVPN, Apple Private Relay |
| `tor` | a Tor exit node | |
| `bot` | a declared crawler | Googlebot, GPTBot, ClaudeBot |
| `reserved` | private, loopback, link-local, documentation | `127.0.0.1`, `10.0.0.0/8` |
| `unknown` | in none of our lists — most often a residential ISP | |

Two sets are exported for the common decisions:

```python
origin.kind in iporigin.DATACENTER_KINDS   # a machine, not a home line
origin.kind in iporigin.ANONYMIZER_KINDS   # vpn or tor
```

They are deliberately different questions. Someone arriving through Mullvad
is a person at home, but the address they arrive *from* is a server — so it
is in both sets, and you may well want to rate-limit one and refuse the
other.

`unknown` means *absence of evidence*. It is not a positive claim that the
address is residential, and the difference matters if you are going to block
someone over it.

### Scan a lot of them

```python
for origin in iporigin.classify_many(ip_list):
    if origin.is_datacenter:
        print(origin.ip, origin.provider)
```

`classify_many` loads the table once for the whole batch.

### From the shell

```console
$ iporigin 8.8.8.8 140.82.121.4 192.168.1.1
8.8.8.8                                  hosting   Google
140.82.121.4                             hosting   GitHub
192.168.1.1                              reserved

$ cut -d' ' -f1 access.log | iporigin --datacenter-only --json
{"ip": "34.82.1.5", "kind": "hosting", "provider": "Google Cloud", ...}
```

`iporigin --info` prints what is in the bundled dataset and when it was built.

### Going beyond the bundled table

The table covers the VPN providers whose exits are publicly tracked —
Mullvad, ProtonVPN, Apple Private Relay. Most VPN companies are not in that
set. When you need broader coverage, `iporigin.online` asks the free
[Unblock Master IP API](https://www.unblockmaster.com/free-ip-api/), which
does its own detection:

```python
from iporigin.online import classify_online

classify_online("203.0.113.10")   # may return kind='vpn'
```

It falls back to the offline answer if the request fails, so it is safe in a
request path. Nothing else in the library touches the network — you have to
import this module on purpose. No key required.

## What is in the dataset

48 providers, in three tiers.

**Published by the provider.** The authoritative tier — each of these is the
company's own feed, fetched at build time:

| Provider | Feed |
| --- | --- |
| Amazon AWS | `ip-ranges.amazonaws.com/ip-ranges.json` |
| Google, Google Cloud | `gstatic.com/ipranges/goog.json`, `cloud.json` |
| Microsoft Azure | Service Tags JSON |
| DigitalOcean | `digitalocean.com/geo/google.csv` |
| Linode | RFC 8805 geofeed |
| Vultr | `geofeed.constant.com` |
| Oracle Cloud | `public_ip_ranges.json` |
| GitHub | `api.github.com/meta` |
| Cloudflare | `cloudflare.com/ips-v4`, `ips-v6` |
| Fastly | `api.fastly.com/public-ip-list` |

**Community-maintained lists.** Some providers publish nothing
machine-readable — Hetzner and OVH being the two that matter most, since a
large share of abusive traffic comes from them. Consumer VPN exits, Tor and
crawler ranges have the same problem for a different reason: nobody with the
data has an interest in publishing it. Those come from two community repos,
and are second-hand by definition:

- [`rezmoss/cloud-provider-ip-addresses`](https://github.com/rezmoss/cloud-provider-ip-addresses) (CC0)
- [`lord-alfred/ipranges`](https://github.com/lord-alfred/ipranges) (CC0)

Covering Hetzner, OVHcloud, Scaleway, Alibaba Cloud, Leaseweb, UpCloud, IBM
Cloud, Huawei Cloud, Tencent Cloud, Rackspace, Akamai, Gcore, Mullvad,
ProtonVPN, Apple Private Relay, Tor, and ten declared crawlers.

Both are CC0, a public-domain dedication, so they carry no conditions.

**Used with the maintainer's permission.** Two further repositories publish
no licence file, which normally rules them out. They are included because
permission was obtained from each maintainer directly — see
[NOTICE](NOTICE), which records what was granted and by whom:

- [`123jjck/cdn-ip-ranges`](https://github.com/123jjck/cdn-ip-ranges) —
  Cogent, DataCamp, Contabo, Vercel, CDN77, GleSYS, Scalaxy, GTHost,
  Melbicom, BuyVM, BunnyCDN
- [`SecOps-Institute/Akamai-ASN-and-IPs-List`](https://github.com/SecOps-Institute/Akamai-ASN-and-IPs-List) —
  additional Akamai ranges

Only what is additive is taken. `jhassine/server-ip-addresses` is the
best-known list of this kind and is **not** included: 52,772 prefixes,
227M addresses, and every one of 211,616 sampled addresses was already
covered. It is a subset of the provider feeds it was itself built from, and
a source that adds nothing is still another endpoint that can break the
weekly rebuild.

About 454,000 published prefixes collapse into roughly 38,400 disjoint
ranges (about 21,900 IPv4 and 16,500 IPv6) covering 287 million IPv4
addresses. The exact figures move every week with the feeds; the build
prints them. Rebuild it yourself at any time:

```
python tools/build_dataset.py
```

A GitHub Action re-runs that weekly and commits the result when the ranges
move. The build refuses to replace the committed dataset if it shrinks by
more than 20% — a feed that starts answering with an empty body looks
exactly like a provider giving up its address space, and nothing else
would catch it. Pass `--allow-shrink` when the drop is genuine.

### Known gaps

Being explicit about these is more useful than pretending they are not there:

- **Most consumer VPNs.** Only the ones whose exits are publicly tracked are
  in the table. Use `iporigin.online` for the rest.
- **Some provider-owned addresses** sit outside the ranges the provider
  publishes. `1.1.1.1` is Cloudflare's resolver but is not in Cloudflare's
  published edge list, so it comes back `unknown`.
- **Second-hand data is second-hand.** Tiers 2 and 3 are as good as those
  repos are, and they are not the provider speaking.
- The data is **as accurate as the feeds**. A range reassigned yesterday is
  wrong until the next rebuild.

## How the lookup works

Ranges are stored as inclusive integer start/end pairs in sorted, *disjoint*
order, so a lookup is one `bisect` plus one comparison.

Making them disjoint is the part that matters. Feeds overlap each other —
GitHub runs on Azure and AWS, so its prefixes sit inside theirs. A bisect
inspects exactly one candidate, and with overlapping ranges that candidate
can be a narrow range that ends before the address while a wider range still
contains it, which returns `unknown` for an address plainly in the table. The
build script therefore sweeps the ranges into a disjoint partition, and where
they overlap the narrowest one wins — GitHub inside Azure answers GitHub,
which is the more specific truth.

The table loads lazily on the first lookup, so importing the library and
never calling it costs nothing.

## Compatibility

Python 3.8+. No dependencies.

## License

The code is MIT. The bundled dataset comes from third parties; every source,
its licence, and — where there is none — the permission it is used under are
recorded in [NOTICE](NOTICE).

---

Built by [Yuix Networks](https://yuix.org), who also run
[Unblock Master](https://www.unblockmaster.com/) and its
[free IP lookup API](https://www.unblockmaster.com/free-ip-api/).
