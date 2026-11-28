#!/bin/bash
# ATLAS dashboard watchdog (user timer, every 20 s). If the dashboard does not answer twice in a row, dump its thread
# stacks (SIGUSR1 -> faulthandler -> journal) and restart rover-status-web. Touches nothing else.
STATE=/tmp/atlas_status_web_watchdog.fail
# 2026-11-13: startup grace. A deliberate restart takes ~20-40 s before the page answers; without this the watchdog
# counted it as a hang, sent SIGUSR1 before faulthandler was registered (killing the starting process) and
# restarted it again (seen 22:48:45, 23:37:05, 23:37:45).
GRACE_S=60
since=$(systemctl --user show rover-status-web -p ActiveEnterTimestampMonotonic --value 2>/dev/null)
now_s=$(cut -d. -f1 /proc/uptime)          # whole seconds (awk %d overflowed on microseconds)
if [ "${since:-0}" -gt 0 ] && [ $(( now_s - since / 1000000 )) -lt $GRACE_S ]; then rm -f $STATE; exit 0; fi
if curl -s -o /dev/null --max-time 8 http://127.0.0.1:8088/v2/; then rm -f $STATE; exit 0; fi
n=$(( $(cat $STATE 2>/dev/null || echo 0) + 1 )); echo $n > $STATE
[ $n -lt 2 ] && exit 0
PID=$(systemctl --user show rover-status-web -p MainPID --value)
logger -t atlas-status-web-watchdog "dashboard not answering ($n checks); dumping stacks of pid $PID and restarting"
[ "${PID:-0}" -gt 0 ] && kill -USR1 $PID && sleep 2
systemctl --user restart rover-status-web
rm -f $STATE
