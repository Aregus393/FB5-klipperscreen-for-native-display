#!/bin/bash
# Run KlipperScreen on :99 and restart it whenever it exits or crashes.
. "$(dirname "$0")/fb5-env.sh"
export DISPLAY=:99
# KlipperScreen restarts itself (eg, after a font size change) with
# os.execv(sys.executable, ["python"] + argv); a bare "python" in argv[0]
# makes Python locate its environment through PATH, so put the venv first
export PATH=$KS_ENV/bin:$PATH
# Camera picture area fraction (panels/camera.py patched by patch_ks_camera.py)
export FB5_CAMERA_AREA
while true; do
    echo "$(date '+%F %T') starting KlipperScreen" >> "$FB5_LOGS/klipperscreen.log"
    "$KS_ENV/bin/python" "$KS_DIR/screen.py" \
        >> "$FB5_LOGS/klipperscreen.log" 2>&1 < /dev/null
    echo "$(date '+%F %T') KlipperScreen exited ($?), restarting" \
        >> "$FB5_LOGS/klipperscreen.log"
    sleep 2
done
