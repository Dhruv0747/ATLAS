// Executed by tests/test_vision3d_stage32_ui_state.py under Node; prints JSON results only.
const S = require('../web/v2/vision3d_state.js');
const out = {};
const rt = (state, extra) => Object.assign({ state, mode: 'ir', worker_pid: 11, driver_pid: 22, remaining_s: 40 }, extra || {});
const st = (state, received) => ({ state, received });
let m = S.newMemo();
out.checking = S.sessionView(rt('CHECKING'), {}, m, 0);
out.wait = S.sessionView(rt('ACTIVE'), { ir: st('UNAVAILABLE', 0) }, m, 1);
out.nofr = S.sessionView(rt('ACTIVE'), { ir: st('UNAVAILABLE', 0) }, m, 12.5);
out.ended_none = S.sessionView(rt('OFF', { reason: '60-second session complete; explicit Start required', driver_stopped: true }), {}, m, 70);
m = S.newMemo();
S.sessionView(rt('ACTIVE', { worker_pid: 12 }), { ir: st('UNAVAILABLE', 0) }, m, 0);
out.live = S.sessionView(rt('ACTIVE', { worker_pid: 12 }), { ir: st('ACTIVE', 1624) }, m, 3);
out.stale = S.sessionView(rt('ACTIVE', { worker_pid: 12 }), { ir: st('STALE', 1624) }, m, 30);
out.ended_ok = S.sessionView(rt('OFF', { worker_pid: 12, reason: '60-second session complete; explicit Start required', driver_stopped: true }), { ir: st('UNAVAILABLE', 0) }, m, 62);
out.lease = S.sessionView(rt('OFF', { worker_pid: 12, reason: 'viewer lease expired', driver_stopped: true }), {}, m, 63);
m = S.newMemo();
S.sessionView(rt('ACTIVE', { worker_pid: 13, mode: 'ir_depth' }), {}, m, 0);
out.mixed = S.sessionView(rt('ACTIVE', { worker_pid: 13, mode: 'ir_depth' }), { ir: st('UNAVAILABLE', 0), depth: st('ACTIVE', 300) }, m, 15);
out.blocked = S.sessionView(rt('RESOURCE BLOCKED', { worker_pid: 13, mode: 'ir_depth', reason: 'RESOURCE BLOCKED: CPU', failed_resources: { cpu: 76.2 }, driver_stopped: true }), {}, m, 20);
m = S.newMemo();
S.sessionView(rt('ACTIVE', { worker_pid: 14 }), { ir: st('ACTIVE', 50) }, m, 0);
out.newworker = S.sessionView(rt('ACTIVE', { worker_pid: 15 }), { ir: st('UNAVAILABLE', 0) }, m, 1);
out.none = S.sessionView(null, {}, S.newMemo(), 0);
out.off = S.sessionView({ state: 'OFF', reason: '' }, {}, S.newMemo(), 0);
out.modes = { verified: S.modeNote('ir', { state: 'verified' }), untested: S.modeNote('ir_depth', { state: 'untested' }), unsupported: S.modeNote('rgb_ir', { state: 'unsupported' }),
  cloud_blocked: S.modeNote('depth_cloud', { state: 'unsupported' }), cloud_ok: S.modeNote('depth_cloud', { state: 'untested' }), depth_default: S.modeNote('depth', undefined) };
console.log(JSON.stringify(out));
