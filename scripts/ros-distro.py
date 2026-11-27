"""Print the ROS distribution selected for this Ubuntu release."""
from install_ros2 import os_release, validate_os

if __name__ == "__main__":
    try:
        print(validate_os(os_release()))
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error))
