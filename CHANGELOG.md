# Changelog

## 1.1.0

- 11 more providers, from two repositories used with their maintainers'
  permission: Cogent, DataCamp, Contabo, Vercel, CDN77, GleSYS, Scalaxy,
  GTHost, Melbicom, BuyVM, BunnyCDN, plus extra Akamai ranges.
  37 providers to 48; 33,647 ranges to 38,379; IPv4 coverage 248M to 287M
  addresses.
- NOTICE records every data source, its licence, and — where a repository
  has none — the permission it is used under.
- `jhassine/server-ip-addresses` was measured and deliberately left out:
  every one of 211,616 sampled addresses was already covered, so it adds
  nothing but another endpoint that can break the weekly rebuild.

## 1.0.0

First release.

- Offline classification of IPv4 and IPv6 addresses into `hosting`, `cdn`,
  `vpn`, `tor`, `bot`, `reserved` and `unknown`, from a table of 33,647
  disjoint ranges covering 37 providers.
- Ten providers come from their own published feeds; the rest — Hetzner,
  OVHcloud, Akamai, Mullvad, ProtonVPN, Tor, Googlebot and others — from two
  CC0 community lists, because those providers publish nothing
  machine-readable.
- `classify`, `is_datacenter`, `classify_many`, `dataset_info`, plus the
  `DATACENTER_KINDS` and `ANONYMIZER_KINDS` sets.
- `iporigin` command line tool, reads addresses from arguments or stdin.
- Optional live lookup in `iporigin.online` for VPN providers the offline
  table does not reach.
- No runtime dependencies.
