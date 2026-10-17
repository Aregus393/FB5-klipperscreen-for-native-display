#!/bin/bash
# Install KlipperScreen on the native display of the Flying Bear Ghost 5.
#
# NOT TESTED ON A CLEAN SYSTEM: the project runs on the author's printer,
# but this script was written afterwards and has never been run from
# scratch. Read it before running it; ideally run it together with an AI
# assistant that can read the output and the logs.
#
# Usage: ./install.sh --check    only check and show what would change
#        ./install.sh            install (asks before changing anything)
. "$(dirname "$0")/scripts/fb5-env.sh"
. "$FB5_DIR/versions.env"
CHECK=0
[ "$1" = "--check" ] && CHECK=1
BAUD=500000
APT="git curl make python3-numpy python3-pil python3-serial python3-venv
 xvfb xdotool libxtst6 gcc-arm-none-eabi binutils-arm-none-eabi
 libnewlib-arm-none-eabi libgirepository1.0-dev gcc libcairo2-dev
 pkg-config python3-dev gir1.2-gtk-3.0 fonts-nanum fonts-ipafont libmpv-dev
 librsvg2-common libopenjp2-7 libdbus-glib-1-dev autoconf build-essential
 cmake libsystemd-dev"
problems=0
ok()   { echo "  ok    $*"; }
warn() { echo "  WARN  $*"; }
fail() { echo "  FAIL  $*"; problems=$((problems + 1)); }

echo "== Checks"
[ "$(id -u)" != 0 ] && ok "running as $USER" \
    || fail "run as your normal user, not root (sudo is asked when needed)"
if [ -d "$KLIPPER_DIR/.git" ]; then
    ok "Klipper: $KLIPPER_DIR ($(git -C "$KLIPPER_DIR" describe --always --tags 2>/dev/null))"
    if [ -n "$(git -C "$KLIPPER_DIR" status --porcelain --untracked-files=no)" ]; then
        fail "Klipper has local changes (git -C $KLIPPER_DIR status): commit or stash them first"
    fi
else
    fail "no Klipper git checkout in $KLIPPER_DIR (set KLIPPER_DIR in fb5.conf)"
fi
if [ -f "$PRINTER_CFG" ]; then
    ok "printer.cfg: $PRINTER_CFG"
    serial=$(python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG" --serial 2>&1)
    case "$serial" in
        /dev/ttyAMA*|/dev/serial0) ok "[mcu] serial: $serial (Pi UART)";;
        /dev/ttyS0) warn "[mcu] serial: /dev/ttyS0 is the Pi mini UART, unreliable at high speed; use the PL011 UART (dtoverlay=disable-bt, /dev/ttyAMA0)";;
        *usb*|*USB*|*ACM*) fail "[mcu] serial: $serial - this project needs the Pi UART (GPIO14/15) wired to the board Wi-Fi header, see README";;
        *) fail "[mcu] serial: $serial - expected a Pi UART like /dev/ttyAMA0";;
    esac
    ok "[mcu] baud now: $(python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG" 2>&1)"
else
    fail "no $PRINTER_CFG (set CONFIG_DIR in fb5.conf)"
fi
s=$(klippy_state)
[ -n "$s" ] && ok "Moonraker answers, klippy: $s" || warn "Moonraker does not answer at $MOONRAKER"
case "$(print_state)" in printing|paused) fail "the printer is printing";; esac
if systemctl is-enabled KlipperScreen >/dev/null 2>&1; then
    warn "KlipperScreen.service (HDMI/DSI screen) is enabled: it will be disabled, this project runs KlipperScreen itself"
fi
[ -d "$KS_DIR" ] && ok "KlipperScreen: $KS_DIR (kept as is)" \
    || ok "KlipperScreen: not installed, will be cloned ($KS_COMMIT)"
[ -x "$HOME/klippy-env/bin/python" ] && ok "klippy-env: $("$HOME/klippy-env/bin/python" --version 2>&1)"

echo
echo "== What install.sh will do"
echo "  1. sudo apt-get install the packages for Xvfb, KlipperScreen, the firmware build"
echo "  2. switch $KLIPPER_DIR to $KLIPPER_REPO ($KLIPPER_BRANCH);"
echo "     the current branch/commit is saved for uninstall.sh"
echo "  3. clone Katapult ($KATAPULT_BRANCH) to $KATAPULT_DIR"
echo "  4. KlipperScreen: clone if missing, build its venv ($KS_ENV), patch the camera panel"
echo "  5. printer.cfg (backup in $FB5_STATE): [include fb5-display.cfg], [mcu] baud: $BAUD"
echo "  6. build the firmware SD image: firmware/$BAUD/Robin_nano35.bin"
echo "  7. autostart: crontab @reboot -> scripts/ks-start.sh, loginctl enable-linger"
if [ $CHECK = 1 ]; then
    echo
    [ $problems = 0 ] && echo "check passed - nothing was changed" \
        || echo "$problems problem(s) - nothing was changed"
    exit 0
fi
[ $problems = 0 ] || { echo; echo "fix the problems above first"; exit 1; }
echo
read -r -p "Continue? [y/N] " answer
[ "$answer" = y ] || [ "$answer" = Y ] || exit 1
set -e
mkdir -p "$FB5_STATE"

echo "== 1. packages"
sudo apt-get update
sudo apt-get install -y $APT

