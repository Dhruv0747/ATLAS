"""Generate opt-in robot_localization 3.5.4 consumer events in a new copy.

Original processMeasurement/reset/reference expressions remain unchanged.
This is additional internal evidence, not a serializable restart checkpoint.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from stage20_amcl_overlay import once

BODY=r'''
template<typename T>
void RosFilter<T>::atlasCheckpointEvent(const char * phase, const std::string & source,
  int64_t source_ns) noexcept
{
  if (!atlas_checkpoint_pub_) return;
  try {
    std::ostringstream s; s << std::setprecision(17);
    s << "{\"schema\":2,\"phase\":\"" << phase << "\",\"source\":\"" << source
      << "\",\"seq\":" << ++atlas_checkpoint_seq_ << ",\"session\":" << atlas_checkpoint_session_
      << ",\"source_ns\":" << source_ns << ",\"ros_ns\":" << now().nanoseconds()
      << ",\"monotonic_ns\":" << std::chrono::steady_clock::now().time_since_epoch().count()
      << ",\"initialized\":" << (filter_.getInitializedStatus()?"true":"false")
      << ",\"complete_checkpoint\":false,\"state\":[";
    auto number=[&s](double v){if(std::isfinite(v))s<<v;else s<<"null";};
    const auto & x=filter_.getState();
    for(int i=0;i<x.size();++i){if(i){s<<',';}number(x(i));}
    s << "],\"covariance\":[";const auto & p=filter_.getEstimateErrorCovariance();
    for(int i=0;i<p.rows();++i)for(int j=0;j<p.cols();++j){if(i||j){s<<',';}number(p(i,j));}
    s << "],\"relative_references\":[";bool first=true;
    for(const auto & item:initial_measurements_){
      if(!first){s<<',';}first=false;const auto & t=item.second;
      s << "{\"source\":\"" << item.first << "\",\"xyz\":[";
      number(t.getOrigin().x());s<<',';number(t.getOrigin().y());s<<',';number(t.getOrigin().z());
      s << "],\"quaternion\":[";number(t.getRotation().x());s<<',';number(t.getRotation().y());
      s<<',';number(t.getRotation().z());s<<',';number(t.getRotation().w());s<<"]}";
    }
    s << "]}";std_msgs::msg::String m;m.data=s.str();
    if(std::string(phase)=="constructed_uninitialized")atlas_checkpoint_bootstrap_=m.data;
    if(atlas_checkpoint_pending_bytes_+m.data.size()>8*1024*1024) {
      ++atlas_checkpoint_failures_;return;
    }
    atlas_checkpoint_pending_bytes_+=m.data.size();atlas_checkpoint_pending_.push_back(std::move(m));
    // Preserve the construction event through DDS discovery without waiting for a subscriber.
    if(atlas_checkpoint_pub_->get_subscription_count()>0) {
      while(!atlas_checkpoint_pending_.empty()) {
        atlas_checkpoint_pub_->publish(atlas_checkpoint_pending_.front());
        atlas_checkpoint_pending_bytes_-=atlas_checkpoint_pending_.front().data.size();
        atlas_checkpoint_pending_.pop_front();
      }
    }
  }catch(...){++atlas_checkpoint_failures_;}
}
'''

def instrument(cpp,h):
    cpp=once(cpp,'#include <algorithm>','#include <algorithm>\n#include <chrono>\n#include <cstdlib>\n#include <iomanip>\n#include <sstream>')
    h=once(h,'protected:','''protected:
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr atlas_checkpoint_pub_;
  uint64_t atlas_checkpoint_seq_=0, atlas_checkpoint_failures_=0;
  std::deque<std_msgs::msg::String> atlas_checkpoint_pending_;
  size_t atlas_checkpoint_pending_bytes_=0;
  std::string atlas_checkpoint_bootstrap_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr atlas_checkpoint_bootstrap_service_;
  const int64_t atlas_checkpoint_session_=std::chrono::steady_clock::now().time_since_epoch().count();
  void atlasCheckpointEvent(const char * phase, const std::string & source="", int64_t source_ns=0) noexcept;
''')
    at=h.index('#include');h=h[:at]+'#include <chrono>\n#include <std_srvs/srv/trigger.hpp>\n'+h[at:]
    cpp=once(cpp,'  tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());','''  if(const auto * enabled=std::getenv("ATLAS_CHECKPOINT_EVENTS")) {
    if(std::string(enabled)=="1") {
      atlas_checkpoint_pub_=create_publisher<std_msgs::msg::String>(
        "/atlas/diagnostics/ekf_event",rclcpp::QoS(32).best_effort().transient_local());
      atlasCheckpointEvent("constructed_uninitialized");
      atlas_checkpoint_bootstrap_service_=create_service<std_srvs::srv::Trigger>(
        "~/checkpoint_bootstrap",[this](const std_srvs::srv::Trigger::Request::SharedPtr,
          std_srvs::srv::Trigger::Response::SharedPtr response){
            response->success=!atlas_checkpoint_bootstrap_.empty();
            response->message=atlas_checkpoint_bootstrap_;
          });
    }
  }
  tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());''')
    cpp=once(cpp,'void RosFilter<T>::reset()\n{','void RosFilter<T>::reset()\n{\n  atlasCheckpointEvent("reset_begin");')
    cpp=once(cpp,'  filter_.reset();','  filter_.reset();\n  atlasCheckpointEvent("reset_end");')
    call='      filter_.processMeasurement(*(measurement.get()));'
    cpp=once(cpp,call,'      atlasCheckpointEvent("measurement_before",measurement->topic_name_,measurement->time_.nanoseconds());\n'+call+'\n      atlasCheckpointEvent("measurement_after",measurement->topic_name_,measurement->time_.nanoseconds());')
    anchor='            std::pair<std::string, tf2::Transform>(topic_name, pose_tmp));'
    cpp=once(cpp,anchor,anchor+'\n          atlasCheckpointEvent("relative_reference_created",topic_name,rclcpp::Time(msg->header.stamp).nanoseconds());')
    cpp=once(cpp,'}  // namespace robot_localization',BODY+'\n}  // namespace robot_localization')
    return cpp,h

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    src,dst=a.source.resolve(),a.destination.resolve()
    if dst.exists() or src==dst or src in dst.parents or dst in src.parents:p.error('new separate destination')
    if ET.parse(src/'package.xml').getroot().findtext('version')!='3.5.4':p.error('robot_localization 3.5.4 required')
    names=('src/ros_filter.cpp','include/robot_localization/ros_filter.hpp')
    originals=[(src/k).read_text() for k in names];changed=instrument(*originals)
    shutil.copytree(src,dst)
    for k,text in zip(names,changed):(dst/k).write_text(text)
    (dst/'atlas_overlay_identity.json').write_text(json.dumps({'default':'OFF','complete_checkpoint':False,
        'before':{k:hashlib.sha256(t.encode()).hexdigest() for k,t in zip(names,originals)},
        'after':{k:hashlib.sha256(t.encode()).hexdigest() for k,t in zip(names,changed)}},indent=2))

if __name__=='__main__':main()
