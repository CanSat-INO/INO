"""REGULUSミッションPC試験の回帰テスト。"""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import regulus_mission_host as mission


REQUIRED = [
    "platformio.ini",
    "src/MissionController.cpp",
    "src/MissionState.cpp",
    "include/MissionController.h",
    "include/MissionState.h",
    "include/MissionConfig.h",
    "include/MotorController.h",
    "include/CanSatData.h",
]


@pytest.fixture
def project(tmp_path):
    for name in REQUIRED:
        file = tmp_path / name
        file.parent.mkdir(
            parents=True, exist_ok=True
        )
        file.write_text(
            "placeholder\n", encoding="utf-8"
        )
    return tmp_path


def patch_process(monkeypatch, output, exit_code=0):
    monkeypatch.setattr(
        mission.shutil,
        "which",
        lambda _: "/fake/g++",
    )

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)

        if len(calls) == 1:
            assert any(
                "MissionController.cpp" in arg
                for arg in command
            )
            return subprocess.CompletedProcess(
                command, 0, "", ""
            )

        return subprocess.CompletedProcess(
            command,
            exit_code,
            output,
            "",
        )

    monkeypatch.setattr(
        mission.subprocess,
        "run",
        fake_run,
    )
    return calls


def test_explicit_trust_required(project):
    with pytest.raises(ValueError, match="同意"):
        mission.run_mission_host(
            project,
            trusted=False,
        )


def test_missing_project_files(tmp_path):
    with pytest.raises(ValueError, match="必要なREGULUS"):
        mission.run_mission_host(
            tmp_path,
            trusted=True,
        )


def test_compiler_missing(project, monkeypatch):
    monkeypatch.setattr(
        mission.shutil,
        "which",
        lambda _: None,
    )

    with pytest.raises(ValueError, match="g\\+\\+"):
        mission.run_mission_host(
            project,
            trusted=True,
        )


def test_compile_failure(project, monkeypatch):
    monkeypatch.setattr(
        mission.shutil,
        "which",
        lambda _: "/fake/g++",
    )

    def fail_compile(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            "synthetic compiler failure",
        )

    monkeypatch.setattr(
        mission.subprocess,
        "run",
        fail_compile,
    )

    result = mission.run_mission_host(
        project,
        trusted=True,
    )

    assert result["status"] == "COMPILE_FAILED"
    assert "synthetic compiler failure" in result["details"]


def test_success_report(project, monkeypatch):
    output = "\n".join(
        f"PASS: check-{n}"
        for n in range(7)
    )

    calls = patch_process(
        monkeypatch,
        output + "\n失敗件数: 0\n",
    )

    result = mission.run_mission_host(
        project,
        trusted=True,
    )

    assert result["status"] == "PASS"
    assert result["passed"] == 7
    assert result["failed"] == 0
    assert result["skipped"] == 0
    assert len(calls) == 2

    source = project / "src/MissionController.cpp"
    assert result["source_sha256"] == (
        hashlib.sha256(source.read_bytes()).hexdigest()
    )


def test_incomplete_report(project, monkeypatch):
    output = "\n".join(
        f"PASS: check-{n}"
        for n in range(6)
    )

    patch_process(
        monkeypatch,
        output,
    )

    result = mission.run_mission_host(
        project,
        trusted=True,
    )

    assert result["status"] == "INCOMPLETE"
    assert result["passed"] == 6


def test_failed_check(project, monkeypatch):
    output = (
        "\n".join(
            f"PASS: check-{n}"
            for n in range(6)
        )
        + "\nFAIL: last-check\n"
    )

    patch_process(
        monkeypatch,
        output,
        exit_code=1,
    )

    result = mission.run_mission_host(
        project,
        trusted=True,
    )

    assert result["status"] == "FAIL"
    assert result["failed"] == 1


def test_compiler_timeout(project, monkeypatch):
    monkeypatch.setattr(
        mission.shutil,
        "which",
        lambda _: "/fake/g++",
    )

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command,
            30,
        )

    monkeypatch.setattr(
        mission.subprocess,
        "run",
        timeout,
    )

    with pytest.raises(ValueError, match="コンパイル"):
        mission.run_mission_host(
            project,
            trusted=True,
        )
