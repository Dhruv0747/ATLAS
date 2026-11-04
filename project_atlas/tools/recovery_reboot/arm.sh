#!/bin/bash
# arm.sh baseline  : boot monitor only; Recovery bytes unchanged.
# arm.sh candidate : exact-byte install of 4af4ddad (snapshot DISABLED) + boot monitor in candidate mode.
# Both: no daemon-reload, no restart, no reboot. The monitor unit is enabled with --no-reload and is
# first loaded by the user manager at the next (separately approved) reboot.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
MODE=${1:-}; [ "$MODE" = baseline ] || [ "$MODE" = candidate ] || die 'usage: arm.sh baseline|candidate'
[ "$D" = "$HOME/project-atlas-migration/recovery-reboot-4af4ddad" ] || die "package must live at ~/project-atlas-migration/recovery-reboot-4af4ddad"
( cd "$D" && sha256sum -c --quiet SHA256SUMS ) || die 'package manifest'
U=$HOME/.config/systemd/user
[ "$(h $U/atlas-sensor-recovery.service)" = 1b1010efa44deb44c5c706f212d0db16f762b904bc498b776b1a60185102e256 ] || die 'Recovery unit drift'
[ "$(ls -A $U/atlas-sensor-recovery.service.d)" = gnss-disabled.conf ] || die 'unexpected Recovery drop-ins'
[ "$(h $U/atlas-sensor-recovery.service.d/gnss-disabled.conf)" = ca513ea0abfa6c963a7f777ad635dfc298e9e9efb012fe5760cdfb210ccd1590 ] || die 'GNSS drop-in drift'
[ "$(systemctl --user show atlas-sensor-recovery -p ActiveState --value)" = active ] || die 'Recovery not active now'
[ -e "$D/ARMED" ] && die 'already armed'
if [ "$MODE" = candidate ]; then bash "$D/install.sh" || die 'candidate install failed (nothing armed)'; else
  [ "$(h $T)" = "$LIVE" ] || die 'baseline mode needs the original live script'; helpers; snapshot_off; fi
cmp -s "$D/atlas-boot-evidence.service" "$U/atlas-boot-evidence.service" || cp "$D/atlas-boot-evidence.service" "$U/atlas-boot-evidence.service"
systemctl --user enable --no-reload atlas-boot-evidence.service || die 'enable failed'
echo "$MODE" > "$D/ARMED"
echo "ARMED $MODE. Recovery PID unchanged. Takes effect only at the next approved reboot."
