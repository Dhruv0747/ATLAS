const assert=require('node:assert/strict');
const {lines,pose}=require('../web/v2/location-check.js');
assert.match(lines({state:'STALE'}),/STALE/);
assert.match(lines({state:'VERIFIED',historical_result:true}),/timestamped result/);
assert.match(lines({state:'MISMATCH',result:{lidar_pose:{x:1,y:2,yaw_deg:30},candidates:[]}}),/X 1.000 m/);
assert.match(lines({state:'UNCERTAIN'}),/Correction is disabled/);
assert.equal(pose(null),'Not independently established');
assert.match(lines({state:'CHECKING',evidence:{scan_stamp:123,scan_age_s:.2}}),/123.000000/);
console.log('6 location UI assertions passed');
