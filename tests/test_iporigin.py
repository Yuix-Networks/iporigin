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


def test_every_label_is_a_known_kind():
    for _, kind in _data.dataset().labels:
        assert kind in (core.HOSTING, core.CDN, core.VPN)


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
