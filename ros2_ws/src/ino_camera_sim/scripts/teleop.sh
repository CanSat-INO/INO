#!/usr/bin/env bash
set -e
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-64}
source "$(dirname "$0")/environment.sh"
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -p speed:=0.04 -p turn:=0.06
