# PADAN di DE10-Nano: kompilasi dan pemeriksaan wajib

> **Status: belum pernah dikompilasi dan belum pernah dijalankan di board.**
> Quartus, Platform Designer, dan System Console tidak tersedia di lingkungan
> pembuat repo ini. Tidak ada angka pemakaian sumber daya, timing, atau hasil
> board yang diklaim di dokumen ini. Tabel hasil di bagian 8 sengaja kosong dan
> diisi oleh orang yang menjalankan langkah-langkahnya.

Label keyakinan:
- **[Pasti]** dibuktikan di repo ini (simulasi, Yosys, atau test skrip).
- **[Kemungkinan Besar]** inferensi kuat yang belum dicek dengan alat Intel.
- **[Menebak]** perlu dicek sebelum dipercaya.

## Ringkasan

| Berkas | Isi |
|---|---|
| `fpga/ip/padan_avmm/padan_avmm_hw.tcl` | Komponen Platform Designer untuk `rtl/padan_avmm.v`. Slave Avalon-MM `s0` 32 bit, alamat word 10 bit (4 KiB). |
| `fpga/de10_nano/qsys/add_padan.tcl` | Skrip `qsys-script` yang menambahkan `padan_0` dan JTAG-to-Avalon master `padan_jtag` ke `soc_system.qsys` GHRD, lalu menghubungkannya ke lightweight HPS-to-FPGA bridge. |
| `fpga/de10_nano/padan_de10_nano.sdc` | SDC pengganti SDC GHRD |
| `fpga/de10_nano/sysconsole/padan_test.tcl` | Skrip System Console: enroll template sintetis, kirim probe, bandingkan dengan model |
| `fpga/de10_nano/sysconsole/padan_vectors.tcl` | Vektor dan STATUS harapan, dihasilkan dari `model/padan.py` oleh `gen_vectors.py` |
| `fpga/de10_nano/scripts/check_reports.py` | Pemeriksaan DSP/M10K dari laporan fitter |
| `fpga/de10_nano/scripts/check_timing.tcl` | Pemeriksaan slack dan Ignored Constraints (`quartus_sta -t`) |

### Peta alamat

| Master | Alamat byte `padan_0` | STATUS (word `0x302`) |
|---|---|---|
| `padan_jtag` (System Console) | `0x0004_0000`–`0x0004_0FFF` | `0x0004_0C08` |
| HPS, lightweight bridge | `0xFF24_0000`–`0xFF24_0FFF` | `0xFF24_0C08` |

Register map: `docs/rtl_decision.md`. **Hanya akses 32 bit.** Slave tidak punya
byteenable, sehingga tulis 8/16 bit menulis word penuh dengan byte lain tidak
terdefinisi.

### Mengapa berbasis GHRD Terasic, bukan sistem HPS dari nol

- **Konfigurasi HPS khusus board.** Parameter DDR3 (timing, ODT, drive), pin
  HPS, dan clock HPS DE10-Nano ditentukan oleh Terasic. Menuliskannya dari
  ingatan berisiko DDR gagal kalibrasi, dan itu tidak bisa dicek tanpa board.
  [Kemungkinan Besar]
- **Cukup menambah, bukan menulis ulang.** `add_padan.tcl` hanya menambah ke
  sistem GHRD yang sudah teruji. Instance HPS dan clock source dicari menurut
  **kelas** (`altera_hps`, `clock_source`), bukan nama.
- **Port top GHRD tidak berubah.** `padan_0` tidak mengekspor conduit, jadi
  `DE10_NANO_SoC_GHRD.v` tidak perlu disunting.
- **GHRD tidak disalin ke repo.** Ia berasal dari CD Terasic dengan lisensinya
  sendiri. [Menebak tentang syarat redistribusinya] Direktori
  `fpga/de10_nano/ghrd/` ada di `.gitignore`.

**Reset.** `padan_0` direset oleh `clk_reset` clock source GHRD, **tidak** oleh
`hps_0.h2f_reset`. Jalur JTAG harus tetap bisa dipakai walau HPS tidak boot.
[Menebak] Tanpa kartu SD, h2f_reset mungkin tetap aktif.

