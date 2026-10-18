#!/usr/bin/env bash
# Pemeriksaan inferensi primitif Zynq UltraScale+ (K26 di Kria KV260) dengan
# Yosys (synth_xilinx -family xcup -flatten). Vivado tidak tersedia di CI; Yosys
# dipakai sebagai pembanding independen bahwa gaya penulisan RTL dikenali
# sebagai block RAM dan DSP48E2, dan bahwa register redundan tidak digabung
# (docs/rtl_style.md). Angka Vivado bisa berbeda: lihat docs/fpga_howto.md.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${OUT:-$ROOT/tb/padan/sim_build/infer}
mkdir -p "$OUT"
CORE="padan_avmm.v guard.v decision.v template_mem.v mac_array.v abft_check.v"

count() { { grep -E "^ +$2 +[0-9]+" "$1" || true; } | awk '{s += $2} END {print s + 0}'; }

synth() {   # synth <top> -> $OUT/<top>.stat
    local top=$1 files="$top.v" f src=""
    [ "$top" = padan_avmm ] && files=$CORE
    [ "$top" = padan_axil ] && files="padan_axil.v $CORE"
    for f in $files; do src="$src $ROOT/rtl/$f"; done
    yosys -q -l "$OUT/$top.log" -p "read_verilog -I$ROOT/rtl $src; \
        synth_xilinx -family xcup -flatten -top $top; tee -q -o $OUT/$top.stat stat" \
        >/dev/null 2>"$OUT/$top.err" || { cat "$OUT/$top.err"; echo "FAIL sintesis $top"; exit 1; }
    # Peringatan "Resizing cell port" (port RAMB18E2 lebih lebar dari data) normal.
    if grep -v "Resizing cell port" "$OUT/$top.err" | grep -q .; then
        grep -v "Resizing cell port" "$OUT/$top.err"
    fi
}

check() {   # check <top> <regex sel> <jumlah harapan> <label>
    local top=$1 cell=$2 want=$3 label=${4:-$2} stat="$OUT/$1.stat" got
    [ -f "$stat" ] || synth "$top"
    got=$(count "$stat" "$cell")
    if [ "$got" != "$want" ]; then
        echo "FAIL inferensi $top: $label = $got, harapan $want"; exit 1
    fi
    echo "PASS inferensi $top: $label = $got"
}

FF='FD[CPRS]E'
LUTRAM='RAM[0-9]+[XM][0-9A-Z]*'
rm -f "$OUT"/*.stat
check template_mem 'RAMB18E2'  16 'RAMB18E2'     # satu block RAM 18 Kb per bank lane
check template_mem 'RAMB36E2'   0 'RAMB36E2'
check template_mem "$LUTRAM"    0 'LUTRAM'
check mac_array    'DSP48E2'   16 'DSP48E2'      # satu DSP per lane (16x8 bertanda)
check mac_array    "$LUTRAM"    0 'LUTRAM'       # probe tetap register
check mac_array    'RAMB[0-9]+E2' 0 'block RAM'
# decision: semua register kedua komparator bertahan (tidak ada yang digabung).
# 151 = tau_a, tau_bn, best_a, best_b (4 x 32) + idx_a, idx_b (2 x 4) + any_a,
# hit_b, busy (3) + code_hi, code_lo_n, idx, idx_n (2 + 2 + 4 + 4).
check decision     "$FF"      151 'FF'
# guard: register redundan (nilai + komplemen) tidak digabung atau dibuang
# (safe-state dibuktikan terpisah: tb/guard/prove_safe.sh).
# 103 = t_sync 2 + state 4 + fail/fail_n 8 + k/k_n 8 + fault/fault_n 4 +
# tau_lk/tau_lk_n 64 + reason 2 + zs 3 + zcnt 7 + dbq 1.
check guard        "$FF"      103 'FF'
# Top KV260 (wrapper AXI4-Lite + inti): primitif keras total.
# DSP48E2 19 = 16 lane mac_array + 2 abft_check (bobot j+1) + 1 template_mem
# (pembaruan Cw: w(j) x selisih).
check padan_axil   'RAMB18E2'  16 'RAMB18E2'
check padan_axil   'DSP48E2'   19 'DSP48E2'
check padan_axil   "$LUTRAM"    0 'LUTRAM'
echo "ESTIMASI padan_axil (Yosys, bukan Vivado): LUT $(count "$OUT/padan_axil.stat" 'LUT[1-6]')," \
     "FF $(count "$OUT/padan_axil.stat" "$FF"), SRL16E $(count "$OUT/padan_axil.stat" 'SRL16E')"
