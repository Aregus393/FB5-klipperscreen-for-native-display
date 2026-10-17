#!/usr/bin/env python3
# Motion stress test: home, go to the middle of the axis ranges, then run
# circles where X, Y, Z (helix) and the extruder all move together, while
# the link and MCU load are sampled. Use with the filament unloaded.
# Usage: fb5-motion-test.py --speed 150 --accel 7200 --circles 20
import argparse, math, os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
KlippyAPI = import_module("fb5-mirror").KlippyAPI

ap = argparse.ArgumentParser()
ap.add_argument("--speed", type=float, default=150.)
ap.add_argument("--accel", type=float, default=7200.)
ap.add_argument("--path", choices=["circles", "lines"], default="circles",
                help="lines: long diagonals/sides that reach full speed")
ap.add_argument("--margin", type=float, default=10.)
ap.add_argument("--circles", type=int, default=20,
                help="number of circles (or line cycles)")
ap.add_argument("--radius", type=float, default=90.)
ap.add_argument("--segments", type=int, default=72)
ap.add_argument("--z", type=float, default=20., help="helix middle height")
ap.add_argument("--z-amp", type=float, default=2.)
ap.add_argument("--e-ratio", type=float, default=0.033,
                help="extruder mm per mm of XY travel (0 = no extrusion)")
ap.add_argument("--hotend", type=float, default=0.,
                help="heat the extruder to this temperature first (M109)")
ap.add_argument("--no-endstop-check", action="store_true",
                help="skip the X/Y endstop trigger measurement before/after")
ap.add_argument("--socket", help="Klipper API socket (default: found)")
args = ap.parse_args()

api = KlippyAPI(args.socket)
def query(objs):
    return api.call("objects/query", {"objects": objs})["status"]
def gcode(script):
    api.call("gcode/script", {"script": script})

STEP = 0.025            # 4 microsteps at 160 steps/mm

def trigger_position(axis):
    # Approach the min endstop of axis ("x"/"y") in small steps from 1.5mm
    # away down to position_min and return where it triggers. The fast
    # single pass homing leaves the switch point ~0.2-0.3mm above the min,
    # so no coordinate shift (SET_KINEMATIC_POSITION needs force_move) is
    # needed. Coordinates are not touched: before/after use the same homing.
    idx = "xyz".index(axis)
    st = query({"toolhead": ["axis_minimum"]})["toolhead"]
    amin_ax = st["axis_minimum"][idx]
    A = axis.upper()
    p = amin_ax + 1.5
    gcode("G90\nG1 %s%.3f F600\nM400" % (A, p))
    while True:
        status = api.call("query_endstops/status", {})
        if status["stepper_" + axis].lower() == "triggered":
            found = p
            break
        if p - STEP < amin_ax - 1e-6:
            found = None            # not triggered down to position_min
            break
        p -= STEP
        gcode("G1 %s%.3f F60\nM400" % (A, p))
    gcode("G1 %s%.3f F600\nM400" % (A, amin_ax + 5.))
    return found

def endstop_report(label):
    res = {}
    for axis in "xy":
        res[axis] = trigger_position(axis)
        print("%s: %s endstop triggers at %s" % (
            label, axis.upper(), "NOT FOUND (below position_min)"
            if res[axis] is None else "%.3f" % res[axis]), flush=True)
    return res

th = query({"toolhead": ["max_velocity", "max_accel"]})["toolhead"]
orig = (th["max_velocity"], th["max_accel"])
if args.hotend:
    print("heating extruder to %.0f..." % (args.hotend,), flush=True)
    gcode("M109 S%.0f" % (args.hotend,))
print("homing...", flush=True)
gcode("G28")
th = query({"toolhead": ["axis_minimum", "axis_maximum"]})["toolhead"]
amin, amax = th["axis_minimum"], th["axis_maximum"]
cx, cy = (amin[0] + amax[0]) / 2., (amin[1] + amax[1]) / 2.
r = args.radius
if (cx - r < amin[0] or cx + r > amax[0] or cy - r < amin[1]
        or cy + r > amax[1]):
    sys.exit("radius %.0f does not fit around %.1f,%.1f" % (r, cx, cy))
print("center X%.1f Y%.1f Z%.1f" % (cx, cy, args.z), flush=True)
before = None
if not args.no_endstop_check:
    gcode("G90\nG0 Z%.2f F600" % (args.z,))
    before = endstop_report("before")

f = args.speed * 60.
seg_len = 2. * r * math.sin(math.pi / args.segments)
lines = []
for c in range(args.circles):
    for i in range(1, args.segments + 1):
        a = 2. * math.pi * i / args.segments
        z = args.z + args.z_amp * math.sin(a)
        e = " E%.4f" % (seg_len * args.e_ratio,) if args.e_ratio else ""
        lines.append("G1 X%.2f Y%.2f Z%.3f%s F%.0f"
                     % (cx + r * math.cos(a), cy + r * math.sin(a), z, e, f))
