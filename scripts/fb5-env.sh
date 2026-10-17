# Common paths and settings of the FB5 display scripts (sourced, not run).
# Local overrides go to <repo>/fb5.conf (written by install.sh).
FB5_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
FB5_SCRIPTS=$FB5_DIR/scripts
FB5_LOGS=$FB5_DIR/logs
FB5_STATE=$FB5_DIR/state
CONFIG_DIR=$HOME/printer_data/config
KLIPPER_DIR=$HOME/klipper
KS_DIR=$HOME/KlipperScreen
KS_ENV=$HOME/.KlipperScreen-env
KATAPULT_DIR=$FB5_DIR/katapult
MOONRAKER=localhost:7125
# Camera picture area fraction (1 = full screen) and the display stream
# limit while printing in KiB/s (0 = no limit)
FB5_CAMERA_AREA=0.5
FB5_PRINT_RATE=64
[ -f "$FB5_DIR/fb5.conf" ] && . "$FB5_DIR/fb5.conf"
PRINTER_CFG=$CONFIG_DIR/printer.cfg
mkdir -p "$FB5_LOGS"

# Print the Klipper print state (standby, printing, paused, ...) or nothing
print_state() {
    curl -s -m 5 "$MOONRAKER/printer/objects/query?print_stats=state" \
        | grep -o '"state": *"[a-z]*"' | grep -o '[a-z]*"$' | tr -d '"'
}

# Print the klippy state (ready, startup, shutdown, error) or nothing
klippy_state() {
    curl -s -m 5 "$MOONRAKER/printer/info" \
        | grep -o '"state": *"[a-z]*"' | grep -o '[a-z]*"$' | tr -d '"'
}

refuse_while_printing() {
    local s
    s=$(print_state)
    case "$s" in printing|paused)
        echo "printer is $s - refusing to continue"; exit 1;;
    esac
}
