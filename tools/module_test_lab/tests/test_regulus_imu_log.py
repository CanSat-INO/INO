"""REGULUS IMUシリアルログ解析のテスト。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulus_imu_log import parse_imu_text, read_imu_log


VALID_SAMPLE = (
    "A[m/s2] 0.000 0.000 9.810 "
    "G[dps] 0.100 0.200 -0.100"
)


def test_valid_samples():
    text = (
        "=== REGULUS QMI8658 Test ===\n"
        "QMI8658 initialized at 0x6A\n"
        + VALID_SAMPLE + "\n"
        + VALID_SAMPLE + "\n"
    )

    result = parse_imu_text(text)

    assert result["status"] == "PARSED"
    assert result["sample_count"] == 2
    assert result["read_failures"] == 0

    assert result["statistics"]["accel_norm_mps2"]["mean"] \
        == pytest.approx(9.81)


def test_sensor_read_failure():
    result = parse_imu_text(
        VALID_SAMPLE + "\nQMI8658 read failed\n"
    )

    assert result["status"] == "WARNING"
    assert result["read_failures"] == 1
    assert result["sample_count"] == 1


def test_initialization_failure():
    result = parse_imu_text(
        "QMI8658 initialization failed; check wiring\n"
    )

    assert result["status"] == "NO_VALID_SAMPLES"
    assert result["initialization_failures"] == 1


def test_nonfinite_value():
    result = parse_imu_text(
        "A[m/s2] 0 0 nan G[dps] 0 0 0\n"
    )

    assert result["sample_count"] == 0
    assert result["malformed_samples"] == 1


def test_incomplete_sample():
    result = parse_imu_text(
        "A[m/s2] 0 0 9.81 G[dps] 0 0\n"
    )

    assert result["malformed_samples"] == 1
    assert result["status"] == "NO_VALID_SAMPLES"


def test_source_is_not_modified(tmp_path):
    path = tmp_path / "imu_log.txt"
    path.write_text(VALID_SAMPLE + "\n", encoding="utf-8")

    before = path.read_bytes()
    report = read_imu_log(path)

    assert report["sample_count"] == 1
    assert path.read_bytes() == before


def test_log_size_limit():
    with pytest.raises(ValueError):
        parse_imu_text("x" * (1024 * 1024 + 1))
