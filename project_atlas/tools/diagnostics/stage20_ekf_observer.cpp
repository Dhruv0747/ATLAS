// Isolated diagnostic replacement executable, never installed automatically.
// Uses the upstream filter unchanged. Single-thread executor avoids state races.
#include <iomanip>
#include <sstream>
#include <filesystem>
#include <cstdlib>
#include <iostream>
#include <robot_localization/ros_filter.hpp>
#include <robot_localization/ekf.hpp>
#include <std_msgs/msg/string.hpp>

class Observer : public robot_localization::RosFilter<robot_localization::Ekf> {
 public:
  Observer() : robot_localization::RosFilter<robot_localization::Ekf>(
      rclcpp::NodeOptions().arguments({"atlas_ekf"})) {
    pub_ = create_publisher<std_msgs::msg::String>("/atlas/diagnostics/ekf_state", 10);
  }
  void start() {
    initialize();
    timer_ = create_wall_timer(std::chrono::milliseconds(100), [this]() {
      try { snapshot(); } catch (...) { /* diagnostics must not alter filter processing */ }
    });
  }
 private:
  void snapshot() {
    auto & f = getFilter();
    std::ostringstream s;
    s << std::setprecision(17) << "{\"schema\":1,\"stamp_ns\":" << now().nanoseconds()
      << ",\"initialized\":" << (f.getInitializedStatus() ? "true" : "false")
      << ",\"last_measurement_ns\":" << f.getLastMeasurementTime().nanoseconds()
      << ",\"state\":[";
    const auto & x = f.getState();
    for (int i=0; i<x.size(); ++i) { if(i) s << ','; s << x(i); }
    s << "],\"covariance\":[";
    const auto & p = f.getEstimateErrorCovariance();
    for (int i=0; i<p.rows(); ++i) for (int j=0; j<p.cols(); ++j) {
      if(i || j) s << ','; s << p(i,j);
    }
    s << "],\"relative_references\":[";
    bool first=true;
    for (const auto & item : initial_measurements_) {
      // Topic names are JSON-safe ROS graph names; transform is actual internal reference.
      if(!first) s << ','; first=false;
      const auto & t=item.second;
      s << "{\"source\":\"" << item.first << "\",\"xyz\":["
        << t.getOrigin().x() << ',' << t.getOrigin().y() << ',' << t.getOrigin().z()
        << "],\"quaternion\":[" << t.getRotation().x() << ',' << t.getRotation().y()
        << ',' << t.getRotation().z() << ',' << t.getRotation().w() << "]}";
    }
    s << "],\"complete_restorable_checkpoint\":false}";
    std_msgs::msg::String m; m.data=s.str(); pub_->publish(m);
  }
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};
int main(int argc, char ** argv) {
  auto equal = [](const char * key, const char * value) {
    const auto * found=std::getenv(key); return found && std::string(found)==value;
  };
  if (!equal("ATLAS_STAGE19_SANDBOX","1") || !equal("ROS_DOMAIN_ID","187") ||
      !equal("ROS_LOCALHOST_ONLY","1")) {
    std::cerr << "Refuse observer outside private diagnostic sandbox\n"; return 2;
  }
  for (const auto * ns : {"net", "pid"}) {
    const auto * host=std::getenv(std::string("ATLAS_HOST_" +
      std::string(ns==std::string("net") ? "NET" : "PID") + "_NS").c_str());
    if (!host || std::filesystem::read_symlink(std::string("/proc/self/ns/")+ns).string()==host)
      return 2;
  }
  for (const auto & entry : std::filesystem::directory_iterator("/dev")) {
    auto name=entry.path().filename().string();
    if (name=="serial" || name.rfind("ttyUSB",0)==0 || name.rfind("ttyACM",0)==0) return 2;
  }
  rclcpp::init(argc, argv);
  auto node=std::make_shared<Observer>(); node->start();
  rclcpp::spin(node); rclcpp::shutdown();
}
