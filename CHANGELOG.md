# Changelog

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
