#!/bin/bash
# Controlled Stage 26 CPU A/B. Only restarts rover-status-web (via rollback.sh / apply.sh). Aborts safely; always ends with Stage 26 installed.
set -u
D=~/s26_ab; mkdir -p $D; LOG=$D/ab.log; exec >>$LOG 2>&1
STG=~/stage26_pkg_staging; W=300; SETTLE=120
safe(){ curl -s -m5 http://127.0.0.1:8088/api/estop/state | python3 -c "import sys,json;sys.exit(0 if json.load(sys.stdin)['latched'] else 1)"; }
say(){ echo "$(date +%T) $*"; }
installed(){ [ -f ~/project_atlas/scripts/atlas_testlab_web.py ]; }
ensure_installed(){ if ! installed; then say "RE-INSTALLING Stage 26"; (cd $STG/tools/deploy/stage26_testlab && OWNER_APPROVED=yes ./apply.sh); fi; }
trap 'say "exit trap"; ensure_installed' EXIT
safe || { say "ABORT: E-STOP not latched"; exit 1; }
say "phase A1 (Stage 26 installed, running pid $(systemctl --user show rover-status-web -p MainPID --value))"; python3 $D/measure.py A1_installed_running $W $D/A1.json
safe || { say "ABORT: E-STOP released"; exit 1; }
say "ROLLBACK"; (cd $STG/tools/deploy/stage26_testlab && ./rollback.sh); installed && { say "rollback left files"; exit 2; }
say "settle $SETTLE"; sleep $SETTLE; safe || { say "ABORT: E-STOP released"; exit 1; }
say "phase B (rolled back)"; python3 $D/measure.py B_rolled_back $W $D/B.json
safe || { say "ABORT: E-STOP released"; exit 1; }
say "REAPPLY"; (cd $STG/tools/deploy/stage26_testlab && OWNER_APPROVED=yes ./apply.sh)
say "settle $SETTLE"; sleep $SETTLE
say "phase A2 (reinstalled, fresh restart)"; python3 $D/measure.py A2_reinstalled_fresh $W $D/A2.json
say "DONE"
