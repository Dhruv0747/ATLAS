// Offline AMCL 1.1.20 core replay of a saved drive WITH motion.
// Companion to atlas_amcl_diversity_experiment.cpp (parked only). No ROS
// initialization, publishers, services or actuators. Input is a bundle from
// atlas_amcl_motion_replay_extract.py.
//
// Reproduces nav2_amcl's per-scan loop for one laser:
//   delta = odom(scan) - odom(last update)            (odom frame)
//   update if |dx| > update_min_d || |dy| > update_min_d || |dyaw| > update_min_a
//          or a forced no-motion update is pending
//   DifferentialMotionModel::odometryUpdate (logic copied verbatim from 1.1.20)
//   LikelihoodFieldModel sensorUpdate, pf_update_resample every update
//   published pose = mean of heaviest cluster; covariance = whole-set cov
// Forced updates model atlas_mission_control's 1 Hz /request_nomotion_update.
//
// Configurations are diagnostics only, never deployed settings:
//   --odom recorded|scaled|scaled_shift   odom source exported by the extractor
//   --forced-period S                      0 disables forced updates
//   --alpha a1,a2,a3,a4                    motion noise
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>
extern "C" {
#include "nav2_amcl/pf/pf.hpp"
#include "nav2_amcl/pf/pf_kdtree.hpp"
#include "nav2_amcl/pf/pf_pdf.hpp"
}
#include "nav2_amcl/sensors/laser/laser.hpp"

using json = nlohmann::json;

static double angle_diff(double a, double b) {
  a = std::atan2(std::sin(a), std::cos(a));
  b = std::atan2(std::sin(b), std::cos(b));
  double d1 = a - b, d2 = 2 * M_PI - std::fabs(d1);
  if (d1 > 0) d2 *= -1.0;
  return std::fabs(d1) < std::fabs(d2) ? d1 : d2;
}

struct Alphas { double a1, a2, a3, a4; };

// Verbatim logic of nav2_amcl::DifferentialMotionModel::odometryUpdate (1.1.20).
static void differential_update(pf_t *pf, const pf_vector_t &pose, const pf_vector_t &delta, const Alphas &al) {
  pf_sample_set_t *set = pf->sets + pf->current_set;
  pf_vector_t old_pose = pf_vector_sub(pose, delta);
  double delta_rot1, delta_trans, delta_rot2;
  if (std::sqrt(delta.v[1] * delta.v[1] + delta.v[0] * delta.v[0]) < 0.01)
    delta_rot1 = 0.0;
  else
    delta_rot1 = angle_diff(std::atan2(delta.v[1], delta.v[0]), old_pose.v[2]);
  delta_trans = std::sqrt(delta.v[0] * delta.v[0] + delta.v[1] * delta.v[1]);
  delta_rot2 = angle_diff(delta.v[2], delta_rot1);
  double rot1_noise = std::min(std::fabs(angle_diff(delta_rot1, 0.0)), std::fabs(angle_diff(delta_rot1, M_PI)));
  double rot2_noise = std::min(std::fabs(angle_diff(delta_rot2, 0.0)), std::fabs(angle_diff(delta_rot2, M_PI)));
  for (int i = 0; i < set->sample_count; i++) {
    pf_sample_t *s = set->samples + i;
    double r1 = angle_diff(delta_rot1, pf_ran_gaussian(std::sqrt(al.a1 * rot1_noise * rot1_noise + al.a2 * delta_trans * delta_trans)));
    double tr = delta_trans - pf_ran_gaussian(std::sqrt(al.a3 * delta_trans * delta_trans + al.a4 * rot1_noise * rot1_noise + al.a4 * rot2_noise * rot2_noise));
    double r2 = angle_diff(delta_rot2, pf_ran_gaussian(std::sqrt(al.a1 * rot2_noise * rot2_noise + al.a2 * delta_trans * delta_trans)));
    s->pose.v[0] += tr * std::cos(s->pose.v[2] + r1);
    s->pose.v[1] += tr * std::sin(s->pose.v[2] + r1);
    s->pose.v[2] += r1 + r2;
  }
}

static void refresh_clusters(pf_t *pf) {
  auto *set = &pf->sets[pf->current_set];
  pf_kdtree_clear(set->kdtree);
  for (int i = 0; i < set->sample_count; ++i)
    pf_kdtree_insert(set->kdtree, set->samples[i].pose, set->samples[i].weight);
  pf_cluster_stats(pf, set);
}

