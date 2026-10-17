#!/bin/bash
# Build the FB5 Klipper firmware (display driver, UART DMA reception) for
# one link speed from the patched ~/klipper. With --sd, also build Katapult
# and the combined SD card image Robin_nano35.bin (MKS bootloader ->
# Katapult at 0x8007000 -> Klipper at 0x8008800).
# Usage: build-firmware.sh <baud> [--sd]
# Output: <repo>/firmware/<baud>/ (klipper.bin, Robin_nano35.bin, SHA256SUMS)
. "$(dirname "$0")/fb5-env.sh"
set -e
BAUD=$1
case "$BAUD" in 250000|500000|1500000|2000000) ;;
    *) echo "usage: build-firmware.sh <250000|500000|1500000|2000000> [--sd]"; exit 1;;
esac
B=$FB5_DIR/firmware/$BAUD
mkdir -p "$B"
sed "s/^CONFIG_SERIAL_BAUD=.*/CONFIG_SERIAL_BAUD=$BAUD/" \
    "$FB5_DIR/config/build/klipper.config" > "$B/klipper.config"
cd "$KLIPPER_DIR"
grep -q WANT_FSMC_LCD src/Kconfig || { echo "$KLIPPER_DIR has no FB5 display driver - run install.sh first"; exit 1; }
echo "building klipper ($BAUD baud) in $B"
make KCONFIG_CONFIG="$B/klipper.config" OUT="$B/out/" olddefconfig >/dev/null
make KCONFIG_CONFIG="$B/klipper.config" OUT="$B/out/" clean >/dev/null
make -j4 KCONFIG_CONFIG="$B/klipper.config" OUT="$B/out/" >/dev/null
cp "$B/out/klipper.bin" "$B/klipper.bin"
if [ "$2" = "--sd" ]; then
    echo "building katapult"
    cd "$KATAPULT_DIR"
    cp "$FB5_DIR/config/build/katapult.config" .config
    make olddefconfig >/dev/null && make clean >/dev/null && make -j4 >/dev/null
    cp out/katapult.bin "$B/katapult.bin"
    python3 - "$B" <<"PY"
import sys, struct
B = sys.argv[1]
c = open(B + "/katapult.bin", "rb").read()
k = open(B + "/klipper.bin", "rb").read()
assert len(c) <= 0x1800, "katapult too big"
sp, rst = struct.unpack("<II", k[:8])
assert 0x08008800 < rst < 0x08080000, hex(rst)
open(B + "/fb5_katapult_klipper.bin", "wb").write(c + b"\xff" * (0x1800 - len(c)) + k)
print("katapult %d B, klipper %d B" % (len(c), len(k)))
PY
    python3 "$KLIPPER_DIR/scripts/update_mks_robin.py" "$B/fb5_katapult_klipper.bin" "$B/Robin_nano35.bin"
fi
cd "$B" && sha256sum *.bin > SHA256SUMS
echo "klipper $(python3 -c "import json; print(json.load(open('$B/out/klipper.dict'))['version'])")"
ls -l "$B"/*.bin
