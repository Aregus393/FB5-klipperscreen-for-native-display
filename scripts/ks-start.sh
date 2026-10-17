#!/bin/bash
# Start KlipperScreen on a virtual 480x320x16 Xvfb display (:99) whose
# framebuffer (/dev/shm/Xvfb_screen0) is mirrored to the FB5 display,
# with the XPT2046 touch fed back as mouse events.
# Usage: ks-start.sh [stop]
. "$(dirname "$0")/fb5-env.sh"
pkill -f "[k]s-loop.sh"
pkill -x Xvfb
pkill -f "[K]lipperScreen/screen.py"
pkill -f "[f]b5-mirror.py --xvfb"
pkill -f "[f]b5-touch.py"
[ "$1" = stop ] && { echo stopped; exit 0; }
sleep 1
nohup Xvfb :99 -screen 0 480x320x16 -fbdir /dev/shm -nolisten tcp -nocursor \
    > "$FB5_LOGS/xvfb.log" 2>&1 < /dev/null &
# Xvfb is slow right after boot; the mirror waits for the file as well
for i in $(seq 1 120); do [ -e /dev/shm/Xvfb_screen0 ] && break; sleep 0.5; done
nohup "$FB5_SCRIPTS/ks-loop.sh" > /dev/null 2>&1 < /dev/null &
nohup python3 "$FB5_SCRIPTS/fb5-mirror.py" --xvfb /dev/shm/Xvfb_screen0 \
    --print-rate "$FB5_PRINT_RATE" > "$FB5_LOGS/mirror.log" 2>&1 < /dev/null &
if [ -f "$FB5_DIR/touch-cal.json" ]; then
    nohup python3 "$FB5_SCRIPTS/fb5-touch.py" -v \
        > "$FB5_LOGS/touch.log" 2>&1 < /dev/null &
fi
sleep 1
pgrep -a Xvfb; pgrep -af "[s]creen.py" | cut -c1-80; pgrep -af "[f]b5-mirror|[f]b5-touch|[k]s-loop" | cut -c1-80
