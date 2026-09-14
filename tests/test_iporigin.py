"""Tests for iporigin.

The dataset changes every time it is rebuilt, so nothing here asserts on a
specific prefix that might be reassigned next week. What is pinned instead
is behaviour a caller depends on: the classification contract, the reserved
and unknown cases, and the binary format round-tripping.
"""

import ipaddress

import pytest

import iporigin
from iporigin import _data, core


# --- contract --------------------------------------------------------------


def test_a_known_cloud_address_is_hosting():
    # AWS has announced 52.95.0.0/16 for many years; if this ever stops
    # being true the dataset is telling us something real.
    origin = iporigin.classify("52.95.110.1")
    assert origin.kind == iporigin.HOSTING
    assert origin.provider
    assert origin.is_datacenter


def test_classification_agrees_with_is_datacenter():
    for ip in ("52.95.110.1", "8.8.8.8", "127.0.0.1", "192.168.1.1"):
        assert iporigin.is_datacenter(ip) is iporigin.classify(ip).is_datacenter


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "192.168.1.1", "10.0.0.1", "169.254.1.1", "::1", "fe80::1"],
)
def test_reserved_addresses_are_reserved_not_unknown(ip):
    """Answering "unknown" for 127.0.0.1 is technically true and useless."""
    assert iporigin.classify(ip).kind == iporigin.RESERVED


def test_reserved_is_not_a_datacenter():
    assert iporigin.is_datacenter("127.0.0.1") is False


def test_unknown_has_no_provider():
    """An unmatched address must not invent a provider name."""
    origin = iporigin.classify("203.0.113.7")  # TEST-NET-3, never in a feed
    assert origin.kind in (iporigin.UNKNOWN, iporigin.RESERVED)
    assert origin.provider == ""


def test_origin_is_always_truthy():
    """`if classify(ip):` must not read as "is a datacenter"."""
    assert bool(iporigin.classify("127.0.0.1")) is True
    assert bool(iporigin.classify("52.95.110.1")) is True


def test_origin_is_immutable():
    origin = iporigin.classify("8.8.8.8")
    with pytest.raises(Exception):
        origin.kind = "nonsense"


# --- input handling --------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "nope", "8.8.8", "999.1.1.1", "::gg", None, 42])
def test_invalid_input_raises_value_error(bad):
    with pytest.raises(ValueError):
        iporigin.classify(bad)


def test_whitespace_is_tolerated():
    assert iporigin.classify("  8.8.8.8\n").ip == "8.8.8.8"


def test_accepts_an_ipaddress_object():
    origin = iporigin.classify(ipaddress.ip_address("52.95.110.1"))
    assert origin.kind == iporigin.HOSTING


def test_ipv6_is_classified():
    origin = iporigin.classify("2001:4860:4860::8888")
    assert origin.kind == iporigin.HOSTING
    assert origin.provider


def test_ipv4_and_ipv6_tables_are_independent():
    """A v6 address must never be matched against the v4 table."""
    data = _data.dataset()
    assert data.find(int(ipaddress.ip_address("2001:4860:4860::8888")), 6) is not None
    # The same integer read as v4 is out of range and must simply miss.
    assert len(data.v4_starts) and len(data.v6_starts)


# --- batch and metadata ----------------------------------------------------


def test_classify_many_yields_one_result_per_input():
    ips = ["8.8.8.8", "127.0.0.1", "52.95.110.1"]
    results = list(iporigin.classify_many(ips))
    assert [r.ip for r in results] == ips


def test_dataset_info_reports_provenance():
    info = iporigin.dataset_info()
    assert info["ranges"] > 1000
    assert info["ipv4_ranges"] and info["ipv6_ranges"]
    assert "Amazon AWS" in info["providers"]
    assert info["built_at"] > 1_700_000_000


# --- dataset integrity -----------------------------------------------------


def test_ranges_are_sorted_and_non_overlapping():
    """The lookup is a bisect that checks exactly one candidate, which is
    only correct if the table holds that invariant."""
    data = _data.dataset()
    for starts, ends in ((data.v4_starts, data.v4_ends), (data.v6_starts, data.v6_ends)):
        previous_end = -1
        for start, end in zip(starts, ends):
            assert start <= end
            assert start > previous_end, "overlapping or unsorted range at %d" % start
            previous_end = end