length = seg_len * args.segments * args.circles
start_xy = (cx + r, cy)
if args.path == "lines":
    # Corners, diagonals and sides; Z alternates on every move
    x0, x1 = amin[0] + args.margin, amax[0] - args.margin
    y0, y1 = amin[1] + args.margin, amax[1] - args.margin
    za, zb = args.z, args.z + args.z_amp
    pts = [(x1, y1, zb), (x1, y0, za), (x0, y1, zb), (x0, y0, za),
           (x1, y0, zb), (x1, y1, za), (x0, y1, zb), (x0, y0, za)]
    lines, length, prev = [], 0., (x0, y0)
    for c in range(args.circles):
        for x, y, z in pts:
            d = ((x - prev[0]) ** 2 + (y - prev[1]) ** 2) ** .5
            e = " E%.4f" % (d * args.e_ratio,) if args.e_ratio else ""
            lines.append("G1 X%.2f Y%.2f Z%.3f%s F%.0f" % (x, y, z, e, f))
            length += d
            prev = (x, y)
    start_xy = (x0, y0)
prologue = ["G90", "M83",
            "G0 X%.2f Y%.2f Z%.2f F6000" % (cx, cy, args.z),
            "G0 X%.2f Y%.2f F6000" % start_xy, "M400"]
epilogue = ["G0 X%.2f Y%.2f Z%.2f F6000" % (cx, cy, args.z), "M400"]

# Background sampler on its own API connection
samples, stop = [], threading.Event()
def sampler():
    mon = KlippyAPI(args.socket)
    while not stop.is_set():
        try:
            st = mon.call("objects/query", {"objects": {
                "mcu": ["last_stats"], "webhooks": ["state"],
                "system_stats": ["sysload", "cputime"]}})["status"]
            samples.append((time.monotonic(), st))
        except Exception as e:
            samples.append((time.monotonic(), {"error": str(e)}))
        time.sleep(0.5)

err = None
try:
    gcode("SET_VELOCITY_LIMIT VELOCITY=%.0f ACCEL=%.0f"
          % (args.speed, args.accel))
    gcode("\n".join(prologue))
except Exception as e:
    err = str(e)
t = threading.Thread(target=sampler, daemon=True)
t.start()
start = time.monotonic()
if err is None:
    print("moving: %s x%d, %.0f mm XY path, %.0f mm/s, accel %.0f,"
          " E %.3f mm/mm" % (args.path, args.circles, length, args.speed,
                             args.accel, args.e_ratio), flush=True)
    try:
        gcode("\n".join(lines + epilogue))
    except Exception as e:
        err = str(e)
elapsed = time.monotonic() - start
stop.set()
t.join()
try:
    gcode("SET_VELOCITY_LIMIT VELOCITY=%.0f ACCEL=%.0f" % orig)
except Exception:
    pass
after = None
if before is not None and err is None:
    # Slowly back to the homing corner, then measure the endstops again
    st = query({"toolhead": ["axis_minimum"]})["toolhead"]
    gcode("G90\nG0 X%.2f Y%.2f F1200\nM400" % (
        st["axis_minimum"][0] + 5., st["axis_minimum"][1] + 5.))
    after = endstop_report("after")
    gcode("G28 X Y")            # back to exact homed coordinates

ok = [s for _, s in samples if "mcu" in s]
if not ok:
    sys.exit("no samples collected (%s)" % (err,))
first, last = ok[0]["mcu"]["last_stats"], ok[-1]["mcu"]["last_stats"]
awake = max(s["mcu"]["last_stats"]["mcu_awake"] for s in ok)
load = max(s["system_stats"]["sysload"] for s in ok)
states = sorted(set(s["webhooks"]["state"] for s in ok))
print("result: %s in %.1fs (avg %.0f mm/s incl. accel)"
      % ("ERROR " + err if err else "OK", elapsed, length / elapsed))
print("klippy states seen: %s" % (", ".join(states),))
print("mcu_awake max %.3f, retransmit +%d bytes, invalid +%d, bytes_write +%d,"
      " Pi sysload max %.2f"
      % (awake, last["bytes_retransmit"] - first["bytes_retransmit"],
         last["bytes_invalid"] - first["bytes_invalid"],
         last["bytes_write"] - first["bytes_write"], load))
if before and after:
    for axis in "xy":
        if before[axis] is None or after[axis] is None:
            print("%s endstop: not measured" % (axis.upper(),))
            continue
        d = after[axis] - before[axis]
        print("%s endstop shift after test: %+.3f mm (%+.0f microsteps)%s"
              % (axis.upper(), d, d / 0.00625,
                 "  OK" if abs(d) <= STEP + 1e-6 else "  <-- LOST STEPS?"))
