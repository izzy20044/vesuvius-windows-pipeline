#!/bin/bash
# after_fits.sh - start each band's screen as soon as its fit finishes. Writes SCREEN_STATUS.
W=/workspace/vesuvius; cd "$W"
st() { echo "$*" > "$W/SCREEN_STATUS"; echo "[$(date +%T)] $*" >> "$W/after_fits.log"; }
wait_for() { until grep -qE "$2" "$W/$1" 2>/dev/null; do sleep 30; done; }
(
  wait_for STATUS "MAIN FIT DONE|MAIN FIT FAILED"
  grep -q "MAIN FIT DONE" STATUS && { st "screening main-ACW"; bash pod/screen.sh main-ACW 8700 10200; st "main screen finished"; }
) &
(
  wait_for BAND2_STATUS "BAND2 FIT DONE|BAND2 .*FAILED"
  grep -q "BAND2 FIT DONE" BAND2_STATUS && { st "screening band2-ACW"; bash pod/screen.sh band2-ACW 7200 8700; st "band2 screen finished"; }
) &
wait
st "ALL SCREENS FINISHED"
# never leave the GPU billing idle if nobody is watching (see autostop.sh)
bash pod/autostop.sh "${AUTOSTOP_GRACE_MIN:-20}"