## 1. Prasyarat

- **Quartus Prime Lite atau Standard,** versi yang sama dengan GHRD di CD
  DE10-Nano yang dipakai. Cyclone V didukung di edisi Lite. `add_padan.tcl` dan
  `padan_avmm_hw.tcl` memakai `package require -exact qsys 16.1`, jadi butuh
  Platform Designer ≥ 16.1.
- **CD DE10-Nano dari Terasic,** proyek `DE10_NANO_SoC_GHRD`.
- **Driver USB-Blaster II.**
- **Python 3 dengan numpy,** hanya untuk membangkitkan ulang vektor.

Device DE10-Nano: `5CSEBA6U23I7`. [Kemungkinan Besar] Konfirmasi di proyek GHRD:
*Assignments → Device*.

## 2. Siapkan proyek

```sh
REPO=/jalur/ke/padan
cp -r <CD>/Demonstrations/SOC_FPGA/DE10_NANO_SoC_GHRD $REPO/fpga/de10_nano/ghrd
cd $REPO/fpga/de10_nano/ghrd
```

Kompilasi GHRD **tanpa perubahan** sekali dulu, ikuti README GHRD. Ini memberi
pembanding bila langkah berikutnya gagal.

## 3. Tambahkan padan ke sistem Platform Designer

```sh
qsys-script --system-file=soc_system.qsys \
    --search-path="$REPO/fpga/ip/**/*,\$" \
    --script=$REPO/fpga/de10_nano/qsys/add_padan.tcl
# alamat lain: tambahkan --cmd="set PADAN_BASE 0x00050000"
```

Buka `soc_system.qsys` di Platform Designer, dengan search path yang sama di
*Tools → Options → IP Search Path*, lalu periksa:

- **Tidak ada error di panel Messages.** Bila ada tumpang-tindih alamat di jendela
  lightweight bridge, pilih `PADAN_BASE` lain dan ulangi dari salinan
  `soc_system.qsys` yang bersih. `add_padan.tcl` menolak berjalan dua kali.
- **Address Map:** `padan_0.s0` ada di `PADAN_BASE` untuk `hps_0.h2f_lw_axi_master`
  dan `padan_jtag.master`, dengan span `0x1000`.

Lalu generate:

```sh
qsys-generate soc_system.qsys --synthesis=VERILOG --search-path="$REPO/fpga/ip/**/*,\$"
```

### 3b. Hubungkan tamper ke KEY[0] (wajib)

`add_padan.tcl` mengekspor input tamper `guard.v` sebagai conduit `padan_tamper`.
Di top GHRD (`DE10_NANO_SoC_GHRD.v`), tambahkan pada instance `soc_system u0`:

```verilog
    .padan_tamper_tamper_n (KEY[0]),   // aktif rendah: tombol ditekan = tamper
```

- **Nama port.** [Kemungkinan Besar] Platform Designer menamai port ekspor
  `<nama ekspor>_<nama port>`, yaitu `padan_tamper_tamper_n`. Pastikan dengan
  membaca deklarasi modul `soc_system` di `soc_system/synthesis/soc_system.v`.
- **Jangan dibiarkan tidak terhubung.** [Kemungkinan Besar] Quartus mengikat
  input yang tidak terhubung ke 0. Bagi `guard.v`, itu berarti tamper permanen,
  dan setiap reset langsung berakhir di HALT dengan memori nol.
- **KEY[0] boleh tetap dipakai GHRD.** KEY[0] juga masuk ke debouncer
  `button_pio` GHRD. Fanout tambahan tidak mengubah perilaku itu.
- **Sinyal mentah, tanpa debounce.** `guard.v` hanya menyinkronkan KEY[0] dengan
  2-FF. Pantulan tombol tidak berpengaruh, karena tamper sekali saja sudah
  final (HALT sampai reset).

## 4. SDC dan setelan proyek

Di `DE10_NANO_SoC_GHRD.qsf`:

```tcl
# ganti baris SDC_FILE bawaan GHRD dengan:
set_global_assignment -name SDC_FILE <REPO>/fpga/de10_nano/padan_de10_nano.sdc
set_global_assignment -name IP_SEARCH_PATHS "<REPO>/fpga/ip/**/*"
```

