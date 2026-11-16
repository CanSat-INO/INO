"""REGULUS GNSSログ解析の回帰テスト。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulus_gnss_log import parse_gnss_text, read_gnss_log


def snapshot(valid=1, fix=1, lat="35.0", lon="139.0"):
    return (
        f"valid={valid} fix={fix} lat={lat} lon={lon} "
        "alt=20.0 m sats=8 age=100 ms "
        "chars=500 ok=10 failed=0"
    )


def nmea(payload):
    checksum = 0
    for char in payload:
        checksum ^= ord(char)
    return f"${payload}*{checksum:02X}"


def test_valid_snapshot():
    r = parse_gnss_text(snapshot())
    assert r["status"] == "PARSED"
    assert r["snapshot_count"] == 1
    assert r["reported_fix_count"] == 1


def test_no_fix_snapshot():
    r = parse_gnss_text(snapshot(valid=0, fix=0))
    assert r["reported_no_fix_count"] == 1
    assert r["reported_fix_count"] == 0


def test_invalid_latitude():
    r = parse_gnss_text(snapshot(lat="95.0"))
    assert r["malformed_snapshots"] == 1
    assert r["snapshot_count"] == 0


def test_invalid_longitude():
    r = parse_gnss_text(snapshot(lon="181"))
    assert r["malformed_snapshots"] == 1


def test_nan_coordinate():
    r = parse_gnss_text(snapshot(lat="nan"))
    assert r["malformed_snapshots"] == 1


def test_inconsistent_valid_fix():
    r = parse_gnss_text(snapshot(valid=0, fix=1))
    assert r["status"] == "WARNING"
    assert r["inconsistent_fix_count"] == 1


def test_nmea_gga_fix_indication():
    line = nmea(
        "GNGGA,120000.00,3530.000,N,13930.000,E,"
        "1,08,0.9,20.0,M,0.0,M,,"
    )
    r = parse_gnss_text(line)
    assert r["nmea_count"] == 1
    assert r["nmea_fix_indications"] == 1


def test_nmea_rmc_no_fix():
    line = nmea("GNRMC,120000.00,V,,,,,,,161126,,,N")
    r = parse_gnss_text(line)
    assert r["nmea_count"] == 1
    assert r["nmea_no_fix_indications"] == 1


def test_nmea_bad_checksum():
    line = nmea("GNRMC,120000.00,V,,,,,,,161126,,,N")
    original = int(line[-2:], 16)
    bad = line[:-2] + f"{original ^ 0xFF:02X}"
    r = parse_gnss_text(bad)
    assert r["nmea_bad_checksum"] == 1
    assert r["nmea_count"] == 0


def test_incomplete_nmea():
    r = parse_gnss_text("$GNGGA,120000.00")
    assert r["nmea_malformed"] == 1


def test_mixed_formats():
    line = nmea("GNRMC,120000.00,V,,,,,,,161126,,,N")
    r = parse_gnss_text(
        "GNSS UART RX=1 TX=2 baud=9600\n"
        + line + "\n" + snapshot()
    )
    assert r["nmea_count"] == 1
    assert r["snapshot_count"] == 1
    assert r["ignored_lines"] == 1


def test_source_not_modified(tmp_path):
    file = tmp_path / "gnss.txt"
    file.write_text(snapshot() + "\n", encoding="utf-8")
    before = file.read_bytes()
    r = read_gnss_log(file)
    assert r["snapshot_count"] == 1
    assert file.read_bytes() == before


def test_size_limit():
    with pytest.raises(ValueError):
        parse_gnss_text("x" * (1024 * 1024 + 1))
