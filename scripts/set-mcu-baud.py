#!/usr/bin/env python3
# Print or set the "baud" option of the main [mcu] section in printer.cfg,
# or print its "serial" option.
# Usage: set-mcu-baud.py <printer.cfg> [new_baud | --serial]
import re, sys

path = sys.argv[1]
lines = open(path).read().split("\n")
start = next((i for i, l in enumerate(lines) if l.strip() == "[mcu]"), None)
if start is None:
    sys.exit("no [mcu] section in %s (in an included file?)" % (path,))
end = next((i for i in range(start + 1, len(lines))
            if lines[i].startswith("[")), len(lines))

def find(option):
    return next((i for i in range(start + 1, end)
                 if re.match(r"%s\s*[:=]" % (option,), lines[i])), None)

def value(idx):
    return re.split(r"[:=]", lines[idx], 1)[1].split("#")[0].strip()

baud_idx = find("baud")
if len(sys.argv) < 3:
    print(250000 if baud_idx is None else int(value(baud_idx)))
    sys.exit(0)
if sys.argv[2] == "--serial":
    serial_idx = find("serial")
    if serial_idx is None:
        sys.exit("no serial option in [mcu]")
    print(value(serial_idx))
    sys.exit(0)
new = "baud: %d" % (int(sys.argv[2]),)
if baud_idx is not None:
    lines[baud_idx] = new
else:
    lines.insert(find("serial") + 1, new)
open(path, "w").write("\n".join(lines))
print("set", new)