static void restore_prior(pf_t *pf, const json &prior) {
  auto *set = &pf->sets[pf->current_set];
  if (prior.empty() || prior.size() > static_cast<size_t>(pf->max_samples))
    throw std::runtime_error("invalid prior size");
  set->sample_count = prior.size();
  double total = 0;
  for (const auto &p : prior) total += p.at(3).get<double>();
  if (!(total > 0)) throw std::runtime_error("invalid prior weights");
  for (int i = 0; i < set->sample_count; ++i) {
    for (int k = 0; k < 3; ++k) set->samples[i].pose.v[k] = prior[i].at(k).get<double>();
    set->samples[i].weight = prior[i].at(3).get<double>() / total;
  }
  pf->w_slow = pf->w_fast = 0;
  refresh_clusters(pf);
}

static void fill_scan(nav2_amcl::LaserData &d, nav2_amcl::Laser &model, const json &scan) {
  // nav2: range_min = max(scan.range_min, laser_min_range=-1); range_max = min(scan.range_max, 100)
  const double rmin = scan.at("range_min").get<double>();
  const double rmax = std::min(scan.at("range_max").get<double>(), 100.0);
  d.laser = &model;
  d.range_count = scan.at("ranges").size();
  d.range_max = rmax;
  d.ranges = new double[d.range_count][2];
  for (int i = 0; i < d.range_count; ++i) {
    const auto &r = scan["ranges"][i];
    double v = r.is_null() ? std::numeric_limits<double>::infinity() : r.get<double>();
    d.ranges[i][0] = v <= rmin ? rmax : v;  // nav2 replaces <= range_min with range_max (skipped)
    d.ranges[i][1] = scan["angle_min"].get<double>() + i * scan["angle_increment"].get<double>();
  }
}

static json publish(pf_t *pf) {
  auto *set = &pf->sets[pf->current_set];
  int best = -1; double w = -1;
  for (int i = 0; i < set->cluster_count; ++i)
    if (set->clusters[i].weight > w) { w = set->clusters[i].weight; best = i; }
  if (best < 0) throw std::runtime_error("no cluster");
  const auto &m = set->clusters[best].mean;
  // nav2 copies the WHOLE-SET covariance into /amcl_pose
  double xy = std::sqrt(std::max(0.0, set->cov.m[0][0]) + std::max(0.0, set->cov.m[1][1]));
  double yaw = std::sqrt(std::max(0.0, set->cov.m[2][2])) * 180.0 / M_PI;
  return {{"x", m.v[0]}, {"y", m.v[1]}, {"yaw", m.v[2]}, {"xy_std", xy}, {"yaw_std_deg", yaw},
          {"clusters", set->cluster_count}, {"winner_weight", w}, {"particles", set->sample_count}};
}

