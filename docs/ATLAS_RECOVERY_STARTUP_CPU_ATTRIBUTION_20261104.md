# Recovery startup CPU burst: attribution from existing evidence (2026-11-04)

Offline analysis only. No service restart, install, reboot, measurement or config change.
Source: existing private evidence `work/recovery-restoration-result-20261031` (Oct 31 09:03 IST,
per-PID and cgroup counters for every 1 s window, 6 online CPUs) and
`work/recovery-startup-diagnostic-evidence-20261031` (08:35 IST). Raw evidence is not committed.

## Rejected window 09:03:50.75-51.75 (86.93 %), vs mean of 5 quiet windows (60.13 %)

| Contributor | One-core % | Whole-machine points |
|---|---:|---:|
| Recovery process itself (new PID 374161) | +54.5 | +9.1 |
| 36 existing ROS processes, all rising at once (net of decreases) | +137.4 / -45.8 | +15.3 |
| Total aggregate jump | | +26.8 |

- Kernel time: system 11-16 % -> 30.2 %, softirq 1.7 % -> 6.0 %, irq 2.0 % -> 3.0 % of the machine.
  The softirq/irq rise (~5 points) is network-stack work not charged to any process.
- Idle processes that do no periodic work rose too: static TF publishers 0 -> 7.9 and 0 -> 5.9,
  teleop 0 -> 4.9, carrier-health 0 -> 7.9, INA3221 0 -> 4.9. That pattern fits every DDS
  participant reacting to a new participant and its endpoints joining the graph. It is not
  instrumented at DDS level, so the mechanism is highly likely, not proven.
- Recovery logged READY at 51.554, inside this window: its endpoints were being created then.

## Localization

Localization cgroup 16.8 -> 48.2 % one core is genuine CPU, not coincidence: it is spread over
11 Nav2/EKF processes (AMCL +4.7, two lifecycle managers +3.5/+2.4, planner +3.3, waypoint
follower +2.8, bt_navigator +2.8, two EKFs +2.7/+1.8, behavior +2.6, map server +2.4, controller
+2.0). The localization monitor and its paced search worker stayed at 11.8 (normal), so the
search-pacing burst is not the cause. Localization is simply the largest group of participants
reacting to the same graph event.

## Supervisor-induced costs (outside the rejected window, but in the same 10 s)

- systemd user manager (PID 1578) 48.9-49.3 % one core in the window ~2 s before each start:
  the Restart=no override daemon-reload (~8 whole points). Same effect found for Neural.
- polkitd 42-61 % one core in the first observer window of both runs.

## Headroom arithmetic

With a 60 % baseline the burst must stay <= 15 points. Observed starts: 26.8 (Oct 31 09:03),
>= 20 (Oct 31 00:28, 81.34 %), ~18 (Nov 2, 77.45 %). Removing ALL of Recovery's own CPU
(9.1 points) would still leave 60.1 + 15.3 + reload drift ~= 75.4 % for the 09:03 case. Therefore no
Recovery-local change (type preload, snapshot removal, script tuning) can be shown to pass alone.

## Options reviewed (none applied)

| Option | Effect on dominant term | Verdict |
|---|---|---|
| Type preload (ed85ebd) | Reorders Recovery's own work only | Insufficient |
| Remove `bash -lc` setup.bash wrapper | Cost lands in the window before the peak | No peak benefit |
| CPUQuota on Recovery (e.g. 35 %) | Caps own share 9.1 -> 5.8; may pace others via reliable acknacks | UNPROVEN; steady-state Recovery ~17.4 % one core, throttling latency must be reviewed |
| Disable Recovery parameter services | Fewer endpoints announced | Rejected earlier (do not disable parameter services) and changes behavior |
| Fast DDS discovery server / localhost-only | Changes every participant | Requires restarting all ROS services; not small |
| Nav2 composition (fewer participants) | Shrinks Localization reaction | Nav2 change; out of scope |
| Lower baseline (fewer dashboard clients) | Dashboard 32.9-48.4 % one core | Operational, unmeasured |

## Conclusion

Main contributor CONFIRMED from measurements: graph-wide reaction of existing ROS processes
(~57 % of the jump) plus Recovery's own initialization (~34 %). No safe, small startup
optimization was found that is shown to keep a mid-operation Recovery start under 75 %.
Recovery deployment remains NO-GO.
