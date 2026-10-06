---
title: Laporan Proyek PADAN
subtitle: Identifikasi 1:N INT8 dengan ABFT, dari model hingga integrasi FPGA DE10-Nano
date: Per 6 Oktober 2026 · repositori hudaubaya/padan, branch main @ 258c487
lang: id-ID
---

<!--
Sumber laporan. docs/laporan/Laporan_PADAN.docx dibangkitkan dari berkas ini:
    make laporan
`make check-laporan` (bagian dari `make test`) gagal bila .docx tidak sinkron.
Angka di sini ditulis tangan dari docs/ dan log CI; perbarui saat repo berubah.
-->

# Ringkasan

PADAN sudah memiliki golden model, RTL lengkap, antarmuka Avalon-MM, penjaga
keamanan (guard), dan paket integrasi DE10-Nano. Semuanya terbukti **di
simulasi** dan lulus CI. **Belum ada satu pun hasil Quartus, timing, atau
board.** Itu adalah risiko terbesar proyek saat ini.

- **Fungsi:** 16 template × 128 byte INT8, skor s_j = Σ T[j,i]·p_i, keputusan
  MATCH / NO_MATCH / FAULT dengan latensi tetap 153 siklus.
- **Keamanan fault:** dari 48.765 fault bit tunggal yang disuntikkan lewat
  antarmuka bus, tidak satu pun menghasilkan MATCH yang salah.
- **Keamanan sistem:** pembatas percobaan, LOCK dengan τ terkunci, zeroize saat
  tamper atau FAULT berulang, dan FSM safe-state yang dibuktikan dengan SAT
  (Yosys).
- **Estimasi sumber daya (Yosys):** semua di bawah 10% kapasitas, kecuali blok
  DSP yang berada di 9,8–17%. Keputusannya masih menunggu.
- **Status:** 6 PR sudah di-merge ke main. CI terakhir hijau dan log-nya sudah
  diperiksa untuk setiap target baru.

## Cara membaca label

| Label | Arti |
|---|---|
| [Pasti] | Dibuktikan oleh simulasi, bukti formal, aljabar, atau struktur netlist di repo ini. |
| [Kemungkinan Besar] | Inferensi kuat yang belum dibuktikan di sini, misalnya perilaku Quartus. |
| [Menebak] | Mengisi celah informasi; perlu dicek. |
| (model) | Angka dari golden model Python, bukan dari RTL, FPGA, atau silikon. |
| estimasi Yosys | Pemetaan Yosys `synth_intel_alm`, bukan laporan fitter Quartus. |

# Kronologi

Seluruh pekerjaan dilakukan pada 6 Oktober 2026 dalam 6 pull request,
masing-masing di-merge setelah CI hijau.

