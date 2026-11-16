"""REGULUS HP203Bログ解析テスト。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulus_baro_log import parse_baro_text, read_baro_log

SAMPLE1 = (
    "pressure=1013.25 hPa "
    "temperature=24.50 C altitude=15.20 m"
)
SAMPLE2 = (
    "pressure=1013.15 hPa "
    "temperature=24.70 C altitude=16.20 m"
)


def test_valid_samples():
    report = parse_baro_text(SAMPLE1 + "\n" + SAMPLE2)
    assert report["status"] == "PARSED"
    assert report["sample_count"] == 2
    assert report["statistics"]["pressure_hpa"]["mean"] \
        == pytest.approx(1013.20)


def test_altitude_change():
    report = parse_baro_text(SAMPLE1 + "\n" + SAMPLE2)
    assert report["altitude_change_m"] == pytest.approx(1.0)
    assert report["altitude_range_m"] == pytest.approx(1.0)


def test_read_failure():
    report = parse_baro_text(
        SAMPLE1 + "\nHP203B read failed"
    )
    assert report["status"] == "WARNING"
    assert report["read_failures"] == 1


def test_initialization_failure():
    report = parse_baro_text(
        "HP203B initialization failed"
    )
    assert report["status"] == "NO_VALID_SAMPLES"
    assert report["initialization_failures"] == 1


def test_nonfinite_number():
    report = parse_baro_text(
        "pressure=nan hPa "
        "temperature=24.5 C altitude=15.2 m"
    )
    assert report["malformed_samples"] == 1
    assert report["sample_count"] == 0


def test_incomplete_sample():
    report = parse_baro_text(
        "pressure=1013.2 hPa temperature=24.5 C"
    )
    assert report["malformed_samples"] == 1


def test_impossible_pressure():
    report = parse_baro_text(
        "pressure=-10 hPa "
        "temperature=24 C altitude=10 m"
    )
    assert report["invalid_values"] == 1


def test_negative_altitude_allowed():
    report = parse_baro_text(
        "pressure=1013 hPa "
        "temperature=20 C altitude=-5 m"
    )
    assert report["sample_count"] == 1


def test_source_not_modified(tmp_path):
    file = tmp_path / "baro.txt"
    file.write_text(SAMPLE1 + "\n", encoding="utf-8")
    original = file.read_bytes()

    report = read_baro_log(file)

    assert report["sample_count"] == 1
    assert file.read_bytes() == original


def test_log_size_limit():
    with pytest.raises(ValueError):
        parse_baro_text("x" * (1024 * 1024 + 1))
