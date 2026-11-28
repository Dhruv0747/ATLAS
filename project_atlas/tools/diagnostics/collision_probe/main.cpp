// Offline native Nav2 footprint checker. No ROS initialization or publishers.
// Reads a frozen raw costmap and candidate poses from stdin. This is not a
// controller action test and does not simulate obstacle-layer clearing.
#include <iostream>
#include <cmath>
#include "nav2_costmap_2d/footprint_collision_checker.hpp"
int main() {
  unsigned int w,h;double res,ox,oy;
  if(!(std::cin>>w>>h>>res>>ox>>oy)||w*h>1000000||res<=0)return 2;
  nav2_costmap_2d::Costmap2D grid(w,h,res,ox,oy,0);
  for(unsigned int y=0;y<h;y++)for(unsigned int x=0;x<w;x++) {
    int c;if(!(std::cin>>c)||c<0||c>255)return 3;grid.setCost(x,y,c);
  }
  nav2_costmap_2d::Footprint fp;
  for(auto xy:{std::pair<double,double>{.25,.18},{.25,-.18},{-.25,-.18},{-.25,.18}}){geometry_msgs::msg::Point p;p.x=xy.first;p.y=xy.second;fp.push_back(p);}
  nav2_costmap_2d::FootprintCollisionChecker<nav2_costmap_2d::Costmap2D*> checker(&grid);
  double x,y,a;while(std::cin>>x>>y>>a)std::cout<<checker.footprintCostAtPose(x,y,a,fp)<<"\n";
}
