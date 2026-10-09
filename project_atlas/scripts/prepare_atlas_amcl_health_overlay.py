#!/usr/bin/env python3
"""Generate a separate AMCL 1.1.20 diagnostic overlay; never modify input.

The generated signal is scan-processing evidence, NOT a localization verdict.
Do not install this overlay into the production workspace without validation.
"""
import argparse
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('unsupported source anchor: ' + old[:90])
    return text.replace(old, new, 1)


def instrument(source):
    cpp = source['src/amcl_node.cpp']
    header = source['include/nav2_amcl/amcl_node.hpp']
    cpp = once(cpp, '#include <algorithm>', '#include <algorithm>\n#include <sstream>\n#include <chrono>\n#include <cmath>')
    header = once(header, '    pose_pub_;', '''    pose_pub_;
  rclcpp_lifecycle::LifecyclePublisher<std_msgs::msg::String>::SharedPtr processing_pub_;
  uint64_t processing_seq_ = 0, pose_publish_seq_ = 0;
  const int64_t processing_session_ = std::chrono::steady_clock::now().time_since_epoch().count();
  void publishProcessing(const sensor_msgs::msg::LaserScan & scan,
    bool attempted, bool succeeded);
''')
    # Place includes before the original first include, outside its guard is safe.
    first = header.index('#include')
    header = header[:first] + '#include <chrono>\n#include "std_msgs/msg/string.hpp"\n' + header[first:]
    for anchor, replacement in (
        ('  pose_pub_->on_activate();', '  pose_pub_->on_activate();\n  processing_pub_->on_activate();'),
        ('  pose_pub_->on_deactivate();', '  pose_pub_->on_deactivate();\n  processing_pub_->on_deactivate();'),
        ('  pose_pub_.reset();', '  pose_pub_.reset();\n  processing_pub_.reset();'),
        ('  bool resampled = false;', '  bool resampled = false;\n  bool health_attempted = false, health_succeeded = false;'),
        ('    updateFilter(laser_index, laser_scan, pose);',
         '    health_attempted = true;\n    health_succeeded = updateFilter(laser_index, laser_scan, pose);'),
        ('    pose_pub_->publish(std::move(p));',
         '    pose_pub_->publish(std::move(p));\n    ++pose_publish_seq_;'),
        ('  pose_pub_ = create_publisher<geometry_msgs::msg::PoseWithCovarianceStamped>(',
         '  processing_pub_ = create_publisher<std_msgs::msg::String>(\n'
         '    "atlas_amcl/processing", rclcpp::QoS(1));\n'
         '  pose_pub_ = create_publisher<geometry_msgs::msg::PoseWithCovarianceStamped>('),
        ('\n}\n\nbool AmclNode::addNewScanner(',
         '\n  publishProcessing(*laser_scan, health_attempted, health_succeeded);\n}\n\nbool AmclNode::addNewScanner('),
    ):
        cpp = once(cpp, anchor, replacement)
    # Preserve sensor algorithm; propagate its success only to diagnostics.
    cpp = once(cpp,
        '  lasers_[laser_index]->sensorUpdate(pf_, reinterpret_cast<nav2_amcl::LaserData *>(&ldata));',
        '  const bool sensor_ok = lasers_[laser_index]->sensorUpdate(pf_, reinterpret_cast<nav2_amcl::LaserData *>(&ldata));')
    cpp = once(cpp, '  pf_odom_pose_ = pose;\n  return true;', '  pf_odom_pose_ = pose;\n  return sensor_ok;')
    definition = r'''
void AmclNode::publishProcessing(const sensor_msgs::msg::LaserScan & scan,
  bool attempted, bool succeeded)
{
  // Reached ONLY after active/map checks and scan-time odometry lookup.
  // Not a timer. No pose is republished and no filter update is requested.
  size_t valid = 0;
  for (const auto r : scan.ranges) {
    if (std::isfinite(r) && r > scan.range_min && r < scan.range_max) ++valid;
  }
  std::ostringstream s;
  s << std::boolalpha
    << "{\"schema\":1,\"session\":\"" << processing_session_
    << "\",\"seq\":" << ++processing_seq_
    << ",\"scan_stamp_ns\":" << rclcpp::Time(scan.header.stamp).nanoseconds()
    << ",\"processed_stamp_ns\":" << now().nanoseconds()
    << ",\"pose_seq\":" << pose_publish_seq_
    << ",\"last_pose_stamp_ns\":" << rclcpp::Time(last_published_pose_.header.stamp).nanoseconds()
    << ",\"filter_update_attempted\":" << attempted
    << ",\"filter_update_succeeded\":" << succeeded
    << ",\"initial_pose_known\":" << initial_pose_is_known_
    << ",\"tf_available\":" << latest_tf_valid_
    << ",\"valid_returns\":" << valid
    << ",\"scan_size\":" << scan.ranges.size() << "}";
  std_msgs::msg::String message;
  message.data = s.str();
  processing_pub_->publish(message);
}

'''
    cpp = once(cpp, 'bool AmclNode::addNewScanner(', definition + 'bool AmclNode::addNewScanner(')
    cmake = once(source['CMakeLists.txt'], 'find_package(std_srvs REQUIRED)',
                 'find_package(std_srvs REQUIRED)\nfind_package(std_msgs REQUIRED)')
    cmake = once(cmake, '  std_srvs\n', '  std_srvs\n  std_msgs\n')
    package = once(source['package.xml'], '<depend>std_srvs</depend>',
                   '<depend>std_srvs</depend>\n  <depend>std_msgs</depend>')
    return {'src/amcl_node.cpp': cpp, 'include/nav2_amcl/amcl_node.hpp': header,
            'CMakeLists.txt': cmake, 'package.xml': package}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    src, dst = args.source.resolve(), args.destination.resolve()
    if dst.exists() or src == dst or src in dst.parents or dst in src.parents:
        parser.error('destination must be new and separate from source')
    version = ET.parse(src/'package.xml').getroot().findtext('version')
    if version != '1.1.20':
        parser.error('only inspected AMCL 1.1.20 is supported')
    names = ('src/amcl_node.cpp','include/nav2_amcl/amcl_node.hpp','CMakeLists.txt','package.xml')
    output = instrument({name:(src/name).read_text() for name in names})
    shutil.copytree(src,dst)
    for name, text in output.items():
        (dst/name).write_text(text)
    print('Generated isolated processing-evidence overlay:', dst)


if __name__ == '__main__':
    main()
