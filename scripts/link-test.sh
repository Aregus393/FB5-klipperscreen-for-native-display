#!/bin/bash
# Draw the full screen test image and report the mcu link counters
# (retransmits / invalid bytes) accumulated during the transfer only.
# Usage: link-test.sh <step_number>
STEP=${1:-0}
API=localhost:7125
stats(){ curl -s -m 5 "$API/printer/objects/query?mcu" | python3 -c "
import sys, json
s = json.load(sys.stdin)['result']['status']['mcu']['last_stats']
print(s['bytes_retransmit'], s['bytes_invalid'], s['bytes_write'], s.get('srtt', 0))"; }
read r0 i0 w0 t0 < <(stats)
curl -s -m 120 -X POST "$API/printer/gcode/script" -H "Content-Type: application/json" \
    -d "{\"script\": \"LCD_TEST_IMAGE STEP=$STEP\"}" >/dev/null
sleep 2   # last_stats is refreshed about once per second
read r1 i1 w1 t1 < <(stats)
curl -s -m 5 "$API/server/gcode_store?count=1" | python3 -c "import sys,json;print(json.load(sys.stdin)['result']['gcode_store'][-1]['message'])"
echo "during transfer: bytes_write +$((w1-w0)), bytes_retransmit +$((r1-r0)), bytes_invalid +$((i1-i0)), srtt $t1"
curl -s -m 5 $API/printer/info | grep -o "\"state\": *\"[a-z]*\""