KNOWN_KINDS = (core.HOSTING, core.CDN, core.VPN, core.TOR, core.BOT)


def test_every_label_is_a_known_kind():
    for _, kind in _data.dataset().labels:
        assert kind in KNOWN_KINDS


@pytest.mark.parametrize("kind", KNOWN_KINDS)
def test_the_dataset_actually_contains_each_kind(kind):
    """A source silently returning nothing would leave a kind that the API
    advertises but the data can never produce."""
    kinds = {k for _, k in _data.dataset().labels}
    assert kind in kinds, "no provider in the dataset has kind %r" % kind


def test_the_gaps_the_readme_used_to_list_are_covered():
    """Hetzner and OVH have no official feed and were the two documented
    holes; they are filled from CC0 community lists now."""
    providers = set(iporigin.dataset_info()["providers"])
    assert "Hetzner" in providers
    assert "OVHcloud" in providers


def test_anonymizer_kinds_are_a_subset_of_datacenter_kinds():
    """A VPN or Tor exit is a machine, so anything anonymised is also a
    datacenter address — the two sets must not disagree."""
    assert core.ANONYMIZER_KINDS <= core.DATACENTER_KINDS


def test_bots_and_tor_count_as_datacenter():
    assert core.BOT in core.DATACENTER_KINDS
    assert core.TOR in core.DATACENTER_KINDS


def test_a_known_bot_range_is_classified_as_bot():
    """Sampled from the dataset rather than hardcoded, because crawler
    ranges move and a pinned address would rot."""
    data = _data.dataset()
    for start, label in zip(data.v4_starts, data.v4_labels):
        if data.labels[label][1] == core.BOT:
            origin = iporigin.classify(str(ipaddress.ip_address(start)))
            assert origin.kind == core.BOT
            assert origin.is_datacenter
            return
    pytest.fail("no bot ranges in the dataset")


def test_a_known_vpn_range_is_classified_as_vpn():
    data = _data.dataset()
    for start, label in zip(data.v4_starts, data.v4_labels):
        if data.labels[label][1] == core.VPN:
            origin = iporigin.classify(str(ipaddress.ip_address(start)))
            assert origin.kind == core.VPN
            assert origin.kind in core.ANONYMIZER_KINDS
            return
    pytest.fail("no vpn ranges in the dataset")


def test_a_corrupt_dataset_is_reported_clearly(tmp_path, monkeypatch):
    bad = tmp_path / "ranges.bin"
    bad.write_bytes(b"NOTADATASET" + b"\x00" * 64)
    monkeypatch.setattr(_data, "DATA_FILE", bad)
    monkeypatch.setattr(_data, "_loaded", None)

    with pytest.raises(_data.DatasetError, match="not an iporigin dataset"):
        _data.dataset()


def test_a_missing_dataset_says_how_to_fix_it(tmp_path, monkeypatch):
    monkeypatch.setattr(_data, "DATA_FILE", tmp_path / "absent.bin")
    monkeypatch.setattr(_data, "_loaded", None)

    with pytest.raises(_data.DatasetError, match="build_dataset"):
        _data.dataset()


def test_a_future_format_version_is_refused(tmp_path, monkeypatch):
    """A newer dataset must not be silently misread by an older build."""
    import struct

    blob = struct.pack("<8sHQHII", _data.MAGIC, 99, 0, 0, 0, 0)
    path = tmp_path / "ranges.bin"
    path.write_bytes(blob)
    monkeypatch.setattr(_data, "DATA_FILE", path)
    monkeypatch.setattr(_data, "_loaded", None)

    with pytest.raises(_data.DatasetError, match="upgrade iporigin"):
        _data.dataset()


# --- cli -------------------------------------------------------------------


