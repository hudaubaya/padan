# PADAN di Kria KV260: build dan pemeriksaan wajib

> **Status: build Vivado sudah dijalankan pengguna, board belum.**
> - **Build Vivado:** Vivado 2026.1 di Windows, 21 Oktober 2026. Laporan
>   aslinya ada di `fpga/kv260/testdata/vivado_2026.1/`, dan semua pemeriksaan
>   bagian 5 lulus.
> - **Board:** pemuatan bitstream dan `padan_test.py` di KV260 belum pernah
>   dijalankan, dan tidak ada hasil board yang diklaim di sini.
> - **Bagian 8** diisi oleh orang yang menjalankan langkah-langkahnya.

Label keyakinan:
- **[Pasti]** dibuktikan di repo ini (simulasi, Yosys, test skrip) atau dikutip
  dari berkas resmi AMD/Xilinx yang disebut.
- **[Kemungkinan Besar]** inferensi kuat yang belum dicek dengan Vivado/board.
- **[Menebak]** perlu dicek sebelum dipercaya.

## Ringkasan

```
 Linux di PS (A53)                 PL (K26)
 sw/kv260/padan_test.py
   /dev/mem, 32 bit  ──M_AXI_HPM0_FPD──> AXI SmartConnect ──AXI4-Lite──> padan_axil ──> padan_avmm (inti)
                                                                          ^
 pl_clk0 100 MHz, pl_resetn0 → proc_sys_reset                            tamper_n ← PMOD J2 pin 1 (H12)
```

| Berkas | Isi |
|---|---|
| `rtl/padan_axil.v` | Slave AXI4-Lite di atas `padan_avmm` (peta register tidak berubah). WSTRB ≠ `1111` → SLVERR tanpa efek; B ditahan sampai inti menerima tulis. |
| `fpga/kv260/create_project.tcl` | Proyek Vivado: part `xck26-sfvc784-2LV-c`, board part KV260 SOM, block design PS + SmartConnect + `padan_axil` (module reference), alamat tetap. |
| `fpga/kv260/padan_kv260.xdc` | Pin `tamper_n` (H12, LVCMOS33, pull-up) dan false path. |
| `fpga/kv260/build.tcl` | Sintesis, implementasi, bitstream (`.bit` dan `.bin`), laporan, XSA. |
| `fpga/kv260/check_reports.py` | Pemeriksaan laporan utilisasi hierarkis dan timing Vivado. |
| `sw/kv260/padan_test.py` | Host di Linux PS (pustaka standar Python 3): enroll, probe, bandingkan dengan model. |
| `sw/kv260/padan_vectors.json` | Vektor dan STATUS harapan dari `model/padan.py` (`gen_vectors.py`). |

### Peta alamat

| Master | Alamat byte `padan_0` | STATUS (word `0x302`) | GUARD_STATUS (`0x303`) |
|---|---|---|---|
| PS, `M_AXI_HPM0_FPD` | `0xA000_0000`–`0xA000_0FFF` | `0xA000_0C08` | `0xA000_0C0C` |

- Register map: `docs/rtl_decision.md`. Alamat byte = 4 × alamat word.
- **Hanya akses 32 bit sejajar.** Tulis 8/16 bit dijawab SLVERR dan tidak
  ditulis [Pasti, simulasi: `tb/axil`]. Di Linux, SLVERR pada akses CPU
  kemungkinan berakhir sebagai SIGBUS atau abort eksternal [Menebak].
- `0xA000_0000` adalah awal jendela HPM0_FPD di peta alamat ZynqMP
  [Kemungkinan Besar]; cek *Address Editor* setelah `create_project.tcl`.

### Keputusan desain

- **Wrapper, bukan inti baru.** `padan_avmm` tetap inti dengan bus register
  internal gaya Avalon-MM (waitrequest/readdatavalid). Semua test inti (`tb/avmm`,
  `tb/guard`, `tb/debug`) tetap berlaku. `padan_axil` hanya menerjemahkan
  protokol dan diuji terpisah (`tb/axil`, 6 test, 8 mutan).
- **Host di Linux PS lewat `/dev/mem`.** Tidak butuh driver kernel. Skrip
  memeriksa dengan **baca saja** bahwa jendela itu PADAN sebelum menulis apa pun.
- **Tamper dari pin PMOD.** KV260 tidak punya tombol pengguna yang terhubung ke
  PL [Kemungkinan Besar], jadi tamper diambil dari PMOD J2.
- **Clock 100 MHz.** Inti di DE10-Nano dirancang untuk 50 MHz. Jalur kritis di
  K26 belum diketahui; bila timing gagal, turunkan
  `FCLK_MHZ` di `create_project.tcl` (misalnya 50) [Kemungkinan Besar].

