# Baseline TT07

Tiga desain Tiny Tapeout 07 (TT07) disalin ke `rtl/baseline/` sebagai titik
awal PADAN. Setiap baseline disimpan **apa adanya** (tanpa modifikasi) beserta
lisensinya, supaya bisa di-diff langsung terhadap upstream.

Versi yang dipakai adalah **commit yang di-tapeout di TT07**, bukan HEAD repo
upstream. Commit tapeout diambil dari `projects/<top_module>/commit_id.json` di
repo shuttle resmi [TinyTapeout/tinytapeout-07](https://github.com/TinyTapeout/tinytapeout-07)
(commit shuttle `3c541b4b416e60c8aca1efc2eeb3c05875f8c526`, dibaca 2026-10-06).
Salinan `commit_id.json` itu ikut disimpan di direktori tiap baseline.

## Ringkasan

| # TT07 | Direktori | Top module | Sumber | Commit tapeout | Lisensi | Test upstream |
|---|---|---|---|---|---|---|
| 0590 | `rtl/baseline/tinytpu_0590/` | `tt_um_revenantx86_tinytpu` | [Revenantx86/tt07-tinytpu](https://github.com/Revenantx86/tt07-tinytpu) | `cdc35f3558339f664cd42404c190f08a2e85b8d6` (2024-05-16) | Apache-2.0 | lulus, **tanpa assertion** |
| 0040 | `rtl/baseline/iterative_mac_0040/` | `tt_um_rajum_iterativeMAC` | [RajuMachupalli/tt07_iterativeMAC](https://github.com/RajuMachupalli/tt07_iterativeMAC) | `7d7c200b932afb45a44b5f1c498fb43aad20e78a` (2024-06-01) | Apache-2.0 | lulus, 1 assertion lemah |
| 0642 | `rtl/baseline/vector_cim_0642/` | `tt_um_8bit_vector_compute_in_SRAM` | [ramyadhadidi/tt07-8bit-vector-compute-in-SRAM](https://github.com/ramyadhadidi/tt07-8bit-vector-compute-in-SRAM) | `5f9c5f7b862115bc0431242f63e472443a60c9db` (2024-05-28) | Apache-2.0 | lulus, 18 vektor dot-product diperiksa |

Nomor TT07 (#0590, #0040, #0642) berasal dari permintaan proyek. Nomor itu
**belum diverifikasi** terhadap halaman tinytapeout.com (situs tidak dapat
diakses dari lingkungan pembuatan repo ini). Yang sudah diverifikasi: ketiga
`top_module` ada di repo shuttle TT07 dan `commit_id.json`-nya menunjuk ke repo
dan commit di tabel.

Lisensi:

- Ketiga `LICENSE` identik byte-per-byte. Isinya teks Apache License 2.0 dari
  template Tiny Tapeout, sha256
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.
- `LICENSE`, `info.yaml`, dan `docs/info.md` dari upstream juga identik dengan
  salinan di repo shuttle (`projects/<top_module>/`).
- Header SPDX `test/test.py` berbeda-beda (lihat tiap baseline). Header itu
  berasal dari template Tiny Tapeout dan dipertahankan apa adanya.

Ketiga proyek dibangun dengan alat yang sama, menurut `commit_id.json`:

- OpenLane `337ffbf4749b8bc6e8d8742ed9a595934142198b`
- open_pdks `cd1748bb197f9b7af62a54507de6624e30363943`

## Isi setiap direktori baseline

| Path | Asal |
|---|---|
| `src/`, `test/`, `docs/`, `info.yaml`, `LICENSE` | repo upstream pada commit tapeout (`git archive <commit>`) |
| `commit_id.json` | repo shuttle, `projects/<top_module>/commit_id.json` |
| `gl/<top_module>.v` | repo shuttle, `projects/<top_module>/<top_module>.v`: netlist gate-level pasca-PnR (sky130_fd_sc_hd, dengan pin daya `VPWR`/`VGND`) |

Yang tidak disalin:

- `.github/` (workflow template TT).
- `README.md` upstream (template TT).
- `.gitignore`.
- GDS/LEF/SPEF dari repo shuttle.

`rtl/baseline/SHA256SUMS` mencatat sha256 setiap file yang disalin.
`make check-baseline` (termasuk dalam `make test` dan CI) gagal jika ada isi
yang berubah atau ada file yang ditambah ke `rtl/baseline/`.

## tinytpu_0590 — TinyTPU (#0590)

- Penulis: Refik (`info.yaml`: author "Refik").
- Upstream: <https://github.com/Revenantx86/tt07-tinytpu>.
- Commit yang disalin: `cdc35f3558339f664cd42404c190f08a2e85b8d6`, "cocotb mad", 2024-05-16.
- Workflow GDS tapeout: <https://github.com/Revenantx86/tt07-tinytpu/actions/runs/9121665069>.
- HEAD upstream saat disalin: `0532e7b3b1c59f139c52976fc51799f164be1a7b`, "tiny changes", 2024-09-04.
  - Ada satu commit setelah tapeout.
  - Selisihnya hanya spasi dalam komentar di `src/dff_mem.v`. `test/` identik.
- Netlist tapeout: `gl/tt_um_revenantx86_tinytpu.v`, sha256
  `7c0ae13d482b46710c13f2e1d0b35cd98850bd9c99216181b7b8ba79f004e51a`.
- Desain:
  - Array sistolik MAC 2×2 (`D_W=8`, `N=2`), tile 1x2.
  - Data X/Y masuk serial 1 bit per clock lewat `ui_in[0]` dan `ui_in[1]`.
  - Kendali: `ui_in[2]` = load, `ui_in[3]` = init.
  - Keluaran: hasil serial di `uo_out[0]`, `tx_ready` di `uo_out[1]`.
- Catatan:
  - `test/test.py` **tidak memuat satu pun assertion** (baris pemeriksaan
    dibiarkan sebagai komentar). Test hanya mengirim dua matriks lalu selesai.
    Lulusnya test **tidak** membuktikan hasil perkalian benar.
  - `info.yaml` mencatat `clock_hz: 50000` (50 kHz), sedangkan test memakai
    clock 40 ns (25 MHz).
  - Header `src/tt_um_revenantx86_tinytpu.v` masih berbunyi "Copyright (c) 2024
    Your Name" (sisa template).
  - `test/test.py` membawa `SPDX-License-Identifier: MIT` milik template TT.

## iterative_mac_0040 — Iterative MAC (#0040)

- Penulis: Raju Machupalli.
- Upstream: <https://github.com/RajuMachupalli/tt07_iterativeMAC>.
- Commit yang disalin: `7d7c200b932afb45a44b5f1c498fb43aad20e78a`, "Test case changing", 2024-06-01.
- Workflow GDS tapeout: <https://github.com/RajuMachupalli/tt07_iterativeMAC/actions/runs/9332674809>.
- HEAD upstream saat disalin: `bece194888720d423d67a2ed3abb0064a4b33812`, "Test case extended", 2024-06-01.
  - Ada satu commit setelah tapeout.
  - Selisihnya hanya `test/test.py`: assertion `uo_out == 6` diaktifkan. `src/` identik.
  - Test HEAD itu juga lulus pada RTL tapeout (dicoba lokal; tidak disalin).
- Netlist tapeout: `gl/tt_um_rajum_iterativeMAC.v`, sha256
  `c4428c3b17d92ba63354c09e41dfef396e7d5bb5adbc3648e13030730f3c68ad`.
- Desain:
  - MAC iteratif: pengali 7×8 bit (`multi.v`) dan penjumlah 32 bit (`adder.v`), dikendalikan FSM.
  - Bobot 7 bit dan mode dimuat dari `ui_in` saat reset.
  - Hasil keluar di `uo_out` (bit 31:24) dan `uio_out` (bit 23:16).
  - Tile 1x1, `clock_hz` 50 MHz.
- Catatan:
  - Test pada commit tapeout hanya memeriksa `uo_out == 0` setelah lima
    pasangan input. Assertion hasil (`uo_out == 6`) masih berupa komentar.
    Test ini tidak memverifikasi aritmetika MAC.
  - `test/Makefile` mencantumkan `adder.v` dan `multi.v` di baris
    `VERILOG_SOURCES` terpisah, bukan di `PROJECT_SOURCES`.
  - `uio_out` diberi `8'bxx` saat `mode=1`, sehingga nilainya X di simulasi
    RTL. Pada mode itu `uio_oe=0`, jadi pin tetap input.
  - Header top module masih "Copyright (c) 2024 Your Name" (sisa template).
  - `test/test.py` membawa `SPDX-License-Identifier: Apache-2.0` dari template TT.

## vector_cim_0642 — 8-bit Vector Compute-in-SRAM (#0642)

- Penulis: Ramyad Hadidi.
- Upstream: <https://github.com/ramyadhadidi/tt07-8bit-vector-compute-in-SRAM>.
- Commit yang disalin: `5f9c5f7b862115bc0431242f63e472443a60c9db`, "documentation", 2024-05-28.
- Workflow GDS tapeout: <https://github.com/ramyadhadidi/tt07-8bit-vector-compute-in-SRAM/actions/runs/9270763872>.
- HEAD upstream saat disalin: sama dengan commit tapeout. Tidak ada selisih.
- Netlist tapeout: `gl/tt_um_8bit_vector_compute_in_SRAM.v`, sha256
  `e591ec5893870686efb9ac96db93184d9c0b99b61a35ca36cf693d62d1ba4775`.
- Desain:
  - Delapan unit MAC 8 bit (register `w` dan `a`, hasil `a*w` 16 bit), ditambah
    pohon penjumlah CLA ke hasil 19 bit. Tile 2x2.
  - `ui_in[7:6]` = opcode, `ui_in[5:0]` = alamat MAC, `uio_in` = data.
  - Opcode: `00` `LOAD_W` (tulis bobot), `01` `LOAD_A` (tulis aktivasi),
    `10` `READ_S` (simpan hasil ke cache), `11` `NOP`.
  - Setelah `READ_S` dilepas, hasil keluar 3 byte berurutan di `uo_out`, MSB
    dahulu, satu byte per clock. Selama `READ_S` ditahan, cache terus ditulis
    ulang dan keluaran tidak maju.
- Catatan:
  - `test/test.py` memuat dua test aktif:
    - `test_obvious` (`assert 2 > 1`).
    - `test_read_only_with_external`: 18 pasang vektor, setiap hasil
      dot-product dibandingkan dengan `sum(w*a)`.
  - Test lain di file itu dinonaktifkan dalam string `'''…'''` karena
    mengakses sinyal internal.
  - Vektor berlabel "negative values (two's complement)" tetap dihitung
    **tanpa tanda**, baik oleh desain maupun oleh nilai harapan. Aritmetika
    bertanda belum diuji dan memang tidak didukung RTL.
  - Alamat 6 bit, tetapi hanya alamat < 8 yang menulis. Alamat 8–63 diabaikan
    tanpa tanda galat.
  - `src/project.v` adalah sisa template (`tt_um_example`, `uo_out = ui_in + uio_in`).
    File itu tidak tercantum di `source_files` maupun `test/Makefile`, jadi
    tidak ikut disintesis atau disimulasikan.
  - `test/test.py` tidak memiliki header SPDX.

## Cara menjalankan

```sh
pip install -r requirements.txt   # cocotb==1.8.1, numpy
make test                         # check-baseline + test upstream ketiga baseline
make test-baseline-vector_cim_0642
```

Membutuhkan Icarus Verilog (CI memakai paket `iverilog` Ubuntu 24.04, versi 12).

## Cara memperbarui baseline

1. Ambil commit dari `commit_id.json` di repo shuttle TT07.
2. Salin `src/ test/ docs/ info.yaml LICENSE` dari upstream pada commit itu
   tanpa modifikasi (`git archive <commit> src test docs info.yaml LICENSE`).
3. Salin `commit_id.json` dan netlist `<top_module>.v` (ke `gl/`) dari
   `projects/<top_module>/` di repo shuttle.
4. Buat ulang `rtl/baseline/SHA256SUMS`:
   ```sh
   cd rtl/baseline
   find . -type f ! -name SHA256SUMS | LC_ALL=C sort | sed 's|^\./||' | xargs sha256sum > SHA256SUMS
   ```
5. Jalankan `make test` dan perbarui tabel di atas.
