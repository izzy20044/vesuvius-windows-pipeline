#!/bin/bash
# autostop.sh [grace_minutes] - stop this RunPod pod so it cannot bill while idle.
# Waits grace_minutes (default 20) for someone to copy results off, unless /workspace/vesuvius/KEEP_ALIVE
# exists. Stop (not terminate): the volume survives, only storage keeps billing (~$0.08/hr per 300 GB).
# The pod's RUNPOD_POD_ID and RUNPOD_API_KEY live in PID 1's environment, not in ssh sessions.
GRACE=${1:-20}
W=/workspace/vesuvius
echo "[$(date +%T)] autostop: stopping pod in $GRACE min (touch $W/KEEP_ALIVE to cancel)" | tee -a "$W/autostop.log"
sleep $(( GRACE * 60 ))
if [[ -e $W/KEEP_ALIVE ]]; then echo "[$(date +%T)] autostop: cancelled by KEEP_ALIVE" | tee -a "$W/autostop.log"; exit 0; fi
echo "[$(date +%T)] autostop: stopping now" | tee -a "$W/autostop.log"
env $(tr '\0' '\n' < /proc/1/environ | grep -E '^RUNPOD_(POD_ID|API_KEY)=' | xargs) \
  sh -c 'runpodctl stop pod "$RUNPOD_POD_ID"' >> "$W/autostop.log" 2>&1
