#!/usr/bin/env python3
# Feed the FB5 XPT2046 touch (fsmc_touch/read over the Klipper API) into
# an X display as mouse events (XTest), using fb5-touch-cal.py's mapping.
# Usage: fb5-touch.py [--display :99] [--cal <repo>/touch-cal.json]
import argparse, ctypes, json, os, statistics, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
KlippyAPI = import_module("fb5-mirror").KlippyAPI

W, H = 480, 320


class XTest:
    def __init__(self, display):
        self.x11 = ctypes.CDLL("libX11.so.6")
        self.xtst = ctypes.CDLL("libXtst.so.6")
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.xtst.XTestFakeMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_ulong]
        self.xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.dpy = self.x11.XOpenDisplay(display.encode())
        if not self.dpy:
            raise SystemExit("cannot open X display %s" % display)

    def move(self, x, y):
        self.xtst.XTestFakeMotionEvent(self.dpy, -1, x, y, 0)
        self.x11.XFlush(self.dpy)

    def button(self, down):
        self.xtst.XTestFakeButtonEvent(self.dpy, 1, 1 if down else 0, 0)
        self.x11.XFlush(self.dpy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", default=":99")
    ap.add_argument("--cal", default=os.path.join(
        import_module("fb5-mirror").FB5_DIR, "touch-cal.json"))
    ap.add_argument("--socket", help="Klipper API socket (default: found)")
    ap.add_argument("--rate", type=float, default=50.)
    ap.add_argument("--debounce", type=int, default=2)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    cal = json.load(open(args.cal))
    (ax, bx), (ay, by) = cal["x"], cal["y"]

    def to_screen(r):
        rx, ry = (r["y"], r["x"]) if cal["swap_xy"] else (r["x"], r["y"])
        return (min(W - 1, max(0, int(round(ax * rx + bx)))),
                min(H - 1, max(0, int(round(ay * ry + by)))))

    x = XTest(args.display)
    api = None
    down = False
    on = off = 0
    hist = []
    while True:
        t0 = time.monotonic()
        try:
            if api is None:
                api = KlippyAPI(args.socket)
            r = api.call("fsmc_touch/read", {})
        except (OSError, RuntimeError) as e:
            if down:
                x.button(False)
                down = False
            print("klippy API error: %s - retrying" % (e,), flush=True)
            api = None
            time.sleep(2.)
            continue
        if r["pressed"]:
            on += 1
            off = 0
            hist = (hist + [to_screen(r)])[-3:]
            px = int(statistics.median(p[0] for p in hist))
            py = int(statistics.median(p[1] for p in hist))
            if not down and on >= args.debounce:
                x.move(px, py)
                x.button(True)
                down = True
                if args.verbose:
                    print("down %d,%d" % (px, py), flush=True)
            elif down:
                x.move(px, py)
        else:
            off += 1
            on = 0
            if down and off >= args.debounce:
                x.button(False)
                down = False
                hist = []
                if args.verbose:
                    print("up", flush=True)
            elif not down:
                hist = []
        time.sleep(max(0., t0 + 1. / args.rate - time.monotonic()))


if __name__ == "__main__":
    main()