- **Ganti, jangan tambah.** SDC ini mendefinisikan ulang `FPGA_CLK1_50`/`2`/`3` dan
  `altera_reserved_tck`. Bila dipakai bersama SDC GHRD, clock didefinisikan dua
  kali.
- **Nama port mengikuti top GHRD** (`FPGA_CLK*_50`, `KEY[*]`, `SW[*]`, `LED[*]`).
  [Kemungkinan Besar] Nama yang tidak cocok muncul di pemeriksaan wajib 6b.
- **padan_avmm tidak butuh constraint khusus.** Ia sinkron terhadap clock `clk_0`
  (50 MHz). Satu-satunya input asinkron adalah `tamper_n` dari KEY[0]. Input itu
  masuk lewat sinkronisasi 2-FF di `guard.v` dan sudah tercakup
  `set_false_path -from KEY[*]`.

## 5. Kompilasi

```sh
quartus_sh --flow compile DE10_NANO_SoC_GHRD
```

Bila README GHRD meminta menjalankan `hps_sdram_p0_pin_assignments.tcl` setelah
Analysis & Synthesis pertama, ikuti urutan itu. Itu bagian dari alur HPS SDRAM
GHRD, bukan dari padan. [Kemungkinan Besar]

## 6. Pemeriksaan wajib (berhenti bila satu gagal)

### 6a. Pemakaian DSP dan M10K

```sh
python3 $REPO/fpga/de10_nano/scripts/check_reports.py output_files DE10_NANO_SoC_GHRD
```

Atau di GUI: *Compilation Report → Fitter → Resource Section → Resource
Utilization by Entity*. Lihat baris instance di bawah `soc_system:u0`.

| Instance | Kolom | Harus | Alasan |
|---|---|---|---|
| `padan_avmm:padan_0` | M10Ks | **= 16** | 16 bank lane `template_mem`, satu M10K per bank |
| `template_mem:u_mem` | M10Ks | **= 16** | sama |
| `mac_array:u_mac` | DSP Blocks | **≥ 8** | 16 pengali 16×8 bertanda, dua per blok DSP (mode 18×18) |

- **Total DSP `padan_avmm` diperkirakan 8–11 blok.** Selain lane, ada pengali
  bobot di `template_mem` dan `abft_check`. Yosys memetakan 16 MUL18X18 untuk
  lane, 1 MUL18X18 untuk `template_mem`, serta 1 MUL27X27 + 1 MUL9X9 untuk
  `abft_check` [Pasti untuk Yosys]. Angka Quartus bisa berbeda.
- **Tanda inferensi gagal:**
  - `mac_array` DSP = 0: pengali dibangun dari ALM.
  - `template_mem` M10K = 0: memori menjadi register atau MLAB.
  - Penyebab dan gaya penulisannya: `docs/rtl_style.md` bagian 3–4.
- **Register redundan `decision` tidak boleh dihapus.** Periksa juga *Analysis &
  Synthesis → Optimization Results → Register Statistics → Removed Registers*:
  tidak boleh ada `tau_a`, `tau_bn`, `best_a`, `best_b`, `idx_a`, `idx_b` dari
  `decision:u_dec`. Bila ada, kedua komparator tidak lagi independen
  (`docs/rtl_style.md` bagian 8). `check_reports.py` belum memeriksa ini.
- **Register guard tidak boleh dihapus atau dikode ulang.**
  - *Removed Registers* tidak boleh memuat `fail`, `fail_n`, `k`, `k_n`, `fault`,
    `fault_n`, `state`, atau `t_sync` dari `guard:u_guard`.
  - *Analysis & Synthesis → State Machines*: bila `guard:u_guard|state` muncul,
    pengodeannya harus sama dengan kode di `rtl/guard.v` (ZB 0000, OPEN 0011,
    dan seterusnya), bukan one-hot.
  - Bila Quartus mengode ulang atau menghapus state yang "tak terjangkau", logika
    safe-state (state ilegal → zeroize) bisa hilang. Bukti SAT di repo hanya
    mencakup sintesis Yosys (`docs/rtl_guard.md`).
  - [Menebak] Bila itu terjadi, setel *State Machine Processing* ke *User-Encoded*
    untuk entity `guard`.

