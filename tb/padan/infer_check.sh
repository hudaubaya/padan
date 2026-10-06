#!/usr/bin/env bash
# Pemeriksaan inferensi primitif Cyclone V dengan Yosys (synth_intel_alm).
# Quartus tidak tersedia di CI; Yosys dipakai sebagai pembanding independen
# bahwa gaya penulisan RTL dikenali sebagai M10K dan DSP (docs/rtl_style.md).
# Catatan: yosys-abc 0.33 kadang abort di &mfs (giaMfs.c:386) saat optimasi LUT
# template_mem. Yosys mencatat peringatan dan melanjutkan; jumlah M10K/DSP tidak
# terpengaruh.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${OUT:-$ROOT/tb/padan/sim_build/infer}
mkdir -p "$OUT"

count() { { grep -E "^ +$2 +[0-9]+" "$1" || true; } | awk '{s += $2} END {print s + 0}'; }

check() {   # check <top> <sel> <jumlah harapan>
    local top=$1 cell=$2 want=$3 stat="$OUT/$1.stat"
    if [ ! -f "$stat" ]; then
        yosys -q -l "$OUT/$top.log" -p "read_verilog -I$ROOT/rtl $ROOT/rtl/$top.v; \
            synth_intel_alm -family cyclonev -top $top; tee -q -o $stat stat" >/dev/null
    fi
    local got
    got=$(count "$stat" "$cell")
    if [ "$got" != "$want" ]; then
        echo "FAIL inferensi $top: $cell = $got, harapan $want"; exit 1
    fi
    echo "PASS inferensi $top: $cell = $got"
}

rm -f "$OUT"/*.stat
check template_mem 'MISTRAL_M10K'      16   # satu M10K per bank lane
check template_mem 'MISTRAL_MLAB'       0
check mac_array    'MISTRAL_MUL[0-9X]+' 16  # satu pengali DSP per lane
check mac_array    'MISTRAL_MUL18X18'   16  # 16x8 bertanda -> mode 18x18
check mac_array    'MISTRAL_MLAB'       0   # probe tetap register
check mac_array    'MISTRAL_M10K'       0
