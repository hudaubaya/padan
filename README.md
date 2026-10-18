# padan

| Direktori | Isi |
|---|---|
| `rtl/` | RTL PADAN |
| `rtl/baseline/` | baseline TT07 yang disalin apa adanya (lihat [`docs/baselines.md`](docs/baselines.md)) |
| `tb/` | testbench cocotb |
| `model/` | model referensi Python/NumPy |
| `fpga/` | proyek FPGA |
| `sw/` | perangkat lunak host |
| `docs/` | dokumentasi |

## Menjalankan test

```sh
sudo apt-get install iverilog yosys # Icarus Verilog 12, Yosys 0.33
pip install -r requirements.txt     # cocotb==1.8.1, numpy
make test
```

`make help` menampilkan target lain. CI (`.github/workflows/test.yml`) menjalankan
`make test` pada setiap push ke `main` dan setiap pull request.

## Baseline

| # TT07 | Direktori | Sumber | Lisensi |
|---|---|---|---|
| 0590 | `rtl/baseline/tinytpu_0590/` | [Revenantx86/tt07-tinytpu](https://github.com/Revenantx86/tt07-tinytpu) | Apache-2.0 |
| 0040 | `rtl/baseline/iterative_mac_0040/` | [RajuMachupalli/tt07_iterativeMAC](https://github.com/RajuMachupalli/tt07_iterativeMAC) | Apache-2.0 |
| 0642 | `rtl/baseline/vector_cim_0642/` | [ramyadhadidi/tt07-8bit-vector-compute-in-SRAM](https://github.com/ramyadhadidi/tt07-8bit-vector-compute-in-SRAM) | Apache-2.0 |

Hasil audit ketiga baseline (apa yang benar, salah, dan layak dipakai ulang):
[`docs/baseline_audit.md`](docs/baseline_audit.md).

## RTL PADAN

`rtl/mac_array.v` (16 MAC INT8, adder tree, akumulator 32 bit, satu dot product
D = 128 per 8 siklus), `rtl/template_mem.v` (memori template 16×128 byte, hanya
bisa ditulis dari bus, generator C dan Cw), dan `rtl/abft_check.v`.
Arsitektur dan hasil verifikasi: [`docs/rtl_padan.md`](docs/rtl_padan.md).
Gaya penulisan (block RAM, DSP48E2): [`docs/rtl_style.md`](docs/rtl_style.md).

`rtl/decision.v` (dua komparator independen, keputusan ditahan bila ABFT gagal
atau komparator tidak sepakat), `rtl/padan_avmm.v` (inti dengan bus register
internal gaya Avalon-MM: ENROLL, PROBE, MATCH, STATUS; template tidak bisa
dibaca), dan `rtl/padan_axil.v` (wrapper AXI4-Lite untuk KV260):
[`docs/rtl_decision.md`](docs/rtl_decision.md).

`rtl/guard.v` (pembatas percobaan gagal, LOCK enrollment dengan τ terkunci,
penghitung FAULT, tamper dari pin PMOD, zeroize, FSM safe-state):
[`docs/rtl_guard.md`](docs/rtl_guard.md).

Build debug `DEBUG_FAULT` (injeksi fault terkendali host, lab saja) dan bukti
bahwa build rilis tidak memuatnya:
[`docs/rtl_debug_fault.md`](docs/rtl_debug_fault.md).

## FPGA Kria KV260

Proyek Vivado untuk KV260 (PS Zynq UltraScale+ → M_AXI_HPM0_FPD → AXI4-Lite
`padan_axil` di 0xA000_0000), XDC pin tamper PMOD, skrip host Python di Linux
PS (`sw/kv260/padan_test.py`, lewat `/dev/mem`), dan pemeriksaan wajib:
[`docs/fpga_howto.md`](docs/fpga_howto.md). Belum dijalankan di Vivado atau di
board.

## Laporan proyek

Laporan dari baseline TT07 sampai port Kria KV260 dan estimasi sumber daya:
[`docs/laporan_padan.md`](docs/laporan_padan.md) (sumber) dan versi Word
[`docs/laporan/Laporan_PADAN.docx`](docs/laporan/Laporan_PADAN.docx), per 17
Oktober 2026 (port KV260). `make laporan` membangun ulang .docx dari Markdown;
`make check-laporan` (bagian dari `make test`) gagal bila keduanya tidak
sinkron. Angka di laporan ditulis tangan dari `docs/` dan log CI, jadi perlu
diperbarui saat repo berubah.

## Model PADAN

Golden model integer, analisis batas 32 bit, perbandingan INT8 vs float pada
data sintetis, dan simulasi fault ABFT: [`docs/padan_model.md`](docs/padan_model.md)
(semua angka berlabel "model").

Lisensi tiap baseline ada di `LICENSE` di direktorinya. Lisensi untuk kode
PADAN sendiri belum ditetapkan.
