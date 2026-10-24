// Isolated PC test only. Tests stock executors, NOT a patched RMW wait set.
#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/static_single_threaded_executor.hpp>
#include <std_msgs/msg/int64.hpp>
#include <bondcpp/bond.hpp>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <iostream>
#include <thread>
using namespace std::chrono_literals;
using Clock=std::chrono::steady_clock;
void check(bool ok,const char* message) {if(!ok) throw std::runtime_error(message);}
double cpu(){timespec t{};clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+t.tv_nsec*1e-9;}
bool pump(rclcpp::Executor &e,std::function<bool()> done,double seconds) {
    auto until=Clock::now()+std::chrono::duration<double>(seconds);
    do {e.spin_some();if(done())return true;std::this_thread::sleep_for(1ms);}while(Clock::now()<until);
    return done();
}
void exercise(bool cached) {
    std::unique_ptr<rclcpp::Executor> ex;
    if(cached) ex=std::make_unique<rclcpp::executors::StaticSingleThreadedExecutor>();
    else ex=std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
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
    sub.reset();
    bool removed=pump(*ex,[&]{return pub->get_subscription_count()==0;},2);
    if(!removed) std::cerr<<"subscription_count_after_reset="<<pub->get_subscription_count()<<'\n';
    check(removed,"remove discovery");
    // Create after executor has already spun, not only before its cached collection.
    sub=rx->create_subscription<std_msgs::msg::Int64>("offline_data",10,
        [&](const std_msgs::msg::Int64 &m){check(m.data>last,"recreated ordering");last=m.data;++received;});
    check(pump(*ex,[&]{return pub->get_subscription_count()==1;},2),"recreate discovery");
    std_msgs::msg::Int64 m;m.data=20;pub->publish(m);
    check(pump(*ex,[&]{return received==21;},1),"recreated delivery");
    int ticks=0;auto timer=rx->create_wall_timer(10ms,[&]{++ticks;});
    check(pump(*ex,[&]{return ticks>=3;},1),"dynamic timer");
    timer->cancel();int frozen=ticks;pump(*ex,[]{return false;},.06);
    check(ticks==frozen,"cancelled timer callback");timer.reset();
    // Real bondcpp messages and timers. No production heartbeat values changed.
    bool formed_a=false,formed_b=false,broken=false;
    auto a=std::make_unique<bond::Bond>("offline_bond","pair",rx,[&]{broken=true;},[&]{formed_a=true;});
    auto b=std::make_unique<bond::Bond>("offline_bond","pair",tx,[]{},[&]{formed_b=true;});
    for(auto *p:{a.get(),b.get()}){p->setHeartbeatPeriod(.05);p->setHeartbeatTimeout(.4);p->setConnectTimeout(2);p->start();}
    check(pump(*ex,[&]{return formed_a&&formed_b;},3),"bond formation");
    pump(*ex,[]{return false;},.2);check(!broken,"false bond failure");
    ex->remove_node(tx); // Silence peer timers, rather than explicitly announcing death.
    auto stopped=Clock::now();check(pump(*ex,[&]{return broken;},1.5),"missed heartbeat failure");
    double detection=std::chrono::duration<double>(Clock::now()-stopped).count();
    check(detection>=.2 && detection<1.5,"heartbeat failure timing");
    b.reset();a.reset();ex->remove_node(rx);ex->cancel();
    std::cout<<"{\"mode\":\""<<(cached?"static":"standard")<<"\",\"checks\":\"PASS\",\"messages\":"<<received
             <<",\"heartbeat_failure_s\":"<<detection<<"}\n";
}
void measure(bool cached,int pair) {
    std::unique_ptr<rclcpp::Executor> ex;
    if(cached)ex=std::make_unique<rclcpp::executors::StaticSingleThreadedExecutor>();
    else ex=std::make_unique<rclcpp::executors::SingleThreadedExecutor>();
    auto node=std::make_shared<rclcpp::Node>("offline_bench");ex->add_node(node);
    int sent=0,received=0;
    auto pub=node->create_publisher<std_msgs::msg::Int64>("offline_load",100);
    auto sub=node->create_subscription<std_msgs::msg::Int64>("offline_load",100,[&](const std_msgs::msg::Int64&){++received;});
    check(pump(*ex,[&]{return pub->get_subscription_count()==1;},3),"benchmark discovery");
    auto timer=node->create_wall_timer(10ms,[&]{std_msgs::msg::Int64 m;m.data=++sent;pub->publish(m);});
    double begin=cpu();pump(*ex,[]{return false;},1.0);double used=cpu()-begin;
    timer->cancel();check(pump(*ex,[&]{return sent==received;},1),"benchmark drain");
    check(sent>=80,"benchmark stalled");
    ex->remove_node(node);ex->cancel();
    std::cout<<"{\"mode\":\""<<(cached?"static":"standard")<<"\",\"pair\":"<<pair<<",\"cpu_s\":"<<used
             <<",\"sent\":"<<sent<<",\"received\":"<<received<<"}\n";
}
int main(int argc,char**argv){
    try {
        check(std::getenv("ROS_DOMAIN_ID")&&std::string(std::getenv("ROS_DOMAIN_ID"))=="216","private domain required");
        check(std::getenv("ROS_LOCALHOST_ONLY")&&std::string(std::getenv("ROS_LOCALHOST_ONLY"))=="1","localhost required");
        rclcpp::init(argc,argv);
        if(argc==2 && std::string(argv[1])=="--static-only") {
            exercise(true);rclcpp::shutdown();return 0;
        }
        exercise(false);exercise(true);
        for(int i=0;i<4;++i){measure(i%2,i);measure(!(i%2),i);}
        rclcpp::shutdown();return 0;
    }catch(const std::exception &e){std::cerr<<"FAILED: "<<e.what()<<'\n';if(rclcpp::ok())rclcpp::shutdown();return 1;}
}
