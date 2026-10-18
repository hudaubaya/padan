# fpga/

| Direktori | Isi |
|---|---|
| `kv260/` | Kria KV260 (Zynq UltraScale+ K26): `create_project.tcl` (block design PS + AXI SmartConnect + `padan_axil`), `build.tcl` (bitstream, laporan, XSA), `padan_kv260.xdc` (pin tamper PMOD), `check_reports.py` (pemeriksaan laporan Vivado) |

Host di Linux PS: [`sw/kv260/padan_test.py`](../sw/kv260/padan_test.py).
Langkah build dan pemeriksaan wajib: [`docs/fpga_howto.md`](../docs/fpga_howto.md).
Belum pernah dijalankan di Vivado atau di board.
