#!/bin/bash
# Change the Pi <-> MCU link speed: build the firmware for the new speed,
# flash it over UART (Katapult) and set [mcu] baud in printer.cfg.
# Above 500000 you need a shielded UART cable - AT YOUR OWN RISK.
# Check afterwards with scripts/fb5-motion-test.py and scripts/link-test.sh.
#
# NOT TESTED as a whole (the steps inside were done by hand).
# Usage: ./set-baud.sh <250000|500000|1500000|2000000>
. "$(dirname "$0")/scripts/fb5-env.sh"
BAUD=$1
case "$BAUD" in 250000|500000|1500000|2000000) ;;
    *) echo "usage: ./set-baud.sh <250000|500000|1500000|2000000>"; exit 1;;
esac
refuse_while_printing
CUR=$(python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG")
echo "link speed now $CUR, new $BAUD"
if [ "$BAUD" -gt 500000 ]; then
    echo "Above 500000 the UART wires must be a shielded cable (shield to GND"
    echo "at both ends, away from motor and heater wires). At your own risk."
fi
read -r -p "Build, flash and switch? Klipper will restart. [y/N] " answer
[ "$answer" = y ] || [ "$answer" = Y ] || exit 1
set -e
"$FB5_SCRIPTS/build-firmware.sh" "$BAUD"
# the bootloader request goes out at the old speed, so printer.cfg is
# changed only after flashing
"$FB5_SCRIPTS/flash-uart.sh" --no-start "$FB5_DIR/firmware/$BAUD/klipper.bin"
python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG" "$BAUD"
curl -s -m 8 -X POST "$MOONRAKER/machine/services/start?service=klipper" >/dev/null
for i in $(seq 1 12); do
    sleep 5
    [ "$(klippy_state)" = ready ] && { echo "klipper ready at $BAUD"; exit 0; }
done
cat <<EOF
klipper is not ready - check klippy.log. If it cannot connect at $BAUD
(eg, the wiring is not good enough), go back to 500000 by SD card:
 1. $FB5_SCRIPTS/build-firmware.sh 500000 --sd
 2. copy $FB5_DIR/firmware/500000/Robin_nano35.bin to an SD card,
    put it into the board, power cycle the printer
 3. python3 $FB5_SCRIPTS/set-mcu-baud.py $PRINTER_CFG 500000
    and restart Klipper
EOF
exit 1
