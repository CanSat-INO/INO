"""PlatformIOプロジェクト読み込みの回帰テスト。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from platformio_project_probe import (
    inspect_project,
    test_mission_state as run_mission_state_test,
)


def test_project_inspection(tmp_path):
    (tmp_path / "platformio.ini").write_text(
        "[env]\n"
        "board = esp32-s3-devkitc-1\n"
        "framework = arduino\n"
        "\n"
        "[env:imu_test]\n",
        encoding="utf-8",
    )

    src = tmp_path / "src"
    src.mkdir()
    (src / "main.cpp").write_text(
        "int example = 1;\n",
        encoding="utf-8",
    )

    report = inspect_project(tmp_path)

    assert report["source_count"] == 1
    assert report["files"]["src"] == ["src/main.cpp"]

    env = report["environments"][0]
    assert env["name"] == "imu_test"
    assert env["board"] == "esp32-s3-devkitc-1"
    assert env["framework"] == "arduino"


def test_missing_platformio_ini(tmp_path):
    with pytest.raises(ValueError):
        inspect_project(tmp_path)


def test_missing_mission_state_is_not_supported(tmp_path):
    report = run_mission_state_test(tmp_path)
    assert report["status"] == "NOT_SUPPORTED"


def test_inspection_does_not_modify_source(tmp_path):
    (tmp_path / "platformio.ini").write_text(
        "[env:test]\nboard = esp32-s3-devkitc-1\n",
        encoding="utf-8",
    )

    src = tmp_path / "src"
    src.mkdir()
    source = src / "main.cpp"
    source.write_text("int value = 42;\n", encoding="utf-8")

    before = source.read_bytes()

    inspect_project(tmp_path)

    assert source.read_bytes() == before
