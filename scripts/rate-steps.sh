#!/bin/bash
# Find the display stream limit that is safe while the printer moves:
# for each limit, mirror the screen (keep the camera panel open) with
# fb5-mirror.py --limit-always --print-rate <KiB/s> and run a motion test
# (no heating, no extrusion - unload the filament anyway).
# Stops early if klippy leaves "ready" or mcu_awake exceeds MAX_AWAKE.
# Usage: rate-steps.sh [accel] [speed] [rates...]   (rate 0 = unlimited,
#        "base" = no mirroring at all). Log: logs/rate-steps-*.log
. "$(dirname "$0")/fb5-env.sh"
cd "$FB5_LOGS"
ACCEL=${1:-5000}; SPEED=${2:-150}; shift 2 2>/dev/null
RATES=${*:-base 48 64 96 128 0}
MAX_AWAKE=0.85
LOG=rate-steps-$(date +%Y%m%d-%H%M).log
refuse_while_printing
stop_mirror() { pkill -f "[f]b5-mirror.py --xvfb"; sleep 1; }
echo "=== $(date) accel $ACCEL speed $SPEED rates: $RATES" | tee -a $LOG
for r in $RATES; do
    stop_mirror
    if [ "$r" != base ]; then
        nohup python3 "$FB5_SCRIPTS/fb5-mirror.py" --xvfb /dev/shm/Xvfb_screen0 --report 5 \
            --limit-always --print-rate $r > mirror-step-$r.log 2>&1 < /dev/null &
        sleep 3
    fi
    echo "--- rate $r KiB/s" | tee -a $LOG
    python3 "$FB5_SCRIPTS/fb5-motion-test.py" --speed $SPEED --accel $ACCEL --circles 8 \
        --e-ratio 0 > motion-step-$r.log 2>&1
    grep -E "result:|klippy states|mcu_awake max|endstop shift" motion-step-$r.log | tee -a $LOG
    [ "$r" != base ] && grep "mirror:" mirror-step-$r.log | tail -4 | tee -a $LOG
    state=$(klippy_state)
    awake=$(grep -o "mcu_awake max [0-9.]*" motion-step-$r.log | grep -o "[0-9.]*$")
    if [ "$state" != ready ]; then echo "STOP: klippy $state" | tee -a $LOG; break; fi
    if [ -n "$awake" ] && python3 -c "import sys; sys.exit(not $awake > $MAX_AWAKE)"; then
        echo "STOP: mcu_awake $awake > $MAX_AWAKE" | tee -a $LOG; break
    fi
done
stop_mirror
"$FB5_SCRIPTS/mirror-restart.sh" > /dev/null
echo "=== done $(date)" | tee -a $LOG
