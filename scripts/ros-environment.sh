#!/usr/bin/env bash
# Source from the checkout before starting ROS nodes.
ino_ros_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ino_ros_distro="$(PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$ino_ros_root/ros-distro.py")" || return 2
if [[ -n "${ROS_DISTRO:-}" && "$ROS_DISTRO" != "$ino_ros_distro" ]]; then
    echo "[ERROR] Open a fresh shell before switching from $ROS_DISTRO to $ino_ros_distro." >&2
    return 2
fi
if [[ ! -f "/opt/ros/$ino_ros_distro/setup.bash" ]]; then
    echo "[ERROR] ROS $ino_ros_distro is missing. Run bash scripts/setup.sh." >&2
    return 2
fi
source "/opt/ros/$ino_ros_distro/setup.bash"
