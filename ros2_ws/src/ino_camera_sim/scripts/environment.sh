#!/usr/bin/env bash
# ROS nodes use system Python even when launched from Module Test Lab's venv.
if [ -n "${VIRTUAL_ENV:-}" ]; then
    export PATH="$(/usr/bin/python3 -c 'import os; print(":".join(p for p in os.environ["PATH"].split(":") if p != os.environ["VIRTUAL_ENV"]+"/bin"))')"
    unset VIRTUAL_ENV
fi
unset PYTHONHOME
ino_script_dir="$(dirname "${BASH_SOURCE[0]}")"
ino_ros_environment="$ino_script_dir/ros-environment.sh"
if [[ ! -f "$ino_ros_environment" ]]; then
    ino_ros_environment="$ino_script_dir/../../../../scripts/ros-environment.sh"
fi
source "$ino_ros_environment" || exit 2
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-64}
export GZ_PARTITION=${GZ_PARTITION:-ino_camera_${ROS_DOMAIN_ID}}
export GZ_IP=${GZ_IP:-127.0.0.1}
