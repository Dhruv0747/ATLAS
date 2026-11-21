# Offline depth-preview CPU optimization

2026-10-21, baseline06ed75f. OFFLINE ONLY: no Jetson connection, deployment,
service restart, camera session, recording or movement in this task.

## Evidence and scope

The saved approved session reached17 depth frames then rejected CPU76.0757%.
It passed initial admission and launched the driver; this is distinct from the
earlier pre-driver rejection. Its1s monitor contains aggregate CPU and worker
state, not contemporaneous per-process attribution. The exact total contention
cause remains unresolved. Historical process traces identify background load
but do not justify stopping essential services or assigning this spike to one.

Code-path audit: Dashboard depth frame requests run core.preview under the
VisionService lock, cached at most2Hz. The old depth loop calls depth_at for each
sample, which revalidates the same immutable buffer's dimensions/stride/length
and reconstructs format selection each time. cProfile on160x120 confirms
19,201 image_layout calls and19,200 depth_at calls per conversion. This is a
verified removable CPU contributor, NOT proven sole cause of the live spike.

## Smallest correction

Only production file: scripts/atlas_vision3d_core.py (11 added lines,1 replaced).
Validate complete frame once before looping; prebind endian/encoding Struct;
read the same sampled pixels, preserve invalid-depth handling and colour mapping.
Standalone depth_at still validates every measurement. No NumPy/new dependency,
thread, cached safety state, reduced frame dimensions or changed polling rate.
PNG bytes and statistics identical against the previous implementation.
Raw browser3D transfer and calibrated-cloud gates unchanged. This optimizes the
2D depth image alongside the3D preview; it does not alter3D geometry/calibration.

## Measurements

Synthetic padded160x12016UC1;7 batches of20 conversions each; process CPU clock.

|PC environment|Before ms/frame|After ms/frame|Reduction|
|---|---:|---:|---:|
|WSL Ubuntu22.04 Python3.10|21.2535|9.6043|54.81%|
|Windows Python3.13|21.875|9.375|57.14%|

WSL peak traced allocation422141 ->422412bytes (271bytes increase).
Layout validations19,201 ->1. PNG SHA256 identical:
`a0ae721bb4d6aeb34686d1c4bbaa540db8b30a18b4d7301fc96c001dd321ddfd`.
At the existing2Hz conversion ceiling, WSL saving is~0.0233CPU-seconds/second,
or2.33% of ONE core; do not present54.8% as whole-Jetson CPU reduction.
No measured Jetson savings and no prediction that this alone clears75%.
Reproducer: tools/vision3d/profile_preview_cpu_offline.py, fixed baseline06ed75f.

## Regression results

94 tests pass: new equivalence5, existing core/web37, browser preview4, UI10,
IR15, startup coverage14, startup/shutdown9. No skips in these final runs.
Equivalence covers16UC1/32FC1, both endian orders, row padding, invalid/sentinel/
NaN/Inf/negative depth, native160x120 and downsampled641x481. Truncated buffers
and wrong depth encodings rejected; measurement validation retained.
Initial Windows runs hit known platform constraints: UTF-8 label decoding and
os.getuid absent. Browser tests rerun with -X utf8; Linux-specific tests under
WSL passed without changing application code for those environment failures.
Temporary-file install/rollback byte rehearsal passed. No hardware success claim.

## Package, deployment and rollback (not executed)

Local package artifacts/astra_concurrent_20261021/preview-cpu-candidate.tar:
one production file plus manifest. SHA256:
`39b5c0ac8233a44708d729ebcb1a29025d5d2d68dce1e03895940455e52ce521`.
Expected original SHA256:
`1e4c095d5d2ae76aae528e09aa152f66218d4838855e882f1cb91196a7efe63e`.
Candidate SHA256:
`49777c0c3a3c2542107dcccba0ef26e234a31ab22729b055ca8bc260bff501a2`.
Fresh live hash verification required; abort mismatch rather than assuming
repository bytes equal deployment. Preserve verified backup and atomic replace.
Needs separate approval for single-file installation and monitored web-only
restart. Keep E-STOP/zero commands/manual-only/AstraOFF/recorderOFF,75/80/70,
Domain77 and fresh protected sensors. Verify unchanged protected PIDs/configs.
On failed postflight restore backup and approved web-only rollback restart.
No essential service stops. Subsequent ONE guarded camera test needs separate
approval. Until then remaining contention and real3D Preview remain unresolved.
