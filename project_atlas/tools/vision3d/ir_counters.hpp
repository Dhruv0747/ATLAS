#pragma once
// Scalar-only diagnostics. No ROS/OpenNI dependencies, image buffers or threads.
#include <atomic>
#include <chrono>
#include <cstdint>
#include <limits>
#include <sstream>
namespace atlas_ir {
struct Counters {
  enum Event { created, started, publisher, wait_ok, wait_failed, ready,
               read_ok, read_failed, callback, converted, publish_attempt,
               publish_returned, info_returned, exceptions, count };
  std::atomic<uint64_t> values[count]{};
  std::atomic<int> create_rc{-999}, mode_rc{-999}, start_rc{-999}, wait_rc{-999}, read_rc{-999};
  std::atomic<int> width{0}, height{0}, format{0}, fps{0}, stride{0}, bytes{0}, index{0};
  std::atomic<uint64_t> timestamp_us{0};
  std::chrono::steady_clock::time_point last{}; // summary called only by poller, then joined final
  static void inc(std::atomic<uint64_t>& v) {
    auto n=v.load(std::memory_order_relaxed);
    while(n!=std::numeric_limits<uint64_t>::max() &&
          !v.compare_exchange_weak(n,n+1,std::memory_order_relaxed)) {}
  }
  void hit(Event e) { inc(values[e]); }
  bool due(std::chrono::steady_clock::time_point now, bool final=false) {
    if(!final && now-last<std::chrono::seconds(1)) return false;
    last=now; return true;
  }
  std::string summary(bool final, size_t subscribers) const {
    static const char* names[]={"created","started","publisher","wait_ok","wait_failed","ready",
      "read_ok","read_failed","callback","converted","publish_attempt","publish_returned",
      "info_returned","exceptions"};
    std::ostringstream s; s<<"ATLAS_IR_COUNTERS final="<<final;
    for(int i=0;i<count;++i)s<<" "<<names[i]<<"="<<values[i].load();
    s<<" create_rc="<<create_rc<<" mode_rc="<<mode_rc<<" start_rc="<<start_rc
     <<" wait_rc="<<wait_rc<<" read_rc="<<read_rc<<" width="<<width<<" height="<<height
     <<" pixel_format="<<format<<" fps="<<fps<<" stride="<<stride<<" bytes="<<bytes
     <<" frame_index="<<index<<" hardware_timestamp_us="<<timestamp_us<<" subscribers="<<subscribers;
    return s.str();
  }
};
}
