"""PlatformIOプロジェクトの読み取りとREGULUS状態管理のPC試験。"""

import argparse
from configparser import ConfigParser
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


def inspect_project(folder):
    root = Path(folder).expanduser().resolve()
    ini = root / "platformio.ini"

    if not ini.is_file():
        raise ValueError("platformio.iniが見つかりません")

    config = ConfigParser(interpolation=None, strict=False)
    with ini.open(encoding="utf-8") as stream:
        config.read_file(stream)

    environments = []
    shared_board = config.get("env", "board", fallback=None)
    shared_framework = config.get("env", "framework", fallback=None)

    for section in config.sections():
        if not section.startswith("env:"):
            continue

        environments.append({
            "name": section[4:],
            "board": config.get(
                section, "board", fallback=shared_board
            ) or "未指定・継承の可能性",
            "framework": config.get(
                section, "framework", fallback=shared_framework
            ) or "未指定・継承の可能性",
            "extends": config.get(
                section, "extends", fallback=""
            ),
        })

    files = {}
    extensions = {".cpp", ".c", ".h", ".hpp", ".ino"}

    for name in ("src", "include", "lib"):
        directory = root / name
        if not directory.is_dir():
            files[name] = []
            continue

        files[name] = [
            str(path.relative_to(root))
            for path in sorted(directory.rglob("*"))
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in extensions
        ]

    return {
        "project": str(root),
        "environments": environments,
        "files": files,
        "source_count": sum(len(v) for v in files.values()),
    }


def test_mission_state(folder):
    """信頼できるREGULUS実コードの状態名・コマンド判定を試験。"""
    root = Path(folder).expanduser().resolve()
    source = root / "src/MissionState.cpp"
    header = root / "include/MissionState.h"

    if not source.is_file() or not header.is_file():
        return {
            "status": "NOT_SUPPORTED",
            "reason": "このプロジェクトにMissionState実コードがありません",
        }

    compiler = shutil.which("g++")
    if not compiler:
        return {
            "status": "UNAVAILABLE",
            "reason": "PC用のg++が見つかりません",
        }

    test_code = r'''
#include <iostream>
#include <string_view>
#include "MissionState.h"

int main() {
    using std::string_view;

    if (string_view(mission_state_name(MissionState::BOOT))
        != "BOOT") return 1;

    if (string_view(mission_state_name(MissionState::RUNNING))
        != "RUNNING") return 2;

    if (string_view(mission_state_name(MissionState::FAILSAFE))
        != "FAILSAFE") return 3;

    for (int i = 1; i <= 8; ++i) {
        if (!is_valid_mission_command(i)) return 4;
    }

    if (is_valid_mission_command(0)) return 5;
    if (is_valid_mission_command(9)) return 6;

    std::cout << "REGULUS MissionState: PASS\n";
    return 0;
}
'''

    try:
        with TemporaryDirectory(prefix="cansat-platformio-test-") as tmp:
            work = Path(tmp)
            (work / "Arduino.h").write_text(
                "#pragma once\n#include <stdint.h>\n"
            )
            (work / "check.cpp").write_text(test_code)
            binary = work / "regulus_check"

            built = subprocess.run(
                [
                    compiler, "-std=c++17", "-Wall", "-Wextra",
                    "-I", str(work),
                    "-I", str(root / "include"),
                    str(source),
                    str(work / "check.cpp"),
                    "-o", str(binary),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=work,
            )

            if built.returncode != 0:
                return {
                    "status": "FAIL",
                    "reason": "PC用コンパイル失敗",
                    "details": built.stderr[-2000:],
                }

            executed = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=work,
            )

            return {
                "status": (
                    "PASS" if executed.returncode == 0 else "FAIL"
                ),
                "exit_code": executed.returncode,
                "output": executed.stdout[-1000:],
                "source_sha256": sha256(
                    source.read_bytes()
                ).hexdigest(),
            }

    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "ERROR",
            "reason": str(exc),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument(
        "--test-mission-state",
        action="store_true",
        help="信頼できるMissionState.cppをPC上で実行して検証",
    )
    args = parser.parse_args()

    try:
        report = inspect_project(args.project)
        if args.test_mission_state:
            report["mission_state_test"] = test_mission_state(
                args.project
            )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"検査エラー: {exc}\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
