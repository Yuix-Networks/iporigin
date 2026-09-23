# Data refresh — operations notes

Who this is for: the person who maintains the bundled `iporigin` dataset —
the next time a feed goes 404 or a new one needs adding, this is the page
to read first. Public-API docs live in `README.md`; binary format is in
the `tools/build_dataset.py` docstring; the user-facing explanation of what
the data is and where it comes from is in `NOTICE`.

## What runs when

Two GitHub Actions workflows keep the bundled dataset current. Both run
against `main`; neither has a manual review step.

| Workflow | Schedule | What it does |
| --- | --- | --- |
| `.github/workflows/update-data.yml` | Weekly (Mon 04:17 UTC) + `workflow_dispatch` | Runs `tools/build_dataset.py`, commits `src/iporigin/data/ranges.bin` straight to `main` if it changed |
| `.github/workflows/release.yml` | Monthly (6th at 06:00 UTC) + `workflow_dispatch` | Cuts a patch release on PyPI if the dataset moved since the last release |

A `ci.yml` workflow also runs the test suite on every pull request. It
doesn't refresh data; it only verifies that the tests pass against the
committed dataset.

## What `tools/build_dataset.py` does

`tools/build_dataset.py` is the single source of truth for the dataset.
Its job, in order:

1. **Fetch.** Walk every entry in `tools.sources.SOURCES`, call its
   fetcher, and turn the returned CIDRs into `(start, end, label)` triples.
2. **Flatten.** Run the disjoint sweep — where two ranges overlap, keep
   the narrower one; ties break by insertion order (the earlier-inserted
   provider wins). This is what makes "GitHub inside Azure" answer as
   GitHub rather than Azure.
3. **Pack.** Serialize the disjoint ranges plus their labels into the
   binary format documented in the file's docstring. Write
   `src/iporigin/data/ranges.bin`.
4. **Refuse a big shrink.** Before overwriting, compare the new range
   count against the committed one. If it shrank by more than 20%, exit
   non-zero and do not write the new dataset. This catches a feed that
   silently starts returning empty bodies — which would otherwise look
   exactly like a provider giving up its address space. Pass
   `--allow-shrink` on the command line to override.

## Missing-source behaviour

Each source has one of three tolerance levels for upstream failure:

- **Own feed.** `aws()`, `gcp()`, `azure()`, etc. raise on failure. If
  AWS goes down, the build fails; nothing ships. Acceptable because
  each of these is the provider's authoritative feed — if it goes away,
  the right answer is to know about it.
- **Strict community helper.** `_rezmoss(slug)` and `_lord_alfred(slug)`
  raise on the v4 fetch but skip the v6 fetch (`required=False`). A
  provider that only publishes IPv4 still produces a working dataset.
- **Optional community helper.** `_optional_rezmoss(slug)` and
  `_optional_lord_alfred(slug)` (added for AI-company slugs whose
  upstream availability is not certain) log a `  !! <slug> skipped: <exc>`
  line to stderr and yield nothing. The build still produces a dataset.

The workflow greps `^  !! ` lines out of `/tmp/build.log` after each run
and emits each one as a `::warning::` GitHub annotation. The warnings
also go into the step summary and the commit body, so a feed that's been
gone for several weeks is visible at a glance.

## Adding a new source

Checklist for a maintainer adding a new entry to `tools/sources.py`:

1. **Pick the tier.** Tier 1 is the provider's own published feed
   (`SOURCES` dict); tier 2 is one of the two CC0 community repos
   (`COMMUNITY` dict); tier 3 is a permitted-no-licence repo (the existing
   two are `123jjck/cdn-ip-ranges` and `SecOps-Institute/Akamai-ASN-and-IPs-List`).
2. **Match the upstream slug exactly.** The slug is the path component
   in the upstream URL. Case-sensitive. Probe it with a `curl` first —
   if the file 404s, use the optional helper (`_optional_rezmoss` /
   `_optional_lord_alfred`) so the build keeps working.
3. **Run the build locally.** `python tools/build_dataset.py`. The new
   entry should print `  <name>            <N> prefixes` with `N > 0`.
   If it prints `  !! <name> skipped: HTTP Error 404`, the slug is wrong.
4. **Verify a sample address.** `PYTHONPATH=src python3 -c "import
   iporigin; print(iporigin.classify('<one-of-the-new-prefixes>'))"` —
   `kind` should be the expected tier value and `provider` should be the
   name you chose.
5. **Run the test suite.** `pip install -e '.[dev]' && pytest -q`. New
   bot providers should also get a parametrize entry in
   `tests/test_iporigin.py::test_known_ai_bot_provider_is_classified_as_bot`.
6. **Commit the source-code change and the rebuilt binary as separate
   commits.** Source first, binary second — keeps the diff readable and
   lets the next maintainer bisect on data-only changes.

## Removing a dead source

A feed that's been 404-ing for several weeks is rotting, not a transient
outage. When a `::warning::` for the same name has appeared in the
weekly run summary for ~3 consecutive weeks:

1. Remove the entry from `SOURCES` or `COMMUNITY` in `tools/sources.py`.
2. Run `python tools/build_dataset.py` — the per-source list should no
   longer mention the dead provider.
3. Run `pytest -q`. If the provider had a parametrized test entry,
   remove the entry too (otherwise the test will skip silently forever).
4. Commit the source change and the regenerated `ranges.bin` together.
5. The `release.yml` workflow will ship the change in the next monthly
   patch release without further action.

The 20%-shrink guard in `tools/build_dataset.py` will refuse a build
that removes too much coverage at once. If a single removal would
shrink the dataset by more than 20%, split it across multiple weeks
or use `--allow-shrink` with an explicit comment in the commit body
explaining why.

## AI-company sources

The `bot` tier includes five AI-company outbound IP sources, all
fetched from the existing CC0 community repos:

| Display name | Slug | Repo | Status |
| --- | --- | --- | --- |
| `OpenAI` | `openai` | lord-alfred | Absorbed into `GPTBot` |
| `Perplexity AI` | `perplexity` | lord-alfred | Absorbed into `PerplexityBot` |
| `DuckAssistBot` | `duckassistbot` | lord-alfred | Absorbed into `DuckDuckBot` |
| `Apple Intelligence Proxy` | `apple-proxy` | lord-alfred | Absorbed into `Apple Private Relay` (`vpn`) |
| `Meta` | `meta` | rezmoss | Active as a new `bot` label |

Four of the five are absorbed by the disjoint sweep because their
upstream ranges overlap exactly with ranges already published under
existing labels. The `_optional_*` helpers keep their entries in
`COMMUNITY` so that, if the upstream data ever diverges (e.g. OpenAI
publishes a brand-new outbound range that GPTBot's feed doesn't have),
the new range will appear in the next build without any code change.

Adding a new AI-company source in the future follows the same
checklist as any other community tier-2 source above.

## When something looks wrong

- **Build failed with "Refusing to write: ... is N% below the ...".**
  The 20%-shrink guard tripped. Either several sources failed at once
  or one changed shape and is now parsing to nothing. Look at the
  per-source counts in the run log. Pass `--allow-shrink` if the drop
  is genuine.
- **`::warning::` annotations piling up on the same slug for weeks.**
  The upstream is gone. Remove the entry (see "Removing a dead source").
- **Tests pass locally but fail in the workflow.** Almost always a
  pre-existing source that's now `unknown` because of a coordinate change.
  Run `tools/build_dataset.py` locally and inspect the per-provider counts.
- **The dataset stops getting releases.** `release.yml` only ships if
  the dataset actually changed since the last release tag. A quiet
  month is normal and intentional — see `release.yml` lines 4–8.