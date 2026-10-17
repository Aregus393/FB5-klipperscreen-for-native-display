#!/usr/bin/env python3
# Interactive XPT2046 calibration on the FB5 display: press the red
# targets in turn; writes a linear raw->screen mapping as JSON.
# Usage: fb5-touch-cal.py [out.json]
import json, os, statistics, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
mirror = import_module("fb5-mirror")
KlippyAPI = mirror.KlippyAPI

OUT = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(mirror.FB5_DIR, "touch-cal.json")
W, H = 480, 320
TARGETS = [(30, 30), (450, 30), (450, 290), (30, 290), (240, 160)]
api = KlippyAPI()

def gcode(script):
    api.call("gcode/script", {"script": script})

def square(x, y, color, r=8):
    gcode("LCD_FILL COLOR=%s X0=%d Y0=%d X1=%d Y1=%d"
          % (color, x - r, y - r, x + r, y + r))

def read():
    return api.call("fsmc_touch/read", {})

def wait_press(timeout=60.):
    # Average a steady press (skip the first samples), then wait release
    end = time.monotonic() + timeout
    samples = []
    while time.monotonic() < end:
        r = read()
        if r["pressed"]:
            samples.append(r)
        elif len(samples) >= 8:
            break
        else:
            samples = []
        time.sleep(0.02)
    if len(samples) < 8:
        raise SystemExit("no press detected")
    s = samples[3:-2] or samples
    return (statistics.median(p["x"] for p in s),
            statistics.median(p["y"] for p in s),
            statistics.median(p["z1"] for p in s), len(samples))

def fit(raw, scr):
    # Least squares scr = a * raw + b
    n = len(raw)
    mr, ms = sum(raw) / n, sum(scr) / n
    var = sum((r - mr) ** 2 for r in raw)
    a = sum((r - mr) * (s - ms) for r, s in zip(raw, scr)) / var
    return a, ms - a * mr

gcode("LCD_FILL COLOR=000000")
points = []
for tx, ty in TARGETS:
    square(tx, ty, "FF0000")
    rx, ry, z1, n = wait_press()
    square(tx, ty, "00FF00")
    print("target (%3d,%3d): raw x=%6.0f y=%6.0f z1=%5.0f (%d samples)"
          % (tx, ty, rx, ry, z1, n), flush=True)
    points.append((tx, ty, rx, ry))
    time.sleep(0.3)

sx = [p[0] for p in points]; sy = [p[1] for p in points]
rx = [p[2] for p in points]; ry = [p[3] for p in points]
# Which raw axis follows the screen x axis?
def corr(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** .5
    return num / den
swap = abs(corr(ry, sx)) > abs(corr(rx, sx))
if swap:
    rx, ry = ry, rx
ax, bx = fit(rx, sx)
ay, by = fit(ry, sy)
err = max(max(abs(ax * r + bx - s) for r, s in zip(rx, sx)),
          max(abs(ay * r + by - s) for r, s in zip(ry, sy)))
cal = {"swap_xy": swap, "x": [ax, bx], "y": [ay, by], "max_error_px": err}
json.dump(cal, open(OUT, "w"), indent=1)
print("calibration: %s -> %s" % (json.dumps(cal), OUT))
gcode("LCD_FILL COLOR=000000")
