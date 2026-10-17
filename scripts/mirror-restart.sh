#!/bin/bash
# Restart only the KlipperScreen mirror (it redraws the whole screen on
# start). Safe while printing.
# Usage: mirror-restart.sh [stop]
. "$(dirname "$0")/fb5-env.sh"
pkill -f "[f]b5-mirror.py --xvfb"
[ "$1" = stop ] && { echo "mirror stopped"; exit 0; }
sleep 1
nohup python3 "$FB5_SCRIPTS/fb5-mirror.py" --xvfb /dev/shm/Xvfb_screen0 \
    --print-rate "$FB5_PRINT_RATE" > "$FB5_LOGS/mirror.log" 2>&1 < /dev/null &
sleep 1
pgrep -af "[f]b5-mirror" | cut -c1-80
