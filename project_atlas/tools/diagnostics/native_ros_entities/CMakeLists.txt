cmake_minimum_required(VERSION 3.16)
project(atlas_offline_entities)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(bondcpp REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/onepass_strategy.hpp
  COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/prepare_strategy.py
  /opt/ros/humble/include/rclcpp/rclcpp/strategies/allocator_memory_strategy.hpp
  ${CMAKE_CURRENT_BINARY_DIR}/onepass_strategy.hpp
  DEPENDS prepare_strategy.py onepass_lookup.hpp)
add_executable(check_entities main.cpp)
target_sources(check_entities PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/onepass_strategy.hpp)
target_include_directories(check_entities PRIVATE ${CMAKE_CURRENT_BINARY_DIR} ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(check_entities PRIVATE cxx_std_17)
target_compile_options(check_entities PRIVATE -Wall -Wextra -Werror -O2)
ament_target_dependencies(check_entities rclcpp std_msgs bondcpp)
