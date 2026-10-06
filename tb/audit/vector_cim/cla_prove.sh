#!/usr/bin/env bash
# Buktikan dengan SAT (Yosys) bahwa adder `cla` baseline #0642 benar untuk
# SEMUA input, pada ketiga lebar yang dipakai pohon penjumlah (16, 17, 18 bit).
# Dari root: `make test-audit-vector_cim-formal`.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src=$here/../../../rtl/baseline/vector_cim_0642/src/tt07-8bit-vector-compute-in-SRAM.v
for bits in 16 17 18; do
  log=$(yosys -p "read_verilog -sv $src $here/cla_prove.v; chparam -set BITS $bits cla_prove; \
        hierarchy -top cla_prove; proc; flatten; opt_clean; \
        sat -prove ok 1 -verify -show-ports" 2>&1) || { echo "$log"; echo "FAIL cla #($bits)"; exit 1; }
  grep -q "SAT proof finished - no model found: SUCCESS" <<<"$log" || { echo "$log"; echo "FAIL cla #($bits): tidak ada SUCCESS"; exit 1; }
  echo "PASS cla #($bits): {c_out, s_out} == a + b + c_in untuk semua 2^$((2 * bits + 1)) input"
done
