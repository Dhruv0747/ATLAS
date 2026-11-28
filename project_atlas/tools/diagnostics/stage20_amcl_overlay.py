"""Version-pinned, opt-in AMCL event overlay; generated source is separate.

Does not replace likelihood/RNG/update expressions. Public output remains
unchanged. Events observe both PF sets before/after resampling; RNG opaque.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

def once(text, old, new):
    if text.count(old)!=1: raise ValueError('unsupported AMCL anchor: '+old[:70])
    return text.replace(old,new,1)

DEFINITION = r'''
void AmclNode::atlasCheckpointEvent(const char * phase, int64_t source_ns) noexcept
{
  if (!atlas_checkpoint_pub_) return;
  try {
    std::ostringstream s; s << std::setprecision(17);
    s << "{\"schema\":2,\"session\":" << atlas_checkpoint_session_
      << ",\"seq\":" << ++atlas_checkpoint_seq_ << ",\"phase\":\"" << phase
      << "\",\"source_ns\":" << source_ns << ",\"ros_ns\":" << now().nanoseconds()
      << ",\"monotonic_ns\":" << std::chrono::steady_clock::now().time_since_epoch().count()
      << ",\"rng_restored\":false,\"complete_checkpoint\":false,\"diagnostic_failures\":" << atlas_checkpoint_failures_;
    const std::string event_phase(phase);
    const bool details=event_phase=="particles_initialized" || event_phase=="global_particles_initialized" ||
      event_phase=="weights_before_resample_decision" || event_phase=="resample_after";
    auto number = [&s](double v) { if (std::isfinite(v)) s << v; else s << "null"; };
    if (pf_) {
      s << ",\"current_set\":" << pf_->current_set << ",\"resample_count\":" << resample_count_
        << ",\"converged\":" << pf_->converged << ",\"w_slow\":"; number(pf_->w_slow);
      s << ",\"w_fast\":"; number(pf_->w_fast); s << ",\"sets\":[";
      for (int j=0;j<2;++j) {
        if(j) { s << ','; }
        const auto & set=pf_->sets[j];
        s << "{\"sample_count\":" << set.sample_count << ",\"particle_detail\":" << (details?"true":"false") << ",\"truncated\":"
          << (set.sample_count>2000 ? "true":"false") << ",\"particles\":[";
        for(int i=0;i<(details?std::min(set.sample_count,2000):0);++i) {
          if(i) { s << ','; }
          s << '[';
          for(int k=0;k<3;++k) { if(k) s << ','; number(set.samples[i].pose.v[k]); }
          s << ','; number(set.samples[i].weight); s << ']';
        }
        s << "],\"clusters\":[";
        for(int i=0;i<std::min(set.cluster_count,2000);++i) {
          if(i) { s << ','; }
          const auto & c=set.clusters[i];
          s << "{\"count\":" << c.count << ",\"weight\":"; number(c.weight);
          s << ",\"mean\":[";
          for(int k=0;k<3;++k) { if(k) s << ','; number(c.mean.v[k]); }
          s << "]}";
        }
        s << "],\"covariance\":[";
        for(int a=0;a<3;++a) for(int b=0;b<3;++b) { if(a||b) s << ','; number(set.cov.m[a][b]); }
        s << "]}";
      } s << ']';
    }
    s << '}'; std_msgs::msg::String message; message.data=s.str();
    if(atlas_checkpoint_pending_bytes_+message.data.size()>8*1024*1024) {
      ++atlas_checkpoint_failures_;return;
    }
    atlas_checkpoint_pending_bytes_+=message.data.size();atlas_checkpoint_pending_.push_back(std::move(message));
    if(atlas_checkpoint_pub_->get_subscription_count()>0) {
      unsigned sent=0;
      while(!atlas_checkpoint_pending_.empty() && sent++<4) {
        atlas_checkpoint_pub_->publish(atlas_checkpoint_pending_.front());
        atlas_checkpoint_pending_bytes_-=atlas_checkpoint_pending_.front().data.size();
        atlas_checkpoint_pending_.pop_front();
      }
    }
  } catch (...) { ++atlas_checkpoint_failures_; }
}
'''

def instrument(src):
    cpp=src['src/amcl_node.cpp'];h=src['include/nav2_amcl/amcl_node.hpp']
    cpp=once(cpp,'#include <algorithm>','#include <algorithm>\n#include <sstream>\n#include <iomanip>\n#include <cstdlib>\n#include <chrono>\n#include <cmath>')
    h=once(h,'    pose_pub_;','''    pose_pub_;
  rclcpp_lifecycle::LifecyclePublisher<std_msgs::msg::String>::SharedPtr atlas_checkpoint_pub_;
  uint64_t atlas_checkpoint_seq_=0, atlas_checkpoint_failures_=0;
  std::deque<std_msgs::msg::String> atlas_checkpoint_pending_;
  size_t atlas_checkpoint_pending_bytes_=0;
  const int64_t atlas_checkpoint_session_=std::chrono::steady_clock::now().time_since_epoch().count();
  void atlasCheckpointEvent(const char * phase, int64_t source_ns=0) noexcept;
''')
    at=h.index('#include');h=h[:at]+'#include <chrono>\n#include <deque>\n#include "std_msgs/msg/string.hpp"\n'+h[at:]
    cpp=once(cpp,'  initTransforms();\n  initParticleFilter();','''  initTransforms();
  if (const auto * opt=std::getenv("ATLAS_CHECKPOINT_EVENTS")) {
    if (std::string(opt)=="1") {
      atlas_checkpoint_pub_=create_publisher<std_msgs::msg::String>(
        "/atlas/diagnostics/amcl_event",rclcpp::QoS(16).best_effort().transient_local());
      atlas_checkpoint_pub_->on_activate();
    }
  }
  initParticleFilter();''')
    cpp=once(cpp,'  pose_pub_.reset();','  pose_pub_.reset();\n  atlas_checkpoint_pub_.reset();')
    init='  pf_init(pf_, pf_init_pose_mean, pf_init_pose_cov);'
    if cpp.count(init)!=2:raise ValueError('expected two Gaussian initialization sites')
    cpp=cpp.replace(init,init+'\n  atlasCheckpointEvent("particles_initialized");')
    for old,new in (
        ('  RCLCPP_INFO(get_logger(), "initialPoseReceived");','  RCLCPP_INFO(get_logger(), "initialPoseReceived");\n  atlasCheckpointEvent("initial_pose_received",rclcpp::Time(msg->header.stamp).nanoseconds());'),
        ('  RCLCPP_INFO(get_logger(), "Requesting no-motion update");\n  force_update_ = true;',
         '  RCLCPP_INFO(get_logger(), "Requesting no-motion update");\n  atlasCheckpointEvent("nomotion_request_consumed");\n  force_update_ = true;'),
        ('  pf_vector_t delta = pf_vector_zero();','  atlasCheckpointEvent("scan_tf_accepted",rclcpp::Time(laser_scan->header.stamp).nanoseconds());\n  pf_vector_t delta = pf_vector_zero();'),
        ('      motion_model_->odometryUpdate(pf_, pose, delta);','      atlasCheckpointEvent("motion_update_before",rclcpp::Time(laser_scan->header.stamp).nanoseconds());\n      motion_model_->odometryUpdate(pf_, pose, delta);\n      atlasCheckpointEvent("motion_update_after",rclcpp::Time(laser_scan->header.stamp).nanoseconds());'),
        ('    updateFilter(laser_index, laser_scan, pose);','    updateFilter(laser_index, laser_scan, pose);\n    atlasCheckpointEvent("weights_before_resample_decision",rclcpp::Time(laser_scan->header.stamp).nanoseconds());'),
        ('      pf_update_resample(pf_, reinterpret_cast<void *>(map_));','      atlasCheckpointEvent("resample_before",rclcpp::Time(laser_scan->header.stamp).nanoseconds());\n      pf_update_resample(pf_, reinterpret_cast<void *>(map_));\n      atlasCheckpointEvent("resample_after",rclcpp::Time(laser_scan->header.stamp).nanoseconds());'),
        ('  initial_pose_is_known_ = true;\n  pf_init_ = false;','  initial_pose_is_known_ = true;\n  atlasCheckpointEvent("global_particles_initialized");\n  pf_init_ = false;'),
    ): cpp=once(cpp,old,new)
    cpp += '\nnamespace nav2_amcl {\n'+DEFINITION+'\n}\n'
    cmake=once(src['CMakeLists.txt'],'find_package(std_srvs REQUIRED)','find_package(std_srvs REQUIRED)\nfind_package(std_msgs REQUIRED)')
    cmake=once(cmake,'  std_srvs\n','  std_srvs\n  std_msgs\n')
    package=once(src['package.xml'],'<depend>std_srvs</depend>','<depend>std_srvs</depend>\n  <depend>std_msgs</depend>')
    return {'src/amcl_node.cpp':cpp,'include/nav2_amcl/amcl_node.hpp':h,'CMakeLists.txt':cmake,'package.xml':package}

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
    src,dst=a.source.resolve(),a.destination.resolve()
    if dst.exists() or src==dst or src in dst.parents or dst in src.parents:p.error('new separate destination required')
    if ET.parse(src/'package.xml').getroot().findtext('version')!='1.1.20':p.error('AMCL 1.1.20 required')
    names=('src/amcl_node.cpp','include/nav2_amcl/amcl_node.hpp','CMakeLists.txt','package.xml')
    original={k:(src/k).read_text() for k in names};changed=instrument(original)
    shutil.copytree(src,dst)
    for name,text in changed.items():(dst/name).write_text(text)
    (dst/'atlas_overlay_identity.json').write_text(json.dumps({
        'default':'OFF','complete_checkpoint':False,'rng_state':'opaque',
        'before':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in original.items()},
        'after':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in changed.items()}},indent=2))

if __name__=='__main__':main()
