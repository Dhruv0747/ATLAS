#include "ir_counters.hpp"
#include <cassert>
#include <iostream>
#include <stdexcept>
int main() {
  using C=atlas_ir::Counters;
  C c; assert(c.values[C::callback]==0);
  auto t=std::chrono::steady_clock::now();
  assert(c.due(t)); assert(!c.due(t)); assert(c.due(t+std::chrono::seconds(1)));
  for(int i=0;i<6;++i){c.wait_rc=102;c.hit(C::wait_failed);}
  assert(c.values[C::callback]==0 && c.values[C::wait_failed]==6);
  c.hit(C::created);c.hit(C::started);c.hit(C::publisher);
  // Simulated poll/read/callback/publication events. No SDK or sensor claim.
  for(int i=0;i<180;++i){c.hit(C::ready);c.hit(C::read_ok);c.hit(C::callback);
    c.width=320;c.height=240;c.format=202;c.timestamp_us=i*33333;c.index=i;
    c.hit(C::converted);c.hit(C::publish_attempt);c.hit(C::publish_returned);}
  assert(c.values[C::callback]==180 && c.values[C::publish_returned]==180);
  try{throw std::runtime_error("conversion");}catch(...){c.hit(C::exceptions);}
  c.hit(C::publish_attempt); // attempt is not a returned publish or remote delivery
  assert(c.values[C::publish_attempt]==181 && c.values[C::publish_returned]==180);
  c.values[C::ready]=UINT64_MAX;c.hit(C::ready);assert(c.values[C::ready]==UINT64_MAX);
  auto text=c.summary(true,1);assert(text.find("final=1")!=std::string::npos);
  assert(text.find("subscribers=1")!=std::string::npos);
  assert(c.due(t,true)); // final summary survives zero-frame session too
  auto begin=std::chrono::steady_clock::now();
  for(int i=0;i<1000000;++i)c.hit(C::callback);
  auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  std::cout<<"PASS counter simulation; 1000000 atomic events seconds="<<elapsed
    <<" scalar_struct_bytes="<<sizeof(C)<<" summary_bytes="<<text.size()<<std::endl;
}
