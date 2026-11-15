"""CanSat Simulation用 ROS 2 / Gazebo 環境診断。"""

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


ROS_CHECK = r'''
source "$CANSAT_ROS_SETUP" >/dev/null 2>&1 || exit 9

printf 'DISTRO=%s\n' "${ROS_DISTRO:-unknown}"

if command -v ros2 >/dev/null 2>&1 &&
   ros2 --help >/dev/null 2>&1; then
    echo "ROS2=available"
else
    echo "ROS2=unavailable"
fi

if command -v gz >/dev/null 2>&1; then
    echo "GAZEBO=detected"
else
    echo "GAZEBO=missing"
fi
'''


def check_package(name):
    """インストール済みパッケージだけを確認する。"""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (
            result.returncode == 0
            and result.stdout.strip() == "install ok installed"
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def diagnose(ros_root=Path("/opt/ros")):
    """システムを書き換えず環境を診断する。"""
    report = {
        "os": platform.platform(),
        "wsl": False,
        "python": sys.version.split()[0],
        "colcon": bool(shutil.which("colcon")),
        "ros2": "not_detected",
        "ros_distro": None,
        "ros_setup": None,
        "gazebo": "not_detected",
        "ros_gz_bridge": False,
        "notes": [],
    }

    try:
        kernel = Path("/proc/sys/kernel/osrelease").read_text()
        report["wsl"] = "microsoft" in kernel.lower()
    except OSError:
        pass

    setups = sorted(ros_root.glob("*/setup.bash"))

    preferred = os.environ.get("ROS_DISTRO")
    if preferred:
        setups.sort(
            key=lambda p: (p.parent.name != preferred, p.parent.name)
        )

    if not setups:
        if shutil.which("gz"):
            report["gazebo"] = "command_detected"
        report["notes"].append(
            "ROS 2の標準設定ファイルが見つかりません"
        )
        return report

    setup = setups[0]
    distro = setup.parent.name

    report["ros_distro"] = distro
    report["ros_setup"] = str(setup)
    report["ros_gz_bridge"] = check_package(
        f"ros-{distro}-ros-gz-bridge"
    )

    env = os.environ.copy()
    env["CANSAT_ROS_SETUP"] = str(setup)

    try:
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-c", ROS_CHECK],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
            check=False,
        )

        if result.returncode != 0:
            report["notes"].append(
                "ROS 2の環境設定を正常に読み込めませんでした"
            )
            return report

        values = dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line
        )

        if values.get("ROS2") == "available":
            report["ros2"] = "available_after_setup"

        if values.get("GAZEBO") == "detected":
            report["gazebo"] = "command_detected"

    except subprocess.TimeoutExpired:
        report["notes"].append(
            "ROS 2の確認がタイムアウトしました"
        )
    except OSError as exc:
        report["notes"].append(
            f"診断コマンドを起動できません: {exc}"
        )

    return report


if __name__ == "__main__":
    print(
        json.dumps(
            diagnose(),
            ensure_ascii=False,
            indent=2,
        )
    )