### 6b. Ignored Constraints

Di Timing Analyzer: *Tasks → Diagnostic → Report Ignored Constraints*.
[Kemungkinan Besar untuk letak menu]

- **Harus kosong.** Setiap baris berarti constraint SDC yang tidak mengenai
  apa pun, biasanya karena nama port atau clock salah. Constraint itu tidak
  berlaku, walau kompilasi tetap "berhasil".
- `check_timing.tcl` (6c) menulis daftar yang sama ke
  `padan_ignored_constraints.txt`.

### 6c. Slack

```sh
quartus_sta -t $REPO/fpga/de10_nano/scripts/check_timing.tcl DE10_NANO_SoC_GHRD
```

- Untuk **setiap** kondisi operasi (model Slow dan Fast, semua suhu), worst slack
  **setup, hold, recovery, dan removal harus ≥ 0**.
- Di GUI: *Timing Analyzer → Tasks → Macros → Report All Summaries*.
- `check_timing.tcl` belum pernah dijalankan di Quartus. Bila satu perintahnya
  gagal di versi Anda, pakai GUI.
- Disarankan juga: *Report Unconstrained Paths*. Tidak boleh ada path tanpa
  constraint di dalam `padan_0`.

## 7. Uji di board dengan System Console

1. Program FPGA:
   ```sh
   quartus_pgm -m jtag -o "p;output_files/DE10_NANO_SoC_GHRD.sof@2"
   ```
   [Kemungkinan Besar] Di rantai JTAG DE10-Nano, FPGA adalah device ke-2 (HPS
   ke-1). Cek dengan `jtagconfig`.
2. Jalankan:
   ```sh
   system-console -cli --script=$REPO/fpga/de10_nano/sysconsole/padan_test.tcl
   ```
   - **Pemilihan master.** Skrip memilih master yang terlihat seperti `padan_0`
     dengan **membaca saja**: STATUS valid, dan area ENROLL/PROBE/kosong
     bernilai 0. Bila lebih dari satu atau tidak ada yang cocok, skrip mencetak
     daftar service master. Set `PADAN_MASTER` (indeks atau sub-string path)
     sebagai variabel environment.
   - **Alamat lain.** Bila `PADAN_BASE` diubah di langkah 3, set juga variabel
     `PADAN_BASE`.
   - **Guard harus OPEN.** Jalankan skrip setelah program FPGA atau reset, tanpa
     LOCK, dan jangan tekan KEY0. Skrip menunggu zeroize boot selesai, lalu
     berhenti dengan FAIL yang menyebut state dan alasan guard bila state-nya
     bukan OPEN. Ia juga berhenti bila guard keluar dari OPEN di tengah uji.
     Urutan vektor dijamin tidak melebihi 2 NO_MATCH berturut-turut (batas
     lockout K = 5).
3. Untuk setiap galeri (3 galeri, 46 kasus; 26 MATCH dan 20 NO_MATCH dari model),
   skrip melakukan:
   - ENROLL_CLR, lalu tulis 512 word template;
   - baca **seluruh 1.024 alamat** (semua 0 kecuali STATUS);
   - untuk setiap kasus: tulis probe, MATCH(τ), tunggu `busy` = 0, lalu
     bandingkan `STATUS[11:0]` dengan nilai dari model.
4. Hasil akhir dicetak sebagai satu baris `PADAN SYSCON: PASS ...` atau
   `PADAN SYSCON: FAIL ...`.

**Yang sudah diuji di repo ini** (`make test-fpga-scripts`):
- `padan_test.tcl` **tanpa diubah** dijalankan di `tclsh` melawan RTL
  `padan_avmm` lewat shim System Console (`tb/fpga/`). Hasilnya PASS 46/46.
  [Pasti]
- Bila satu bit memori template dibalik, skrip melaporkan FAIL (FAULT, `0xF0F`).
  [Pasti]