def test_cli_prints_a_line_per_address(capsys):
    from iporigin.cli import main

    assert main(["8.8.8.8", "127.0.0.1"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    assert "8.8.8.8" in out[0]


def test_cli_json_output_is_parseable(capsys):
    import json

    from iporigin.cli import main

    main(["--json", "52.95.110.1"])
    row = json.loads(capsys.readouterr().out.strip())
    assert row["is_datacenter"] is True
    assert row["kind"] == "hosting"


def test_cli_datacenter_only_filters(capsys):
    from iporigin.cli import main

    main(["--datacenter-only", "52.95.110.1", "127.0.0.1"])
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert "52.95.110.1" in out[0]


def test_cli_reports_bad_input_without_aborting_the_batch(capsys):
    from iporigin.cli import main

    code = main(["nonsense", "8.8.8.8"])
    captured = capsys.readouterr()
    assert code == 2, "a bad address should be reflected in the exit code"
    assert "8.8.8.8" in captured.out, "the good address should still be processed"
    assert "nonsense" in captured.err


def test_cli_info_is_json(capsys):
    import json

    from iporigin.cli import main

    main(["--info"])
    assert json.loads(capsys.readouterr().out)["ranges"] > 1000


# --- online lookup ---------------------------------------------------------


def test_online_falls_back_to_offline_when_the_api_is_down(monkeypatch):
    """In a request path a slow API must not become an exception."""
    from iporigin import online

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(online.urllib.request, "urlopen", boom)
    origin = online.classify_online("52.95.110.1")
    assert origin.kind == iporigin.HOSTING
    assert origin.source == "local"


def test_online_can_be_asked_to_raise_instead(monkeypatch):
    from iporigin import online

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(online.urllib.request, "urlopen", boom)
    with pytest.raises(online.LookupError_):
        online.classify_online("52.95.110.1", fall_back=False)


def test_online_never_calls_out_for_a_reserved_address(monkeypatch):
    from iporigin import online

    def boom(*args, **kwargs):
        raise AssertionError("should not make a request for 127.0.0.1")

    monkeypatch.setattr(online.urllib.request, "urlopen", boom)
    assert online.classify_online("127.0.0.1").kind == iporigin.RESERVED


def _as_unknown(monkeypatch, ip):
    """Pin the offline verdict to UNKNOWN so the online logic is what is
    under test, not whichever address happens to be absent from this
    week's dataset."""
    from iporigin import online

    monkeypatch.setattr(
        online, "classify", lambda _: core.Origin(ip, iporigin.UNKNOWN)
    )


def test_online_upgrades_an_unknown_address_to_vpn(monkeypatch):
    """The point of the online mode: consumer VPN exits are in no feed."""
    from iporigin import online

    _as_unknown(monkeypatch, "198.18.7.9")
    _stub_api(monkeypatch, {"is_vpn": True, "provider": "SomeVPN Ltd"})
    origin = online.classify_online("198.18.7.9")
    assert origin.kind == iporigin.VPN
    assert origin.provider == "SomeVPN Ltd"
    assert origin.source == "api"


def test_online_treats_null_as_unknown_not_as_no(monkeypatch):
    """The API answers null when it could not determine the address."""
    from iporigin import online

    _as_unknown(monkeypatch, "198.18.7.9")
    _stub_api(monkeypatch, {"is_vpn": None, "provider": ""})
    origin = online.classify_online("198.18.7.9")
    assert origin.kind == iporigin.UNKNOWN
    assert origin.source == "local", "null must not be recorded as an API verdict"


def test_online_keeps_the_more_specific_local_provider(monkeypatch):
    from iporigin import online

    _stub_api(monkeypatch, {"is_vpn": True, "provider": "generic hoster"})
    origin = online.classify_online("52.95.110.1")
    assert origin.provider == iporigin.classify("52.95.110.1").provider


def _stub_api(monkeypatch, payload):
    import json
    from contextlib import contextmanager
    from iporigin import online

    @contextmanager
    def fake_urlopen(request, timeout=None):
        class Response:
            @staticmethod
            def read():
                return json.dumps(payload).encode()

        yield Response()

    monkeypatch.setattr(online.urllib.request, "urlopen", fake_urlopen)


# --- the build guard -------------------------------------------------------
#
# The weekly refresh commits straight to main, so this check is the only
# thing standing between a broken upstream feed and a shipped dataset.


def _build_module():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "tools" / "build_dataset.py"
    spec = importlib.util.spec_from_file_location("build_dataset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_large_shrink_is_refused():
    build = _build_module()
    assert build.shrink_complaint(30000, 5000) is not None


def test_a_normal_week_is_allowed():
    """Feeds move by a few percent all the time."""
    build = _build_module()
    assert build.shrink_complaint(30000, 29000) is None
    assert build.shrink_complaint(30000, 31500) is None


def test_growth_is_never_refused():
    build = _build_module()
    assert build.shrink_complaint(1000, 100000) is None


def test_the_first_ever_build_is_allowed():
    """No committed dataset to compare against."""
    build = _build_module()
    assert build.shrink_complaint(None, 10) is None
    assert build.shrink_complaint(0, 10) is None


def test_the_threshold_is_the_documented_one():
    build = _build_module()
    assert build.MAX_SHRINK == 0.20
    # Exactly at the limit passes; a hair below does not.
    assert build.shrink_complaint(1000, 800) is None
    assert build.shrink_complaint(1000, 799) is not None


def test_the_complaint_says_what_to_do():
    build = _build_module()
    message = build.shrink_complaint(30000, 5000)
    assert "--allow-shrink" in message
    assert "5000" in message and "30000" in message


def test_existing_range_count_reads_the_committed_dataset():
    build = _build_module()
    count = build.existing_range_count()
    assert count and count > 1000


def test_existing_range_count_survives_a_missing_or_corrupt_file(tmp_path, monkeypatch):
    build = _build_module()
    monkeypatch.setattr(build, "OUT", tmp_path / "absent.bin")
    assert build.existing_range_count() is None

    corrupt = tmp_path / "ranges.bin"
    corrupt.write_bytes(b"nope")
    monkeypatch.setattr(build, "OUT", corrupt)
    assert build.existing_range_count() is None


# --- the release bump ------------------------------------------------------
#
# Releases are cut by a scheduled job, so a bump that goes half-way lands on
# PyPI before anyone looks at it.


def _bump_module():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).parent.parent / "tools" / "bump_version.py"
    spec = importlib.util.spec_from_file_location("bump_version", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_two_declared_versions_agree():
    """pyproject.toml and __init__.py each hold the version separately."""
    bump = _bump_module()
    declared, exported = bump.read_versions(
        bump.PYPROJECT.read_text(), bump.INIT.read_text()
    )
    assert declared == exported == iporigin.__version__


def test_patch_bump():
    bump = _bump_module()
    assert bump.next_patch("1.1.0") == "1.1.1"
    assert bump.next_patch("1.1.9") == "1.1.10"
    assert bump.next_patch("0.0.0") == "0.0.1"


def test_a_non_numeric_version_is_left_alone():
    bump = _bump_module()
    for bad in ("2.0.0rc1", "1.1", "1.1.0.post1", "v1.1.0"):
        with pytest.raises(ValueError):
            bump.next_patch(bad)


def test_bump_rewrites_both_files():
    bump = _bump_module()
    pyproject, init, new = bump.bump(
        'name = "iporigin"\nversion = "1.2.3"\n', '__version__ = "1.2.3"\n'
    )
    assert new == "1.2.4"
    assert 'version = "1.2.4"' in pyproject
    assert '__version__ = "1.2.4"' in init


def test_bump_refuses_when_the_files_disagree():
    bump = _bump_module()
    with pytest.raises(ValueError, match="fix that before releasing"):
        bump.bump('version = "1.2.3"\n', '__version__ = "1.0.0"\n')


def test_bump_refuses_when_a_declaration_is_missing():
    bump = _bump_module()
    with pytest.raises(ValueError, match="pyproject"):
        bump.read_versions("name = \"iporigin\"\n", '__version__ = "1.0.0"\n')
    with pytest.raises(ValueError, match="__init__"):
        bump.read_versions('version = "1.0.0"\n', "x = 1\n")


def test_bump_only_touches_the_version_line():
    """pyproject holds other quoted values; a greedy substitution eats them."""
    bump = _bump_module()
    source = 'version = "1.2.3"\nrequires-python = ">=3.8"\n'
    pyproject, _init, _new = bump.bump(source, '__version__ = "1.2.3"\n')
    assert 'requires-python = ">=3.8"' in pyproject
