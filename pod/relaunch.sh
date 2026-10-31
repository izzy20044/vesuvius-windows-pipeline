#!/bin/bash
# relaunch.sh - stop any running setup/pipeline and start the current versions.
# Patterns use [x] brackets so pkill never matches this script's own command line.
cd /workspace/vesuvius
pkill -f '[p]od/pipeline\.sh'
pkill -f '[p]od/setup_pod\.sh'
pkill -f '[v]env_ink/bin/pip'
sleep 2
[[ -f setup.log ]] && mv setup.log "setup.$(date +%H%M%S).log"
echo "[$(date +%T)] relaunch" >> pipeline.log
nohup bash pod/setup_pod.sh > setup.log 2>&1 < /dev/null &
sleep 1
nohup bash pod/pipeline.sh > /dev/null 2>&1 < /dev/null &
sleep 10
cat setup.log
echo "STATUS: $(cat STATUS)"
ps -eo pid,etime,cmd | grep -E '[s]etup_pod|[p]ipeline\.sh' | cut -c1-90
