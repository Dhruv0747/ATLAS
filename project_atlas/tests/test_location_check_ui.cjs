const assert=require('node:assert/strict');
const {lines,pose}=require('../web/v2/location-check.js');
assert.match(lines({state:'STALE'}),/STALE/);
assert.match(lines({state:'VERIFIED',historical_result:true}),/timestamped result/);
assert.match(lines({state:'MISMATCH',result:{lidar_pose:{x:1,y:2,yaw_deg:30},candidates:[]}}),/X 1.000 m/);
assert.match(lines({state:'UNCERTAIN'}),/Correction is disabled/);
assert.equal(pose(null),'Not independently established');
assert.match(lines({state:'CHECKING',evidence:{scan_stamp:123,scan_age_s:.2}}),/123.000000/);
console.log('6 location UI assertions passed');
// 2026-10-11: precise rejection codes, AMCL status, LiDAR-only result, last success kept apart.
{
  const stages={scan:{status:'ready',source:'/scan',age_s:.2},amcl:{status:'not_available',source:'/amcl_pose + map->odom TF',amcl_status:'NOT_INITIALIZED',reason:'AMCL has published no pose'}};
  const rej=lines({state:'UNAVAILABLE',code:'STOP_NOT_LATCHED',reason:'The drive stop is not latched',stages});
  assert.match(rej,/STOP_NOT_LATCHED/);assert.match(rej,/scan\s+READY/);assert.match(rej,/amcl\s+NOT_AVAILABLE/);
  const idle=lines({state:'IDLE',last_block:{code:'LIDAR_SCAN_STALE',reason:'age 3 s',stages,at_unix:200,age_s:4}});
  assert.match(idle,/Last request REJECTED.*LIDAR_SCAN_STALE/);
  const only=lines({state:'LIDAR_ONLY_MATCH',historical_result:true,ended_unix:100,
    evidence:{amcl_status:'NOT_INITIALIZED',amcl_reason:'AMCL has published no pose since the monitor started'},
    result:{lidar_pose:{x:.235,y:-1.435,yaw_deg:72},best_fit:.996,margin:.124,lidar_verdict:{reason:'unique LiDAR match on the saved map'}}});
  assert.match(only,/AMCL reference: NOT INITIALIZED/);assert.match(only,/Independent LiDAR: X 0.235 m/);
  assert.match(only,/no AMCL pose to compare/);assert.doesNotMatch(only,/State: VERIFIED/);
  const old=lines({state:'STALE',reason:'ROVER_MOVING: moved',last_success:{state:'LIDAR_ONLY_MATCH',lidar_pose:{x:1,y:2,yaw_deg:3},best_fit:.99,margin:.1,age_s:90}});
  assert.match(old,/State: STALE/);assert.match(old,/historical, not a live confirmation/);
  const stale=lines({state:'LIDAR_ONLY_MATCH',ended_unix:300,last_block:{code:'RATE_LIMITED',reason:'r',stages:{},at_unix:200,age_s:100}});
  assert.doesNotMatch(stale,/Last request REJECTED/);   // a rejection older than the newest result is not shown as current
  console.log('11 more location UI assertions passed');
}
