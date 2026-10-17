#!/usr/bin/env python3
# Patch KlipperScreen's camera panel: shrink the video to the area fraction
# given by the FB5_CAMERA_AREA environment variable (set in ks-loop.sh).
# mpv fills the rest with black, which fb5-mirror never resends (unchanged)
# and which costs the MCU nothing. Idempotent.
# Usage: patch_ks_camera.py [~/KlipperScreen/panels/camera.py]
import os, sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/KlipperScreen/panels/camera.py")
src = open(path).read()
if "FB5_CAMERA_AREA" in src:
    print("already patched")
    sys.exit(0)

anchor_import = "import logging\n"
anchor_mpv = ('        self.mpv = mpv.MPV(fullscreen=True, log_handler=self.log, '
              'vo="gpu,wlshm,xv,x11")\n')
if anchor_import not in src or anchor_mpv not in src:
    sys.exit("camera.py changed upstream - anchors not found, not patched")

zoom = (
    "\n"
    "        # FB5: shrink the picture to FB5_CAMERA_AREA of its area; the black\n"
    "        # border is free on the mirrored display link\n"
    "        with suppress(Exception):\n"
    "            area = float(os.environ.get(\"FB5_CAMERA_AREA\", \"1\"))\n"
    "            if 0 < area < 1:\n"
    "                self.mpv.video_zoom = math.log2(area) / 2\n"
    "                logging.info(f\"FB5 camera area {area}\")\n"
)
src = src.replace(anchor_import, "import logging\nimport math\nimport os\n", 1)
src = src.replace(anchor_mpv, anchor_mpv + zoom, 1)
open(path, "w").write(src)
print("patched", path)
