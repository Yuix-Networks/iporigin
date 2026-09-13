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
a 140 KB table compiled out of eleven providers' own published IP feeds.

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

| kind | meaning |
| --- | --- |
| `hosting` | a machine in a cloud or hosting provider |
| `cdn` | edge infrastructure fronting other people's sites |
| `vpn` | a consumer VPN exit node (online lookup only, see below) |
| `reserved` | private, loopback, link-local, documentation |
| `unknown` | in none of our lists — most often a residential ISP |

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

### Consumer VPNs

No VPN company publishes its exit-node ranges, so the offline table cannot
contain them. When that matters, `iporigin.online` asks the free
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

Compiled from these official feeds, all fetched at build time:

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

About 130,000 published prefixes collapse into 6,445 disjoint ranges
(3,129 IPv4, 3,316 IPv6) covering roughly 193 million IPv4 addresses.

Rebuild it yourself at any time:

```
python tools/build_dataset.py
```

A GitHub Action re-runs that weekly and opens a PR when the ranges move.

### Known gaps

Being explicit about these is more useful than pretending they are not there:

- **Consumer VPNs** are not in any published feed. Use `iporigin.online`.
- **Hetzner and OVH** — two of the most common hosts behind abusive traffic —
  publish no machine-readable range feed. Not covered.
- **Some provider-owned addresses** sit outside the ranges the provider
  publishes. `1.1.1.1` is Cloudflare's resolver but is not in Cloudflare's
  published edge list, so it comes back `unknown`.
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

MIT. The compiled dataset is derived from the providers' own public feeds,
each published for exactly this purpose.

---

Built by [Yuix Networks](https://yuix.org), who also run
[Unblock Master](https://www.unblockmaster.com/) and its
[free IP lookup API](https://www.unblockmaster.com/free-ip-api/).