- Deteksi master memilih master padan dan mengabaikan master lain. [Pasti]
- Dengan guard rilis, FAULT ke-3 memicu zeroize dan HALT, dan skrip berhenti
  dengan pesan guard. Bila guard LOCKD di awal, skrip menolak berjalan tanpa
  menulis apa pun. [Pasti, di simulasi]
- Yang **tidak** tercakup: JTAG sungguhan, interkoneksi Platform Designer, dan
  timing.

### Akses dari HPS (opsional, belum diuji)

- **Bridge harus aktif dulu.** Di Linux, misalnya lewat
  `/sys/class/fpga-bridge/*lwhps2fpga*/enable`, atau `bridge enable` di U-Boot.
  [Kemungkinan Besar]
- **Contoh baca STATUS:** `devmem 0xFF240C08 32`. Gunakan akses 32 bit saja.

### Uji tamper manual (setelah `padan_test.tcl` PASS)

Uji ini **merusak** isi template. Jalankan di System Console:

```tcl
set m [lindex [get_service_paths master] <indeks padan>]
claim_service master $m "" ""
master_read_32 $m 0x00040C0C 1   ;# GUARD_STATUS: [3:0] = 0x3 (OPEN)
# tekan dan lepas KEY0
master_read_32 $m 0x00040C0C 1   ;# harus [3:0] = 0xA (HALT), [17:16] = 1 (TAMPER)
master_read_32 $m 0x00040C08 1   ;# STATUS[11:0] = 0xF00 (NONE)
```

Setelah itu, tekan reset (atau program ulang FPGA). Guard melakukan zeroize
boot, lalu kembali ke OPEN dengan memori kosong.

**Batas uji ini.** Ia hanya membuktikan jalur KEY0 → guard → HALT. Bahwa
memori benar-benar nol hanya terbukti di simulasi (`tb/guard`), karena tidak
ada jalur baca template dari bus.

## 8. Catat hasil (diisi oleh yang menjalankan)

| Butir | Nilai | Lulus? |
|---|---|---|
| Commit repo | | |
| Versi Quartus, versi CD GHRD | | |
| M10K `padan_0` / `u_mem` | | = 16 |
| DSP `u_mac` / total `padan_0` | | ≥ 8 / – |
| Register `u_dec` yang dihapus | | harus tidak ada |
| Ignored Constraints | | harus kosong |
| Worst slack setup / hold / recovery / removal (per kondisi) | | ≥ 0 |
| Register `u_guard` yang dihapus / state guard dikode ulang | | harus tidak ada |
| `padan_test.tcl` | | `PADAN SYSCON: PASS (46 kasus ...)` |
| Uji tamper manual: GUARD_STATUS sebelum / sesudah KEY0 | | `0x00000503` → `[3:0]=0xA`, alasan 1 |

Hasil board hanya berlaku untuk commit, bitstream, dan board tempat ia dijalankan.

## 9. Yang dicek di CI dan yang tidak

| Dicek di CI (`make test-fpga-scripts`) | Tidak dicek |
|---|---|
| Port `padan_avmm_hw.tcl` sama dengan `rtl/padan_avmm.v`; fileset cukup untuk elaborasi (Yosys) | Platform Designer menerima komponen dan propertinya |
| Logika `add_padan.tcl` terhadap GHRD tiruan | Hasil pada `soc_system.qsys` GHRD asli |
| `padan_test.tcl` + vektor model melawan RTL | JTAG, System Console asli, board |
| Logika PASS/FAIL `check_timing.tcl` dan parser `check_reports.py` (data tiruan) | Perintah `quartus_sta` asli, format laporan Quartus asli |
| SDC bebas error Tcl | Nama port SDC cocok dengan top GHRD (pemeriksaan 6b) |
| `padan_vectors.tcl` sinkron dengan model | Kompilasi, pemakaian sumber daya, slack |
| Conduit `tamper` ada di `_hw.tcl` dan diekspor oleh `add_padan.tcl` | Nama port ekspor dan sambungan KEY[0] di top GHRD |
| Urutan vektor: maksimal 2 NO_MATCH berturut-turut (`gen_vectors.py --check`) | Perilaku guard di board, termasuk KEY0 sungguhan |
