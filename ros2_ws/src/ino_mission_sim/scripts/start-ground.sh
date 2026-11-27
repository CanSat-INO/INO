#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
# Do not inherit the Test Lab venv in ROS children.
if [ -n "${VIRTUAL_ENV:-}" ]; then
 export PATH="$(/usr/bin/python3 -c 'import os; print(":".join(p for p in os.environ["PATH"].split(":") if p != os.environ["VIRTUAL_ENV"]+"/bin"))')"
 unset VIRTUAL_ENV
fi
unset PYTHONHOME
ino_script_dir=scripts
ino_ros_environment="$ino_script_dir/ros-environment.sh"
if [[ ! -f "$ino_ros_environment" ]]; then
    ino_ros_environment="$ino_script_dir/../../../../scripts/ros-environment.sh"
fi
source "$ino_ros_environment" || exit 2
exec /usr/bin/python3 tools/run_ground.py "$@"
