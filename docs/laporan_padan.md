---
title: Laporan Proyek PADAN
subtitle: Identifikasi 1:N INT8 dengan ABFT, dari model hingga integrasi FPGA Kria KV260
date: Per 17 Oktober 2026 · repositori hudaubaya/padan, main @ 89875e3 + port KV260 (PR #8)
lang: id-ID
---

<!--
Sumber laporan. docs/laporan/Laporan_PADAN.docx dibangkitkan dari berkas ini:
    make laporan
`make check-laporan` (bagian dari `make test`) gagal bila .docx tidak sinkron.
Angka di sini ditulis tangan dari docs/ dan log CI; perbarui saat repo berubah.
-->

# Ringkasan

PADAN sudah memiliki golden model, RTL lengkap, antarmuka bus (inti gaya
Avalon-MM dengan wrapper AXI4-Lite), penjaga keamanan (guard), dan paket
integrasi Kria KV260 (proyek Vivado dan host Python di Linux PS). Semuanya
terbukti **di simulasi** dan lulus CI. **Belum ada satu pun hasil Vivado,
timing, atau board.** Itu adalah risiko terbesar proyek saat ini.

- **Fungsi:** 16 template × 128 byte INT8, skor s_j = Σ T[j,i]·p_i, keputusan
  MATCH / NO_MATCH / FAULT dengan latensi tetap 153 siklus.
- **Keamanan fault:** dari 48.765 fault bit tunggal yang disuntikkan lewat
  antarmuka bus, tidak satu pun menghasilkan MATCH yang salah.
- **Keamanan sistem:** pembatas percobaan, LOCK dengan τ terkunci, zeroize saat
  tamper atau FAULT berulang, dan FSM safe-state yang dibuktikan dengan SAT
  (Yosys).
- **Estimasi sumber daya (Yosys, K26):** semua di bawah 6% kapasitas. Masalah
  DSP di Cyclone V (9,8–17%) tidak berlaku lagi: 19 DSP48E2 = 1,5%.
- **Temuan saat port:** Yosys untuk Xilinx menggabungkan FF kode STATUS
  sehingga jarak NO_MATCH → MATCH turun dari 4 ke 2 flip FF. Sudah diperbaiki
  (bagian 4).
- **Status:** 7 PR sudah di-merge ke main; port KV260 diajukan sebagai PR #8.
  Setiap merge dilakukan setelah CI hijau dan log-nya diperiksa.

## Cara membaca label

| Label | Arti |
|---|---|
| [Pasti] | Dibuktikan oleh simulasi, bukti formal, aljabar, atau struktur netlist di repo ini. |
| [Kemungkinan Besar] | Inferensi kuat yang belum dibuktikan di sini, misalnya perilaku Vivado. |
| [Menebak] | Mengisi celah informasi; perlu dicek. |
| (model) | Angka dari golden model Python, bukan dari RTL, FPGA, atau silikon. |
| estimasi Yosys | Pemetaan Yosys `synth_xilinx -family xcup`, bukan laporan Vivado. |

# Kronologi

Tahap 1–10 dilakukan pada 6 Oktober 2026, tahap 11 pada 17 Oktober 2026.
Setiap pull request di-merge setelah CI hijau.

| Tahap | Commit / PR | Isi |
|---|---|---|
| 1. Kerangka dan baseline | c319f85 | Struktur repo; tiga desain TT07 disalin apa adanya beserta lisensi dan SHA256SUMS |
| 2. Audit baseline | ecbc278 | Ketiga baseline diuji apa adanya (RTL dan netlist gate-level) terhadap model Python |
| 3. Golden model | d1a274d (PR #1) | Model integer PADAN, analisis batas 32 bit, data sintetis INT8 vs float, simulasi fault |
| 4. RTL inti | 982d2a6 (PR #2) | `template_mem`, `mac_array`, `abft_check` + test cocotb dan uji mutasi |
| 5. Keputusan dan bus | 4210629 (PR #3) | `decision` (dua komparator), `padan_avmm` (slave Avalon-MM), paritas probe |
| 6. FPGA DE10-Nano | 1ed2f89 (PR #4) | Komponen Platform Designer, skrip GHRD, SDC, skrip System Console |
| 7. Guard | 811f8ce (PR #5) | Pembatas percobaan, LOCK + τ terkunci, FAULT, tamper (KEY0 di DE10-Nano), zeroize, safe-state |
| 8. Injeksi fault debug | 2e694e4 (PR #6) | Port `DEBUG_FAULT` dan bukti bahwa build rilis tidak memuatnya |
| 9. Estimasi sumber daya | (tanpa commit) | Yosys `synth_intel_alm` per modul (Cyclone V; diganti di tahap 11) |
| 10. Laporan | 89875e3 (PR #7) | Laporan ini (Markdown → .docx), `make check-laporan` |
| 11. Port Kria KV260 | PR #8 | `padan_axil` (AXI4-Lite), proyek Vivado, XDC tamper PMOD, host Python, inferensi UltraScale+, perbaikan `code_lo_n`; berkas DE10-Nano dihapus |

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
| `template_mem` | 16 bank block RAM × 144 word × 16 bit (T, C, Cw); hanya bisa ditulis; generator memperbarui C dan Cw di setiap tulis byte |
| `mac_array` | 16 lane MAC 16×8, adder tree, akumulator 32 bit; satu dot product per 8 siklus; 18 baris per MATCH (16 skor + C·p + Cw·p); probe 1.024 bit dengan paritas per byte |
| `abft_check` | S1, S2, d1, d2 dalam 40 bit; lokalisasi tanpa pembagi, maksimal 16 langkah |

- **38.112 fault** (lane, akumulator, setiap bit memori) terdeteksi dengan indeks
  benar; tidak ada alarm palsu pada 1.317 run bersih. [Pasti]
- **Biaya ABFT:** 16 siklus (+12,5%) untuk dua baris checksum.
- **Uji mutasi:** mutan `no_c`, `no_cw`, dan `weight_j` terbunuh. Mutan `no_c` dan
  `no_cw` membuktikan bahwa test tanpa fault saja tidak cukup, karena pemeriksa
  yang setengah mati tetap diam.

# 4. Keputusan dan antarmuka bus

`decision.v` memakai dua komparator yang ditulis berbeda (diversitas). τ di
komparator B disimpan sebagai komplemen; tanpa itu Yosys menggabungkan register
keduanya. `padan_avmm.v` adalah inti dengan slave Avalon-MM internal tanpa jalur
baca untuk template, probe, atau skor (`docs/rtl_decision.md`). Di KV260 ia
dibungkus `padan_axil.v` (AXI4-Lite) tanpa mengubah peta register.

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
- **Kode STATUS harus bertahan di netlist.** Kedua setengah kode legal selalu
  sama, dan Yosys `synth_xilinx` menggabungkan FF `code[1:0]` dengan
  `code[3:2]` (`synth_intel_alm` tidak). Akibatnya NO_MATCH → MATCH hanya butuh
  2 flip FF, bukan 4. [Pasti, Yosys] Perbaikan: setengah bawah disimpan terbalik
  (`code_lo_n`); FF `decision` kembali 151 di kedua alur, dan test fault kini
  membalik FF yang sebenarnya.

# 5. Integrasi FPGA Kria KV260

Board target sekarang Kria KV260 (Zynq UltraScale+ K26). Paket DE10-Nano
(tahap 6) dihapus. Paket KV260 **belum pernah dijalankan di Vivado atau di
board**. Tidak ada klaim hasil board (`docs/fpga_howto.md`).

| Bagian | Isi |
|---|---|
| `rtl/padan_axil.v` | Slave AXI4-Lite di atas `padan_avmm`. AW/W boleh datang dalam urutan apa pun; WSTRB ≠ `1111` → SLVERR tanpa efek; B ditahan sampai inti menerima tulis (zeroize, byte template). |
| `fpga/kv260/create_project.tcl` | Part `xck26-sfvc784-2LV-c`, board part KV260, PS → `M_AXI_HPM0_FPD` → SmartConnect → `padan_0` di `0xA000_0000` (4 KiB), `pl_clk0` 100 MHz. |
| `fpga/kv260/padan_kv260.xdc` | `tamper_n` di H12 (PMOD J2), LVCMOS33, pull-up, false path. H12/LVCMOS33 dikutip dari XDC resmi Xilinx Kria-PYNQ. [Pasti] Bahwa itu pin fisik 1 di J2: [Kemungkinan Besar]. |
| `fpga/kv260/build.tcl`, `check_reports.py` | Bitstream, laporan, XSA; pemeriksaan RAMB18 16, DSP 16, FF `decision` 151, `guard` 103, WNS/WHS/WPWS ≥ 0. |
| `sw/kv260/padan_test.py` | Host di Linux PS lewat `/dev/mem` (pustaka standar Python). Identifikasi baca-saja sebelum menulis; 3 galeri, 46 kasus dari model, pindai 1.024 word. |

- **Yang diuji di CI tanpa Vivado dan board:**
  - `padan_axil`: 6 test protokol (urutan AW/W, backpressure B/R, SLVERR, AR
    bersamaan, tamper) dan 8 mutan, semua terbunuh. [Pasti]
  - `padan_test.py` tanpa diubah melawan RTL lewat AXI: 46/46 PASS tanpa
    pelanggaran protokol; fault memori terdeteksi dan HALT setelah FAULT ke-3;
    base salah tidak menulis apa pun. [Pasti, simulasi]
  - Skrip Vivado di tclsh dengan stub: nilai kunci konsisten dengan RTL dan
    host, 4 kondisi error memberi pesan jelas.
- **Tidak tercakup:** Vivado sungguhan (otomasi block design, pengenalan
  interface AXI), `/dev/mem` dan PS, overlay device tree, timing.

# 6. Guard: keamanan di tingkat sistem

`guard.v` mengendalikan izin bus. Setiap reset melakukan zeroize sebelum
perangkat bisa dipakai (`docs/rtl_guard.md`).

| Fungsi | Perilaku |
|---|---|
| Pembatas percobaan | K = 5 NO_MATCH berturut-turut → LOUT (keluar hanya lewat reset); MATCH menolkan penghitung |
| LOCK | Setelah LOCK, template tidak bisa ditulis atau dihapus; probe dan MATCH tetap bisa |
| τ terkunci | Di LOCKD, decision memakai GUARD_TAU, bukan τ dari host |
| FAULT | Penghitung kumulatif; FAULT ke-3 → zeroize → HALT |
| Tamper | Pin PMOD J2 (KV260), sinkronisasi 2-FF → zeroize → HALT |
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

Estimasi Yosys (`synth_xilinx -family xcup -flatten`) untuk Zynq UltraScale+
K26 dengan parameter rilis. LUT = LUT1–LUT6; FF = FDRE/FDCE/FDPE/FDSE. Kapasitas:
1.248 DSP dari data AMD; LUT, FF, dan block RAM dari ingatan atas tabel K26 dan
belum dicek ke datasheet DS987. [Kemungkinan Besar]

| Modul | LUT | FF | DSP48E2 | Block RAM |
|---|---|---|---|---|
| `mac_array` | 3.121 | 1.866 (+11 SRL16E) | 16 | – |
| `abft_check` | 472 | 291 | 2 | – |
| `template_mem` | 286 | 86 | 1 | 16 RAMB18E2 |
| `decision` | 135 | 151 | – | – |
| `guard` | 169 | 103 | – | – |
| `padan_avmm` (inti) | 4.130 | 2.560 | 19 | 16 RAMB18E2 |
| **`padan_axil` (top KV260)** | **4.248** | **2.632** | **19** | **16 RAMB18E2** |

| Sumber daya | Estimasi | Kapasitas K26 | % |
|---|---|---|---|
| LUT | 4.248 | ± 117.120 | 3,6% |
| FF | 2.632 | ± 234.240 | 1,1% |
| RAMB18 | 16 | ± 288 | 5,6% |
| DSP48E2 | 19 | 1.248 | 1,5% |

**Keputusan DSP dari Cyclone V tidak diperlukan lagi.** Di Cyclone V, 19
pengali menjadi 11–19 blok DSP (9,8–17%). Di K26 satu DSP48E2 memuat satu
pengali 16×8, dan totalnya 1,5%. Menghapus 3 pengali di `abft_check` dan
`template_mem` tidak lagi sepadan dengan risiko mengubah RTL yang sudah
terverifikasi.

Angka Vivado bisa berbeda. Angka yang dikunci CI adalah jumlah primitif keras
dan FF register redundan, bukan LUT.

# 9. Verifikasi dan CI

`make test` menjalankan semua target di bawah, sekitar 35 menit. CI GitHub
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
| `test-rtl-mutation` | Mutan RTL harus terbunuh (3 inti, 3 decision, 12 guard, 8 AXI) | 26/26 |
| `check-rtl-infer` | Yosys UltraScale+: 16 RAMB18E2, 16 + 3 DSP48E2, tanpa LUTRAM; FF `decision` 151, `guard` 103 | lulus |
| `test-rtl-debug`, `check-rtl-release` | Build debug; bukti build rilis bersih (termasuk port `padan_axil`) | 4/4; PASS |
| `test-rtl-axil` | Wrapper AXI4-Lite, monitor protokol | 6/6 |
| `test-kv260-scripts` | Skrip Vivado (stub), parser laporan, host KV260 vs RTL lewat AXI | 5/5 |

# 10. Batas dan risiko terbuka

1. **Belum ada Vivado, timing, atau board.** Semua klaim fungsional berlaku
   untuk simulasi RTL. Inferensi block RAM/DSP, register redundan, dan logika
   safe-state baru terbukti untuk Yosys. Timing 100 MHz belum diketahui.
2. **Pemuatan bitstream di Linux KV260** (overlay device tree, `xmutil`) adalah
   bagian paling tidak pasti; tanpa overlay `pl_clk0` mungkin mati dan akses
   AXI menggantung. [Menebak]
3. **Template selalu ada di luar chip.** Keadaan guard volatil dan setiap reset
   menghapus template, jadi host harus mengirim ulang template setiap boot.
4. **Pembatas hanya menghitung kegagalan berturut-turut.** Penyerang dengan satu
   probe sah bisa menyelipkannya setiap 4 percobaan.
5. **Fault kendali belum disimulasikan:** sequencer, tag baris, FSM. Flip pada
   tag baris bisa membuat ABFT dan kedua komparator salah secara konsisten.
   [Kemungkinan Besar]
6. **Fault ganda** bisa salah lokalisasi; lokalisasi tidak boleh dipakai untuk
   koreksi otomatis.
7. **Flip dua bit** bisa membawa LOCKD ke OPEN; flip satu bit selalu tertangkap.
8. **Bitstream debug adalah alat DoS** dan bisa dibangun lewat `verilog_define`
   Vivado di luar repo. Penandanya STATUS[31] = 1.
9. **Tamper PMOD dengan pull-up internal** peka terhadap kabel lepas atau
   sentuhan ke GND; satu glitch sudah menghapus enrollment.
10. **Hasil INT8 vs float memakai data sintetis;** tidak ada klaim akurasi
   biometrik nyata.

# 11. Langkah berikutnya

1. **Buat proyek dan build di Vivado** mengikuti `docs/fpga_howto.md`, lalu
   jalankan `check_reports.py`: RAMB18 16, DSP 16, FF `decision` 151 dan
   `guard` 103, FSM guard tidak dikode ulang, WNS/WHS/WPWS ≥ 0 pada 100 MHz.
2. **Cek pin H12 = PMOD J2 pin 1** di skematik carrier KV260 sebelum menyambung
   kabel tamper.
3. **Uji di board:** muat bitstream dengan overlay, jalankan `padan_test.py`
   (target `PADAN KV260: PASS (46 kasus ...)`), lalu uji tamper PMOD manual.
4. **Pertimbangkan penghitung kegagalan total atau pembatas laju** bila ancaman
   probe sah relevan.
5. **Tambah simulasi fault kendali** (sequencer, tag baris) atau duplikasi
   kendali.