## 1. Prasyarat

- **Vivado** dengan dukungan Zynq UltraScale+ dan **board file Kria** (Vivado →
  *Tools → XHub Stores → Boards*, pasang *Kria KV260 Vision AI Starter Kit*).
  `create_project.tcl` berhenti dengan pesan jelas bila board part
  `*kv260_som*` tidak ditemukan.
- **KV260 dengan Linux** (image Ubuntu untuk Kria atau PetaLinux) dan Python 3.
  Image harus mendukung pemuatan bitstream saat runtime (`xmutil`/`fpgautil`)
  [Kemungkinan Besar].
- **Python 3 dengan numpy** di mesin pengembang, hanya untuk membangkitkan ulang
  vektor.

## 2. Buat proyek

```sh
REPO=/jalur/ke/padan
vivado -mode batch -source $REPO/fpga/kv260/create_project.tcl -tclargs $REPO/build/kv260
```

Buka `build/kv260/padan_kv260.xpr` di Vivado, lalu periksa:

- **Block design valid.** `validate_bd_design` dijalankan skrip; tidak boleh ada
  error atau critical warning di panel Messages.
- **Interface AXI dikenali.** `padan_0` harus punya satu interface `s_axi`
  (AXI4-Lite, 12 bit alamat) dengan `s_axi_aclk`/`s_axi_aresetn` terasosiasi.
  Vivado mengenalinya dari nama port `s_axi_*` [Kemungkinan Besar]. Bila tidak,
  otomasi AXI gagal; tambahkan atribut `X_INTERFACE_INFO` di `padan_axil.v`.
- **Address Editor:** `padan_0/s_axi` di `0xA000_0000`, range 4K, untuk
  `zynq_ultra_ps_e_0/Data`.
- **Clock:** `padan_0/s_axi_aclk` tersambung ke `pl_clk0` (skrip berhenti bila
  tidak), dan `pl_clk0` = 100 MHz.
- **`tamper_n`** adalah port luar block design dan ada di wrapper.

## 3. Pin tamper (PMOD J2)

`padan_kv260.xdc` memasang `tamper_n` ke **H12**, LVCMOS33, dengan pull-up
internal.

- **[Pasti]** H12/LVCMOS33 sama dengan `pmod[0]` di XDC resmi Xilinx Kria-PYNQ
  (`kv260/base/vivado/constraints/base.xdc`: Bank 45, `som240_1_b13`,
  `IO_L4N_AD12N_45`).
- **[Kemungkinan Besar]** `pmod[0]` adalah pin fisik 1 di header J2. Cek dengan
  skematik carrier KV260 sebelum menyambung kabel.
- **Cara pakai:** pin dibiarkan terbuka = normal (pull-up menahan 1). Sambungkan
  ke GND (pin GND di J2) = tamper. Pull-up internal lemah; untuk kabel panjang
  pakai pull-up eksternal (mis. 4,7 kΩ ke 3V3) [Kemungkinan Besar].
- **Satu glitch rendah sudah final.** `guard.v` hanya menyinkronkan dengan 2-FF.
  Tamper yang tertangkap satu sisi clock memicu zeroize dan HALT sampai reset.
- **Jangan hapus constraint pin.** Port tanpa `PACKAGE_PIN` membuat
  `write_bitstream` gagal (DRC NSTD/UCIO) [Kemungkinan Besar]. Itu disengaja:
  input tamper yang mengambang lebih buruk.

## 4. Build

```sh
vivado -mode batch -source $REPO/fpga/kv260/build.tcl -tclargs $REPO/build/kv260 8
```

Hasil di `build/kv260`: bitstream (`padan_kv260.runs/impl_1/padan_bd_wrapper.bit`
dan `.bin`), `padan_kv260.xsa`, dan laporan di `reports/`.

## 5. Pemeriksaan wajib (berhenti bila satu gagal)

### 5a. Sumber daya dan register redundan

```sh
python3 $REPO/fpga/kv260/check_reports.py $REPO/build/kv260/reports
```

| Modul | Kolom | Harus | Alasan |
|---|---|---|---|
| `template_mem` | RAMB18 + 2 × RAMB36 | **= 16** | 16 bank lane, satu block RAM 18 Kb per bank |
| `template_mem` | LUTRAMs | **= 0** | memori bukan LUTRAM |
| `mac_array` | DSP Blocks | **16–18** | 16 pengali lane; Vivado 2026.1 menambah 2 DSP untuk adder `tree` |
| `mac_array` | LUTRAMs | **= 0** | probe tetap register |
| `decision` | FFs | **= 151** | kedua komparator tidak digabung |
| `guard` | FFs | **= 103** | register nilai + komplemen bertahan |

