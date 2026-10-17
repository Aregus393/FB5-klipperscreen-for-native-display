# KlipperScreen on the native display of the Flying Bear Ghost 5

**English** | [Русский](README.ru.md)

Run the full [KlipperScreen](https://github.com/KlipperScreen/KlipperScreen) touch UI on the **stock 3.5" touch screen** of the Flying Bear Ghost 5 under Klipper: no extra display, no HDMI screen, no adapter board, no rewiring of the screen. The original screen stays on its original ribbon cable; the Raspberry Pi renders KlipperScreen and the printer's own MCU draws it on the panel.

[![Video: KlipperScreen on the stock Flying Bear Ghost 5 display](docs/media/video-thumb.jpg)](https://www.youtube.com/watch?v=BQfQFEFxjDU)

▶ **Video:** https://www.youtube.com/watch?v=BQfQFEFxjDU

> [!WARNING]
> **Status: works on the author's printer, the installer is untested.**
> The display driver, the screen mirroring and the touch have run on one Ghost 5 for real prints (Benchy, OrcaCube) at 500k, 1.5M and 2M baud.
> `install.sh`, `uninstall.sh` and `set-baud.sh` were written **after** that, from the steps done by hand, and **have never been run on a clean system**. Expect to fix something.
>
> **Strongly recommended: do the installation together with an AI coding assistant** (Claude Code, Codex, Cursor, ...) that can run commands on your Pi over SSH, read the scripts and the logs and fix what breaks. The author built this whole project from zero that way, without prior embedded experience. You flash your printer's firmware at your own risk.

![Flying Bear Ghost 5 running KlipperScreen on its native display](docs/media/hero.jpg)

| Menu | Temperature | Printing | Camera |
|---|---|---|---|
| ![](docs/media/screen-menu.png) | ![](docs/media/screen-temp.png) | ![](docs/media/screen-job.png) | ![](docs/media/screen-camera.png) |

## Hardware

| Part | What it is |
|---|---|
| Printer | Flying Bear Ghost 5 |
| Main board | stock **Flying Bear Reborn V2.0**, a clone of the **MKS Robin Nano 1.x**; MCU **STM32F103VET6** (512 KB flash, 64 KB RAM). A genuine Robin Nano V1.1/V1.2 should work the same way (untested) |
| Screen | stock 3.5" **480x320** TFT, controller **ILI9488**, **16-bit parallel bus (FSMC)**; compatible with the MKS Robin TFT35 module |
| Touch | resistive, XPT2046-compatible (HR2046) on SPI2; no interrupt line, polled |
| Host | Raspberry Pi (author: Pi 4 B, Raspberry Pi OS bullseye 32-bit, FluiddPi image) |
| Link Pi ↔ MCU | UART: Pi GPIO14/15 ↔ the board's Wi-Fi module header (USART1, PA9/PA10) |

Keywords: Flying Bear Ghost 5, FB5, Flying Bear Reborn V2.0, MKS Robin Nano v1.1 / v1.2, MKS Robin TFT35, TFT35, ILI9488, XPT2046, FSMC, STM32F103, Klipper, KlipperScreen, native display, stock screen, original touchscreen.

## How it works

```
Raspberry Pi                                      Robin Nano board (Klipper MCU)
┌───────────────────────────────┐   UART        ┌──────────────────────────────┐
│ KlipperScreen on Xvfb 480x320 │  500k–2M baud │ fsmc_lcd: RLE decode → FSMC  │──▶ ILI9488 screen
│ fb5-mirror: changed areas,RLE ├──────────────▶│ (+ normal Klipper: steppers, │
│ fb5-touch: touch → X events   │◀──────────────┤   heaters, endstops...)      │◀── XPT2046 touch
└───────────────────────────────┘               └──────────────────────────────┘
```

- KlipperScreen runs on the Pi on a virtual 480x320 X display (Xvfb).
- `fb5-mirror` sends only the changed parts of the picture, run-length encoded, through Klipper's own API and the normal Pi ↔ MCU link.
- The Klipper firmware gets a small **FSMC display driver** (`fsmc_lcd`) and a **touch reader**; the host gets the `[fsmc_display]` and `[fsmc_touch]` modules. `fb5-touch` turns touches into mouse clicks.
- Display traffic always has the **lowest priority**: step and heater commands are never delayed by the screen. While printing, the screen stream is capped (64 KiB/s by default), which is why the camera view is slower during a print.
- **DMA reception** on the MCU UART keeps high baud rates reliable while all motors are moving.
- **Katapult** is chained after the MKS bootloader, so after the first SD card flash the firmware can be updated over the UART.

## Performance

![250k vs 500k vs 2M baud](docs/media/performance.jpg)

| | 250k baud (Klipper default) | **500k baud** (default here) | 2M baud (shielded cable) |
|---|---|---|---|
| Main screen live update | 0.12 s | 0.06 s | 0.03 s |
| Full KlipperScreen redraw | 1.2 s | 0.62 s | 0.20 s |
| Webcam while printing | 0.16 FPS | 0.3 FPS | 0.5 FPS |
| Webcam when idle | 0.16 FPS | 0.3 FPS | 1.0 FPS |
| Touch → new screen shown | 1.4 s | 0.8 s | 0.35 s |

2M was measured on the printer; 250k and 500k are calculated from the measured link throughput (20.6 KiB/s at 250k, ~42 KB/s at 500k, ~165 KB/s at 2M).

## Requirements

- Klipper already running on the Ghost 5 with a Raspberry Pi, **connected over the Pi UART** (GPIO14/15, `/dev/ttyAMA0`) to the board's Wi-Fi header, **not over USB**. The author's `/boot/config.txt` has `enable_uart=1` and `dtoverlay=uart0`; the more common way to get the full PL011 UART on GPIO14/15 is `dtoverlay=disable-bt`.
- Wires: TX ↔ RX crossed, plus GND. Plain wires are fine for 500k. For 1.5M / 2M use a **shielded** 2-core cable: TX and RX on the cores, the shield as GND at both ends, routed away from motor and heater wires.
- A FAT32 SD card for the first firmware flash.
- `printer.cfg` in `~/printer_data/config` (KIAUH / MainsailOS / FluiddPi layout) with the `[mcu]` section in it. Other paths: see `scripts/fb5-env.sh` and put overrides into `fb5.conf`.

| Inside the author's printer | UART wires on the Pi GPIO | The stock screen ribbon (untouched) |
|---|---|---|
| ![](docs/media/inside.jpg) | ![](docs/media/wiring.jpg) | ![](docs/media/stock-ribbon.jpg) |

## Installation

On the Pi (not as root):

```bash
git clone https://github.com/Aregus393/FB5-klipperscreen-for-native-display.git
cd FB5-klipperscreen-for-native-display
./install.sh --check     # checks your setup and shows what will change; changes nothing
./install.sh             # asks before doing anything, sudo is needed for apt
```

`install.sh`:

1. installs the apt packages (Xvfb, KlipperScreen dependencies, the ARM compiler);
2. switches `~/klipper` to the branch [`fb5-native-display` of Aregus393/klipper](https://github.com/Aregus393/klipper/tree/fb5-native-display) (Klipper + the display driver; the previous branch is saved for `uninstall.sh`);
3. clones [Katapult with the MKS chaining patches](https://github.com/Aregus393/katapult/tree/fb5-native-display);
4. installs KlipperScreen if it is missing (with its own venv) and patches its camera panel to use half of the screen area; a KlipperScreen service for an HDMI screen is disabled;
5. adds `[include fb5-display.cfg]` to `printer.cfg` and sets `[mcu] baud: 500000` (backup in `state/`);
6. builds the firmware SD image `firmware/500000/Robin_nano35.bin`;
7. sets up autostart (crontab `@reboot`).

Then:

1. **Flash the MCU from SD.** Copy `firmware/500000/Robin_nano35.bin` (or `Robin_nano35.bin` from `fb5-firmware-500k.zip` in the [release](../../releases)) to the root of a FAT32 SD card, insert it into the board and power the printer on. The MKS bootloader flashes it and renames it to `ROBIN_NANO35.CUR`. The MKS bootloader itself is never touched.
2. Klipper connects at 500000 baud and initializes the display.
3. Start the screen: `scripts/ks-start.sh` (or reboot the Pi). KlipperScreen needs ~30 s to connect to Moonraker.
4. If touches miss: `scripts/ks-start.sh stop`, `python3 scripts/fb5-touch-cal.py` (press the red targets), `scripts/ks-start.sh`.

> [!IMPORTANT]
> Do not update Klipper through Moonraker / Mainsail / Fluidd: that switches `~/klipper` back to upstream Klipper without the display driver.

## Changing the link speed

500 000 baud is the default: proven with real prints on plain wires, zero transmission errors with all motors moving. Faster is much nicer for the screen, but needs a shielded cable — **at your own risk**:

```bash
./set-baud.sh 2000000      # or 1500000, or back to 500000
```

It builds the firmware for that speed, flashes it over the UART (Katapult) and changes `printer.cfg`. Only 250000, 500000, 1500000 and 2000000 are allowed: they divide evenly on both the MCU and the Pi; the MCU can't go above 2 250 000. Ready-made firmware for 500k, 1.5M and 2M is in the [release](../../releases).

Checks (no heating; unload the filament): `python3 scripts/fb5-motion-test.py --speed 150 --accel 5000 --circles 8 --e-ratio 0` (all motors in circles, reports link errors), `scripts/link-test.sh` (full-screen transfer speed and errors; run `scripts/mirror-restart.sh` afterwards), `scripts/print-monitor.py` (start before a print, logs link health until it ends), G-code `SERIAL_ERRORS` (UART receive errors on the MCU).

If Klipper does not connect after a speed change, flash the 500k SD image as in the installation and run `python3 scripts/set-mcu-baud.py ~/printer_data/config/printer.cfg 500000`.

## Everyday use

| Situation | What to do |
|---|---|
| Garbage or an old picture on the screen, KlipperScreen itself works | `scripts/mirror-restart.sh` (safe while printing) |
| KlipperScreen hangs | restart the whole screen stack (not while printing): `scripts/ks-start.sh stop`, then `setsid nohup scripts/ks-start.sh > logs/ks-start.log 2>&1 < /dev/null &` |
| After updating KlipperScreen | `python3 scripts/patch_ks_camera.py`, then restart the stack |
| Camera picture size, stream limit while printing | `FB5_CAMERA_AREA=0.5` and `FB5_PRINT_RATE=64` in `fb5.conf` (see `scripts/fb5-env.sh`), then restart the stack |
| Contrast | `init_overrides` in `fb5-display.cfg` (tuned on the author's panel: `0xC0 09 0B`, `0xC5 00 90 80`) |

Logs: `logs/` (`mirror.log`, `touch.log`, `klipperscreen.log`, `xvfb.log`, `ks-start.log`) and KlipperScreen's own `~/printer_data/logs/KlipperScreen.log`.

Pitfall: the scripts stop processes with `pkill -f`. In a one-line `ssh pi@printer "..."` command, do not mention other process names (`fb5-mirror.py --xvfb`, `screen.py`, `ks-loop.sh`) after the script — `pkill` can kill the SSH command itself. Interactive SSH sessions are fine.

`examples/fb5-macros.cfg`: optional fixes for the [ODUCCEU](https://github.com/oducceu/klipper_configs) Ghost 5 macros — `LOAD_FILAMENT` / `UNLOAD_FILAMENT` that the KlipperScreen buttons call, and a `PAUSE` that no longer resumes 10 mm above the part after a second pause.

## Uninstall / rollback

```bash
./uninstall.sh
```

It stops the screen, removes the autostart and `[include fb5-display.cfg]`, switches `~/klipper` back to the saved branch and restores the KlipperScreen camera panel. The MCU keeps the FB5 firmware (Klipper keeps working) until you flash a normal Klipper build from SD; the script prints how.

## Repository layout

- `install.sh`, `uninstall.sh`, `set-baud.sh` — see above.
- `scripts/` — runs on the Pi: `ks-start.sh` / `ks-loop.sh` (Xvfb + KlipperScreen), `fb5-mirror.py`, `fb5-touch.py`, `fb5-touch-cal.py`, `build-firmware.sh`, `flash-uart.sh`, test tools.
- `config/` — `fb5-display.cfg` (pins, panel init), default touch calibration, firmware build configs.
- Firmware sources (GPL-3.0): [Aregus393/klipper `fb5-native-display`](https://github.com/Aregus393/klipper/tree/fb5-native-display) (19 commits on top of Klipper 9cb99754), [Aregus393/katapult `fb5-native-display`](https://github.com/Aregus393/katapult/tree/fb5-native-display) (3 commits on top of Katapult 3b973a4).

## Credits

- [Klipper](https://github.com/Klipper3d/klipper), [Katapult](https://github.com/Arksine/katapult), [KlipperScreen](https://github.com/KlipperScreen/KlipperScreen)
- ILI9488 init sequence and FSMC timings: [Marlin](https://github.com/MarlinFirmware/Marlin)
- Ghost 5 Klipper config and macros: [ODUCCEU](https://github.com/oducceu/klipper_configs)
- Developed with [Claude Code](https://claude.com/claude-code).

## License

GPL-3.0, like Klipper and Katapult that this project modifies. © 2026 Aregus393
