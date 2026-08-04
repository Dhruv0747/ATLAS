#!/usr/bin/env bash
set -e
for c in \
  "AT" \
  "AT+CGPS?" \
  "AT+CGPSINFO" \
  "AT+CGNSSINFO" \
  "AT+CGPSNMEA?" \
  "AT+CGPSAUTO?"
do
  echo "--- $c ---"
  echo password | sudo -S mmcli -m 0 --command="$c" 2>&1 || true
done
