#!/bin/bash
# ATLAS dashboard watchdog (user timer, every 20 s). If the dashboard does not answer twice in a row, dump its thread
# stacks (SIGUSR1 -> faulthandler -> journal) and restart rover-status-web. Touches nothing else.
STATE=/tmp/atlas_status_web_watchdog.fail
if curl -s -o /dev/null --max-time 8 http://127.0.0.1:8088/v2/; then rm -f $STATE; exit 0; fi
n=$(( $(cat $STATE 2>/dev/null || echo 0) + 1 )); echo $n > $STATE
[ $n -lt 2 ] && exit 0
PID=$(systemctl --user show rover-status-web -p MainPID --value)
logger -t atlas-status-web-watchdog "dashboard not answering ($n checks); dumping stacks of pid $PID and restarting"
[ "${PID:-0}" -gt 0 ] && kill -USR1 $PID && sleep 2
systemctl --user restart rover-status-web
rm -f $STATE
