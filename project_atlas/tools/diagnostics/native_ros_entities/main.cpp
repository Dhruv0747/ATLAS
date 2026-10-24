// Isolated PC test only. Stock/explicit-lifecycle executors, NOT patched RMW.
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/static_single_threaded_executor.hpp>
#include <std_msgs/msg/int64.hpp>
#include <bondcpp/bond.hpp>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <thread>
#include "onepass_strategy.hpp"
using namespace std::chrono_literals;
using Clock=std::chrono::steady_clock;
// Offline explicit-lifecycle prototype, NOT an automatic RMW implementation.
// Caller must serialize mutation with spinning and invalidate BEFORE destruction.
bool lifecycle_mode=false;
bool detach_groups=false;
bool collector_owned=false;
bool onepass=false;
std::unique_ptr<rclcpp::Executor> make_executor(bool candidate) {
    if(candidate && onepass) {
        rclcpp::ExecutorOptions options;
        options.memory_strategy=std::make_shared<rclcpp::memory_strategies::atlas_onepass_memory_strategy::AllocatorMemoryStrategy<>>();
        return std::make_unique<rclcpp::executors::SingleThreadedExecutor>(options);
    }
    if(candidate)return std::make_unique<rclcpp::executors::StaticSingleThreadedExecutor>();
    return std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
}
const char* mode_name(bool cached) {
    return !cached?"standard":onepass?"onepass_standard":collector_owned?"collector_owned":lifecycle_mode?"explicit_lifecycle":"static";
}
void invalidate(std::unique_ptr<rclcpp::Executor>& ex,
                const std::vector<rclcpp::Node::SharedPtr>& nodes) {
    if(!lifecycle_mode)return;
    ex->cancel();
    // Explicitly detach groups before nodes: do not leave association ownership
    // to deferred collector refresh while rebuilding a stopped executor.
    if(detach_groups) {
        for(const auto &weak:ex->get_all_callback_groups()) {
            if(auto group=weak.lock())ex->remove_callback_group(group);
        }
    }
    // Humble16.0.21 remove_node erases automatic groups without clearing their
    // association flag. Let the collector destructor release its own map instead.
    if(!collector_owned)for(const auto &node:nodes)ex->remove_node(node);
    ex.reset(); // release cached shared ownership before user destroys an entity
    if(collector_owned)for(const auto &node:nodes) {
        node->get_node_base_interface()->for_each_callback_group([](auto group) {
            if(group->get_associated_with_executor_atomic().load())
                throw std::runtime_error("collector did not release group ownership");
        });
    }
    ex=std::make_unique<rclcpp::executors::StaticSingleThreadedExecutor>();
    for(const auto &node:nodes)ex->add_node(node);
}
void check(bool ok,const char* message) {if(!ok) throw std::runtime_error(message);}
double cpu(){timespec t{};clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+t.tv_nsec*1e-9;}
bool pump(rclcpp::Executor &e,std::function<bool()> done,double seconds) {
    auto until=Clock::now()+std::chrono::duration<double>(seconds);
    do {e.spin_some();if(done())return true;std::this_thread::sleep_for(1ms);}while(Clock::now()<until);
    return done();
}
void lookup_checks() {
    using MS=rclcpp::memory_strategy::MemoryStrategy;
    auto node=std::make_shared<rclcpp::Node>("lookup_checks");
    auto group=node->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
    rclcpp::SubscriptionOptions options;options.callback_group=group;
    auto sub=node->create_subscription<std_msgs::msg::Int64>("lookup_test",10,[](const std_msgs::msg::Int64&){},options);
    MS::WeakCallbackGroupsToNodesMap groups;groups[group]=node->get_node_base_interface();
    auto handle=sub->get_subscription_handle();
    auto match=atlas_offline::lookup(handle,groups);
    check(match.first==sub && match.second==group,"onepass identity");match={};
    check(!atlas_offline::lookup(std::make_shared<rcl_subscription_t>(),groups).first,"unknown handle");
    group->can_be_taken_from().store(false);
    rclcpp::memory_strategies::atlas_onepass_memory_strategy::AllocatorMemoryStrategy<> strategy;
    strategy.collect_entities(groups);
    rclcpp::AnyExecutable exec;strategy.get_next_subscription(exec,groups);
    check(!exec.subscription,"busy callback group dispatched");
    group->can_be_taken_from().store(true);
    strategy.clear_handles();strategy.collect_entities(groups);
    strategy.get_next_subscription(exec,groups);
    check(exec.subscription==sub && exec.callback_group==group,"available group missing");
    exec.subscription.reset();exec.callback_group.reset();exec.node_base.reset();strategy.clear_handles();
    groups[group]={};
    match=atlas_offline::lookup(handle,groups);
    check(match.first==sub && !match.second,"expired node accepted");match={};
    groups[group]=node->get_node_base_interface();
    sub.reset();check(!atlas_offline::lookup(handle,groups).first,"destroyed subscription retained");
    group.reset();check(!atlas_offline::lookup(handle,groups).first,"expired group retained");
    std::cout<<"{\"lookup_checks\":\"PASS\",\"cases\":7}\n";
}
void lookup_benchmark() {
    using MS=rclcpp::memory_strategy::MemoryStrategy;
    for(int count:{1,8,32}) {
        auto node=std::make_shared<rclcpp::Node>("lookup_bench");
        MS::WeakCallbackGroupsToNodesMap groups;
        std::vector<rclcpp::CallbackGroup::SharedPtr> owners;
        std::vector<rclcpp::SubscriptionBase::SharedPtr> subs;
        std::vector<std::shared_ptr<const rcl_subscription_t>> handles;
        for(int i=0;i<count;++i) {
            auto group=node->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
            rclcpp::SubscriptionOptions options;options.callback_group=group;
            auto sub=node->create_subscription<std_msgs::msg::Int64>("lookup_"+std::to_string(i),10,[](const std_msgs::msg::Int64&){},options);
            groups[group]=node->get_node_base_interface();owners.push_back(group);
            handles.push_back(sub->get_subscription_handle());subs.push_back(sub);
        }
        for(int pair=0;pair<4;++pair)for(bool candidate:{bool(pair%2),!bool(pair%2)}) {
            double begin=cpu();
            for(int i=0;i<20000;++i) {
                int index=i%count;atlas_offline::Match match;
                if(candidate)match=atlas_offline::lookup(handles[index],groups);
                else {match.first=MS::get_subscription_by_handle(handles[index],groups);
                      match.second=MS::get_group_by_subscription(match.first,groups);}
                check(match.first==subs[index] && match.second==owners[index],"lookup benchmark identity");
            }
            std::cout<<"{\"lookup_count\":"<<count<<",\"pair\":"<<pair<<",\"onepass\":"<<candidate<<",\"cpu_s\":"<<cpu()-begin<<",\"calls\":20000}\n";
        }
    }
}
void exercise(bool cached) {
    auto ex=make_executor(cached);
    auto tx=std::make_shared<rclcpp::Node>("offline_tx");
    auto rx=std::make_shared<rclcpp::Node>("offline_rx");
    ex->add_node(tx);ex->add_node(rx);
    auto pub=tx->create_publisher<std_msgs::msg::Int64>("offline_data",10);
    int received=0,last=-1;
    auto sub=rx->create_subscription<std_msgs::msg::Int64>("offline_data",10,
        [&](const std_msgs::msg::Int64 &m){check(m.data>last,"ordering");last=m.data;++received;});
    check(pump(*ex,[&]{return pub->get_subscription_count()==1;},3),"discovery");
    for(int i=0;i<20;++i){std_msgs::msg::Int64 m;m.data=i;pub->publish(m);
        check(pump(*ex,[&]{return received==i+1;},1),"delivery");}
    if(cached)invalidate(ex,{tx,rx});
    sub.reset();
    bool removed=pump(*ex,[&]{return pub->get_subscription_count()==0;},2);
    if(!removed) std::cerr<<"subscription_count_after_reset="<<pub->get_subscription_count()<<'\n';
    check(removed,"remove discovery");
    // Create after executor has already spun, not only before its cached collection.
    if(cached)invalidate(ex,{tx,rx});
    sub=rx->create_subscription<std_msgs::msg::Int64>("offline_data",10,
        [&](const std_msgs::msg::Int64 &m){check(m.data>last,"recreated ordering");last=m.data;++received;});
    if(cached)invalidate(ex,{tx,rx}); // rebuild after committing the new generation
    check(pump(*ex,[&]{return pub->get_subscription_count()==1;},2),"recreate discovery");
    std_msgs::msg::Int64 m;m.data=20;pub->publish(m);
    check(pump(*ex,[&]{return received==21;},1),"recreated delivery");
    if(cached)invalidate(ex,{tx,rx});
    int ticks=0;auto timer=rx->create_wall_timer(10ms,[&]{++ticks;});
    if(cached)invalidate(ex,{tx,rx});
    check(pump(*ex,[&]{return ticks>=3;},1),"dynamic timer");
    timer->cancel();int frozen=ticks;pump(*ex,[]{return false;},.06);
    check(ticks==frozen,"cancelled timer callback");
    if(cached)invalidate(ex,{tx,rx});
    timer.reset();
    // Real bondcpp messages and timers. No production heartbeat values changed.
    if(cached)invalidate(ex,{tx,rx});
    bool formed_a=false,formed_b=false,broken=false;
    auto a=std::make_unique<bond::Bond>("offline_bond","pair",rx,[&]{broken=true;},[&]{formed_a=true;});
    auto b=std::make_unique<bond::Bond>("offline_bond","pair",tx,[]{},[&]{formed_b=true;});
    for(auto *p:{a.get(),b.get()}){p->setHeartbeatPeriod(.05);p->setHeartbeatTimeout(.4);p->setConnectTimeout(2);p->start();}
    if(cached)invalidate(ex,{tx,rx});
    check(pump(*ex,[&]{return formed_a&&formed_b;},3),"bond formation");
    pump(*ex,[]{return false;},.2);check(!broken,"false bond failure");
    // Node removal must use the SAME ownership-aware transaction as entity
    // mutation. A raw static remove_node can leave cached peer timers runnable.
    if(cached && collector_owned)invalidate(ex,{rx});
    else ex->remove_node(tx);
    // Silence peer timers, rather than explicitly announcing death.
    auto stopped=Clock::now();check(pump(*ex,[&]{return broken;},1.5),"missed heartbeat failure");
    double detection=std::chrono::duration<double>(Clock::now()-stopped).count();
    check(detection>=.2 && detection<1.5,"heartbeat failure timing");
    if(cached)invalidate(ex,{rx});
    b.reset();a.reset();ex->remove_node(rx);ex->cancel();
    std::cout<<"{\"mode\":\""<<mode_name(cached)<<"\",\"checks\":\"PASS\",\"messages\":"<<received
             <<",\"heartbeat_failure_s\":"<<detection<<"}\n";
}
void measure(bool cached,int pair) {
    auto ex=make_executor(cached);
    auto node=std::make_shared<rclcpp::Node>("offline_bench");ex->add_node(node);
    int sent=0,received=0;
    auto pub=node->create_publisher<std_msgs::msg::Int64>("offline_load",100);
    auto sub=node->create_subscription<std_msgs::msg::Int64>("offline_load",100,[&](const std_msgs::msg::Int64&){++received;});
    check(pump(*ex,[&]{return pub->get_subscription_count()==1;},3),"benchmark discovery");
    auto timer=node->create_wall_timer(10ms,[&]{if(sent>=100)return;std_msgs::msg::Int64 m;m.data=++sent;pub->publish(m);});
    double begin=cpu();auto wall_begin=Clock::now();
    check(pump(*ex,[&]{return received==100;},2.0),"fixed workload delivery");
    double used=cpu()-begin;
    double wall=std::chrono::duration<double>(Clock::now()-wall_begin).count();
    timer->cancel();check(pump(*ex,[&]{return sent==received;},1),"benchmark drain");
    check(sent==100 && received==100,"benchmark workload mismatch");
    // Include a separately reported mutation cost, never label steady-state
    // savings as total lifecycle or whole-robot savings.
    double mutation_begin=cpu();
    if(cached)invalidate(ex,{node});
    timer.reset();sub.reset();
    check(pump(*ex,[&]{return pub->get_subscription_count()==0;},1),"benchmark removal");
    double mutation_cpu=cpu()-mutation_begin;
    ex->remove_node(node);ex->cancel();
    std::cout<<"{\"mode\":\""<<mode_name(cached)<<"\",\"pair\":"<<pair<<",\"cpu_s\":"<<used<<",\"wall_s\":"<<wall<<",\"mutation_cpu_s\":"<<mutation_cpu
             <<",\"sent\":"<<sent<<",\"received\":"<<received<<"}\n";
}
int main(int argc,char**argv){
    try {
        check(std::getenv("ROS_DOMAIN_ID")&&std::string(std::getenv("ROS_DOMAIN_ID"))=="216","private domain required");
        check(std::getenv("ROS_LOCALHOST_ONLY")&&std::string(std::getenv("ROS_LOCALHOST_ONLY"))=="1","localhost required");
        rclcpp::init(argc,argv);
        if(argc==2 && std::string(argv[1])=="--lookup-only") {
            lookup_checks();lookup_benchmark();rclcpp::shutdown();return 0;
        }
        onepass=argc==2 && std::string(argv[1])=="--onepass";
        detach_groups=argc==2 && std::string(argv[1])=="--explicit-groups";
        collector_owned=argc==2 && std::string(argv[1])=="--collector-owned";
        lifecycle_mode=collector_owned || detach_groups || (argc==2 && std::string(argv[1])=="--explicit-lifecycle");
        if(argc==2 && std::string(argv[1])=="--static-only") {
            exercise(true);rclcpp::shutdown();return 0;
        }
        exercise(false);exercise(true);
        for(int i=0;i<6;++i){measure(i%2,i);measure(!(i%2),i);}
        rclcpp::shutdown();return 0;
    }catch(const std::exception &e){std::cerr<<"FAILED: "<<e.what()<<'\n';if(rclcpp::ok())rclcpp::shutdown();return 1;}
}
