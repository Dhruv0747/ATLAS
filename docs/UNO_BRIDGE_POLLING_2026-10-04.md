# UNO bridge polling reduction (offline change)

The Jetson-side `ultrasonic_arduino_bridge.py` timer previously woke the ROS
executor every 10 ms (100 Hz), including when the UNO serial link and local
camera-command socket were idle.  Its default period is now 40 ms (25 Hz).
This removes 75 of the 100 idle timer callbacks per second; it is not a measured
whole-system CPU-improvement claim.

The 40 ms period matches the existing fastest bounded camera command interval.
It is also well below the UNO firmware's 250 ms atomic ultrasonic validity
report interval.  ROS camera topic callbacks remain independent of this timer;
the local socket remains serviced and drains up to eight queued commands on
each tick.

Safety and recovery behavior are unchanged inside each callback:

- newly available USB bytes continue to drain immediately in the same callback,
  bounded by 8192 bytes, 128 complete lines, and 8 ms;
- a pending ultrasonic report is still withheld and `SERIAL_BACKLOG` is
  published while USB bytes or a complete parser line remain;
- a trailing incomplete line is still retained without being mistaken for a
  completed backlog item;
- the MCU report timestamp/sample age is not restamped while draining;
- missing validity reports still invalidate after one second, and consumers
  retain their own independent freshness expiry;
- serial-stale reopening, two-second reconnect backoff, and local camera socket
  handling remain in the same callback path.

`project_atlas/tests/test_uno_bridge_polling.py` is hardware-free.  It checks
that the node uses the 25 Hz policy, a serial burst still drains within one
callback, offline camera/expiry/reconnect work still runs, and complete parser
backlog remains fail-closed.

The change was deployed while ATLAS was stationary. The bridge remained
`active/running` with zero service restarts, and front/rear ultrasonic, radar,
thermal, ambient, I2C status, and camera-servo status all remained fresh.
Process CPU settled from roughly 23.6% to 8.7% of one core. The deployed file
matched the reviewed source, and the rollback copy is stored at
`data/deploy_backups/20261004_cpu_uno/ultrasonic_arduino_bridge.py.before`.
This is a stationary interface/CPU result, not autonomous-motion evidence.
