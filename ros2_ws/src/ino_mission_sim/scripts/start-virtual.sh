#!/usr/bin/env bash
set -eo pipefail
package="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    PATH="${PATH#"$VIRTUAL_ENV/bin:"}"
    unset VIRTUAL_ENV
fi
unset PYTHONHOME
environment="$package/scripts/ros-environment.sh"
if [[ ! -f "$environment" ]]; then
    environment="$package/../../../scripts/ros-environment.sh"
fi
source "$(dirname "$environment")/sim-environment.sh"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-67}
if [[ ! "$ROS_DOMAIN_ID" =~ ^(0|[1-9][0-9]{0,2})$ ]] || (( ROS_DOMAIN_ID > 232 )); then
    echo "ROS_DOMAIN_ID must be an integer between 0 and 232." >&2
    exit 2
fi
export GZ_PARTITION=${GZ_PARTITION:-ino_virtual_$ROS_DOMAIN_ID}
export GZ_IP=127.0.0.1
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
lockdir="${XDG_RUNTIME_DIR:-$HOME/.cache}/ino-virtual"
mkdir -p "$lockdir"
exec 9>"$lockdir/domain-$ROS_DOMAIN_ID.lock"
if ! flock -n 9; then
    echo "A virtual sensor session is already active on ROS domain $ROS_DOMAIN_ID." >&2
    exit 2
fi
run=''
for arg in "$@"; do
    case "$arg" in runtime:=*) run="${arg#runtime:=}";; esac
done
if [[ -z "$run" ]]; then
    run="$(mktemp -d "${TMPDIR:-/tmp}/ino-virtual.XXXXXXXX")"
fi
mkdir -p "$run"
{
    printf 'ros_distro=%s\nros_domain_id=%s\n' "$ROS_DISTRO" "$ROS_DOMAIN_ID"
    printf 'git_commit='
    git -C "$package" rev-parse HEAD 2>/dev/null || printf 'unavailable\n'
    printf 'gazebo_sim_versions=\n'
    gz sim --versions || true
    printf 'launch_argument=%s\n' "$@"
} > "$run/environment.txt"
echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID results=$run"
ino_sim_run ros2 launch "$package/launch/ground.launch.py" sensors_only:=true gui:=false rviz:=false runtime:="$run" "$@"