- **Angka harapan sama dengan Yosys** (`make check-rtl-infer`,
  `synth_xilinx -family xcup`) [Pasti untuk Yosys], kecuali DSP `mac_array`.
  Bila Vivado memberi angka lain, cari penyebabnya sebelum melanjutkan.
- **DSP `mac_array` = 18 di Vivado 2026.1** [Pasti, dari `dsp_cells.txt` di
  `testdata`].
  - 16 DSP lane menyerap `g_sum4[*].sum` lewat kaskade (`g_lane[*].prod_reg`,
    `g_sum4[*].sum0`, `sum0__0`, `sum_reg`).
  - 2 DSP sisanya (`tree0`, `tree_reg`) dipakai sebagai adder untuk `tree`.
  - Akumulator `acc` tetap di fabric (FDRE).
  - Kurang dari 16 berarti ada pengali di fabric. Lebih dari 18 belum pernah
    terlihat.
  - Daftar sel bisa dicetak di Tcl Console setelah `open_run impl_1`:
    `get_cells -hier -filter {REF_NAME == DSP48E2}`.
- **Vivado menggabungkan register ekuivalen secara default** [Kemungkinan Besar].
  RTL memasang `keep`/`dont_touch` pada register komparator dan guard. Selain
  itu, setengah bawah `code` di `decision.v` disimpan terbalik (`code_lo_n`)
  karena Yosys terbukti menggabungkan `code[1:0]` dengan `code[3:2]` tanpa itu
  [Pasti untuk Yosys]. FF `decision` < 151 berarti ada yang digabung.
- **FSM `guard` dan `decision` tidak boleh dikode ulang.** `check_reports.py`
  membaca semua `padan_kv260.runs/*/runme.log`. `padan_axil` disintesis
  terpisah di run `padan_bd_padan_0_0_synth_1`, bukan di `synth_1` [Pasti,
  Vivado 2026.1]. Tidak boleh ada `[Synth 8-802]` untuk `guard` atau `decision`.
  - RTL memakai `fsm_encoding = "none"`. Bila Vivado tetap mengekstrak FSM,
    logika safe-state bisa hilang, dan bukti SAT di repo hanya berlaku untuk
    Yosys (`docs/rtl_guard.md`) [Kemungkinan Besar].
  - Vivado 2026.1 mematuhinya [Pasti].
  - FSM lain yang dikode ulang dicetak sebagai INFO. Di Vivado 2026.1 ada empat:
    `template_mem`, `abft_check` (sequential), `padan_avmm`, dan `padan_axil`
    (one-hot). Cabang `default` mereka kemungkinan besar hilang (lihat laporan,
    risiko terbuka).
- **Hasil Vivado 2026.1 untuk `padan_axil`:** 1.559 LUT, 2.009 FF, 11 SRL,
  16 RAMB18, 21 DSP48E2 [Pasti, dari laporan]. Seluruh desain dengan
  SmartConnect memakai 1.996 LUT dan 2.459 FF. `guard` memakai 424 LUT,
  sedangkan Yosys 169; bukti safe-state hanya berlaku untuk netlist Yosys.
- **Total perangkat (estimasi Yosys, bukan Vivado)** untuk `padan_axil`:
  ± 4.250 LUT, ± 2.630 FF, 11 SRL16E, 16 RAMB18E2, 19 DSP48E2. Terhadap
  kapasitas K26 (± 117.120 LUT, ± 234.240 FF, 288 RAMB18, 1.248 DSP) semuanya
  di bawah 6 % [Kemungkinan Besar; kapasitas dari ingatan, cek *Device* di
  Vivado].

### 5b. Timing

`check_reports.py` juga membaca `timing_summary.rpt` dan `cdc.rpt`:

- WNS, WHS, dan WPWS harus **≥ 0**, dan laporan harus menyatakan
  *All user specified timing constraints are met.*
- `clk_pl_0` di Clock Summary harus berperiode **10,000 ns** (100 MHz). Tanpa
  pemeriksaan ini, slack positif tidak berarti apa-apa.
- `cdc.rpt` harus memuat **tepat satu** perlintasan, yaitu `tamper_n`: dari
  input port ke `clk_pl_0`, 1 endpoint, dengan Unsafe, Unknown, dan No
  ASYNC_REG semuanya 0.
