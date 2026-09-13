# Changelog

## 1.0.0

First release.

- Offline classification of IPv4 and IPv6 addresses into `hosting`, `cdn`,
  `reserved` and `unknown`, from a table compiled out of eleven providers'
  own published feeds.
- `classify`, `is_datacenter`, `classify_many`, `dataset_info`.
- `iporigin` command line tool, reads addresses from arguments or stdin.
- Optional live lookup in `iporigin.online` for consumer VPN exit nodes,
  which no provider publishes.
- No runtime dependencies.
