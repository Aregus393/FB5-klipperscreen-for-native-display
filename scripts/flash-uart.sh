#!/bin/bash
# Flash Klipper to the FB5 MCU over UART via Katapult (chained after the
# MKS bootloader). Needs a firmware with Katapult already on the board
# (the SD image of this project).
# Usage: flash-uart.sh [--no-start] <klipper.bin>
# The bootloader request goes to Klipper at the baud set in printer.cfg
# [mcu]; Katapult itself always talks at KATAPULT_BAUD.
. "$(dirname "$0")/fb5-env.sh"
set -e
START=1
[ "$1" = "--no-start" ] && { START=0; shift; }
BIN=$1
KATAPULT_BAUD=250000
[ -f "$BIN" ] || { echo "usage: flash-uart.sh [--no-start] <klipper.bin>"; exit 1; }
DEV=$(python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG" --serial)
KLIPPER_BAUD=$(python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG")
FT="python3 $KATAPULT_DIR/scripts/flashtool.py -d $DEV"
LOG=$FB5_LOGS/flash-$(date +%Y%m%d-%H%M%S).log
refuse_while_printing
echo "firmware: $BIN ($(stat -c %s "$BIN") bytes), $DEV"
echo "stopping klipper"; curl -s -m 8 -X POST "$MOONRAKER/machine/services/stop?service=klipper" >/dev/null; sleep 2
echo "requesting bootloader at $KLIPPER_BAUD"; $FT -b $KLIPPER_BAUD -r >>"$LOG" 2>&1 || true
ok=0
for i in $(seq 1 15); do
    sleep 2
    if timeout 15 $FT -b $KATAPULT_BAUD -s >>"$LOG" 2>&1; then ok=1; break; fi
done
[ $ok = 1 ] || { echo "Katapult did not answer, see $LOG (klipper left stopped)"; exit 1; }
echo "Katapult connected, flashing"
if ! $FT -b $KATAPULT_BAUD -f "$BIN" >>"$LOG" 2>&1; then echo "FLASH FAILED, MCU stays in Katapult; rerun this script. Log: $LOG"; exit 1; fi
grep -a "Verification Complete" "$LOG" | tail -1
[ $START = 1 ] || exit 0
echo "starting klipper"; curl -s -m 8 -X POST "$MOONRAKER/machine/services/start?service=klipper" >/dev/null
for i in $(seq 1 12); do
    sleep 5
    s=$(klippy_state)
    [ "$s" = ready ] && { echo "klipper ready"; exit 0; }
done
echo "klipper not ready (state: $s) - check klippy.log"; exit 1
