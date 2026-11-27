#!/usr/bin/env bash
set -eo pipefail
if [[ $# != 2 ]]; then
    echo "Usage: bash scripts/sensor-bag.sh record|play BAG_DIRECTORY" >&2
    exit 2
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/ros-environment.sh"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
topics=(/clock /tf /tf_static /odom /ground/imu /ground/encoder_odom
        /raw/left/image /raw/right/image /raw/left/camera_info /raw/right/camera_info)
case "$1" in
    record)
        export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-67}
        exec ros2 bag record --storage mcap --output "$2" --topics "${topics[@]}"
        ;;
    play)
        export ROS_DOMAIN_ID=${INO_REPLAY_DOMAIN:-76}
        if [[ ! "$ROS_DOMAIN_ID" =~ ^(0|[1-9][0-9]{0,2})$ ]] || (( ROS_DOMAIN_ID < 76 || ROS_DOMAIN_ID > 232 )); then
            echo "Choose a dedicated replay domain from 76 to 232." >&2
            exit 2
        fi
        # Explicit allowlist also applies to bags recorded by other tools.
        echo "Replay paused on ROS domain $ROS_DOMAIN_ID. After connecting the subscriber, call /rosbag2_player/resume." >&2
        exec ros2 bag play "$2" --start-paused --qos-profile-overrides-path "$script_dir/sensor-replay-qos.yaml" --topics "${topics[@]}"
        ;;
    *) exit 2 ;;
esac
