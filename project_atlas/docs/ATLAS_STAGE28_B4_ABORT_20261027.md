# B4 supervised receiver test — aborted by PC evidence writer

Owner approved one passive session with actuators isolated, Jetson shut down and no retries. COM26 receiver-only monitoring verified direct-drive-disabled status before the transmitter-ON instruction. Subsequent owner confirmation said transmitter ON, controls untouched, actuators still unplugged.

On checking that confirmation, result.json showed the monitor had already aborted at16.579seconds: Windows WinError5 Access denied during os.replace(latest.tmp, latest.json). Serial port was closed in finally. Exact cause of the Windows file-access conflict is unproven; concurrent status-file reading is a hypothesis, not an established hardware fault.

Captured2021 complete packets including404 RC reports before abort. Last RC report: seq0, ever=false, fresh=false, drive_disabled=true, channels=null. Raw SHA256 ff9ddd1452f8ae53b2e332706cb701c0b22e2bbb9513a272905d7c99860bc91e. No usable ON-state channel baseline, channel movement or signal-loss test was captured. CH1–CH10, directions, ranges and failsafe behavior remain UNVERIFIED. No receiver/firmware failure is established.

The previously written latest.json remained marked MONITORING after abort; result.json is authoritative. Future monitoring must check completion/error state and heartbeat age before presenting a live status. Fix the Windows snapshot write/read interaction offline and test it before requesting a separately approved live retry. Do not bypass evidence failure or automatically reopen COM26.

Owner instructed to switch transmitter OFF immediately. Await OFF confirmation. No motor command, serial write, reset, firmware operation or Jetson deployment occurred. Actuators remain isolated per owner confirmation. Electrical output levels were not measured.

Private evidence: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/stage28-b4-sbus-20261027/ including monitor.py, raw.bin, reports.jsonl, latest/result JSON and SHA256SUMS. Test stopped; no retry performed.
