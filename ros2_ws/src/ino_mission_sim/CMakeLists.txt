cmake_minimum_required(VERSION 3.8)
project(ino_mission_sim)
find_package(ament_cmake REQUIRED)
install(DIRECTORY tools launch config scripts firmware DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE PATTERN "build" EXCLUDE PATTERN "*.pyc" EXCLUDE)
install(FILES README.md DESTINATION share/${PROJECT_NAME})
install(FILES
  ../../../scripts/ros-environment.sh
  ../../../scripts/ros-distro.py
  ../../../scripts/install_ros2.py
  DESTINATION share/${PROJECT_NAME}/scripts)
ament_package()
