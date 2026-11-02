#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-64}
export GZ_PARTITION=${GZ_PARTITION:-ino_camera_${ROS_DOMAIN_ID}}
mkdir -p logs
source scripts/environment.sh
exec python3 tools/supervise.py ros2 launch "$PWD/launch/stereo.launch.py" "$@"