| Tahap | Commit / PR | Isi |
|---|---|---|
| 1. Kerangka dan baseline | c319f85 | Struktur repo; tiga desain TT07 disalin apa adanya beserta lisensi dan SHA256SUMS |
| 2. Audit baseline | ecbc278 | Ketiga baseline diuji apa adanya (RTL dan netlist gate-level) terhadap model Python |
| 3. Golden model | d1a274d (PR #1) | Model integer PADAN, analisis batas 32 bit, data sintetis INT8 vs float, simulasi fault |
| 4. RTL inti | 982d2a6 (PR #2) | `template_mem`, `mac_array`, `abft_check` + test cocotb dan uji mutasi |
| 5. Keputusan dan bus | 4210629 (PR #3) | `decision` (dua komparator), `padan_avmm` (slave Avalon-MM), paritas probe |
| 6. FPGA DE10-Nano | 1ed2f89 (PR #4) | Komponen Platform Designer, skrip GHRD, SDC, skrip System Console |
| 7. Guard | 811f8ce (PR #5) | Pembatas percobaan, LOCK + τ terkunci, FAULT, tamper KEY0, zeroize, safe-state |
| 8. Injeksi fault debug | 2e694e4 (PR #6) | Port `DEBUG_FAULT` dan bukti bahwa build rilis tidak memuatnya |
| 9. Estimasi sumber daya | (tanpa commit) | Yosys `synth_intel_alm` per modul (bagian 8) |

# 1. Baseline TT07 dan audit

Tiga desain Tiny Tapeout 07 disimpan **tanpa modifikasi** pada commit yang
di-tapeout. `make check-baseline` gagal bila satu byte berubah. Audit menguji
RTL dan netlist tapeout (sky130) dengan cocotb terhadap model maksud desain
(`docs/baseline_audit.md`).

| Baseline | Yang benar | Cacat yang ditemukan | Dipakai ulang |
|---|---|---|---|
| TinyTPU #0590 | Array sistolik 2×2 benar untuk 400 pasang matriks acak | `tx_ready` terlambat; akumulator 16 bit overflow; operasi kedua tanpa reset salah; 32 latch; register tanpa reset (X di netlist) | Konsep `mac.v` + `systolic.v`; kendali I/O ditulis ulang |
| Iterative MAC #0040 | Pengali 7×8 benar untuk 32.768 pasangan | Mode 0 selalu 0; `uio` dipakai dua arah; cabang mati; hasil terpotong | Hanya konsep |
| Vector CiSRAM #0642 | Dot product 8 elemen eksak; CLA terbukti formal (SAT) | Tidak ada cacat fungsional; hanya tak bertanda; tidak ada SRAM sungguhan | Ya: `MAC` dan `cla` |

16 test cacat ditandai `expect_fail`. Suite menjadi merah bila perilaku
baseline berubah, tanda dokumen audit perlu diperbarui. Nomor TT07 belum dicek
terhadap tinytapeout.com. [Kemungkinan Besar]

# 2. Golden model dan analisis

`model/padan.py` mendefinisikan skor, baris checksum C dan Cw, residu ABFT d1
dan d2, dan lokalisasi k = d2/d1 − 1. Semua angka di bagian ini berlabel
(model); rinciannya di `docs/padan_model.md`.

- **Semua besaran muat 32 bit bertanda.** [Pasti] Yang terbesar tanpa fault
  adalah Cw·p = 285.212.672 (model, 30 bit), dengan ruang sisa 7,53× terhadap
  2^31 − 1.
- **Baris checksum tidak muat INT8:** C butuh 12 bit dan Cw 16 bit, sehingga
  lane harus 16×8, bukan 8×8. [Pasti]
- **INT8 vs float:** kesepakatan keputusan ≥ 99,882% (model) untuk τ 0,15–0,50.
  Semua beda berada dalam 0,0047 dari ambang. FAR/FRR absolut tidak bermakna
  untuk biometrik nyata, karena data ini sintetis.
- **Fault tunggal:** deteksi 100% (model) untuk semua flip efektif. Pemeriksa
  32 bit salah tunjuk untuk flip bit 27–31 pada skor; pemeriksa 40 bit atau cek
  rentang memberi lokalisasi 100%. RTL memakai 40 bit.
- **Celah yang ditemukan model:** fault pada probe p tidak terlihat oleh ABFT.
  65.536 flip tidak terdeteksi, 229 di antaranya mengubah keputusan (model).
  Celah ini ditutup di RTL dengan paritas per byte.
- **Fault ganda:** dua flip bit 31 bisa saling meniadakan pada pemeriksa 32 bit,
  dan dua fault bisa salah lokalisasi. Lokalisasi cukup untuk pelaporan, tidak
  untuk koreksi otomatis.

# 3. RTL inti

Tiga modul Verilog-2001 dengan parameter rilis N = 16, D = 128, L = 16 lane
(`docs/rtl_padan.md`).

| Modul | Isi |
|---|---|
| `template_mem` | 16 bank M10K × 144 word × 16 bit (T, C, Cw); hanya bisa ditulis; generator memperbarui C dan Cw di setiap tulis byte |
| `mac_array` | 16 lane MAC 16×8, adder tree, akumulator 32 bit; satu dot product per 8 siklus; 18 baris per MATCH (16 skor + C·p + Cw·p); probe 1.024 bit dengan paritas per byte |
| `abft_check` | S1, S2, d1, d2 dalam 40 bit; lokalisasi tanpa pembagi, maksimal 16 langkah |

- **38.112 fault** (lane, akumulator, setiap bit memori) terdeteksi dengan indeks
  benar; tidak ada alarm palsu pada 1.317 run bersih. [Pasti]
- **Biaya ABFT:** 16 siklus (+12,5%) untuk dua baris checksum.
- **Uji mutasi:** mutan `no_c`, `no_cw`, dan `weight_j` terbunuh. Mutan `no_c` dan
  `no_cw` membuktikan bahwa test tanpa fault saja tidak cukup, karena pemeriksa
  yang setengah mati tetap diam.

# 4. Keputusan dan antarmuka Avalon-MM

`decision.v` memakai dua komparator yang ditulis berbeda (diversitas). τ di
komparator B disimpan sebagai komplemen; tanpa itu Yosys menggabungkan register
keduanya. `padan_avmm.v` adalah slave Avalon-MM tanpa jalur baca untuk template,
probe, atau skor (`docs/rtl_decision.md`).

| Kode STATUS | Arti |
|---|---|
| `0000` | NONE (belum ada keputusan) |
| `0101` | NO_MATCH (tanpa indeks, agar identitas terdekat tidak bocor) |
| `1010` | MATCH; indeks dikeluarkan dua kali (idx dan ~idx) |
| `1111` | FAULT: ABFT gagal, paritas probe salah, atau komparator tidak sepakat |

- **814 keputusan** identik dengan model, termasuk seri dan nilai ekstrem.
- **48.765 fault** (datapath, memori, probe, register komparator, sinyal error,
  register keluaran): tidak satu pun menghasilkan MATCH yang salah. [Pasti]
- **Latensi tetap 153 siklus** untuk MATCH, NO_MATCH, dan FAULT, sehingga tidak
  ada kanal samping waktu.
- **Mutan `no_parity`** membuktikan temuan model: satu flip bit probe tanpa
  paritas membuat impostor MATCH.

# 5. Integrasi FPGA DE10-Nano

Paket integrasi ke GHRD Terasic sudah lengkap, tetapi **belum pernah
dikompilasi atau dijalankan di board**. Tidak ada klaim hasil board
(`docs/fpga_howto.md`).

- Komponen Platform Designer (`padan_avmm_hw.tcl`), skrip `add_padan.tcl` (JTAG
  master dan lightweight HPS bridge, alamat 0x0004_0000 / HPS 0xFF24_0000), dan
  SDC pengganti.
- Skrip System Console: 3 galeri, 46 kasus dari model, dan pemindaian 1.024
  alamat.
- Pemeriksaan wajib setelah kompilasi: DSP/M10K (`check_reports.py`), Ignored
  Constraints, dan slack (`check_timing.tcl`).
- **Yang diuji di CI tanpa Quartus:** skrip Tcl dijalankan dengan stub. Skrip
  System Console dijalankan melawan RTL lewat shim, dan lulus 46/46. JTAG,
  interkoneksi, dan timing tidak tercakup.

# 6. Guard: keamanan di tingkat sistem

`guard.v` mengendalikan izin bus. Setiap reset melakukan zeroize sebelum
perangkat bisa dipakai (`docs/rtl_guard.md`).

| Fungsi | Perilaku |
|---|---|
| Pembatas percobaan | K = 5 NO_MATCH berturut-turut → LOUT (keluar hanya lewat reset); MATCH menolkan penghitung |
| LOCK | Setelah LOCK, template tidak bisa ditulis atau dihapus; probe dan MATCH tetap bisa |
| τ terkunci | Di LOCKD, decision memakai GUARD_TAU, bukan τ dari host |
| FAULT | Penghitung kumulatif; FAULT ke-3 → zeroize → HALT |
| Tamper | KEY0, sinkronisasi 2-FF → zeroize → HALT |
| Safe-state | State 4 bit berparitas genap; kode ilegal atau ketidakcocokan penghitung/komplemen → zeroize → HALT |

**τ terkunci tidak ada di spesifikasi awal.** Tanpanya, host cukup menulis
τ = −2^31 untuk mendapat MATCH dan menolkan penghitung, sehingga pembatas
percobaan tidak berarti. [Pasti]

- 9 test dengan parameter rilis. Zeroize dibuktikan dengan memindai seluruh
  16 × 144 word memori dan register probe di simulasi.
- Bukti SAT Yosys setelah sintesis: setiap state ilegal mematikan semua izin dan
  menuju zeroize; ada kontrol negatif.
- 12 mutan guard terbunuh, termasuk clear yang melewatkan baris checksum dan
  sinkronisasi tamper 1-FF.

# 7. Injeksi fault debug (DEBUG_FAULT)

Build debug punya register DBG_FAULT untuk menambahkan delta ke produk satu
lane, serta DBG_ABFT untuk membaca hasil lokalisasi. Build rilis **tidak
memuat** port, register, atau logikanya (`docs/rtl_debug_fault.md`).

- **Delta aditif, bukan pengganti.** Dengan delta aditif, residu ABFT hanya
  bergantung pada delta dan baris. Dengan nilai pengganti, residu membocorkan
  T·p. [Pasti, aljabar]
- 288 injeksi (16 lane × 18 baris): semuanya FAULT; 256 dilokalisasi ke
  barisnya, 32 terdeteksi di baris checksum.
- Bukti build rilis: hasil praproses dan netlist Yosys sebelum optimasi tidak
  memuat jejak `dbg`; build debug dipakai sebagai kontrol positif.

# 8. Estimasi sumber daya

Estimasi Yosys (`synth_intel_alm -family cyclonev`) untuk Cyclone V
5CSEBA6U23I7 dengan parameter rilis. Kapasitas perangkat diambil dari ingatan
atas tabel Intel dan belum dicek ke datasheet. [Kemungkinan Besar]

| Modul | LUT (ALUT) | FF | Pengali | Memori |
|---|---|---|---|---|
| `mac_array` | 3.109 | 1.918 | 16 × 18×18 | – |
| `abft_check` | 462 | 291 | 1 × 27×27 + 1 × 9×9 | – |
| `template_mem` | 290 | 86 | 1 × 18×18 | 16 M10K |
| `decision` | 192 | 151 | – | – |
| `guard` | 143 | 103 | – | – |
| **`padan_avmm` (total)** | **3.924** | **2.612** | **19 pengali** | **16 M10K** |

| Sumber daya | Estimasi | % kapasitas |
|---|---|---|
| ALM | 1.962–3.924 | 4,7%–9,5% |
| FF | 2.612 | 1,6% |
| M10K | 16 blok | 2,9% |
| **Blok DSP** | **11–19 blok** | **9,8%–17%** |

**DSP bisa melewati 10%.** Penyebab utamanya 16 pengali lane, yang harus 18×18
karena baris Cw 16 bit; apakah Quartus memasangkan dua per blok belum diketahui.
Pengali di `abft_check` dan `template_mem` (3 blok) bisa dihapus dengan
geser-tambah. Hasilnya 7,1%–14%.

# 9. Verifikasi dan CI

`make test` menjalankan semua target di bawah, sekitar 25 menit. CI GitHub
Actions menjalankannya di setiap PR dan setiap push ke main. Setiap merge
dilakukan setelah CI hijau dan log-nya diperiksa.

| Target | Isi | Hasil terakhir |
|---|---|---|
| `check-baseline`, `test-baseline`, `test-audit` | Integritas baseline, test upstream, audit RTL + gate-level + bukti SAT CLA | lulus |
| `test-model`, `check-model-report` | Self-test model; dokumen model sinkron | lulus |
| `test-rtl` | Inti RTL vs model, 38.112 fault | 7/7 |
| `test-rtl-avmm` | Bus + decision, 814 keputusan, 48.765 fault | 7/7 |
| `test-rtl-guard` | Guard, parameter rilis | 9/9 |
| `check-rtl-guard-safe` | Bukti SAT safe-state | 21 bukti |
| `test-rtl-mutation` | Mutan RTL harus terbunuh | 18/18 |
| `check-rtl-infer` | M10K/DSP terinferensi; FF `decision` 151, `guard` 103 | lulus |
| `test-rtl-debug`, `check-rtl-release` | Build debug; bukti build rilis bersih | 4/4; PASS |
| `test-fpga-scripts` | Skrip FPGA tanpa Quartus, System Console vs RTL | 4/4 |

# 10. Batas dan risiko terbuka

1. **Belum ada Quartus, timing, atau board.** Semua klaim fungsional berlaku
   untuk simulasi RTL. Inferensi DSP/M10K dan logika safe-state baru terbukti
   untuk Yosys.
2. **Template selalu ada di luar chip.** Keadaan guard volatil dan setiap reset
   menghapus template, jadi host harus mengirim ulang template setiap boot.
3. **Pembatas hanya menghitung kegagalan berturut-turut.** Penyerang dengan satu
   probe sah bisa menyelipkannya setiap 4 percobaan.
4. **Fault kendali belum disimulasikan:** sequencer, tag baris, FSM. Flip pada
   tag baris bisa membuat ABFT dan kedua komparator salah secara konsisten.
   [Kemungkinan Besar]
5. **Fault ganda** bisa salah lokalisasi; lokalisasi tidak boleh dipakai untuk
   koreksi otomatis.
6. **Flip dua bit** bisa membawa LOCKD ke OPEN; flip satu bit selalu tertangkap.
7. **Bitstream debug adalah alat DoS** dan bisa dibangun lewat pengaturan Quartus
   di luar repo. Penandanya STATUS[31] = 1.
8. **Hasil INT8 vs float memakai data sintetis;** tidak ada klaim akurasi
   biometrik nyata.

# 11. Langkah berikutnya

1. **Putuskan soal DSP:** hapus 3 pengali di `abft_check` dan `template_mem`
   sekarang, atau tunggu fitter Quartus.
2. **Kompilasi di Quartus** mengikuti `docs/fpga_howto.md`. Lalu jalankan
   pemeriksaan wajib: DSP/M10K, register yang tidak boleh dihapus, Ignored
   Constraints, dan slack.
3. **Uji di board:** jalankan `padan_test.tcl` (target PASS 46/46), lalu uji
   tamper KEY0 secara manual.
4. **Pertimbangkan penghitung kegagalan total atau pembatas laju** bila ancaman
   probe sah relevan.
5. **Tambah simulasi fault kendali** (sequencer, tag baris) atau duplikasi
   kendali.
