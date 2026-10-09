# ATLAS complete failure timeline

Updated 2026-10-09. Canonical requested filename; **historical coverage is incomplete**. This contains an initial curated failure chronology plus the complete index of 268 currently reachable Git commits. Commit titles are historical author claims, not independent test results. Author dates are retained with offsets and need not equal physical test time; merge ordering and boot clock changes need care.

## Curated failure chronology

| Date / period | IDs | Observation and disposition |
| --- | --- | --- |
| 2026-10-09 evening | 011 | Passive stationary capture found 2,000 AMCL particles at one effective geometric support point at the previously wrong return pose. Saved round-trip cloud support also collapses at +104.009 s. Forced-update/resampling policy identified for isolated testing; original five-jump selection cause remains unresolved. No production change. |
| 2026-08-04 | 001,010 | Baseline command-integrated odometry, inconsistent TF/IMU mounting; isolated counts absent on M2–M4. Hardware replacement restored historical responses. Calibration remained separate. |
| 2026-08-06 | 014 | Commissioning report claimed broad passes with old motor mapping. Preserve as historical scope, not current certification. |
| 2026-08-09–24 | 012,013 | Navigation model and remote timing changes; planner/controller mismatch aligned Aug24. Working remote restored after experiments. |
| 2026-08-24 | 011 | 120-beam and beam-skipping AMCL trials rejected; autonomous Hall start failed; manual recovery ended at physical room but stale saved coordinate disagreed. |
| 2026-08-25–26 | 002,003,011 | Same-boot odom checkpoint added for reconnect; discovery/AMCL heartbeat changes; no universal long-term fix inferred. |
| 2026-09-01–03 | 009 | Mega I2C/restart loop fixes, migration to UNO, native USB/boot-order repairs; hardware generations must not be conflated. |
| 2026-09-10 | 001,003,013 | Encoder stop/degraded guards tested; low-power stall trial rejected; separate drive floors improved recorded stops. CLI discovery recovered independently of running stack. |
| 2026-09-16–17 | 001,002,008,010 | IM10A/USB role problems; manual 40 cm produced roughly 21 cm odometry; recovery JSON truncation caused unnecessary restart and was repaired with scoped live verification. |
| 2026-09-19–21 | 002,009 | Passive identity discovery added; camera auto-energization on reconnect removed. No all-device electrical endurance proof. |
| 2026-09-25 | 010,014 | Stationary corrected IMU drift triggered authority revocation; three-encoder/fusion changes proceeded under gates. |
| 2026-09-30–Oct2 | 001,003,011 | Ground failure revoked navigation validation; mapping/EKF discovery/source fixes; new successful isolated test does not certify route reliability. |
| 2026-10-04–06 | 011,013,014 | Manual mapping readiness race and genuine corrections; steering authority restored; CPU optimizations; readiness gates documented. |
| 2026-10-08 | 001,004,005,006,011 | Saved-bag comparisons rejected or inconclusive; origin-dependent jump interpretation corrected; six commissioning attempts issued no pulse; BMS/parser/deadline and owner timing defects separated. |
| 2026-10-09 ~09:16 IST | 004,005 | 60-second subscription-only observation passed limited stationary freshness window; not active test channel. |
| 2026-10-09 09:23–09:28 IST | 007,015 | New diagnostics isolated BMS connect timeouts. Automatic recovery restart briefly restored reads; failures returned. LiDAR startup retries later showed service running/device health OK. |
| 2026-10-09 manual Hall→Dhruv return | 001,010,011 | Dedicated bag showed fresh ROS delivery but five large AMCL corrections after remote stop. During motion, 32 encoder-consensus samples were critical, with M3 most often rejected; wheel and IM10A integrated yaw rates disagreed by about 49°. Different odom/map endpoint displacements are not proof of a wheel-scale error. Autonomous route reliability remains unqualified. |
| 2026-10-09 same-bag EKF replay | 001,010,011 | Isolated velocity-only wheel input improved median saved-map scan endpoint fit from 23.1% to 50.2% versus current pose+velocity fusion; prior Oct8 bag had mixed results, so no production EKF change. Diagnostic-only map page now displays AMCL uncertainty and recent pose jumps; all five corrections were flagged offline. |
| 2026-10-09 cross-bag and AMCL A/B | 001,010,011 | Eleven corrected-IMU/wheel/scan bags inventoried. Heading mismatch recurred, with one Oct9 wrong-sign wheel-model interval despite four selected encoders. Fixed a diagnostic analyzer that had mixed raw and corrected IMU streams. Isolated saved-map AMCL A/B did not reproduce five live jumps; velocity-only improved maximum correction but worsened final-window drift (1.789 m versus 0.845 m). No production EKF or motor change; localization remains unresolved. |
| 2026-10-09 no-motion replay-fidelity follow-up | 011 | Original journal and mission-control source showed AMCL no-motion update requests about once per second through the jump window. Full-bag isolated replay with that trigger matched 384 total/80 post-stop AMCL poses and reproduced two large stationary jumps (max 3.470 m), versus five live (max 2.206 m). It explains earlier missing replay updates, not the exact jump sequence; no production change or motion. |
| 2026-10-09 jump scan-window/particle comparison | 011 | Original jumps 1 and 4 moved to poses with worse map-endpoint proximity on all seven preceding scans each; both replay jumps moved to better-fitting poses on every selected scan. Clouds were broad in both. Published uniform weights omit pre-resampling likelihood/cluster state, so the precise live hypothesis-selection cause remains unverified. Read-only analysis only. |
| 2026-10-09 stationary AMCL shadow trace | 011 | Separately built Nav2 AMCL 1.1.20 with pre-resampling particle and cluster diagnostics. A corrected 1 Hz, 10-second stationary capture recorded weighted clouds and selection traces, with one stable cluster; no production AMCL/TF/motor change. A prior helper pacing bug briefly sent excessive shadow no-motion requests and raised load; corrected before accepted capture. Historic five-jump cause remains unverified. |

## Exact Oct8 commissioning sequence (UTC filename timestamps)

| UTC prefix | First observed failure | Pulse requests |
| --- | --- | ---: |
| 20261008T094506Z | fresh_latched_stop_required | 0 |
| 20261008T101458Z | control_policy_stale | 0 |
| 20261008T110222Z | bms_unhealthy | 0 |
| 20261008T114102Z | no_active_session | 0 |
| 20261008T114226Z | bms_telemetry_stale | 0 |
| 20261008T131845Z | motor_controller_link_lost | 0 |

Re-parsed from Jetson JSONL on Oct9; all observed nonzero-output flags false. Maximum client send gap 0.235386 s does not prove owner receipt. See [detailed audit](../LIFTED_TEST_FAILURE_AUDIT_2026-10-08.md).

## All reachable commit index

Scope: all refs after fetch, non-shallow clone, before this report's publication. This is an index, not a claim all diffs were deeply reviewed. New audit commits naturally postdate this index.

