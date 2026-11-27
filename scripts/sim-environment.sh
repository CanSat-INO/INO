#!/usr/bin/env bash
# Source in each external terminal. A simulation or replay launcher owns the router.
ino_sim_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ino_sim_dir/ros-environment.sh" || return
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-67}
if [[ ! "$ROS_DOMAIN_ID" =~ ^(0|[1-9][0-9]{0,2})$ ]] || (( ROS_DOMAIN_ID > 232 )); then
    echo '[ERROR] ROS_DOMAIN_ID は 0〜232 の整数を指定してください。' >&2
    return 2
fi
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
if [[ "$ROS_DISTRO" == lyrical ]]; then
    export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}
fi

ino_zenoh_managed=0
if [[ "${RMW_IMPLEMENTATION:-}" == rmw_zenoh_cpp &&
      "${ZENOH_SESSION_CONFIG_URI:-}" == "${INO_MANAGED_ZENOH_SESSION:-}" ]]; then
    ino_zenoh_port=$((17000 + ROS_DOMAIN_ID))
    ino_zenoh_dir="${XDG_RUNTIME_DIR:-$HOME/.cache}/ino-sim/domain-$ROS_DOMAIN_ID"
    ino_zenoh_prefix="$(ros2 pkg prefix rmw_zenoh_cpp)" || return
    ino_zenoh_defaults="$ino_zenoh_prefix/share/rmw_zenoh_cpp/config"
    mkdir -p -m 700 "$ino_zenoh_dir" || return
    (
        flock -x 8
        sed "s@tcp/localhost:7447@tcp/127.0.0.1:$ino_zenoh_port@g" \
            "$ino_zenoh_defaults/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5" > "$ino_zenoh_dir/session.json5"
        sed "s@tcp/\[::\]:7447@tcp/127.0.0.1:$ino_zenoh_port@g" \
            "$ino_zenoh_defaults/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5" > "$ino_zenoh_dir/router.json5"
        grep -Fq "tcp/127.0.0.1:$ino_zenoh_port" "$ino_zenoh_dir/session.json5" &&
        grep -Fq "tcp/127.0.0.1:$ino_zenoh_port" "$ino_zenoh_dir/router.json5"
    ) 8>"$ino_zenoh_dir/config.lock" || {
        echo '[ERROR] Zenoh設定を生成できません。rmw_zenoh_cpp の配布設定を確認してください。' >&2
        return 2
    }
    export ZENOH_SESSION_CONFIG_URI="$ino_zenoh_dir/session.json5"
    export INO_MANAGED_ZENOH_SESSION="$ZENOH_SESSION_CONFIG_URI"
    ino_zenoh_managed=1
fi

ino_zenoh_ready() {
    /usr/bin/python3 -c '
import socket, sys
try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=0.2):
        pass
except OSError:
    sys.exit(1)
' "$ino_zenoh_port"
}

ino_sim_wait() {
    [[ "${ino_zenoh_managed:-}" == 1 ]] || return 0
    for _ in {1..150}; do
        ino_zenoh_ready && return 0
        sleep 0.1
    done
    echo "[ERROR] Zenohに接続できません。ドメイン $ROS_DOMAIN_ID の仮想試験または再生を先に起動してください。" >&2
    return 2
}

ino_sim_run() {
    if [[ "${ino_zenoh_managed:-}" != 1 ]]; then
        exec "$@"
    fi
    exec /usr/bin/python3 "$ino_sim_dir/sim-supervisor.py" \
        "$ino_zenoh_dir" "$ino_zenoh_port" "$ino_zenoh_prefix/lib/rmw_zenoh_cpp/rmw_zenohd" "$@"
}
