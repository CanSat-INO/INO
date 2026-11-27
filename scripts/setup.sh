#!/usr/bin/env bash
# Clone-local GUI environment + Ubuntu/ROS dependencies. Safe to rerun.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_ONLY=0; SYSTEM_ONLY=0; SKIP_SYSTEM=0; DRY=0; DEV=0; IME=0
usage() {
 cat <<'HELP'
Usage: bash scripts/setup.sh [options]
  --lab-only               GUI / offline Test Lab only; no ROS repository changes
  --system-only            ROS / system dependencies only; do not create a venv
  --skip-system-packages   Reuse already installed dependencies; install local Python only
  --with-ime               Install optional Fcitx5/Mozc tools (no user profile overwrite)
  --dev                    Also install pinned test dependencies
  --dry-run                Print plan; do not install, download or write files
  --help                   Show this help
HELP
}
for arg in "$@"; do
 case "$arg" in
  --lab-only) LAB_ONLY=1;; --system-only) SYSTEM_ONLY=1;;
  --skip-system-packages) SKIP_SYSTEM=1;; --dry-run) DRY=1;; --dev) DEV=1;; --with-ime) IME=1;;
  --help|-h) usage; exit 0;; *) echo "Unknown option: $arg" >&2; exit 2;;
 esac
done
if (( LAB_ONLY && SYSTEM_ONLY )); then echo 'Choose lab-only or system-only, not both.' >&2; exit 2; fi
ROS_DISTRO="$(/usr/bin/python3 - "$ROOT" <<'CHECK'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from install_ros2 import os_release,validate_os
print(validate_os(os_release()))
CHECK
)"
if (( EUID == 0 && ! SYSTEM_ONLY )); then
 echo 'Run as your normal Ubuntu user. Only apt operations use sudo; the venv must not belong to root.' >&2; exit 2
fi
if (( ! SYSTEM_ONLY )); then
 if [[ -L "$ROOT/.venv" ]]; then echo 'Refusing to change a symlinked .venv. Use a clone-local environment.' >&2; exit 2; fi
 if [[ -e "$ROOT/.venv" && ! -x "$ROOT/.venv/bin/python" ]]; then
  echo 'Existing .venv is incomplete. Move it aside yourself; setup will not overwrite or delete it.' >&2; exit 2
 fi
fi
export LANG=C.UTF-8 LC_ALL=C.UTF-8
run() {
 printf '+'; printf ' %q' "$@"; printf '\n'
 if (( ! DRY )); then "$@"; fi
}
SUDO=(); if (( EUID != 0 )); then SUDO=(sudo); fi
GUI_PACKAGES=(git python3-venv libegl1 libgl1 libopengl0 libdbus-1-3 libxcb-cursor0
 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
 libxcb-xinerama0 libxcb-xkb1 fonts-noto-cjk mesa-utils)
ROS_PACKAGES=(g++ "ros-$ROS_DISTRO"-rosbag2 "ros-$ROS_DISTRO"-rosbag2-storage-mcap "ros-$ROS_DISTRO"-ros-gz "ros-$ROS_DISTRO"-rtabmap-ros "ros-$ROS_DISTRO"-rviz2 "ros-$ROS_DISTRO"-cv-bridge
 "ros-$ROS_DISTRO"-teleop-twist-keyboard "ros-$ROS_DISTRO"-rmw-zenoh-cpp "ros-$ROS_DISTRO"-gz-transport-vendor
 "ros-$ROS_DISTRO"-gz-msgs-vendor python3-opencv python3-numpy python3-scipy python3-yaml
 python3-pil python3-matplotlib python3-tk python3-colcon-common-extensions)
if (( ! SKIP_SYSTEM )); then
 if (( ! LAB_ONLY )); then
  OPTIONS=(); if (( DRY )); then OPTIONS+=(--dry-run); fi
  /usr/bin/python3 "$ROOT/scripts/install_ros2.py" "${OPTIONS[@]}"
 fi
 run "${SUDO[@]}" apt-get update
 PACKAGES=("${GUI_PACKAGES[@]}")
 if (( ! LAB_ONLY )); then PACKAGES+=("${ROS_PACKAGES[@]}"); fi
 if (( IME )); then PACKAGES+=(fcitx5 fcitx5-mozc fcitx5-config-qt); fi
 run "${SUDO[@]}" apt-get install -y "${PACKAGES[@]}"
fi
if (( ! SYSTEM_ONLY )); then
 if [[ ! -x "$ROOT/.venv/bin/python" ]]; then run /usr/bin/python3 -m venv "$ROOT/.venv"; fi
 REQUIREMENTS="$ROOT/requirements-gui.txt"; if (( DEV )); then REQUIREMENTS="$ROOT/requirements-dev.txt"; fi
 run "$ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"
fi
if (( DRY )); then echo 'Dry run finished. No setup changes were made.'; exit 0; fi
CHECK_ARGS=(); if (( LAB_ONLY )); then CHECK_ARGS+=(--lab-only); fi
if (( SYSTEM_ONLY )); then CHECK_ARGS+=(--ros-only); fi
exec /usr/bin/python3 "$ROOT/scripts/doctor.py" "${CHECK_ARGS[@]}"
