"""REGULUS実コードのPC用仮想ミッション試験。実機操作なし。"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


ARDUINO = r'''
#pragma once
#include <cstdint>
#include <cmath>
using std::isfinite;
#define DEG_TO_RAD 0.017453292519943295
#define RAD_TO_DEG 57.29577951308232
uint32_t millis();
'''

PREFERENCES = r'''
#pragma once
#include <cstdint>
#include <cstddef>

class Preferences {
public:
    bool begin(const char*, bool = false) { return true; }
    void end() {}
    uint8_t getUChar(const char*, uint8_t v = 0) { return v; }
    bool getBool(const char*, bool v = false) { return v; }
    double getDouble(const char*, double v = 0) { return v; }
    size_t putUChar(const char*, uint8_t) { return 1; }
    size_t putBool(const char*, bool) { return 1; }
    size_t putDouble(const char*, double) { return 8; }
};
'''

HOST = r'''
#include <iostream>
#include <cstdint>
#include "MissionController.h"
#include "MissionConfig.h"

static uint8_t last_motor_state = 0;
static int failures = 0;

uint32_t millis() { return 0; }

void MotorController::begin() { stop(); }
void MotorController::stop() {
    state_ = MotorDriveState::STOPPED;
}
void MotorController::forward() {
    state_ = MotorDriveState::FORWARD;
}
void MotorController::turnLeft() {
    state_ = MotorDriveState::TURN_LEFT;
}
void MotorController::turnRight() {
    state_ = MotorDriveState::TURN_RIGHT;
}

bool update_mission_status(
    MissionState, MissionSubState, OperationMode
) { return true; }

bool update_failsafe_reason(FailsafeReason) {
    return true;
}

bool update_navigation_status(
    bool, double, double, float,
    uint8_t motor_state, uint8_t
) {
    last_motor_state = motor_state;
    return true;
}

void check(bool condition, const char* label) {
    std::cout << (condition ? "PASS: " : "FAIL: ")
              << label << '\n';
    if (!condition) ++failures;
}

int main() {
    CanSatData_t data{};
    data.sys.battery_voltage =
        MissionConfig::BATTERY_VALID_MAX_VOLTAGE;

    {
        MissionController mission;
        mission.begin();

        check(
            mission.state() == MissionState::BOOT,
            "初期状態はBOOT"
        );

        bool accepted = mission.handleCommand(
            static_cast<uint8_t>(
                MissionCommand::SELECT_MISSION_MODE
            ), 1000
        );

        check(
            accepted &&
            mission.state() == MissionState::LAUNCH_STANDBY,
            "ミッションモード選択で待機状態へ"
        );

        mission.update(data, 2000);

        check(
            mission.state() == MissionState::LAUNCH_STANDBY,
            "IMU未取得時は打ち上げ判定しない"
        );
    }

    {
        MissionController mission;
        mission.begin();

        bool mode_ok = mission.handleCommand(
            static_cast<uint8_t>(
                MissionCommand::SELECT_DEVELOPMENT_MODE
            ), 1000
        );

        bool landed_ok = mission.handleCommand(
            static_cast<uint8_t>(
                MissionCommand::CONFIRM_LANDED
            ), 1100
        );

        check(
            mode_ok && landed_ok &&
            mission.state() == MissionState::LANDED,
            "開発モードで着地状態へ"
        );

        mission.update(data, 1200);
        mission.update(
            data,
            1201 + MissionConfig::SEPARATION_HOLD_MS
        );

        check(
            mission.state() == MissionState::RUNNING,
            "分離処理後に走行状態へ"
        );

        mission.update(
            data,
            1202 + MissionConfig::SEPARATION_HOLD_MS
        );

        check(
            last_motor_state ==
                static_cast<uint8_t>(
                    MotorDriveState::STOPPED
                ),
            "測位データがない場合は停止を指示"
        );
    }

    if (
        MissionConfig::LOW_BATTERY_VOLTAGE >=
        MissionConfig::BATTERY_VALID_MIN_VOLTAGE
    ) {
        MissionController mission;
        mission.begin();

        CanSatData_t low_data{};
        low_data.sys.battery_voltage =
            MissionConfig::LOW_BATTERY_VOLTAGE;

        mission.update(low_data, 2000);
        mission.update(
            low_data,
            2001 + MissionConfig::LOW_BATTERY_CONFIRM_MS
        );

        check(
            mission.state() == MissionState::FAILSAFE,
            "低電圧継続でFAILSAFEへ"
        );
    } else {
        std::cout
            << "SKIP: 低電圧閾値が有効範囲外\n";
    }

    std::cout << "失敗件数: " << failures << '\n';
    return failures == 0 ? 0 : 1;
}
'''


def run_mission_host(project, *, trusted=False):
    """明示的に許可されたローカルC++のみコンパイル・実行。"""

    if not trusted:
        raise ValueError(
            "C++コード実行への明示的な同意が必要です"
        )

    root = Path(project).expanduser().resolve()

    required = [
        root / "platformio.ini",
        root / "src/MissionController.cpp",
        root / "src/MissionState.cpp",
        root / "include/MissionController.h",
        root / "include/MissionState.h",
        root / "include/MissionConfig.h",
        root / "include/MotorController.h",
        root / "include/CanSatData.h",
    ]

    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise ValueError(
            "必要なREGULUSファイルがありません: "
            + ", ".join(missing)
        )

    compiler = shutil.which("g++")
    if not compiler:
        raise ValueError("g++が見つかりません")

    with TemporaryDirectory(
        prefix="cansat-mission-host-"
    ) as tmp:
        work = Path(tmp)

        (work / "Arduino.h").write_text(
            ARDUINO, encoding="utf-8"
        )
        (work / "Preferences.h").write_text(
            PREFERENCES, encoding="utf-8"
        )
        (work / "host.cpp").write_text(
            HOST, encoding="utf-8"
        )

        binary = work / "mission_test"

        command = [
            compiler, "-std=c++17", "-O0",
            "-Wall", "-Wextra",
            "-I", str(work),
            "-I", str(root / "include"),
            str(root / "src/MissionController.cpp"),
            str(root / "src/MissionState.cpp"),
            str(work / "host.cpp"),
            "-o", str(binary),
        ]

        try:
            built = subprocess.run(
                command, capture_output=True,
                text=True, timeout=30, cwd=work
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                "コンパイルを完了できませんでした"
            ) from exc

        if built.returncode != 0:
            return {
                "status": "COMPILE_FAILED",
                "checks": [],
                "details": built.stderr[-5000:],
            }

        try:
            executed = subprocess.run(
                [str(binary)], capture_output=True,
                text=True, timeout=10, cwd=work
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                "PC試験を完了できませんでした"
            ) from exc

    lines = executed.stdout.splitlines()
    passed = [s[6:] for s in lines if s.startswith("PASS: ")]
    failed = [s[6:] for s in lines if s.startswith("FAIL: ")]
    skipped = [s[6:] for s in lines if s.startswith("SKIP: ")]

    # 7項目が実行されて初めて完全合格とする
    complete = len(passed) == 7 and not failed and not skipped

    status = (
        "PASS" if executed.returncode == 0 and complete
        else "INCOMPLETE" if executed.returncode == 0
        else "FAIL"
    )

    source = root / "src/MissionController.cpp"

    return {
        "status": status,
        "project": str(root),
        "source_sha256": sha256(
            source.read_bytes()
        ).hexdigest(),
        "passed": len(passed),
        "failed": len(failed),
        "skipped": len(skipped),
        "checks": [
            {"result": "PASS", "name": x} for x in passed
        ] + [
            {"result": "FAIL", "name": x} for x in failed
        ] + [
            {"result": "SKIP", "name": x} for x in skipped
        ],
        "output": executed.stdout[-5000:],
        "errors": executed.stderr[-3000:],
        "limitations": [
            "Arduino・Preferences・モーターをPC用に模擬",
            "不揮発保存・実機GPIO・FreeRTOSは未検証",
            "元のREGULUSソースは変更しない",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument(
        "--trust-cpp", action="store_true",
        help="信頼できるC++をPCでコンパイル・実行する"
    )
    args = parser.parse_args()

    try:
        report = run_mission_host(
            args.project, trusted=args.trust_cpp
        )
    except ValueError as exc:
        parser.exit(1, f"試験エラー: {exc}\n")

    print(json.dumps(
        report, ensure_ascii=False, indent=2
    ))

    if report["status"] != "PASS":
        parser.exit(1)


if __name__ == "__main__":
    main()
