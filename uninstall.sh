#!/bin/bash
# Undo install.sh: stop the screen, remove the autostart and the display
# config, switch Klipper back to the branch/commit it was on.
# The MCU keeps the FB5 firmware until you flash a normal Klipper build
# (instructions are printed at the end).
#
# NOT TESTED: read it before running it.
. "$(dirname "$0")/scripts/fb5-env.sh"
refuse_while_printing
read -r -p "Remove the FB5 display setup? [y/N] " answer
[ "$answer" = y ] || [ "$answer" = Y ] || exit 1

echo "== screen"
"$FB5_SCRIPTS/ks-start.sh" stop
( crontab -l 2>/dev/null | grep -v "/scripts/ks-start.sh" || true ) | crontab -

echo "== printer.cfg"
mkdir -p "$FB5_STATE"
cp "$PRINTER_CFG" "$FB5_STATE/printer.cfg.before-uninstall-$(date +%Y%m%d-%H%M%S)"
sed -i '/^\[include fb5-display.cfg\]/d' "$PRINTER_CFG"
[ -f "$CONFIG_DIR/fb5-display.cfg" ] && mv "$CONFIG_DIR/fb5-display.cfg" "$FB5_STATE/"

echo "== Klipper"
if [ -f "$FB5_STATE/klipper-orig" ]; then
    git -C "$KLIPPER_DIR" checkout "$(cat "$FB5_STATE/klipper-orig")" \
        && echo "Klipper back on $(cat "$FB5_STATE/klipper-orig")"
else
    echo "no saved Klipper branch: switch $KLIPPER_DIR back yourself (eg, git checkout master)"
fi

echo "== KlipperScreen"
if [ -d "$KS_DIR/.git" ]; then
    git -C "$KS_DIR" checkout -- panels/camera.py && echo "camera panel restored"
fi
if [ -f "$FB5_STATE/ks-service-disabled" ]; then
    sudo systemctl enable --now KlipperScreen && rm "$FB5_STATE/ks-service-disabled"
fi
[ -f "$FB5_STATE/ks-cloned" ] && echo "KlipperScreen was installed by install.sh: remove $KS_DIR and $KS_ENV if you do not need it"

baud_now=$(python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG")
baud_orig=$(cat "$FB5_STATE/baud-orig" 2>/dev/null || echo 250000)
cat <<EOF

== Done. The MCU still runs the FB5 firmware at $baud_now baud, and
printer.cfg still says baud: $baud_now, so Klipper keeps working.
To go back to a normal Klipper firmware:
 1. cd $KLIPPER_DIR && make menuconfig: STM32F103, "28KiB bootloader",
    "Serial (on USART1 PA10/PA9)", baud $baud_orig; then make
 2. ./scripts/update_mks_robin.py out/klipper.bin out/Robin_nano35.bin
 3. copy out/Robin_nano35.bin to an SD card, flash it as usual
 4. python3 $FB5_SCRIPTS/set-mcu-baud.py $PRINTER_CFG $baud_orig
    and restart Klipper
Backups of printer.cfg are in $FB5_STATE.
EOF