echo "== 2. Klipper"
if [ ! -f "$FB5_STATE/klipper-orig" ]; then
    git -C "$KLIPPER_DIR" symbolic-ref -q --short HEAD > "$FB5_STATE/klipper-orig" \
        || git -C "$KLIPPER_DIR" rev-parse HEAD > "$FB5_STATE/klipper-orig"
fi
git -C "$KLIPPER_DIR" fetch "$KLIPPER_REPO" "$KLIPPER_BRANCH"
git -C "$KLIPPER_DIR" checkout -B fb5-native-display FETCH_HEAD
echo "Klipper now: $(git -C "$KLIPPER_DIR" describe --always --tags) (was: $(cat "$FB5_STATE/klipper-orig"))"

echo "== 3. Katapult"
if [ -d "$KATAPULT_DIR/.git" ]; then
    git -C "$KATAPULT_DIR" fetch "$KATAPULT_REPO" "$KATAPULT_BRANCH"
    git -C "$KATAPULT_DIR" checkout -B fb5-native-display FETCH_HEAD
else
    git clone -b "$KATAPULT_BRANCH" "$KATAPULT_REPO" "$KATAPULT_DIR"
fi

echo "== 4. KlipperScreen"
if [ ! -d "$KS_DIR" ]; then
    git clone "$KS_REPO" "$KS_DIR"
    git -C "$KS_DIR" checkout -q "$KS_COMMIT"
    touch "$FB5_STATE/ks-cloned"
fi
[ -x "$KS_ENV/bin/python" ] || python3 -m venv "$KS_ENV"
"$KS_ENV/bin/pip" install -U pip setuptools wheel
"$KS_ENV/bin/pip" install -r "$KS_DIR/scripts/KlipperScreen-requirements.txt"
"$KS_ENV/bin/python" -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk; print("GTK OK")'
if systemctl is-enabled KlipperScreen >/dev/null 2>&1; then
    sudo systemctl disable --now KlipperScreen
    touch "$FB5_STATE/ks-service-disabled"
fi
python3 "$FB5_SCRIPTS/patch_ks_camera.py" "$KS_DIR/panels/camera.py" \
    || echo "WARN: camera panel not patched - the camera works, but full size (slower)"

echo "== 5. printer.cfg"
cp "$PRINTER_CFG" "$FB5_STATE/printer.cfg.before-install-$(date +%Y%m%d-%H%M%S)"
[ -f "$FB5_STATE/baud-orig" ] \
    || python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG" > "$FB5_STATE/baud-orig"
[ -f "$CONFIG_DIR/fb5-display.cfg" ] || cp "$FB5_DIR/config/fb5-display.cfg" "$CONFIG_DIR/"
python3 - "$PRINTER_CFG" <<"PY"
import sys
path = sys.argv[1]
text = open(path).read()
line = "[include fb5-display.cfg]"
if line not in text.split("\n"):
    # before the SAVE_CONFIG block, which must stay at the end
    marker = "#*# <---------------------- SAVE_CONFIG"
    pos = text.find(marker)
    if pos < 0:
        text = text.rstrip("\n") + "\n\n" + line + "\n"
    else:
        text = text[:pos] + line + "\n\n" + text[pos:]
    open(path, "w").write(text)
    print("added", line)
PY
# Only on the first install: on a re-run the MCU may already run the FB5
# firmware at another speed (set-baud.sh)
if [ ! -f "$FB5_STATE/baud-set" ]; then
    python3 "$FB5_SCRIPTS/set-mcu-baud.py" "$PRINTER_CFG" $BAUD
    touch "$FB5_STATE/baud-set"
fi
[ -f "$FB5_DIR/touch-cal.json" ] || cp "$FB5_DIR/config/touch-cal.json" "$FB5_DIR/"

echo "== 6. firmware"
"$FB5_SCRIPTS/build-firmware.sh" $BAUD --sd

echo "== 7. autostart"
chmod +x "$FB5_SCRIPTS"/*.sh
( crontab -l 2>/dev/null | grep -v "/scripts/ks-start.sh" || true
  echo "@reboot sleep 20 && $FB5_SCRIPTS/ks-start.sh > $FB5_LOGS/ks-start.log 2>&1" ) | crontab -
# Without linger, systemd-logind removes the user's /dev/shm files (the
# Xvfb framebuffer) when the last session closes
loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER"

cat <<EOF

== Done. Next steps:
 1. Copy $FB5_DIR/firmware/$BAUD/Robin_nano35.bin to the root of a FAT32
    SD card (exactly this file name), put it into the printer board and
    power the printer on. The MKS bootloader flashes it (the screen shows
    a progress bar) and renames the file to ROBIN_NANO35.CUR.
 2. Klipper should connect at $BAUD baud and initialize the display
    (check Mainsail/Fluidd or klippy.log).
 3. Start the screen: $FB5_SCRIPTS/ks-start.sh (or reboot the Pi).
 4. If touches land in the wrong place: stop the screen
    ($FB5_SCRIPTS/ks-start.sh stop), run python3 $FB5_SCRIPTS/fb5-touch-cal.py,
    then start the screen again.
Do not update Klipper through Moonraker: that switches it back to upstream
Klipper without the display driver. Undo everything: ./uninstall.sh
EOF
