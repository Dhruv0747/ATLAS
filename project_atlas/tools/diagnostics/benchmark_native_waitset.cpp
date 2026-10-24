// Offline native FastDDS experiment. No participants, network, ROS nodes or control.
// NOT an RMW patch: retained guards have explicit lifetimes in this fixture only.
#include <fastdds/dds/core/condition/GuardCondition.hpp>
#include <fastdds/dds/core/condition/WaitSet.hpp>
#include <algorithm>
#include <chrono>
#include <ctime>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
using namespace eprosima::fastdds::dds;
using RC = eprosima::fastrtps::types::ReturnCode_t;
void require(bool value) { if (!value) throw std::runtime_error("native equivalence check failed"); }
double cpu() { timespec ts{}; clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&ts); return ts.tv_sec+ts.tv_nsec*1e-9; }

void correctness() {
    GuardCondition a,b; WaitSet w; ConditionSeq ready;
    require(w.attach_condition(a)==RC::RETCODE_OK);
    require(w.wait(ready,{0,1000000})==RC::RETCODE_TIMEOUT);
    a.set_trigger_value(true);
    require(w.wait(ready,{0,0})==RC::RETCODE_OK && ready.size()==1 && ready[0]==&a);
    a.set_trigger_value(false);
    require(w.attach_condition(b)==RC::RETCODE_OK);
    b.set_trigger_value(true);
    require(w.wait(ready,{0,0})==RC::RETCODE_OK && ready.size()==1 && ready[0]==&b);
    require(w.detach_condition(b)==RC::RETCODE_OK);
    require(w.wait(ready,{0,0})==RC::RETCODE_TIMEOUT);
    // A retained condition must still wake a blocked waiter; no polling sleeps added.
    std::thread trigger([&]{std::this_thread::sleep_for(std::chrono::milliseconds(5)); a.set_trigger_value(true);});
    auto result=w.wait(ready,{1,0}); trigger.join();
    require(result==RC::RETCODE_OK && ready.size()==1 && ready[0]==&a);
    require(w.detach_condition(a)==RC::RETCODE_OK);
    // Safe destruction is explicit, never a cached dangling entity pointer.
    auto transient=std::make_unique<GuardCondition>();
    require(w.attach_condition(*transient)==RC::RETCODE_OK);
    require(w.detach_condition(*transient)==RC::RETCODE_OK); transient.reset();
    require(w.get_conditions(ready)==RC::RETCODE_OK && ready.empty());
}

double run(int count, bool retained, int rounds) {
    std::vector<std::unique_ptr<GuardCondition>> guards;
    for(int i=0;i<count;++i) guards.emplace_back(new GuardCondition);
    WaitSet wait; ConditionSeq ready;
    double begin=cpu();
    if(retained) for(auto &g:guards) require(wait.attach_condition(*g)==RC::RETCODE_OK);
    for(int i=0;i<rounds;++i) {
        if(!retained) for(auto &g:guards) require(wait.attach_condition(*g)==RC::RETCODE_OK);
        auto &selected=guards[i%count]; selected->set_trigger_value(true);
        require(wait.wait(ready,{0,0})==RC::RETCODE_OK);
        require(ready.size()==1 && ready[0]==selected.get());
        selected->set_trigger_value(false);
        if(!retained) for(auto &g:guards) require(wait.detach_condition(*g)==RC::RETCODE_OK);
    }
    if(retained) for(auto &g:guards) require(wait.detach_condition(*g)==RC::RETCODE_OK);
    return cpu()-begin;
}

int main(int argc, char **argv) {
    try {
        require(argc==1 || (argc==2 && std::string(argv[1])=="--check-only"));
        correctness();
        if(argc==2) {std::cout << "correctness PASS\n"; return 0;}
        std::cout << "{\"correctness\":\"PASS\",\"participants\":0,\"rounds\":500000,\"pairs\":[";
        bool first=true;
        for(int n:{1,8,32}) for(int pair=0;pair<6;++pair) {
            double baseline,candidate;
            if(pair%2) {candidate=run(n,true,500000);baseline=run(n,false,500000);}
            else {baseline=run(n,false,500000);candidate=run(n,true,500000);}
            if(!first) std::cout << ',';
            first=false;
            std::cout << "{\"entities\":"<<n<<",\"pair\":"<<pair<<",\"baseline_s\":"<<baseline
                      <<",\"retained_s\":"<<candidate<<",\"saving_percent\":"<<100*(baseline-candidate)/baseline<<'}';
        }
        std::cout << "]}\n";
    } catch(const std::exception &e) {std::cerr<<e.what()<<'\n'; return 1;}
}
