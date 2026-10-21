"""Exact-anchor, offline-only instrumentation of pinned vendor source. Never deploys."""
import pathlib,subprocess,sys
PIN='f7e71d9ce806e788cb48d8580aac2c778fba4214'
def instrument(root):
    root=pathlib.Path(root)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==PIN
    h=root/'astra_camera/include/astra_camera/ob_camera_node.h'
    c=root/'astra_camera/src/ob_camera_node.cpp'
    hs=h.read_text();cs=c.read_text()
    assert 'atlas_ir::Counters' not in hs, 'Already instrumented; do not reapply'
    def replace(s,a,b):
        assert s.count(a)==1, 'Source anchor mismatch: '+a[:100]
        return s.replace(a,b)
    hs=replace(hs,'  rclcpp::Node* node_ = nullptr;',
       '  atlas_ir::Counters ir_diag_;\n  void reportIR(bool final=false);\n  rclcpp::Node* node_ = nullptr;')
    hs='#include "astra_camera/ir_counters.hpp"\n'+hs
    cs=replace(cs,'  stopStreams();','  reportIR(true);\n  stopStreams();')
    cs=replace(cs,'void OBCameraNode::pollFrame() {','''void OBCameraNode::reportIR(bool final) {
  if (!enable_stream_[INFRA1] || !ir_diag_.due(std::chrono::steady_clock::now(), final)) return;
  auto p=image_publishers_.find(INFRA1);
  size_t subscribers=p==image_publishers_.end()?0:p->second->get_subscription_count();
  RCLCPP_INFO_STREAM(logger_, ir_diag_.summary(final, subscribers));
}

void OBCameraNode::pollFrame() {''')
    cs=replace(cs,'    if (!has_stream_started) {','    reportIR();\n    if (!has_stream_started) {')
    cs=replace(cs,'    if (status != openni::STATUS_OK) {\n      continue;','''    if (enable_stream_[INFRA1]) {
      ir_diag_.wait_rc=status;
      ir_diag_.hit(status==openni::STATUS_OK?atlas_ir::Counters::wait_ok:atlas_ir::Counters::wait_failed);
      reportIR();
    }
    if (status != openni::STATUS_OK) {
      continue;''')
    cs=replace(cs,'    status = streams[ready_stream]->readFrame(&frame);','''    if(stream_index==INFRA1) ir_diag_.hit(atlas_ir::Counters::ready);
    status = streams[ready_stream]->readFrame(&frame);
    if(stream_index==INFRA1) {
      ir_diag_.read_rc=status;
      ir_diag_.hit(status==openni::STATUS_OK?atlas_ir::Counters::read_ok:atlas_ir::Counters::read_failed);
    }''')
    cs=replace(cs,'    onNewFrameCallback(frame, stream_index);','''    try { onNewFrameCallback(frame, stream_index); }
    catch (...) {
      if(stream_index==INFRA1) { ir_diag_.hit(atlas_ir::Counters::exceptions); reportIR(true); }
      throw; // preserve vendor failure behavior, never silently swallow conversion/publish failure
    }''')
    cs=replace(cs,'      auto status = stream->create(*device_, stream_index.first);','''      auto status = stream->create(*device_, stream_index.first);
      if(stream_index==INFRA1) { ir_diag_.create_rc=status;
        if(status==openni::STATUS_OK) ir_diag_.hit(atlas_ir::Counters::created); }''')
    cs=replace(cs,'      streams_[stream_index]->setVideoMode(video_mode);','''      auto mode_status=streams_[stream_index]->setVideoMode(video_mode);
      if(stream_index==INFRA1) ir_diag_.mode_rc=mode_status;''')
    cs=replace(cs,'      auto status = streams_[stream_index]->start();','''      auto status = streams_[stream_index]->start();
      if(stream_index==INFRA1) { ir_diag_.start_rc=status;
        if(status==openni::STATUS_OK) ir_diag_.hit(atlas_ir::Counters::started);
        const auto actual=streams_[stream_index]->getVideoMode();
        RCLCPP_INFO_STREAM(logger_, "ATLAS_IR_START create_rc="<<ir_diag_.create_rc
          <<" mode_rc="<<ir_diag_.mode_rc<<" start_rc="<<status<<" requested="<<video_mode
          <<" negotiated="<<actual<<" domain="<<node_->get_node_options().context()->get_domain_id());
      }''')
    cs=replace(cs,'      topic = name + "/camera_info";','''      if(stream_index==INFRA1) {
        ir_diag_.hit(atlas_ir::Counters::publisher);
        RCLCPP_INFO_STREAM(logger_, "ATLAS_IR_PUBLISHER topic="<<image_publishers_[stream_index]->get_topic_name()
          <<" type=sensor_msgs/msg/Image qos="<<image_qos);
      }
      topic = name + "/camera_info";''')
    cs=replace(cs,'  int width = frame.getWidth();','''  if(stream_index==INFRA1) {
    ir_diag_.hit(atlas_ir::Counters::callback);
    ir_diag_.width=frame.getWidth(); ir_diag_.height=frame.getHeight();
    ir_diag_.format=frame.getVideoMode().getPixelFormat(); ir_diag_.fps=frame.getVideoMode().getFps();
    ir_diag_.stride=frame.getStrideInBytes(); ir_diag_.bytes=frame.getDataSize();
    ir_diag_.index=frame.getFrameIndex(); ir_diag_.timestamp_us=frame.getTimestamp();
  }
  int width = frame.getWidth();''')
    cs=replace(cs,'  CHECK_NOTNULL(image_msg);','  CHECK_NOTNULL(image_msg);\n  if(stream_index==INFRA1) ir_diag_.hit(atlas_ir::Counters::converted);')
    cs=replace(cs,'  image_publisher->publish(*image_msg);','''  if(stream_index==INFRA1) ir_diag_.hit(atlas_ir::Counters::publish_attempt);
  image_publisher->publish(*image_msg);
  if(stream_index==INFRA1) ir_diag_.hit(atlas_ir::Counters::publish_returned);''')
    cs=replace(cs,'  camera_info_publisher->publish(camera_info);','''  camera_info_publisher->publish(camera_info);
  if(stream_index==INFRA1) ir_diag_.hit(atlas_ir::Counters::info_returned);''')
    h.write_text(hs);c.write_text(cs)
    (h.parent/'ir_counters.hpp').write_text(pathlib.Path(__file__).with_name('ir_counters.hpp').read_text())
if __name__=='__main__':instrument(sys.argv[1])
