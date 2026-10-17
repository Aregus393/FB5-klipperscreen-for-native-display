#!/usr/bin/env python3
# Log printer/link health every few seconds during a print and flag
# problems. Exits when the print ends (complete/cancelled/error) or klippy
# shuts down. Output: <repo>/logs/print-monitor.log (+ stdout)
# Usage: print-monitor.py [--interval 5] [--wait-start 1800]
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
mirror = import_module("fb5-mirror")
KlippyAPI = mirror.KlippyAPI

ap = argparse.ArgumentParser()
ap.add_argument("--interval", type=float, default=5.)
ap.add_argument("--wait-start", type=float, default=1800.,
                help="give up if no print starts within this time")
ap.add_argument("--retransmit-alert", type=int, default=200,
                help="bytes retransmitted per interval that raise an alert")
args = ap.parse_args()

os.makedirs(os.path.join(mirror.FB5_DIR, "logs"), exist_ok=True)
LOG = os.path.join(mirror.FB5_DIR, "logs", "print-monitor.log")
logf = open(LOG, "a")
def out(msg, alert=False):
    line = "%s %s%s" % (time.strftime("%H:%M:%S"), "ALERT " if alert else "", msg)
    logf.write(line + "\n")
    logf.flush()
    print(line, flush=True)

OBJS = {"webhooks": ["state", "state_message"],
        "print_stats": ["state", "filename", "print_duration", "message"],
        "virtual_sdcard": ["progress"],
        "mcu": ["last_stats"],
        "extruder": ["temperature", "target"],
        "heater_bed": ["temperature", "target"],
        "system_stats": ["sysload"]}

api = None
start = time.monotonic()
seen_printing = False
last = None
last_se = None
alerts = 0
out("monitor started")
while True:
    try:
        if api is None:
            api = KlippyAPI()
        st = api.call("objects/query", {"objects": OBJS})["status"]
    except Exception as e:
        out("klippy API unavailable: %s" % (e,), alert=True)
        alerts += 1
        api = None
        time.sleep(args.interval)
        if time.monotonic() - start > args.wait_start and not seen_printing:
            break
        continue
    ks, ps = st["webhooks"]["state"], st["print_stats"]["state"]
    m = st["mcu"]["last_stats"]
    try:
        se = api.call("fsmc_display/serial_errors", {})
    except Exception:
        se = None
    if last is not None:
        d_rt = m["bytes_retransmit"] - last["bytes_retransmit"]
        d_inv = m["bytes_invalid"] - last["bytes_invalid"]
    else:
        d_rt = d_inv = 0
    last = m
    # mcu side receive errors (Pi -> mcu direction), if the firmware has them
    se_txt = ""
    if se is not None:
        if last_se is not None:
            d_se = [se[k] - last_se[k] for k in ("noise", "frame", "overrun")]
            se_txt = " | mcu rx ne+%d fe+%d ore+%d" % tuple(d_se)
            if any(d_se):
                out("mcu rx errors: noise+%d frame+%d overrun+%d" % tuple(d_se),
                    alert=True)
                alerts += 1
        last_se = se
    out("klippy=%s print=%s %.1f%% %s | E %.0f/%.0f B %.0f/%.0f | mcu_awake=%.3f"
        " rt+%d inv+%d srtt=%.4f | sysload=%.2f"
        % (ks, ps, 100. * st["virtual_sdcard"]["progress"],
           st["print_stats"]["filename"] or "-",
           st["extruder"]["temperature"], st["extruder"]["target"],
           st["heater_bed"]["temperature"], st["heater_bed"]["target"],
           m.get("mcu_awake", 0.), d_rt, d_inv, m.get("srtt", 0.),
           st["system_stats"]["sysload"]) + se_txt)
    if ks != "ready":
        out("klippy state %s: %s" % (ks, st["webhooks"]["state_message"]
                                      .strip().splitlines()[0]), alert=True)
        alerts += 1
        break
    if d_rt > args.retransmit_alert or d_inv:
        out("link: %d bytes retransmitted, %d invalid in %.0fs"
            % (d_rt, d_inv, args.interval), alert=True)
        alerts += 1
    if ps in ("printing", "paused"):
        seen_printing = True
    elif seen_printing:
        out("print ended: %s %s" % (ps, st["print_stats"]["message"]),
            alert=(ps != "complete"))
        break
    elif time.monotonic() - start > args.wait_start:
        out("no print started within %.0fs" % (args.wait_start,))
        break
    time.sleep(args.interval)
out("monitor finished, %d alert(s)" % (alerts,))