| Author timestamp | Commit | Historical subject |
| --- | --- | --- |
| 2026-08-04T10:18:47+05:30 | [63bbbcd](https://github.com/Dhruv0747/ATLAS/commit/63bbbcd49eacd39da543fc233842f0f737f621e4) | Establish ATLAS source baseline |
| 2026-08-04T11:26:13+05:30 | [7f881c5](https://github.com/Dhruv0747/ATLAS/commit/7f881c53f45d5aa8b22e8d105081a5730d222e39) | Document CrowPanel wireless controller plan |
| 2026-08-04T11:26:49+05:30 | [9f1fda7](https://github.com/Dhruv0747/ATLAS/commit/9f1fda7e6c51ace43ac1d125665208356bf1cc55) | Require automatic wireless CrowPanel connection |
| 2026-08-04T11:49:34+05:30 | [8537897](https://github.com/Dhruv0747/ATLAS/commit/85378979792d88c8ba9093ea77ca4c1179595203) | Document navigation foundation audit |
| 2026-08-04T11:55:47+05:30 | [dbf9e99](https://github.com/Dhruv0747/ATLAS/commit/dbf9e9940db4f047d2bce00f889adc8a01ad6f89) | Record lifted wheel encoder calibration |
| 2026-08-04T12:01:47+05:30 | [ab50c8c](https://github.com/Dhruv0747/ATLAS/commit/ab50c8cde0ae2d02ae8e75e3877e6f50bd84f821) | Confirm four motor outputs and encoder fault |
| 2026-08-04T12:11:23+05:30 | [7a84b41](https://github.com/Dhruv0747/ATLAS/commit/7a84b414002cbd018454e1527f31efe731a9bbff) | Confirm encoder fault after cold boot |
| 2026-08-04T12:23:52+05:30 | [8172c00](https://github.com/Dhruv0747/ATLAS/commit/8172c00acd4bfcd8f5155a948e823a86c60cb723) | Verify replacement M2 encoder |
| 2026-08-04T12:31:55+05:30 | [146798d](https://github.com/Dhruv0747/ATLAS/commit/146798da0d75dd4689c6f15f6476a4c26bbab28a) | Confirm all four encoder channels |
| 2026-08-04T13:43:15+05:30 | [b01171b](https://github.com/Dhruv0747/ATLAS/commit/b01171b21795f1c449c4efdcf5414cac842bdb76) | Accept permanent motor encoder installation |
| 2026-08-04T14:14:25+05:30 | [3da892a](https://github.com/Dhruv0747/ATLAS/commit/3da892a1ed761aa5e56c2fff25c5dfb3eb43c6b6) | Save verified motor mapping and encoder calibration |
| 2026-08-04T14:23:48+05:30 | [49f149f](https://github.com/Dhruv0747/ATLAS/commit/49f149f29269cac87617c4bcb87b1a35e25469a7) | Show all four motor encoders on dashboard |
| 2026-08-04T14:29:34+05:30 | [af4110e](https://github.com/Dhruv0747/ATLAS/commit/af4110e3fe04a8f6c83d052709df6eaf90640f7e) | Record ATLAS 125 mm wheel geometry |
| 2026-08-04T14:35:05+05:30 | [ae045fe](https://github.com/Dhruv0747/ATLAS/commit/ae045febd76f01d7f0eec68b1d12c50de652a56f) | Add metric telemetry for all four wheels |
| 2026-08-04T14:37:31+05:30 | [00fd53d](https://github.com/Dhruv0747/ATLAS/commit/00fd53d6d5b157ef25bbce242c46db6cf930f867) | Correct M1 calibration and stabilize wheel RPM verification |
| 2026-08-04T14:46:01+05:30 | [eeb430b](https://github.com/Dhruv0747/ATLAS/commit/eeb430b17685fe99efa62cd127320aa8fa055ece) | Use calibrated wheel encoders for four-wheel-steering odometry |
| 2026-08-04T14:51:55+05:30 | [fe69a47](https://github.com/Dhruv0747/ATLAS/commit/fe69a47c5bd0ec42281496055ded8e6780b57e6f) | Repair automatic SLAM startup and verify Nav2 TF chain |
| 2026-08-04T14:54:51+05:30 | [d3745c6](https://github.com/Dhruv0747/ATLAS/commit/d3745c694f3220bf3acf696ea2e3c58f2071a029) | Add bounded air-lifted Nav2 response verification |
| 2026-08-04T14:57:37+05:30 | [43b21e8](https://github.com/Dhruv0747/ATLAS/commit/43b21e8b48c347e364e8c40a5be6d40e43302006) | Add visible dual-steering air test |
| 2026-08-04T15:30:41+05:30 | [ec661fe](https://github.com/Dhruv0747/ATLAS/commit/ec661fe2a91e88efe65d95285fb76feda28fbe81) | Harden safe autonomous mapping and LiDAR pipeline |
| 2026-08-04T15:37:20+05:30 | [9c62622](https://github.com/Dhruv0747/ATLAS/commit/9c626226dc8c483765d1e163d88520425c970864) | Add speed-aware autonomy braking gate |
| 2026-08-04T15:40:39+05:30 | [9f08a23](https://github.com/Dhruv0747/ATLAS/commit/9f08a2361dd4ece965559f302707d6099f5b58de) | Allow safe frontier endpoint substitution |
| 2026-08-04T17:37:52+05:30 | [60d843b](https://github.com/Dhruv0747/ATLAS/commit/60d843b2702f93f7984010023b07c60790f4532f) | Replace SHT21 with BME680 environmental monitoring |
| 2026-08-04T17:46:00+05:30 | [f47f3e2](https://github.com/Dhruv0747/ATLAS/commit/f47f3e2438a2f95d5572c9e06d9678ad4dddb7f4) | Separate inside and outside environmental displays |
| 2026-08-06T19:33:29+05:30 | [cf189b6](https://github.com/Dhruv0747/ATLAS/commit/cf189b6783a90c936f00ff328e5b9dcc518395fb) | Add complete ATLAS assembly and operation manual |
| 2026-08-06T19:40:08+05:30 | [7515676](https://github.com/Dhruv0747/ATLAS/commit/751567654426e77d4d8bf48e896205cd93677513) | Synchronize current ATLAS commissioning state |
| 2026-08-06T19:40:15+05:30 | [241384c](https://github.com/Dhruv0747/ATLAS/commit/241384cbad2e35289337bb6a7d123feb80803e36) | Merge remote-tracking branch 'origin/main' |
| 2026-08-06T23:42:09+05:30 | [ac15279](https://github.com/Dhruv0747/ATLAS/commit/ac15279064e014d42e2198b9023630e54ae97fa0) | Add live sensor details and reduce dashboard load |
| 2026-08-06T23:50:26+05:30 | [471723b](https://github.com/Dhruv0747/ATLAS/commit/471723bc7931860b45cd8b0689d1469d3d32fcaf) | Restore dashboard display autostart |
| 2026-08-06T23:57:50+05:30 | [c00e2bb](https://github.com/Dhruv0747/ATLAS/commit/c00e2bbed988a2fbc5187e8ea5dcb1f5b117fefb) | Add live touchscreen sensor detail pages |
| 2026-08-07T00:01:52+05:30 | [05a1add](https://github.com/Dhruv0747/ATLAS/commit/05a1adde82caae2f49a48f98bcf7b230dce31302) | Balance touchscreen dashboard CPU and reuse AI detections |
| 2026-08-07T22:26:14+05:30 | [d197c2b](https://github.com/Dhruv0747/ATLAS/commit/d197c2b7fd663e10cc7735222cc5f9a2a3a360b8) | Add native CrowPanel overview camera stream |
| 2026-08-08T21:52:56+05:30 | [9fd8e31](https://github.com/Dhruv0747/ATLAS/commit/9fd8e31c86e1fcdbf8022fd79f4f3690bb169323) | Add safety-gated ATLAS MCP interface (#1) |
| 2026-08-08T21:56:36+05:30 | [d99bf62](https://github.com/Dhruv0747/ATLAS/commit/d99bf621e64a22c0be9028dd9ae37c55b3f4d5fb) | Fix ATLAS MCP gateway port (#2) |
| 2026-08-08T21:58:20+05:30 | [a2790f1](https://github.com/Dhruv0747/ATLAS/commit/a2790f139af28691f9689a533d1904a57f4aaf4f) | Pin compatible ATLAS MCP SDK (#3) |
| 2026-08-08T21:59:59+05:30 | [39c433a](https://github.com/Dhruv0747/ATLAS/commit/39c433a982bb8ef1a1a59a4bf435577716250cec) | Record ATLAS MCP commissioning (#4) |
| 2026-08-08T23:17:29+05:30 | [bd1f474](https://github.com/Dhruv0747/ATLAS/commit/bd1f474642371d953ebadcd799fb58403ab1d407) | Add safety-constrained ATLAS mission agent |
| 2026-08-09T08:05:28+05:30 | [54491b9](https://github.com/Dhruv0747/ATLAS/commit/54491b906bf598b1bc477da00878cd5070c69a72) | Fix tight recovery autostart dependency cycle |
| 2026-08-09T08:25:21+05:30 | [34325b3](https://github.com/Dhruv0747/ATLAS/commit/34325b3320c30a8d54c270eec60b822d331e5f75) | Make exploration stop and map save bounded |
| 2026-08-09T08:29:48+05:30 | [684878b](https://github.com/Dhruv0747/ATLAS/commit/684878b379475da0541725c396f6adca70e7826e) | Correct LiDAR sectors for rear-facing mount |
| 2026-08-09T08:34:24+05:30 | [ec99175](https://github.com/Dhruv0747/ATLAS/commit/ec9917544169b1bf1a37c32fd5d44c84fe7b3538) | Reject aborted return-home agent results |
| 2026-08-09T09:37:59+05:30 | [0524eeb](https://github.com/Dhruv0747/ATLAS/commit/0524eebd21a77ffd8d18b65f6d98f1f161f6ce79) | Fix final return-home convergence |
| 2026-08-09T09:52:46+05:30 | [4403811](https://github.com/Dhruv0747/ATLAS/commit/440381166f4b01bb2f04b245ac144adbd866c71b) | Use car-like Hybrid-A star navigation |
| 2026-08-09T09:56:58+05:30 | [9bf7339](https://github.com/Dhruv0747/ATLAS/commit/9bf7339e83ec4776a513271c8869bf12fc8120cf) | Smooth Xbox remote command repeat |
| 2026-08-09T10:03:14+05:30 | [6e5a2b4](https://github.com/Dhruv0747/ATLAS/commit/6e5a2b487f230e5939484a915037d9af324d0bab) | Restore proven Xbox remote timing |
| 2026-08-10T10:01:10+05:30 | [a20c1b0](https://github.com/Dhruv0747/ATLAS/commit/a20c1b0133acc3c2ef613f8a0b923645d795b646) | Document Project ATLAS authorship and discovery metadata |
| 2026-08-10T10:04:50+05:30 | [1f15409](https://github.com/Dhruv0747/ATLAS/commit/1f15409041fc8c0a317e5cfed0533d2017cf4ea6) | Document Project ATLAS authorship and discovery metadata (#6) |
| 2026-08-10T11:01:17+05:30 | [1aae529](https://github.com/Dhruv0747/ATLAS/commit/1aae52912a75f89d28ae7985040f6496ad215831) | Document offline ATLAS agent team plan |
| 2026-08-10T11:01:17+05:30 | [ebb10dd](https://github.com/Dhruv0747/ATLAS/commit/ebb10ddf3defa2e8a5eb245f4098412e4036aa71) | Document offline ATLAS agent team plan |
| 2026-08-11T16:15:03+05:30 | [e5a2495](https://github.com/Dhruv0747/ATLAS/commit/e5a24958c06a8047370fcde051b6e8c6237fb278) | Fix mapping footprint lethal-start failures |
| 2026-08-11T20:04:36+05:30 | [e2388fe](https://github.com/Dhruv0747/ATLAS/commit/e2388fe5f022cd18a8e90fc9cadecddc1dc557a2) | Add camera radar LiDAR autonomy fusion |
| 2026-08-18T16:53:43+05:30 | [9747f31](https://github.com/Dhruv0747/ATLAS/commit/9747f31724f2cce94b6f197178a6067e4cd6a39e) | complete ATLAS autonomy and carrier integration |
| 2026-08-19T21:29:22+05:30 | [2c63e7d](https://github.com/Dhruv0747/ATLAS/commit/2c63e7dd3dd68e962f6a896a3ccf1968e4409848) | add secure ATLAS WebRTC intercom |
| 2026-08-19T21:48:54+05:30 | [0284617](https://github.com/Dhruv0747/ATLAS/commit/0284617867b08cbd50d7322167f205b2a873c857) | add persistent Tailscale intercom recovery |
| 2026-08-19T21:52:14+05:30 | [c9f5a8e](https://github.com/Dhruv0747/ATLAS/commit/c9f5a8ec90bbc36db6dd64cb5c546da6248f367b) | reduce intercom feedback and dashboard CPU overlap |
| 2026-08-19T22:51:17+05:30 | [473f8e4](https://github.com/Dhruv0747/ATLAS/commit/473f8e4d9d69deb15c88ddeba63bf080bd8f9462) | Permanently harden ATLAS mapping and return-home |
| 2026-08-19T22:54:30+05:30 | [b2d7945](https://github.com/Dhruv0747/ATLAS/commit/b2d794545466cbab9b969b28a0d3efc09459b23c) | Merge remote-tracking branch 'origin/main' into agent/fix-mapping-footprint |
| 2026-08-24T08:13:19+05:30 | [5c9064c](https://github.com/Dhruv0747/ATLAS/commit/5c9064cd67358f0dd25c094a27fef96f8449eb70) | Align ATLAS planner controller and encoder calibration |
| 2026-08-24T08:56:41+05:30 | [8879bb5](https://github.com/Dhruv0747/ATLAS/commit/8879bb5355231d0129c7996480f1d639349113ae) | Calibrate steering centers and harden remote recovery |
| 2026-08-24T09:24:05+05:30 | [f9faeb6](https://github.com/Dhruv0747/ATLAS/commit/f9faeb6bf0061987d944450d735e9316adb89153) | Apply commissioned asymmetric steering limits |
| 2026-08-24T10:05:31+05:30 | [21c6a8f](https://github.com/Dhruv0747/ATLAS/commit/21c6a8f8312aefd57995b896c8150b53d6d8773e) | Harden remote arbitration and add bounded motion diagnostics |
| 2026-08-24T10:40:45+05:30 | [4892f81](https://github.com/Dhruv0747/ATLAS/commit/4892f81c055df377d7c4dc81041a1ef92e60cb20) | Add repeatable motor encoder stress diagnostic |
| 2026-08-24T13:24:15+05:30 | [738512c](https://github.com/Dhruv0747/ATLAS/commit/738512c71179160651fa15fc08f3b44ef6f1c9a5) | Add Foxglove rear clearance and camera controls |
| 2026-08-24T13:24:45+05:30 | [bbaec1b](https://github.com/Dhruv0747/ATLAS/commit/bbaec1b368fafff7aaf9db16048ed103e6bec59f) | Archive ATLAS Foxglove drive panel source |
| 2026-08-24T13:28:53+05:30 | [7f2c293](https://github.com/Dhruv0747/ATLAS/commit/7f2c2937b01ab457723040f73f3636c807f63e99) | Keep rear view and camera controls prominent in Foxglove |
| 2026-08-24T13:56:19+05:30 | [358636e](https://github.com/Dhruv0747/ATLAS/commit/358636e0b2d4e05e6357c675a57388c7223f6486) | Fix autonomous tight-space recovery command path |
| 2026-08-24T14:41:41+05:30 | [a4785c2](https://github.com/Dhruv0747/ATLAS/commit/a4785c22aa904203279388f4908a4b0cdfbe093b) | Add safe manual mapping teaching sessions |
| 2026-08-24T18:12:07+05:30 | [1938122](https://github.com/Dhruv0747/ATLAS/commit/193812272b296d1cc3567bf311a47d995a7cf024) | Correct navigation heading fusion from route evidence |
| 2026-08-24T18:34:58+05:30 | [4b84b2b](https://github.com/Dhruv0747/ATLAS/commit/4b84b2b9f697102b1541c078cb16480ea8ca4878) | Commission final house map and room localization |
| 2026-08-24T18:51:04+05:30 | [0e76af6](https://github.com/Dhruv0747/ATLAS/commit/0e76af6b41d82dbb5016adeaf462de96fc401133) | Feed validated recovery experience into mission decisions |
| 2026-08-24T18:53:34+05:30 | [f453438](https://github.com/Dhruv0747/ATLAS/commit/f4534385f820bd6012853b28e95734c01f41777d) | Record every terminal autonomous mission outcome |
| 2026-08-24T19:06:50+05:30 | [c066b1a](https://github.com/Dhruv0747/ATLAS/commit/c066b1af3f30dcda83f79bb949d1d9a9bb4f9382) | Correct Hall waypoint from manual teaching route |
| 2026-08-24T19:21:56+05:30 | [6c62d53](https://github.com/Dhruv0747/ATLAS/commit/6c62d53f8dd63fa36a9ed706d953325171bea06f) | Diagnose AMCL jumps and start single-variable beam trial |
| 2026-08-24T19:26:59+05:30 | [e6b2a47](https://github.com/Dhruv0747/ATLAS/commit/e6b2a47dc17772cedaf4c4f6ab98370bfc9537fb) | Reject unstable 120-beam AMCL trial |
| 2026-08-24T19:33:09+05:30 | [50c7bd1](https://github.com/Dhruv0747/ATLAS/commit/50c7bd12a8e631dde2e5d916f11c4a0dc1408b42) | Reduce stationary AMCL drift with beam skipping |
| 2026-08-24T19:38:13+05:30 | [ca8b601](https://github.com/Dhruv0747/ATLAS/commit/ca8b6019dd4ef8072e88bc8f5c77c816ff3f6d21) | Reject beam skipping after failed movement closure |
| 2026-08-24T19:56:48+05:30 | [79eb523](https://github.com/Dhruv0747/ATLAS/commit/79eb523a0832322ac06a125879a0175316e74a08) | Correct four-wheel-steering odometry yaw sign |
| 2026-08-24T20:28:17+05:30 | [6a18b0e](https://github.com/Dhruv0747/ATLAS/commit/6a18b0e43418bad87037678c592a71b9c029b898) | Document tight recovery localization failure |
| 2026-08-24T20:32:26+05:30 | [a7027d5](https://github.com/Dhruv0747/ATLAS/commit/a7027d58af65984e96dea453a5ec4c104895f8a9) | Archive ATLAS map validation artifacts |
| 2026-08-24T21:18:06+05:30 | [ad35f77](https://github.com/Dhruv0747/ATLAS/commit/ad35f771151e46b6bf8c5caa168d89da2e6d45f4) | Add read-only ATLAS Visual Cloud foundation |
| 2026-08-24T21:22:59+05:30 | [aaa8a68](https://github.com/Dhruv0747/ATLAS/commit/aaa8a680417e5eecb22bc3805a2b07afe5f2b7f7) | Add local Visual Cloud preview service |
| 2026-08-24T21:25:49+05:30 | [a8c3fdf](https://github.com/Dhruv0747/ATLAS/commit/a8c3fdfd0766e0ddbf313cc7d4fcfd761461487c) | Link Visual Cloud from ATLAS dashboard |
| 2026-08-24T21:39:10+05:30 | [2a76de0](https://github.com/Dhruv0747/ATLAS/commit/2a76de085ac3aa1175d07a7e0f6edc2c33337916) | Allow intentional ultrasonic disable with LiDAR primary |
| 2026-08-24T21:39:53+05:30 | [ab82ac2](https://github.com/Dhruv0747/ATLAS/commit/ab82ac2da421e8b6f5decc2f92b96b26d2a52f4e) | Show intentionally disabled ultrasonic status |
| 2026-08-25T08:51:00+05:30 | [b1b7a37](https://github.com/Dhruv0747/ATLAS/commit/b1b7a37f30d46c3c0d05ca42b01ad97920194988) | Gate autonomy on AMCL confidence |
| 2026-08-25T09:35:57+05:30 | [f91d95b](https://github.com/Dhruv0747/ATLAS/commit/f91d95b2aa1df8629098969f8545fd3ad75e9462) | Teach ATLAS the room-to-hall corridor |
| 2026-08-25T09:52:38+05:30 | [726218e](https://github.com/Dhruv0747/ATLAS/commit/726218ef1b5129edaf1488059ffc9a32147f621a) | Match Nav2 curvature in steering driver |
| 2026-08-25T09:58:36+05:30 | [e45b7a3](https://github.com/Dhruv0747/ATLAS/commit/e45b7a30130609c967bbedab634e0f2795474d36) | Block named navigation on sensor faults |
| 2026-08-25T10:14:39+05:30 | [f079a6d](https://github.com/Dhruv0747/ATLAS/commit/f079a6dc6932d2a9008b23396e4aa4a0aeb27b1f) | Add sensor-guarded reverse arc recovery |
| 2026-08-25T10:28:50+05:30 | [cec0d0b](https://github.com/Dhruv0747/ATLAS/commit/cec0d0bfd16f4da7cd22e3299b432261cd47e496) | Use raw odometry for bounded recovery |
| 2026-08-25T11:00:43+05:30 | [8e5cdf7](https://github.com/Dhruv0747/ATLAS/commit/8e5cdf76b587145f969a09593a351683b87f4d2c) | Rearm recovery after manual reposition |
| 2026-08-25T13:14:43+05:30 | [a3ca113](https://github.com/Dhruv0747/ATLAS/commit/a3ca1138b34daa7bc76d264a931e5ff7ba146fdb) | Sanitize rover footprint in saved maps |
| 2026-08-25T13:43:12+05:30 | [75905d9](https://github.com/Dhruv0747/ATLAS/commit/75905d9d155390dcc4b1d85193c64f5774669482) | Gate autonomy on stable localization |
| 2026-08-25T14:31:13+05:30 | [137283d](https://github.com/Dhruv0747/ATLAS/commit/137283ddfb39be0946f83a85a02294ed299974ca) | Gate reliability campaign on costmap |
| 2026-08-25T15:00:38+05:30 | [c3efbce](https://github.com/Dhruv0747/ATLAS/commit/c3efbce78c58bbada193bfaa2251540c50b48ad4) | Preserve autonomous side clearance |
| 2026-08-25T15:02:23+05:30 | [494574c](https://github.com/Dhruv0747/ATLAS/commit/494574c743578d327c57140d71d7051f6caceba4) | Promote guarded fresh occupancy map |
| 2026-08-25T15:19:56+05:30 | [a6f2a5b](https://github.com/Dhruv0747/ATLAS/commit/a6f2a5b104661fb64bac18d70fbbf19864638bb8) | Stop Nav2 on localization collapse |
| 2026-08-25T15:30:39+05:30 | [6623332](https://github.com/Dhruv0747/ATLAS/commit/6623332a8179038ffacca4a6b7be8603badd14b7) | Preserve odometry across USB reconnects |
| 2026-08-25T15:59:23+05:30 | [21cb718](https://github.com/Dhruv0747/ATLAS/commit/21cb718e9469d212f3344076811ab0b60afe46d5) | Accept AMCL motion between localization updates |
| 2026-08-25T21:45:30+05:30 | [055ce11](https://github.com/Dhruv0747/ATLAS/commit/055ce111325e5f6ff02c00c8084ed3b7c088a28f) | Add rear ultrasonic safety integration |
| 2026-08-26T13:06:14+05:30 | [80f629e](https://github.com/Dhruv0747/ATLAS/commit/80f629ec0d4549efee1c5137b64d3e56c8b6e8b7) | Validate rear ultrasonic reverse guard |
| 2026-08-26T14:47:04+05:30 | [926735e](https://github.com/Dhruv0747/ATLAS/commit/926735ed2f2bcdc0980bb26ddd63502dfec80540) | Preserve mapped places and add Foxglove ultrasonic data |
| 2026-08-26T14:47:23+05:30 | [692944b](https://github.com/Dhruv0747/ATLAS/commit/692944b03461c3291b5347e1e3be3741dcb10580) | Record fresh Hall and Dhruv Room map |
| 2026-08-26T15:36:35+05:30 | [f84f5d8](https://github.com/Dhruv0747/ATLAS/commit/f84f5d87a6daa644b60d85d0f34eaa34fa74fbf9) | Stabilize ROS discovery and AMCL heartbeat |
| 2026-09-01T13:45:56+05:30 | [205fb2d](https://github.com/Dhruv0747/ATLAS/commit/205fb2d95c319e61672c2b4a165c0dc599719b17) | Make Mega 2560 the authoritative sensor hub |
| 2026-09-01T14:23:35+05:30 | [fa3837e](https://github.com/Dhruv0747/ATLAS/commit/fa3837e626c4025364cc2ff1f2100dc567eb83fa) | Fix Mega sensor hub autostart ordering |
| 2026-09-01T14:33:33+05:30 | [5e7a908](https://github.com/Dhruv0747/ATLAS/commit/5e7a9081d6569eeebec5d4c4714a721c76df4d3c) | Fix radar and AMG8833 dashboard telemetry |
| 2026-09-01T21:13:51+05:30 | [8843725](https://github.com/Dhruv0747/ATLAS/commit/8843725683e299866a96531ed184bc556b0729a3) | Route camera PCA9685 control through Mega sensor hub |
| 2026-09-01T21:41:39+05:30 | [56a44ef](https://github.com/Dhruv0747/ATLAS/commit/56a44efc10b4f42698760e3d96ac41f4be897ae8) | Recover Mega I2C bus without reboot |
| 2026-09-01T21:47:55+05:30 | [1a75ee5](https://github.com/Dhruv0747/ATLAS/commit/1a75ee585627b58ff37c0752690bc30cae99c297) | Prevent Mega serial resets from dropping I2C |
| 2026-09-01T21:55:55+05:30 | [fb5a1ec](https://github.com/Dhruv0747/ATLAS/commit/fb5a1ec7cbe716284d45062452412c72aa2b62a1) | Keep web camera control working during ROS discovery faults |
| 2026-09-01T22:02:04+05:30 | [1159fe3](https://github.com/Dhruv0747/ATLAS/commit/1159fe38eeaa0ebcb14d68c1a21f299bbc38b678) | Stop watchdog from resetting Mega sensor hub |
| 2026-09-01T22:08:02+05:30 | [bcfe285](https://github.com/Dhruv0747/ATLAS/commit/bcfe2857d7b771c154b19a47a70bfb6d167867dd) | Release camera servos during Mega startup |
| 2026-09-02T13:37:40+05:30 | [42bec52](https://github.com/Dhruv0747/ATLAS/commit/42bec52440a9a845d9441ea7e683774391c81dda) | Add isolated UNO R4 sensor hub |
| 2026-09-02T14:31:30+05:30 | [35c121b](https://github.com/Dhruv0747/ATLAS/commit/35c121bfc0a2617aed151171fe3648c278fbbf22) | Deploy UNO R4 sensor hub on Jetson |
| 2026-09-02T14:49:07+05:30 | [c2efb6e](https://github.com/Dhruv0747/ATLAS/commit/c2efb6ebe7d776b139b7884cb3bba7d4e2bb085f) | Fix live I2C sensor status dashboard |
| 2026-09-02T14:52:00+05:30 | [b2a515e](https://github.com/Dhruv0747/ATLAS/commit/b2a515eac6b09b6705a18560d55f9468e361c603) | Recover stalled UNO sensor telemetry automatically |
| 2026-09-02T15:13:13+05:30 | [24d2d77](https://github.com/Dhruv0747/ATLAS/commit/24d2d77dcf1bf7eb16d8e67a95342abd369b89ae) | Expose invalid RD-03D radar frames |
| 2026-09-02T15:41:11+05:30 | [68f8af0](https://github.com/Dhruv0747/ATLAS/commit/68f8af0dc688adbc0c1ba97714832bfdf065f134) | Stabilize reboot sensor telemetry |
| 2026-09-02T16:35:21+05:30 | [5d60a3b](https://github.com/Dhruv0747/ATLAS/commit/5d60a3b5bdcad836b0197a5e2966aa998f9dcdb1) | Isolate UNO I2C recovery from offline IMU |
| 2026-09-02T17:07:10+05:30 | [560c79e](https://github.com/Dhruv0747/ATLAS/commit/560c79e52350b98d3283573055811c83978aa5d4) | Harden UNO sensor hub and diagnose radar UART |
| 2026-09-02T17:37:21+05:30 | [a24368b](https://github.com/Dhruv0747/ATLAS/commit/a24368bbdc51bb03ffeeff2d9635004a0619eeae) | Isolate radar initialization from sensor startup |
| 2026-09-03T09:47:53+05:30 | [c508fed](https://github.com/Dhruv0747/ATLAS/commit/c508fed157be2f8ec44d90517f0e6d70f89a4a9d) | Stabilize UNO R4 native USB sensor telemetry |
| 2026-09-03T09:59:37+05:30 | [52da7c8](https://github.com/Dhruv0747/ATLAS/commit/52da7c89dd7257e5cd86c65d55d8f05008e26a8c) | Fix UNO R4 sensor hub boot ordering |
| 2026-09-03T10:03:51+05:30 | [28b0583](https://github.com/Dhruv0747/ATLAS/commit/28b05837266ca0e245a2e3272f3a002b560d4431) | Record commissioned RD-03D radar stream |
| 2026-09-03T10:49:41+05:30 | [8996950](https://github.com/Dhruv0747/ATLAS/commit/8996950be9cc3aab21f498433a859f320f5bb564) | Calibrate Yahboom backup IMU safely |
| 2026-09-03T11:12:27+05:30 | [c3544a1](https://github.com/Dhruv0747/ATLAS/commit/c3544a1d106179ea98d961eb04fb6fa875ca673b) | Make Yahboom the primary ATLAS IMU |
| 2026-09-03T11:30:19+05:30 | [e783592](https://github.com/Dhruv0747/ATLAS/commit/e7835928edcd4bd8b65fd7fad211486b122cf0b2) | Force clean UNO native USB builds |
| 2026-09-03T11:31:48+05:30 | [3976c82](https://github.com/Dhruv0747/ATLAS/commit/3976c82f237ca7a1d96e9a081598a1cb97078a5b) | Remove retired BNO label from IMU dashboard |
| 2026-09-03T11:54:41+05:30 | [cb6217f](https://github.com/Dhruv0747/ATLAS/commit/cb6217f5416d13414cb9bc1da47463cbdd7a57ee) | Retire the Mega 2560 sensor hub |
| 2026-09-03T12:31:15+05:30 | [3009794](https://github.com/Dhruv0747/ATLAS/commit/300979419a557b7d8d1dbb57113e6c4da09e5b71) | Keep sensor dashboard live across restarts |
| 2026-09-03T12:40:58+05:30 | [0f5625b](https://github.com/Dhruv0747/ATLAS/commit/0f5625b4ecb307cd25e4fd8045358fda8ce32cec) | Explain and recover ATLAS voice USB state |
| 2026-09-03T13:27:18+05:30 | [22dbcb6](https://github.com/Dhruv0747/ATLAS/commit/22dbcb613b37340207d055f16e2bf2913eea5b79) | Diagnose L76K UART failures explicitly |
| 2026-09-03T13:44:25+05:30 | [157523d](https://github.com/Dhruv0747/ATLAS/commit/157523d040df61a8e64ff753b62b1d2d041b033d) | Move L76K GNSS to Jetson UART |
| 2026-09-03T14:29:05+05:30 | [347b2b1](https://github.com/Dhruv0747/ATLAS/commit/347b2b129916ffe4014f09749b8354886b52c14e) | Fix deterministic dashboard camera control |
| 2026-09-03T15:00:45+05:30 | [87eeb3e](https://github.com/Dhruv0747/ATLAS/commit/87eeb3e1140360f5daa01ce53f1b0b1a54219d03) | Speed up dashboard camera response |
| 2026-09-03T15:04:40+05:30 | [f6c2dfd](https://github.com/Dhruv0747/ATLAS/commit/f6c2dfd6c947e2c26cf76d5c9246831b7923b055) | Use fast dashboard camera profile |
| 2026-09-03T15:08:51+05:30 | [385b850](https://github.com/Dhruv0747/ATLAS/commit/385b85032ea45c7ded0bf914b0a789ba91001fb5) | Remove dashboard camera stream buffering |
| 2026-09-03T17:18:13+05:30 | [31e6e5d](https://github.com/Dhruv0747/ATLAS/commit/31e6e5d8937f69b562268e083b9236079a1cdc20) | Set commissioned camera boot home |
| 2026-09-03T17:27:13+05:30 | [be25b57](https://github.com/Dhruv0747/ATLAS/commit/be25b57830b3d411e89a956e92200b9a983cc74a) | Fix Yahboom telemetry USB identity |
| 2026-09-09T21:33:06+05:30 | [b27e42f](https://github.com/Dhruv0747/ATLAS/commit/b27e42fae916cef5677b519d543f10bb7f26dfed) | Save confirmed steering centers and correct physical axle channels |
| 2026-09-09T21:41:39+05:30 | [a50a632](https://github.com/Dhruv0747/ATLAS/commit/a50a6326b1809e21582c0f19c024ffdace9a07df) | Save user-approved front right steering operating limit |
| 2026-09-09T21:44:41+05:30 | [be4c7ce](https://github.com/Dhruv0747/ATLAS/commit/be4c7ce59f7fd31f02d868422d78fd8e2761f3e3) | Save user-approved front left steering operating limit |
| 2026-09-09T21:48:41+05:30 | [3d54b5b](https://github.com/Dhruv0747/ATLAS/commit/3d54b5bd4d961fd4f08d1b4d25254feab1873afe) | Save user-approved rear right steering operating limit |
| 2026-09-09T21:51:34+05:30 | [2d9bfed](https://github.com/Dhruv0747/ATLAS/commit/2d9bfed9b443f726643d15e92ffbd6955408b76d) | Save user-approved rear left steering operating limit |
| 2026-09-09T23:38:56+05:30 | [afd035c](https://github.com/Dhruv0747/ATLAS/commit/afd035c32ecc03ccaf3080b53a650f2db1154c3e) | Improve dashboard glass UI and boot diagnostics |
| 2026-09-10T08:55:32+05:30 | [7213e1c](https://github.com/Dhruv0747/ATLAS/commit/7213e1c15e0442a125a3ac3439360a48c1f2f187) | Increase remote light drive power |
| 2026-09-10T08:59:47+05:30 | [4310162](https://github.com/Dhruv0747/ATLAS/commit/431016284bd2a23cf15a2df98bb6d0609cd0722c) | Keep remote traction during steering slew |
| 2026-09-10T09:02:59+05:30 | [8d1567f](https://github.com/Dhruv0747/ATLAS/commit/8d1567fe07a1267eba9601d2ff35dea2b5530e8c) | Hold remote steering until traction release |
| 2026-09-10T09:06:38+05:30 | [3e324b5](https://github.com/Dhruv0747/ATLAS/commit/3e324b505b3a62ebdc266b2f9962e61e2805590f) | Debounce remote steering recenter |
| 2026-09-10T09:12:24+05:30 | [3c40862](https://github.com/Dhruv0747/ATLAS/commit/3c408625225bac555365fb21a8944eee3658ebb1) | Latch remote steering ownership |
| 2026-09-10T09:18:30+05:30 | [90a0751](https://github.com/Dhruv0747/ATLAS/commit/90a0751e1a4c50f66a523a6d9660e339ef12257c) | Latch manual steering in command mux |
| 2026-09-10T09:45:36+05:30 | [8faf635](https://github.com/Dhruv0747/ATLAS/commit/8faf6359e34229345aaed62bf9ae6921e75a4d5a) | Restore remote ROS command chain |
| 2026-09-10T12:30:11+05:30 | [aac3db8](https://github.com/Dhruv0747/ATLAS/commit/aac3db8074bdb30b15c1ff96b26dddff730f91df) | Prevent ROS graph split after service restart |
| 2026-09-10T12:44:31+05:30 | [2ad6c69](https://github.com/Dhruv0747/ATLAS/commit/2ad6c69a8be5fd78a72d1066b87363944118adb9) | Add encoder fault containment and autonomous stop guard |
| 2026-09-10T12:46:18+05:30 | [4bf6137](https://github.com/Dhruv0747/ATLAS/commit/4bf61375eaeeff1e84fa703504c86fe0fc099070) | Limit encoder link recovery to one stationary restart |
| 2026-09-10T13:44:04+05:30 | [cb86dc1](https://github.com/Dhruv0747/ATLAS/commit/cb86dc1b014055deecdb48d397bd631a008d1c4d) | Remove retired hardware integrations |
| 2026-09-10T14:30:44+05:30 | [6ddca45](https://github.com/Dhruv0747/ATLAS/commit/6ddca45cb47b049f9f20124d3d0b917ad9c08a35) | Document encoder safety validation |
| 2026-09-10T15:51:54+05:30 | [9cccda3](https://github.com/Dhruv0747/ATLAS/commit/9cccda3ac1f0acd3126618c07be9825bf174220b) | Validate single encoder degraded mode |
| 2026-09-10T16:05:52+05:30 | [a5f3d45](https://github.com/Dhruv0747/ATLAS/commit/a5f3d45769ef7d597045566f46dfb78d15699730) | Tune autonomous low-speed motor floor |
| 2026-09-10T16:42:22+05:30 | [8dbba15](https://github.com/Dhruv0747/ATLAS/commit/8dbba151787dcd48a9dca07244b5be25f261a9fb) | Gate mapping home on fresh SLAM localization |
| 2026-09-10T19:06:26+05:30 | [eb7cdf1](https://github.com/Dhruv0747/ATLAS/commit/eb7cdf1dbae8c64a36a89ee45884d74c024212fb) | Fix remote steering latch and sustained motor load |
| 2026-09-10T19:13:40+05:30 | [0b3b236](https://github.com/Dhruv0747/ATLAS/commit/0b3b2367739a6e8bd20a20c1b3a3bb654325ecb8) | Add explicit momentary remote boost power |
| 2026-09-16T16:20:54+05:30 | [d81c39a](https://github.com/Dhruv0747/ATLAS/commit/d81c39af830e313b6efa6e989947096c54753a78) | Integrate Hiwonder sensor monitoring and synchronize dashboard diagnostics |
| 2026-09-16T16:40:26+05:30 | [f4a2e74](https://github.com/Dhruv0747/ATLAS/commit/f4a2e749575411136d8f038971ebe040c86fef35) | Correct remaining IM10A dashboard source labels |
| 2026-09-17T20:36:43+05:30 | [fda24a7](https://github.com/Dhruv0747/ATLAS/commit/fda24a7f79719afdde398520ad1b3c2170665e90) | Save ATLAS commissioning updates and support M1-M3 encoder selection |
| 2026-09-18T07:19:45+05:30 | [c138ec7](https://github.com/Dhruv0747/ATLAS/commit/c138ec7a451ddc6ce36dcf53adce5d596ca95a36) | Add gated local companion and verified diagnostic repairs |
| 2026-09-19T13:55:10+05:30 | [6d8f5c0](https://github.com/Dhruv0747/ATLAS/commit/6d8f5c0e2721c2b225d84a2174b558e2e221293a) | Enable front ultrasonic reconnect persistence and save 90-degree steering neutral |
| 2026-09-20T08:35:55+05:30 | [1b6004c](https://github.com/Dhruv0747/ATLAS/commit/1b6004ccbab7bfe72631f052865ece34c38cf57a) | Add observation-only web commissioning console and diagnostic history |
| 2026-09-20T09:33:58+05:30 | [8e4a2a1](https://github.com/Dhruv0747/ATLAS/commit/8e4a2a11b395bf9d207e7b0336181f05cd0bf9fc) | Add steering commissioning, camera home controls and USB role discovery |
| 2026-09-20T09:50:37+05:30 | [212e4dd](https://github.com/Dhruv0747/ATLAS/commit/212e4dd6824ae060c5ffebeca1fc945b04918cfb) | Add Phase 2 commissioning evidence ledger and next-gate workflow |
| 2026-09-20T10:39:39+05:30 | [d3f2d87](https://github.com/Dhruv0747/ATLAS/commit/d3f2d87ab915b8ee5ba91d2490142adfe17913c8) | Add read-only capability audit and ordered fallback work plan |
| 2026-09-20T10:55:49+05:30 | [16ff10c](https://github.com/Dhruv0747/ATLAS/commit/16ff10ce6843ea3fe4e30676a0ea488a33fb821a) | Stage atomic ultrasonic validity and fail-closed directional guard |
| 2026-09-20T11:06:45+05:30 | [23670da](https://github.com/Dhruv0747/ATLAS/commit/23670daa82336b562333e814fd2ff914ee48cf1a) | Record blocked UNO upload and unresolved USB recovery |
| 2026-09-20T11:32:59+05:30 | [e207f87](https://github.com/Dhruv0747/ATLAS/commit/e207f8764c14fa959112ba9ecde3548a33cb42a5) | Record UNO deployment and stage partial-line validity correction |
| 2026-09-20T11:43:54+05:30 | [3127f7d](https://github.com/Dhruv0747/ATLAS/commit/3127f7dc16c330ee6ce8242b91c381674250e6ff) | Bound sensor serial draining and record stationary deployment checks |
| 2026-09-20T11:51:08+05:30 | [89e9264](https://github.com/Dhruv0747/ATLAS/commit/89e926429237803f814a74b67dc7d839fc5273ba) | Record ultrasonic expiry check and front target distance mismatch |
| 2026-09-20T12:10:34+05:30 | [f284213](https://github.com/Dhruv0747/ATLAS/commit/f284213ab08565a39e1abb306dafdb5d14d6fc6c) | Record ultrasonic and LiDAR stationary validation |
| 2026-09-20T12:29:36+05:30 | [b772abf](https://github.com/Dhruv0747/ATLAS/commit/b772abf4e15bd319876d0142ba8a9cf6f5cc1dab) | Qualify front ultrasonic close range |
| 2026-09-20T12:34:35+05:30 | [d0442cf](https://github.com/Dhruv0747/ATLAS/commit/d0442cf8676e9d98decc3d29e3f838db031a535a) | Qualify rear ultrasonic close range |
| 2026-09-20T12:42:16+05:30 | [70fad5f](https://github.com/Dhruv0747/ATLAS/commit/70fad5fc5b31bbe60b847055d276b36ef0a40bf2) | Record ultrasonic physical recovery test |
| 2026-09-20T12:45:13+05:30 | [5ae1fb5](https://github.com/Dhruv0747/ATLAS/commit/5ae1fb5bcc1e53332cbf7e9c1055e4d27c93e1a5) | Validate ultrasonic recovery and veto logic |
| 2026-09-20T20:02:40+05:30 | [4f74c4b](https://github.com/Dhruv0747/ATLAS/commit/4f74c4ba1bec913db0c4f80114ce26b857d7bb80) | Commission IM10A yaw fusion and steering geometry |
| 2026-09-21T10:00:16+05:30 | [d77195b](https://github.com/Dhruv0747/ATLAS/commit/d77195b55d7bc5affc0e2a2f872b2e8ba663db40) | fix(sensor-hub): prevent I2C brownout on reconnect |
| 2026-09-21T12:41:43+05:30 | [48d3844](https://github.com/Dhruv0747/ATLAS/commit/48d38442bcd766e1a9d9602cedd766845b23dc1e) | fix(dashboard): keep radar live with zero targets |
| 2026-09-23T09:15:33+05:30 | [d042c7d](https://github.com/Dhruv0747/ATLAS/commit/d042c7d976e6c634ec58e6f8647066a23d2ac92e) | feat(control): add gated four-wheel PID framework |
| 2026-09-25T00:44:17+05:30 | [6a6dcef](https://github.com/Dhruv0747/ATLAS/commit/6a6dcef6bfb28bc62ce6413620b36e59a52c81e7) | fix(diagnostics): clarify live sensor and encoder state |
| 2026-09-25T07:54:41+05:30 | [cb1af9e](https://github.com/Dhruv0747/ATLAS/commit/cb1af9e668ad1ed14de13ccf652401cc44addd96) | feat(dashboard): consolidate drive and Jetson reports |
| 2026-09-25T08:21:23+05:30 | [b1b333f](https://github.com/Dhruv0747/ATLAS/commit/b1b333fbbbe8dec563d1960be2a8b3991720f140) | fix(dashboard): restore live telemetry API |
| 2026-09-25T12:34:14+05:30 | [5f3e309](https://github.com/Dhruv0747/ATLAS/commit/5f3e3091711f08f92b76e6edae089b4bbf2ecf00) | fix(control): preserve steering and fail closed on IMU drift |
| 2026-09-25T13:10:33+05:30 | [b2f7668](https://github.com/Dhruv0747/ATLAS/commit/b2f7668cfdb3db62ec9524e2fa844a47ae9e302f) | fix(odometry): select measured encoder channels |
| 2026-09-25T13:19:27+05:30 | [feab837](https://github.com/Dhruv0747/ATLAS/commit/feab837dec9024e7a7d6adc640cbedf8446f0eac) | feat(diagnostics): analyze measured ground runs |
| 2026-09-25T13:30:37+05:30 | [0950b00](https://github.com/Dhruv0747/ATLAS/commit/0950b00f95b2838aa79824da7c9685c18e3f687c) | feat(diagnostics): separate manual motion segments |
| 2026-09-25T13:52:10+05:30 | [338242b](https://github.com/Dhruv0747/ATLAS/commit/338242b09173d0b6dee42873366ba659e172b98c) | fix(odometry): use dynamic encoder consensus |
| 2026-09-25T14:43:35+05:30 | [7dcc784](https://github.com/Dhruv0747/ATLAS/commit/7dcc7845c05f0485d9763e3bc43710e033edb9fb) | Add gated LiDAR odometry fusion candidate |
| 2026-09-25T15:15:17+05:30 | [7d0f7b2](https://github.com/Dhruv0747/ATLAS/commit/7d0f7b20059c6c4d9977421d04cd6a0aa2521f81) | Fuse LiDAR as signed body speed |
| 2026-09-25T21:09:58+05:30 | [3a19eac](https://github.com/Dhruv0747/ATLAS/commit/3a19eac6b27b775da66e134cdb1f814f9a3a2298) | Fail closed on commissioning feedback faults |
| 2026-09-25T22:02:45+05:30 | [b7a1878](https://github.com/Dhruv0747/ATLAS/commit/b7a18781abe54818e8f360feb1600b0b9d1cd5bc) | Improve bidirectional distance commissioning |
| 2026-09-25T22:12:36+05:30 | [4cc2ef5](https://github.com/Dhruv0747/ATLAS/commit/4cc2ef5b4ca8913983148650a015937d7fa140e4) | Add fail-closed bounded arc commissioning |
| 2026-09-25T22:25:51+05:30 | [1052fd5](https://github.com/Dhruv0747/ATLAS/commit/1052fd5d80df682daf1e3fe4234c75eb4fb74a21) | Normalize encoder consensus for steering geometry |
| 2026-09-25T22:34:38+05:30 | [0ba88b0](https://github.com/Dhruv0747/ATLAS/commit/0ba88b03692a9bfb493dd0d02be160fc8e45211d) | Record bounded turn diagnostics |
| 2026-09-25T22:51:31+05:30 | [577aac9](https://github.com/Dhruv0747/ATLAS/commit/577aac9f0417998248ee9ecaf3190737606bad71) | Activate validated three-encoder navigation feedback |
| 2026-09-30T21:20:25+05:30 | [4919f74](https://github.com/Dhruv0747/ATLAS/commit/4919f749e2164b813e4535bc07ad19c55c9f022c) | Document guarded AI robotics adaptation roadmap |
| 2026-09-30T21:44:36+05:30 | [9132425](https://github.com/Dhruv0747/ATLAS/commit/9132425ea7faec539efed11c2a7dfd2fb755ebcc) | Revoke navigation validation after encoder ground failure |
| 2026-09-30T22:25:19+05:30 | [edfb26b](https://github.com/Dhruv0747/ATLAS/commit/edfb26be59528d744235eeec606195975dbbbc3f) | Add bounded stopped-only active vision adviser |
| 2026-09-30T22:40:31+05:30 | [4453e13](https://github.com/Dhruv0747/ATLAS/commit/4453e1392a85ee35fd1787d27e9f21bf6cc5359e) | Add humorous one-shot battery reminders |
| 2026-10-01T10:22:23+05:30 | [af38120](https://github.com/Dhruv0747/ATLAS/commit/af3812078786004d25a618363466949726458de1) | Reduce observability load and fix saved map health |
| 2026-10-01T10:33:09+05:30 | [9f2f7c7](https://github.com/Dhruv0747/ATLAS/commit/9f2f7c75ff2d11b79af139ba8f4862d632bfe0d2) | Adapt Visual Cloud history rate to system load |
| 2026-10-01T10:55:29+05:30 | [5b293ab](https://github.com/Dhruv0747/ATLAS/commit/5b293abdf474f78fb41b53448bee679066a18835) | Separate LiDAR and ultrasonic clearance telemetry |
| 2026-10-01T18:09:44+05:30 | [a5dbb31](https://github.com/Dhruv0747/ATLAS/commit/a5dbb317804ce3b905e854446a6d56baaed5dc14) | Requalify three-encoder fallback with M4 excluded |
| 2026-10-02T13:51:31+05:30 | [953f12f](https://github.com/Dhruv0747/ATLAS/commit/953f12fd27c5ff62492f31867c175d51ba8a98d1) | Add live mapping dashboard |
| 2026-10-02T14:25:15+05:30 | [f884203](https://github.com/Dhruv0747/ATLAS/commit/f88420393c05df16e6a358e425290f7f7309db12) | Restore authoritative EKF odometry identity |
| 2026-10-02T14:47:51+05:30 | [ad39acb](https://github.com/Dhruv0747/ATLAS/commit/ad39acbc3d4a47c7533bc6253c66b70761bd1325) | Bind live map markers to active map |
| 2026-10-02T15:13:45+05:30 | [f866d2f](https://github.com/Dhruv0747/ATLAS/commit/f866d2f85455c49db689fab6e6edfe46927aedc8) | Commit Nav2 to stable global path |
| 2026-10-02T15:24:38+05:30 | [01d0a07](https://github.com/Dhruv0747/ATLAS/commit/01d0a0724dc1b76318ce0f447747ed6ab80f76f4) | Persist commissioned camera home pose |
| 2026-10-02T15:30:01+05:30 | [ed546ec](https://github.com/Dhruv0747/ATLAS/commit/ed546ec1678b01cbd97ba84722dfde52c23164a5) | Tune IMX708 indoor image quality |
| 2026-10-02T15:38:48+05:30 | [1de23a9](https://github.com/Dhruv0747/ATLAS/commit/1de23a9cfe21a9e842850aaf146774ed2189cbe7) | Commission 720p camera profile |
| 2026-10-02T16:54:27+05:30 | [d3d91af](https://github.com/Dhruv0747/ATLAS/commit/d3d91af39c42ebe832bfd83c2b47b2286f86adc7) | Stabilize odometry discovery for EKF and Nav2 |
| 2026-10-04T14:20:03+05:30 | [53e55e5](https://github.com/Dhruv0747/ATLAS/commit/53e55e50441456d891db84b8808e5df5b445f35b) | Document rejected remap TF forensics |
| 2026-10-04T15:32:55+05:30 | [c224156](https://github.com/Dhruv0747/ATLAS/commit/c224156866c10e8f3a1fe7fa7a0cdcf5934ca3aa) | Harden map acceptance and reduce stationary ROS load |
| 2026-10-04T16:59:48+05:30 | [17c0662](https://github.com/Dhruv0747/ATLAS/commit/17c06626ad39d69633cf89e3c79f8c5ecea4cb65) | Normalize SLAM TF acceptance timestamps |
| 2026-10-04T17:02:47+05:30 | [b6463a8](https://github.com/Dhruv0747/ATLAS/commit/b6463a86403a80d3df0f37995a0b2d020cf86487) | Cap remote speed during manual mapping |
| 2026-10-04T19:48:44+05:30 | [6ceb123](https://github.com/Dhruv0747/ATLAS/commit/6ceb123c2a4c476ca207032b126972a4d02d0234) | Restore full steering authority during mapping |
| 2026-10-05T22:08:43+05:30 | [5478fac](https://github.com/Dhruv0747/ATLAS/commit/5478fac974ff465c018d3013926d81d1f58436d1) | Gate manual mapping until SLAM is ready |
| 2026-10-05T22:11:58+05:30 | [0f3ce22](https://github.com/Dhruv0747/ATLAS/commit/0f3ce22b654d13772e73fc484a78b666e90f2951) | Document rejected mapping run forensics |
| 2026-10-06T18:12:33+05:30 | [cadb67d](https://github.com/Dhruv0747/ATLAS/commit/cadb67db52c48fbbeb3d9780caac01ad493dda34) | Fail closed on manual mapping drive readiness |
| 2026-10-06T18:12:53+05:30 | [6330ec4](https://github.com/Dhruv0747/ATLAS/commit/6330ec4fdbee9e7585a990c2dc50e09da37cfad9) | Add fail-closed mapping session readiness core |
| 2026-10-06T18:12:56+05:30 | [3d4bf18](https://github.com/Dhruv0747/ATLAS/commit/3d4bf188b3932c7d3201bb3c909644e3cefff6c7) | Test mapping session readiness gating |
| 2026-10-06T18:15:39+05:30 | [f1d6e54](https://github.com/Dhruv0747/ATLAS/commit/f1d6e54d5e41db54e7a967062a839eb5079fc27a) | Document fail-closed manual mapping readiness |
| 2026-10-06T19:54:18+05:30 | [260c24c](https://github.com/Dhruv0747/ATLAS/commit/260c24cd30a661337bc11d822276e1db8b30f5a9) | Add manual read-only ATLAS health workflow |
| 2026-10-06T19:54:21+05:30 | [440c29b](https://github.com/Dhruv0747/ATLAS/commit/440c29b21ae6f7413859080245837aeddec24b5f) | Document secure runner trust boundary |
| 2026-10-06T20:08:03+05:30 | [c3d4ffa](https://github.com/Dhruv0747/ATLAS/commit/c3d4ffa43f5cf44aba938976ae5bf848d2fbd1ab) | Align health workflow outputs with trusted sudoers path |
| 2026-10-06T20:20:44+05:30 | [dbdd1d7](https://github.com/Dhruv0747/ATLAS/commit/dbdd1d7d2b5e6d32ccebac8284241547de78b6a5) | Remove health-check arguments from trusted sudo boundary |
| 2026-10-06T20:23:42+05:30 | [bf1453e](https://github.com/Dhruv0747/ATLAS/commit/bf1453e9e04b73ac1b7148faf39e385ffa57a517) | Add reviewed trusted ATLAS health checker reference |
| 2026-10-06T20:23:45+05:30 | [239b579](https://github.com/Dhruv0747/ATLAS/commit/239b579b51f4d84d29ebb913a09eeab0425b60b5) | Add narrow ATLAS health sudoers reference |
| 2026-10-06T20:23:54+05:30 | [a641e76](https://github.com/Dhruv0747/ATLAS/commit/a641e769e2d17dc2779a9bedeae7b7575946c8b9) | Document trusted health checker installation boundary |
| 2026-10-06T20:28:42+05:30 | [8d8f824](https://github.com/Dhruv0747/ATLAS/commit/8d8f824a48a1c5dfcf8f23f23113eebd1531c9b4) | Add secure runner handoff checkpoint |
| 2026-10-06T20:30:05+05:30 | [a28cd19](https://github.com/Dhruv0747/ATLAS/commit/a28cd19146541cf55dd1e2750b313856a93e021a) | Require zero arguments for trusted health checker sudo |
| 2026-10-06T20:35:24+05:30 | [37979b5](https://github.com/Dhruv0747/ATLAS/commit/37979b5fa664dbc3af5deb4eaeb2c0f036bebf11) | Record successful trusted Jetson health gate |
| 2026-10-06T20:45:34+05:30 | [b09d4df](https://github.com/Dhruv0747/ATLAS/commit/b09d4df7b1a397afaa993a6d5d00243cce08dfc5) | Add trusted read-only ATLAS health workflow |
| 2026-10-06T20:48:23+05:30 | [a6f044d](https://github.com/Dhruv0747/ATLAS/commit/a6f044da652cf1ffeffc82b0e39dc4a498ae2df4) | Fix trusted health workflow invocation |
| 2026-10-08T11:23:22+05:30 | [c521ffc](https://github.com/Dhruv0747/ATLAS/commit/c521ffcecf545b67a8d83d09351c2cf6bd229856) | Record complete manual mapping sessions |
| 2026-10-08T11:44:17+05:30 | [118d7e9](https://github.com/Dhruv0747/ATLAS/commit/118d7e99ba08cbacfdad7c1e8296747583d855ff) | Document SLAM turn correction evidence |
| 2026-10-08T12:01:04+05:30 | [986fe60](https://github.com/Dhruv0747/ATLAS/commit/986fe605136641be2578b7f4d6609e44ed5a7d79) | Validate isolated SLAM loop closure comparison |
| 2026-10-08T12:07:42+05:30 | [ac7434b](https://github.com/Dhruv0747/ATLAS/commit/ac7434bfd1c0abb4085213377c28cfd8ab4252e3) | Diagnose recorded turn sensor disagreement without live tuning |
| 2026-10-08T13:55:18+05:30 | [6583319](https://github.com/Dhruv0747/ATLAS/commit/658331916426abd292edb2fded20430867c515f4) | Compare isolated wheel fusion variants on recorded mapping loop |
| 2026-10-08T14:06:55+05:30 | [4f47a80](https://github.com/Dhruv0747/ATLAS/commit/4f47a80d0ab338c7121818abe0d03f99c3a046b3) | Measure scan timing and reject zero-offset replay regression |
| 2026-10-08T14:12:27+05:30 | [349b105](https://github.com/Dhruv0747/ATLAS/commit/349b10547909020a66efe6419b60d729630eb9ce) | Audit LiDAR ray timing and record inconclusive rotation sensitivity |
| 2026-10-08T14:15:32+05:30 | [60d0bda](https://github.com/Dhruv0747/ATLAS/commit/60d0bda3ada26f5a45e8046b2a27a5a9442a6168) | Compare correction against prior map and distinguish robot displacement |
| 2026-10-08T14:18:40+05:30 | [b0c59c9](https://github.com/Dhruv0747/ATLAS/commit/b0c59c9cb6cddbd92542e53ad67861cefd59bcdd) | Trace turn corrections and encoder consensus timing across saved run |
| 2026-10-08T14:23:02+05:30 | [63a7d3d](https://github.com/Dhruv0747/ATLAS/commit/63a7d3dd9b73684d65bc1a6f9bd2b3db7b522ffe) | Audit recorded encoder normalization without changing steering |
| 2026-10-08T14:27:59+05:30 | [1771b1d](https://github.com/Dhruv0747/ATLAS/commit/1771b1dcd733f03732a5d75f77c08295a4808c25) | Add coherent diagnostic snapshots for encoder odometry updates |
| 2026-10-08T14:32:21+05:30 | [c7a9a0a](https://github.com/Dhruv0747/ATLAS/commit/c7a9a0a7453c3fe6c488ae68c1cdba23dd1e768d) | Record verified stationary activation of encoder diagnostics |
| 2026-10-08T14:43:30+05:30 | [7024a59](https://github.com/Dhruv0747/ATLAS/commit/7024a59d43da99fc6c3068b134cfab97c343e8b1) | Review synchronized manual turn recording without tuning |
| 2026-10-08T14:46:11+05:30 | [b8b32a7](https://github.com/Dhruv0747/ATLAS/commit/b8b32a70e400a8532f30b4db4e00daedebfe3bc1) | Separate recorded steering directions and check ICP seed sensitivity |
| 2026-10-08T14:47:52+05:30 | [6b7d1a6](https://github.com/Dhruv0747/ATLAS/commit/6b7d1a6208611bfe60d6abe9eb0cf88befb25ec6) | Verify recorded encoder calculation replay and timing |
| 2026-10-08T15:00:49+05:30 | [edfbc8e](https://github.com/Dhruv0747/ATLAS/commit/edfbc8ec1b3ace829692eb5581e86d95c7320c44) | Record offline steering delay sensitivity without control changes |
| 2026-10-08T15:05:21+05:30 | [25e3e1e](https://github.com/Dhruv0747/ATLAS/commit/25e3e1e2895f95b688779e08be75729b125a3289) | Inspect saved turn camera evidence and document visibility limits |
| 2026-10-08T15:09:22+05:30 | [f5a1cea](https://github.com/Dhruv0747/ATLAS/commit/f5a1ceaf6cb1c108778b5cdc28515ccb9bea20d9) | Record separated turn retry and persistent M3 feedback discrepancy |
| 2026-10-08T15:27:57+05:30 | [80f6dc8](https://github.com/Dhruv0747/ATLAS/commit/80f6dc87c9e153ac8b45ccfd468925950d22a8f1) | Retry USB ownership timeout safely and reject incomplete Daly snapshots |
| 2026-10-08T15:52:03+05:30 | [475de9c](https://github.com/Dhruv0747/ATLAS/commit/475de9c9389fb783e399507e2e21af2528284ac5) | Fix policy heartbeat margin without relaxing lifted safety deadline |
| 2026-10-08T16:50:49+05:30 | [677948a](https://github.com/Dhruv0747/ATLAS/commit/677948a09d1f40c5558e373e4f96918da96e55aa) | Wait for fresh battery before lifted entry and surface rejections |
| 2026-10-08T16:54:59+05:30 | [80e2b56](https://github.com/Dhruv0747/ATLAS/commit/80e2b56f3fa6aa7702671637a93130091bd59824) | Repair Daly BLE MTU truncation and validate complete frames |
| 2026-10-08T17:02:53+05:30 | [4b23b19](https://github.com/Dhruv0747/ATLAS/commit/4b23b19d626d47499086a6ff5f42a562717e3f42) | Record stationary verification and remaining BMS timing gate |
| 2026-10-08T17:13:07+05:30 | [2c38b07](https://github.com/Dhruv0747/ATLAS/commit/2c38b07daceb6d5e51778c42db708782905d8746) | Wait for lifted request subscriber before entry |
| 2026-10-08T18:38:43+05:30 | [2f501c1](https://github.com/Dhruv0747/ATLAS/commit/2f501c1e49a0b7d5acac08fb9a92229fe16941b1) | Replace fixed Daly polling delays with bounded response waits |
| 2026-10-08T19:07:23+05:30 | [7e35614](https://github.com/Dhruv0747/ATLAS/commit/7e35614ab00a045a157c5ab58cacf8e7d8cf9396) | Gate lifted test entry on continuous readiness and expose feedback timing |
| 2026-10-08T19:11:11+05:30 | [3d66c38](https://github.com/Dhruv0747/ATLAS/commit/3d66c3812c968796fed70b7f32dae511aadeed45) | Audit repeated lifted commissioning failures and evidence gaps |

