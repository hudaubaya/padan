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

## Model PADAN

Golden model integer, analisis batas 32 bit, perbandingan INT8 vs float pada
data sintetis, dan simulasi fault ABFT: [`docs/padan_model.md`](docs/padan_model.md)
(semua angka berlabel "model").

Lisensi tiap baseline ada di `LICENSE` di direktorinya. Lisensi untuk kode
PADAN sendiri belum ditetapkan.
