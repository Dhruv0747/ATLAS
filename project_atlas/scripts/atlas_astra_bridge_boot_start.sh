#!/bin/bash
# Track A: start the domain-77 -> domain-0 bridge ONCE after boot, only when it is safe to do so.
# Joining production domain 0 costs ~5-9 s of ~100 % CPU (measured), so this waits until ALL of these hold:
#   * atlas-astra-obstacles is active and the Astra scan exists (domain 77 node running);
#   * the rover is verifiably parked (atlas_astra_bridge_parked_check.py) twice, 10 s apart;
#   * whole-Jetson CPU over 10 s is below 72 % (boot-time load has settled).
# Gives up after 15 minutes (bridge stays off; start it by hand when parked). Never restarts the bridge later.
set -u
LIMIT_S=900; T0=$(date +%s)
cpu10(){ read -r _ a b c d e f g h _ < /proc/stat; t1=$((a+b+c+d+e+f+g+h)); i1=$((d+e)); sleep 10
         read -r _ a b c d e f g h _ < /proc/stat; t2=$((a+b+c+d+e+f+g+h)); i2=$((d+e)); echo $(( 100*((t2-t1)-(i2-i1))/(t2-t1) )); }
CHECK=/home/jetson/project_atlas/scripts/atlas_astra_bridge_parked_check.py
while [ $(( $(date +%s) - T0 )) -lt $LIMIT_S ]; do
  if systemctl --user is-active --quiet atlas-astra-bridge; then echo "bridge already active"; exit 0; fi
  if ! systemctl --user is-active --quiet atlas-astra-obstacles; then echo "waiting: atlas-astra-obstacles not active"; sleep 15; continue; fi
  if ! /usr/bin/python3 "$CHECK" >/dev/null 2>&1; then echo "waiting: rover not verifiably parked (or dashboard not up yet)"; sleep 15; continue; fi
  C=$(cpu10)
  if [ "$C" -ge 72 ]; then echo "waiting: CPU ${C} % >= 72 %"; continue; fi
  if ! /usr/bin/python3 "$CHECK" >/dev/null 2>&1; then echo "waiting: parked check failed on re-check"; sleep 15; continue; fi
  echo "starting bridge: parked twice, CPU ${C} %, after $(( $(date +%s) - T0 )) s"
  systemctl --user start atlas-astra-bridge && exit 0
  echo "bridge start refused or failed (its own parked ExecCondition may have skipped it)"; exit 0
done
echo "gave up after ${LIMIT_S} s: bridge NOT started (start by hand while parked: systemctl --user start atlas-astra-bridge)"
exit 0
