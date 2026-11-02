cmake_minimum_required(VERSION 3.8)
project(ino_camera_sim)
find_package(ament_cmake REQUIRED)
install(DIRECTORY launch config tools scripts assets DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE PATTERN "*.pyc" EXCLUDE)
install(FILES README.md DESTINATION share/${PROJECT_NAME})
ament_package()