- Vivado 2026.1 memberi WNS +3,680 ns, WHS +0,025 ns, dan WPWS +3,500 ns.
  Jalur terlambat ada di `template_mem`, dari block RAM ke DSP `g_wdelta`.
- Periksa juga `reports/methodology.rpt` secara manual.

## 6. Muat bitstream di KV260

Ini bagian yang paling tidak pasti, karena bergantung pada image Linux.

1. **Device tree overlay.** Linux perlu overlay yang mengaktifkan `pl_clk0` dan
   memuat bitstream. Bangkitkan dari XSA, misalnya dengan `xsct` (`createdts
   -hw padan_kv260.xsa -overlay -compile`) lalu `dtc -@ -O dtb -o padan.dtbo
   pl.dtsi` [Kemungkinan Besar; cek dokumentasi Kria untuk versi Anda].
   Tanpa overlay, `pl_clk0` mungkin mati dan akses AXI menggantung [Menebak].

   Periksa `pl.dtsi` sebelum dikompilasi. Dari XSA proyek ini (diuji 21
   Oktober 2026), isinya sebagai berikut [Pasti untuk berkas itu]:
   - `padan_axil@a0000000` dengan `reg = <0x0 0xa0000000 0x0 0x1000>`, sama
     dengan base dan SPAN `padan_test.py`;
   - `clocks = <&zynqmp_clk 71>`, yaitu `pl_clk0`;
   - node `xlnx,fclk` untuk clock 71 sekitar 99,999 MHz, yang menjaga
     `pl_clk0` tetap hidup;
   - parameter `kw = 4`, `fw = 2`, `k-default = 5`, `fault-max = 3`, sama
     dengan default `rtl/padan_axil.v` (build rilis).

   Node `clocking1` (clock 72, `pl_clk1`) juga muncul karena preset board,
   meskipun tidak dipakai PADAN.

   **`firmware-name` harus sama dengan nama berkas `.bit.bin`.** `createdts`
   menamainya dari XSA (`padan_kv260.bit.bin`). Bila namanya tidak sama, Linux
   tidak menemukan bitstream saat overlay diterapkan [Kemungkinan Besar]. Cek
   dengan `grep firmware-name pl.dtsi`.
2. **Pasang sebagai aplikasi `xmutil`** (image Ubuntu Kria) [Kemungkinan Besar]:
   ```sh
   sudo mkdir -p /lib/firmware/xilinx/padan
   sudo cp padan_bd_wrapper.bin /lib/firmware/xilinx/padan/padan_kv260.bit.bin   # = firmware-name
   sudo cp padan.dtbo /lib/firmware/xilinx/padan/padan.dtbo
   echo '{ "shell_type" : "XRT_FLAT", "num_slots": "1" }' | sudo tee /lib/firmware/xilinx/padan/shell.json
   sudo xmutil unloadapp
   sudo xmutil loadapp padan
   ```
3. **Cek tanpa menulis:** `sudo devmem2 0xA0000C0C w` (GUARD_STATUS) harus
   memberi `[3:0] = 0x3` (OPEN), `[11:8] = 5` setelah zeroize boot.

**Jangan membaca `0xA000_0000` sebelum bitstream PADAN dimuat.** Akses ke PL
tanpa slave yang menjawab bisa membuat bus AXI menggantung dan Linux hang
[Kemungkinan Besar].

## 7. Uji di board

```sh
scp $REPO/sw/kv260/padan_test.py $REPO/sw/kv260/padan_vectors.json ubuntu@kria:
sudo python3 padan_test.py            # --base 0x... bila alamat diubah
```

- **Identifikasi baca-saja.** Skrip membaca STATUS, GUARD_STATUS, dan word
  `0x000`, `0x200`, `0x306`, `0x3FF` (harus 0). Bila tidak tampak seperti PADAN,
  skrip berhenti dengan kode 3 **tanpa satu tulis pun**.
- **Guard harus OPEN.** Jalankan setelah memuat bitstream, tanpa LOCK, dan
  jangan sentuh pin tamper. Skrip menunggu zeroize boot, lalu berhenti dengan
  FAIL yang menyebut state dan alasan guard bila bukan OPEN. Urutan vektor
  dijamin tidak lebih dari 2 NO_MATCH berturut-turut (batas lockout K = 5).
- **Per galeri** (3 galeri, 46 kasus; 26 MATCH dan 20 NO_MATCH dari model):
  ENROLL_CLR, tulis 512 word template, baca **seluruh 1.024 word** (semua 0
  kecuali STATUS dan GUARD_STATUS), lalu per kasus: tulis probe, MATCH(τ),
  tunggu `busy` = 0, bandingkan `STATUS[11:0]` dengan model.
