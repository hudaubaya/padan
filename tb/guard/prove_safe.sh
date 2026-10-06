#!/usr/bin/env bash
# Bukti SAT (Yosys) pada guard.v SETELAH sintesis generik (synth -flatten), untuk
# setiap kode state ilegal c (paritas ganjil, 1100, 1111), dengan semua input
# lain bebas (tamper, perintah, keadaan inti) dan rst_n = 1:
#   1. pada siklus itu: semua izin (enroll, probe, match, status) = 0
#   2. siklus berikutnya: state = ZH (1001)
# Juga: HALT tetap HALT untuk semua input. Lalu kontrol negatif: guard dengan
# deteksi ilegal dihapus (mutan illegal_stays) HARUS gagal dibuktikan, supaya
# bukti di atas tidak kosong. Ini membuktikan logika safe-state bertahan dari
# optimasi Yosys; Quartus tidak tercakup (docs/rtl_guard.md).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

ILLEGAL="0001 0010 0100 0111 1000 1011 1100 1101 1110 1111"
PREP="synth -flatten -top guard; async2sync; dffunmap"

prove() {  # prove <file guard.v> <label> <perintah sat>
    if yosys -q -p "read_verilog -I$ROOT/rtl $1; $PREP; $3" > "$WORK/log" 2>&1; then
        return 0
    fi
    return 1
}

cmds=()
for c in $ILLEGAL; do
    cmds+=("sat -seq 1 -set rst_n 1 -set-at 1 state 4'b$c -prove allow_enroll 0 -prove allow_probe 0 -prove allow_match 0 -prove allow_status 0 -verify")
    cmds+=("sat -seq 2 -set rst_n 1 -set-at 1 state 4'b$c -prove-skip 1 -prove state 4'b1001 -verify")
done
cmds+=("sat -seq 2 -set rst_n 1 -set-at 1 state 4'b1010 -prove-skip 1 -prove state 4'b1010 -verify")

for cmd in "${cmds[@]}"; do
    prove "$ROOT/rtl/guard.v" ok "$cmd" || { cat "$WORK/log"; echo "FAIL prove_safe: $cmd"; exit 1; }
done

# Kontrol negatif: mutan illegal_stays (tb/padan/mutate.py).
sed -e "s/wire st_illegal = (^state) || (state == 4'b1100) || (state == 4'b1111);/wire st_illegal = 1'b0;/" \
    -e "s/default: go_zh(R_ILLEGAL);/default: ;/" "$ROOT/rtl/guard.v" > "$WORK/guard_mut.v"
if cmp -s "$ROOT/rtl/guard.v" "$WORK/guard_mut.v"; then
    echo "FAIL prove_safe: mutan kontrol tidak terbentuk"; exit 1
fi
if prove "$WORK/guard_mut.v" mut "sat -seq 2 -set rst_n 1 -set-at 1 state 4'b0001 -prove-skip 1 -prove state 4'b1001 -verify"; then
    echo "FAIL prove_safe: bukti juga lolos pada guard tanpa deteksi ilegal (bukti kosong)"; exit 1
fi
grep -q "proof did fail" "$WORK/log" || { cat "$WORK/log"; echo "FAIL prove_safe: kontrol negatif gagal karena alasan lain"; exit 1; }
echo "PASS prove_safe: ${#cmds[@]} bukti SAT (10 kode ilegal -> izin 0 dan ZH; HALT tetap HALT); kontrol negatif gagal seperti seharusnya"