int main(int argc, char **argv) {
  try {
    std::string bundle_path, out_path, odom = "recorded";
    double forced = 1.0, min_d = 0.05, min_a = 0.05;
    Alphas al{0.2, 0.2, 0.2, 0.2};
    int seed = 1;
    for (int i = 1; i < argc; ++i) {
      std::string a = argv[i];
      auto next = [&]() { if (i + 1 >= argc) throw std::runtime_error("missing value for " + a); return std::string(argv[++i]); };
      if (a == "--odom") odom = next();
      else if (a == "--forced-period") forced = std::stod(next());
      else if (a == "--seed") seed = std::stoi(next());
      else if (a == "--update-min-d") min_d = std::stod(next());
      else if (a == "--update-min-a") min_a = std::stod(next());
      else if (a == "--alpha") {
        std::stringstream ss(next()); std::string t; std::vector<double> v;
        while (std::getline(ss, t, ',')) v.push_back(std::stod(t));
        if (v.size() != 4) throw std::runtime_error("--alpha needs 4 values");
        al = {v[0], v[1], v[2], v[3]};
      } else if (bundle_path.empty()) bundle_path = a;
      else if (out_path.empty()) out_path = a;
      else throw std::runtime_error("unexpected argument " + a);
    }
    if (bundle_path.empty() || out_path.empty())
      throw std::runtime_error("usage: replay bundle.json out.json [--odom recorded|scaled|scaled_shift] [--forced-period 1.0] [--alpha a1,a2,a3,a4] [--seed N]");
    std::ifstream in(bundle_path); json b; in >> b;
    // Production parameters (nav2_params.yaml amcl section).
    const int min_particles = 500, max_particles = 2000;
    pf_t *pf = pf_alloc(min_particles, max_particles, 0.0, 0.0, nullptr);
    srand48(seed);
    pf->pop_err = 0.05; pf->pop_z = 0.99;
    restore_prior(pf, b.at("particles"));
    auto &g = b.at("map");
    map_t *map = map_alloc();
    map->size_x = g.at("width"); map->size_y = g.at("height"); map->scale = g.at("resolution");
    map->origin_x = g["origin"][0].get<double>() + (map->size_x / 2) * map->scale;
    map->origin_y = g["origin"][1].get<double>() + (map->size_y / 2) * map->scale;
    size_t count = static_cast<size_t>(map->size_x) * map->size_y;
    if (g["cells"].size() != count) throw std::runtime_error("map size mismatch");
    map->cells = static_cast<map_cell_t *>(calloc(count, sizeof(map_cell_t)));
    for (size_t i = 0; i < count; ++i) {
      int v = g["cells"][i];
      map->cells[i].occ_state = v == 0 ? -1 : v == 100 ? 1 : 0;
    }
    nav2_amcl::LikelihoodFieldModel model(0.5, 0.5, 0.2, 2.0, 60, map);
    pf_vector_t laser_pose = {{b["laser"][0].get<double>(), b["laser"][1].get<double>(), 0.0}};
    model.SetLaserPose(laser_pose);  // laser yaw is folded into exported bearings
    const auto &scans = b.at("scans");
    if (scans.empty()) throw std::runtime_error("no scans");
    pf_vector_t last = pf_vector_zero();
    bool init = false;
    double last_forced = -1e9;
    json traj = json::array();
    int motion_updates = 0, forced_updates = 0;
    for (size_t k = 0; k < scans.size(); ++k) {
      const auto &s = scans[k];
      const double t = s["time_s"];
      const auto &o = s["odom"][odom];
      pf_vector_t pose = {{o[0].get<double>(), o[1].get<double>(), o[2].get<double>()}};
      bool force = false, motion = false;
      pf_vector_t delta = pf_vector_zero();
      if (!init) { last = pose; init = true; force = true; last_forced = t; }
      else {
        delta.v[0] = pose.v[0] - last.v[0];
        delta.v[1] = pose.v[1] - last.v[1];
        delta.v[2] = angle_diff(pose.v[2], last.v[2]);
        motion = std::fabs(delta.v[0]) > min_d || std::fabs(delta.v[1]) > min_d || std::fabs(delta.v[2]) > min_a;
        if (forced > 0 && t - last_forced >= forced) { force = true; last_forced = t; }
      }
      if (!motion && !force) continue;
      // nav2 1.1.20: a forced update still applies the (sub-threshold)
      // accumulated delta through the motion model, except on initialisation.
      if (k > 0) differential_update(pf, pose, delta, al);
      if (motion) ++motion_updates; else ++forced_updates;
      last = pose;
      nav2_amcl::LaserData d;
      fill_scan(d, model, s);
      if (!model.sensorUpdate(pf, &d)) throw std::runtime_error("sensor update failed");
      pf_update_resample(pf, nullptr);
      refresh_clusters(pf);
      json p = publish(pf);
      p["time_s"] = t; p["scan_index"] = k; p["moving"] = s["moving"]; p["forced"] = !motion;
      traj.push_back(p);
    }
    pf_free(pf); map_free(map);
    json out = {{"source_bag", b["source_bag"]}, {"odom", odom}, {"forced_period_s", forced},
                {"alpha", {al.a1, al.a2, al.a3, al.a4}}, {"update_min_d", min_d}, {"update_min_a", min_a},
                {"seed", seed}, {"motion_updates", motion_updates}, {"forced_updates", forced_updates},
                {"navigation_authorized", false},
                {"limitations", "AMCL core library replay from the recorded initial cloud; not a full ROS replay; no ground truth"},
                {"trajectory", traj}};
    std::ofstream(out_path) << out.dump() << std::endl;
    std::cout << json({{"output", out_path}, {"updates", traj.size()}, {"motion_updates", motion_updates},
                       {"forced_updates", forced_updates}}).dump() << std::endl;
  } catch (const std::exception &e) { std::cerr << e.what() << std::endl; return 1; }
}
