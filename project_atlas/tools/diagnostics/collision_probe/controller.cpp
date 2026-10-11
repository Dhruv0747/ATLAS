// Isolated installed Nav2 RPP + obstacle/inflation-layer integration probe.
// Domain 173 required. No cmd_vel publisher, actions, controller server or motors.
// Observations are injected into the real obstacle layer; TF is local identity.
#include <cstdlib>
#include <iostream>
#include <cmath>
#include "rclcpp/rclcpp.hpp"
#include "nav2_costmap_2d/costmap_2d_ros.hpp"
#include "nav2_costmap_2d/obstacle_layer.hpp"
#include "nav2_regulated_pure_pursuit_controller/regulated_pure_pursuit_controller.hpp"
#include "nav2_controller/plugins/simple_goal_checker.hpp"
#include "sensor_msgs/point_cloud2_iterator.hpp"

int main(int argc, char **argv) {
  if (!std::getenv("ROS_DOMAIN_ID") || std::string(std::getenv("ROS_DOMAIN_ID")) != "173") return 90;
  rclcpp::init(argc,argv);
  auto parent=std::make_shared<nav2_util::LifecycleNode>("controller_server");
  auto cm=std::make_shared<nav2_costmap_2d::Costmap2DROS>("local_costmap");
  cm->on_configure(rclcpp_lifecycle::State());
  auto grid=cm->getCostmap();
  auto layers=cm->getLayeredCostmap();
  std::shared_ptr<nav2_costmap_2d::ObstacleLayer> obstacles;
  for(auto p:*layers->getPlugins()) if(auto o=std::dynamic_pointer_cast<nav2_costmap_2d::ObstacleLayer>(p)) obstacles=o;
  if(!obstacles) return 91;
  auto tf=std::make_shared<tf2_ros::Buffer>(parent->get_clock());
  // Only static, synchronously inserted transforms; no future TF is awaited.
  tf->setUsingDedicatedThread(true);
  geometry_msgs::msg::TransformStamped t;
  t.header.frame_id="odom";t.child_frame_id="base_link";t.transform.rotation.w=1;
  tf->setTransform(t,"isolated_probe",true);
  nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController controller;
  controller.configure(parent,"FollowPath",tf,cm);controller.activate();
  nav2_controller::SimpleGoalChecker goal;goal.initialize(parent,"probe_goal",cm);
  auto clear=[&](){obstacles->clearStaticObservations(true,true);cm->resetLayers();layers->updateMap(0,0,0);};
  auto observe=[&](double x,double y,bool mark,bool ray){
    sensor_msgs::msg::PointCloud2 cloud;cloud.header.frame_id="odom";
    sensor_msgs::PointCloud2Modifier mod(cloud);mod.setPointCloud2FieldsByString(1,"xyz");mod.resize(1);
    sensor_msgs::PointCloud2Iterator<float> ix(cloud,"x"),iy(cloud,"y"),iz(cloud,"z");
    *ix=x;*iy=y;*iz=.1;
    geometry_msgs::msg::Point origin;
    nav2_costmap_2d::Observation obs(origin,cloud,2.5,.05,3.,0.);
    obstacles->clearStaticObservations(true,true);obstacles->addStaticObservation(obs,mark,ray);
    layers->updateMap(0,0,0);
  };
  auto drive=[&](const char*name,int curve,bool reverse){
    nav_msgs::msg::Path path;path.header.frame_id="odom";path.header.stamp=parent->now();
    for(int i=0;i<=60;i++) {double s=i*.01*(reverse?-1:1),a=curve*s/.35;
      geometry_msgs::msg::PoseStamped p;p.header=path.header;
      p.pose.position.x=curve?.35*std::sin(a)/curve:s;
      p.pose.position.y=curve?.35*(1-std::cos(a))/curve:0;
      p.pose.orientation.z=std::sin(a/2);p.pose.orientation.w=std::cos(a/2);path.poses.push_back(p);
    }
    controller.setPlan(path);geometry_msgs::msg::PoseStamped pose=path.poses[0];geometry_msgs::msg::Twist v;
    try {auto out=controller.computeVelocityCommands(pose,v,&goal);
      std::cout<<"RESULT "<<name<<" COMMAND "<<out.twist.linear.x<<" "<<out.twist.angular.z<<std::endl;
    } catch(const std::exception&e){std::cout<<"RESULT "<<name<<" REJECT "<<e.what()<<std::endl;}
  };
  clear();drive("clear_straight",0,false);drive("clear_left",1,false);drive("clear_right",-1,false);
  observe(.3618828573,-.358044129,true,true);drive("front_right_051_straight",0,false);drive("front_right_051_right",-1,false);
  clear();observe(.30,0,true,true);drive("obstacle_appears",0,false);
  observe(2.,0,true,true);drive("obstacle_ray_cleared",0,false);
  clear();observe(.27,.20,true,true);drive("left_corner_curve",1,false);
  clear();observe(.27,-.20,true,true);drive("right_corner_curve",-1,false);
  clear();observe(-.30,0,true,true);drive("rear_occupied",0,true);
  clear();observe(0.,.26,true,true);drive("inflated_side_straight",0,false);
  auto changed=parent->set_parameter(rclcpp::Parameter("FollowPath.inflation_cost_scaling_factor",3.0));
  if(!changed.successful)return 92;
  drive("dynamic_factor_3",0,false);
  changed=parent->set_parameter(rclcpp::Parameter("FollowPath.inflation_cost_scaling_factor",15.0));
  if(!changed.successful)return 93;
  drive("dynamic_factor_15",0,false);
  clear();for(unsigned y=0;y<grid->getSizeInCellsY();y++) for(unsigned x=0;x<grid->getSizeInCellsX();x++) {
    double wx,wy;grid->mapToWorld(x,y,wx,wy);if(wx<-.26)grid->setCost(x,y,255);
  } drive("rear_unknown_encoded",0,true);
  clear();obstacles->clearStaticObservations(true,true);layers->updateMap(0,0,0);
  std::cout<<"RESULT missing_scan_costmap_current "<<cm->isCurrent()<<std::endl;
  drive("missing_scan_empty_free_map",0,false);
  rclcpp::sleep_for(std::chrono::milliseconds(1100));layers->updateMap(0,0,0);
  drive("stale_scan_empty_free_map",0,false);
  controller.deactivate();controller.cleanup();cm->on_cleanup(rclcpp_lifecycle::State());
  rclcpp::shutdown();return 0;
}