- **Hasil** satu baris `PADAN KV260: PASS ...` atau `PADAN KV260: FAIL ...`.
  Kode keluar 0 PASS, 1 FAIL, 2 argumen/akses, 3 bukan PADAN.

**Yang sudah diuji di repo ini** (`make test-kv260-scripts`, `tb/kv260`):
- `padan_test.py` **tanpa diubah** dijalankan dengan `--backend pipe` melawan RTL
  `padan_axil`; setiap akses menjadi transaksi AXI4-Lite. PASS 46/46, tanpa
  pelanggaran protokol AXI. [Pasti, simulasi]
- Satu bit memori template dibalik: FAIL (FAULT `0xF0F`), lalu FAULT ke-3 memicu
  zeroize dan HALT, dan skrip berhenti dengan pesan guard. [Pasti, simulasi]
- Base salah: kode 3, nol tulis. Guard LOCKD: FAIL tanpa tulis. [Pasti, simulasi]
- Backend `/dev/mem` diuji pada berkas biasa: word i di offset 4i,
  little-endian, akses lewat `memoryview` 32 bit. [Pasti]
- **Tidak tercakup:** `/dev/mem` sungguhan, PS, SmartConnect, overlay, timing.
  Bahwa `memoryview` CPython menghasilkan satu load/store 32 bit di aarch64
  adalah [Kemungkinan Besar], belum dicek di board.

### Uji tamper manual (setelah `padan_test.py` PASS)

Uji ini **merusak** isi template.

```sh
sudo devmem2 0xA0000C0C w     # GUARD_STATUS [3:0] = 0x3 (OPEN)
# sambungkan PMOD J2 pin 1 ke GND sebentar, lalu lepas
sudo devmem2 0xA0000C0C w     # harus [3:0] = 0xA (HALT), [17:16] = 1 (TAMPER)
sudo devmem2 0xA0000C08 w     # STATUS[11:0] = 0xF00 (NONE)
```

Muat ulang bitstream (`xmutil unloadapp; xmutil loadapp padan`) untuk reset PL.
Guard melakukan zeroize boot, lalu kembali ke OPEN dengan memori kosong.

**Batas uji ini.** Ia hanya membuktikan jalur pin → guard → HALT. Bahwa memori
benar-benar nol hanya terbukti di simulasi (`tb/guard`), karena tidak ada jalur
baca template dari bus.

## 8. Catat hasil (diisi oleh yang menjalankan)

| Butir | Nilai | Lulus? |
|---|---|---|
| Commit repo | | |
| Versi Vivado, versi board file, image Linux | | |
| `check_reports.py` (RAMB18, DSP, FF, timing, clock, CDC, FSM) | | PASS |
| GUARD_STATUS setelah `loadapp` | | `0x00000503` |
| `padan_test.py` | | `PADAN KV260: PASS (46 kasus ...)` |
| Uji tamper manual: GUARD_STATUS sebelum / sesudah | | `0x00000503` → `[3:0]=0xA`, alasan 1 |

Hasil board hanya berlaku untuk commit, bitstream, dan board tempat ia dijalankan.

## 9. Yang dicek di CI dan yang tidak

| Dicek di CI | Tidak dicek |
|---|---|
| `padan_axil`: protokol AXI4-Lite (urutan AW/W, backpressure B/R, SLVERR, AR bersamaan), 6 test + 8 mutan (`make test-rtl-axil`, `test-rtl-mutation`) | Interface AXI dikenali Vivado dari nama port |
| `create_project.tcl`/`build.tcl` di tclsh dengan stub: part, board part, file RTL lengkap, alamat = host, clock, port tamper, 4 kondisi error (`tb/kv260/check_tcl.py`) | Vivado menerima setiap perintah, properti, dan VLNV; hasil otomasi block design |
| XDC: `tamper_n` H12/LVCMOS33/PULLUP + false path; port ada di RTL | Pin H12 = J2 pin 1 di carrier (skematik) |
| `padan_test.py` + vektor model melawan RTL lewat AXI (`tb/kv260`) | `/dev/mem`, PS, SmartConnect, overlay, board |
| Parser `check_reports.py` terhadap laporan asli Vivado 2026.1 (`testdata`) dan kasus negatif | Format laporan versi Vivado lain |
| Inferensi Yosys UltraScale+: 16 RAMB18E2, 16+3 DSP48E2, FF `decision` 151, `guard` 103 (`make check-rtl-infer`) | Angka Vivado, timing |
| `padan_vectors.json` sinkron dengan model; maksimal 2 NO_MATCH berturut-turut | Perilaku guard di board, termasuk tamper sungguhan |
