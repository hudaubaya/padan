# Gaya penulisan RTL PADAN

Berlaku untuk `rtl/*.v` dan `rtl/*.vh`. Tidak berlaku untuk `rtl/baseline/`, yang
disalin apa adanya. Targetnya AMD Zynq UltraScale+ K26 di Kria KV260 (block RAM
RAMB18E2, DSP48E2) dengan Vivado. Simulasi memakai Icarus Verilog 12.

Label keyakinan:
- **[Pasti]** dibuktikan oleh simulasi atau alat di repo ini.
- **[Kemungkinan Besar]** inferensi kuat yang belum dibuktikan di sini.

> **Batas bukti.** Vivado tidak tersedia di lingkungan ini maupun di CI. Pola
> di bawah adalah template inferensi yang lazim untuk Vivado. Yosys
> `synth_xilinx -family xcup` memetakannya ke 16 RAMB18E2 dan 16 DSP48E2 untuk
> lane (`make check-rtl-infer`). [Pasti] Bahwa Vivado akan memetakan hal yang
> sama adalah [Kemungkinan Besar]. Pastikan di laporan utilisasi Vivado
> (`docs/fpga_howto.md` 5a).
>
> Sebelumnya targetnya Intel Cyclone V (DE10-Nano). Yang berubah saat pindah ke
> KV260 hanya atribut alat (`ramstyle` → `ram_style`, `multstyle` → `use_dsp`,
> `preserve` → `dont_touch`) dan penyimpanan `code` di `decision.v` (bagian 8).

## 1. Bahasa dan file

- **Hanya Verilog-2001/2005** (`$clog2`), tanpa SystemVerilog. File yang sama
  dibaca Icarus, Yosys, dan Vivado tanpa flag khusus.
- `` `default_nettype none `` di awal setiap modul dan `` `default_nettype wire ``
  di akhir. Net yang salah ketik menjadi error, bukan wire 1 bit implisit.
- Satu modul utama per file, nama file = nama modul. Modul pembantu kecil boleh
  satu file dengan pemakainya, misalnya `padan_sdp_ram` di `template_mem.v`.
- Definisi bersama ada di `padan_defs.vh`, di-include di dalam badan modul,
  **tanpa include guard** (setiap modul butuh salinannya sendiri).
- **Bobot w(j) = j + 1 hanya didefinisikan di satu tempat** (`padan_weight`).
  Generator checksum dan pemeriksa tidak bisa memakai bobot berbeda.
- **Parameter default = parameter rilis:** N = 16, D = 128, L = 16. Adder tree
  ditulis untuk L = 16, dan D/L harus pangkat dua.

## 2. Clock dan reset

- **Satu clock, sisi naik.** Tidak ada latch, gated clock, atau sisi turun.
- **Reset asinkron aktif-rendah `rst_n` hanya untuk register kendali:** state
  FSM, bit valid pipeline, `busy`, `issue`.
- **Datapath tidak di-reset:** register produk, adder tree, akumulator, data
  memori, dan probe. Alasannya:
  - Register DSP48E2 hanya punya reset sinkron. Register dengan reset asinkron
    tidak bisa dipak ke DSP dan keluar ke fabric. [Kemungkinan Besar]
  - Isi block RAM memang tidak bisa di-reset. Kebenaran datapath dijaga oleh bit
    valid. `template_mem` punya perintah `clr` untuk mengenolkan isi secara
    eksplisit.
- Dalam blok sekuensial hanya ada assignment nonblocking (`<=`).

## 3. Memori → block RAM

Pola "Simple Dual-Port RAM (single clock)" dari template HDL Vivado, dalam modul
`padan_sdp_ram`:

```verilog
(* ram_style = "block", no_rw_check *) reg [DW-1:0] mem [0:DEPTH-1];
always @(posedge clk) begin
    if (we)
        mem[wa] <= wd;
    q <= mem[ra];          // baca terdaftar: data valid 1 siklus setelah alamat
end
```

- **Bentuk tetap:** satu port tulis, satu port baca, satu blok `always`, tanpa
  reset, tanpa inisialisasi, tanpa byte enable.
- **`no_rw_check` aman:**
  - Generator `template_mem` tidak pernah membaca dan menulis alamat yang sama
    pada siklus yang sama.
  - `mac_array` hanya membaca saat `template_mem` tidak `busy`, dan `busy`
    mencakup tulis terakhir yang masih tertunda.
- **Satu bank per lane** (16 bank × 144 word × 16 bit):
  - Setiap siklus 16 lane membaca 16 elemen sekaligus, tanpa byte enable atau
    port lebar.
  - Satu bank = satu RAMB18E2 (lebar 18). [Pasti, Yosys]
- **Word 16 bit** karena baris checksum Cw butuh 16 bit dan C butuh 12 bit
  (`docs/padan_model.md` bagian 2). T disimpan diperluas tanda. Kapasitas
  terpakai ±12,5% per RAMB18E2 (144 × 16 dari 18 Kb); ini dipilih demi
  kesederhanaan port.
- **`no_rw_check`** adalah atribut Yosys; Vivado mengabaikan atribut yang tidak
  dikenalnya (dengan peringatan) [Kemungkinan Besar]. Tanpa `no_rw_check`,
  Yosys menolak memetakan memori ke block RAM.
- **Bus hanya bisa menulis.** Tidak ada mux baca dari bus, jadi isi template
  secara struktural tidak bisa dibaca balik oleh host.

## 4. Pengali → DSP

```verilog
(* use_dsp = "yes" *) reg signed [23:0] prod;
always @(posedge clk)
    prod <= $signed(rd_data[l*16 +: 16]) * p_m;   // 16 x 8 bertanda
```

- **Operand bertanda eksplisit** (`signed` atau `$signed`). Lebar hasil ditulis
  eksplisit: 16 + 8 = 24 bit.
- **Kedua operand berasal dari register:** keluaran block RAM (baca terdaftar)
  dan `p_m`.
- **Hasil langsung disimpan ke register tanpa reset dan tanpa enable,** pola
  yang dipak Vivado ke register PREG/MREG DSP48E2. [Kemungkinan Besar]
- **Satu DSP48E2 per lane:** 16×8 bertanda muat di pengali 27×18. [Pasti,
  Yosys: 16 `DSP48E2` di `mac_array`]

## 5. Register yang tidak boleh menjadi memori

**Probe p** (128 byte, 16 dibaca paralel per siklus) ditulis sebagai **vektor
datar** `reg [D*8-1:0] probe`, bukan array. Versi array dengan atribut
"logic" dipetakan Yosys ke LUTRAM (MLAB di Cyclone V: 512 sel) [Pasti], karena
atribut itu hanya dikenali satu vendor. Vektor datar tidak bergantung pada
atribut alat; `make check-rtl-infer` mengunci LUTRAM = 0 di `mac_array`.
Yosys memetakan 11 bit tag pipeline (`o_row`, `t2_ch`) ke SRL16E; itu bukan
data probe. [Pasti, Yosys]

## 6. Datapath dan pipeline

- **Adder tree dua tingkat terdaftar:** 16 → 4 → 1, lebar 24 → 28 bit, lalu
  akumulator 32 bit. Semua lebar mengikuti `model/padan_bounds.py`.
- **Ekstensi tanda ditulis eksplisit** dengan replikasi, misalnya
  `{{(CW-32){x[31]}}, x}`.
- **Pemotongan hanya terjadi di satu tempat yang didokumentasikan:** pembaruan
  C/Cw di generator, mod 2¹⁶, sama dengan lebar penyimpanan.
- **Tag pipeline `*_vld`, `*_row`, `*_ch` berjalan sejajar data.** Biayanya
  beberapa flip-flop, sebagai gantinya:
  - setiap stage bisa diamati;
  - testbench bisa menyuntik fault tepat di baris dan chunk tertentu tanpa
    mengodekan latensi.
- **Nama blok `generate` stabil** (`g_lane`, `g_bank`, `g_sum4`). Testbench
  mengaksesnya sebagai `u_mac.g_lane[l].prod` dan
  `u_mem.g_bank[l].u_ram.mem[a]`.

## 7. Kendali

- **FSM:** state berupa `localparam`, satu blok `case` dengan `default`, keluaran
  kendali terdaftar.
- **Handshake level:**
  - `bus_wr`/`clr` diterima saat `bus_ready`.
  - `start` diterima saat `!busy && !hold`.
  - `mem_lock = busy || start` mencegah tulis bus diterima pada siklus yang sama
    dengan `start`.
  - `hold` menahan `start` baru sampai `template_mem` dan `abft_check` selesai,
    sehingga pemeriksaan yang berjalan tidak terpotong.

## 8. Redundansi dan register yang tidak boleh digabung

Berlaku untuk `decision.v`.

- **Register redundan diberi `(* keep, dont_touch = "true" *)`.** `dont_touch`
  dikenali Vivado, `keep` dikenali Yosys. Keduanya diperlukan karena sintesis
  menggabungkan register ekuivalen (D dan enable sama) menjadi satu, dan dua
  komparator lalu berbagi satu titik gagal.
- **Atribut saja tidak cukup untuk register yang isinya identik.** Yosys
  `opt_merge` tetap menggabungkan `tau_a` dan `tau_b` walau keduanya diberi
  `keep`. [Pasti] Solusinya, salinan kedua disimpan dalam **representasi lain**
  (`tau_bn = ~tau`). Isinya tidak pernah sama, dan fault stuck-at yang sama pada
  kedua salinan muncul sebagai ketidaksepakatan.
  - `make check-rtl-infer` mengunci jumlah FF `decision` (151), sehingga
    penggabungan di masa depan langsung terlihat.
  - Untuk Vivado: `check_reports.py` memeriksa FF `decision` = 151 di laporan
    utilisasi hierarkis. [Kemungkinan Besar] Vivado menghormati `dont_touch`.
- **Register keluaran `code` juga.** Kode legal (`0000`, `0101`, `1010`,
  `1111`) punya dua setengah yang sama, sehingga FF `code[1:0]` dan `code[3:2]`
  punya input identik. Yosys `synth_xilinx` terbukti menggabungkannya
  (`assign code[1:0] = code[3:2]`), dan `keep` pada port tidak mencegahnya
  [Pasti]. Akibatnya NO_MATCH → MATCH hanya butuh 2 flip FF, bukan 4.
  Perbaikannya sama: setengah bawah disimpan terbalik (`code_lo_n`), nilai di
  port tidak berubah. `synth_intel_alm` tidak menggabungkannya, sehingga
  masalah ini baru terlihat saat pindah ke alur Xilinx.
- **Diversitas implementasi:** komparator A memakai perbandingan bertanda,
  komparator B memakai bit tanda selisih 33 bit. Bug sistematis di satu bentuk
  tidak otomatis ada di bentuk lain.

Berlaku juga untuk `guard.v` (`docs/rtl_guard.md`):

- **Penghitung dan τ terkunci disimpan sebagai nilai + komplemen**
  (`fail`/`fail_n`, `k`/`k_n`, `fault`/`fault_n`, `tau_lk`/`tau_lk_n`). Alasannya
  sama seperti `tau_bn`: salinan tidak pernah identik, jadi tidak bisa digabung.
  Ketidakcocokan dianggap state ilegal. `make check-rtl-infer` mengunci 103 FF.
- **State FSM dikode tangan dengan paritas genap**, dengan
  `(* fsm_encoding = "none" *)`. Tanpa atribut itu, pass `fsm` Yosys boleh
  mengode ulang state, dan kode ilegal yang dideteksi RTL tidak lagi bermakna.
  - Deteksi state ilegal ditulis sebagai logika eksplisit pada bit state
    (`^state`, dua kode tak terpakai), bukan hanya cabang `default`.
  - `make check-rtl-guard-safe` membuktikan dengan SAT bahwa logika itu bertahan
    setelah sintesis Yosys.
  - Untuk Vivado belum terbukti (`docs/fpga_howto.md` 5a).
- **Keluaran keamanan dikodekan dengan jarak Hamming ≥ 2.** Kode STATUS
  `0101`/`1010`/`1111`/`0000`, plus indeks ganda (`idx`, `~idx`). Satu flip bit
  tidak menghasilkan MATCH yang salah.
- **Register komparator tidak di-reset;** nilai awalnya diatur oleh `start`.
  Register keputusan (`busy`, `code_hi`, `code_lo_n`, `idx`, `idx_n`) di-reset
  ke NONE.
- **Tamper asinkron** masuk lewat 2-FF `t_sync` dengan `(* ASYNC_REG = "TRUE" *)`
  agar Vivado menempatkan keduanya berdekatan dan mengenalinya sebagai
  sinkronisasi di `report_cdc` [Kemungkinan Besar].

## 9. Catatan simulasi (Icarus)

**Part-select dari bus lebar dibaca di dalam blok `always @(posedge clk)`,
bukan lewat `wire`.** Contohnya `rd_data` 256 bit dengan 16 driver parsial.

- Di Icarus, `wire a = rd_data[l*16 +: 16]` dievaluasi ulang pada setiap update
  bank.
- Bersama bus produk 384 bit, pola itu membuat satu run 18 baris memakan 41 ms
  dengan data acak. Setelah diubah: 8 ms. [Pasti, diukur]
- Bagi sintesis kedua penulisan setara.

## 10. Pemeriksaan

| Target | Isi |
|---|---|
| `make test-rtl` | test cocotb dengan parameter rilis (`docs/rtl_padan.md`) |
| `make test-rtl-mutation` | 26 mutan RTL harus dibunuh oleh test (3 inti, 3 decision, 12 guard, 8 AXI) |
| `make test-rtl-axil` | test cocotb `padan_axil` (wrapper AXI4-Lite KV260, `docs/fpga_howto.md`) |
| `make test-rtl-avmm` | test cocotb `padan_avmm` + `decision` (`docs/rtl_decision.md`) |
| `make check-rtl-infer` | Yosys UltraScale+: 16 RAMB18E2, 16 DSP48E2 lane (19 total), tanpa LUTRAM; `decision` 151 FF; `guard` 103 FF |
| `make test-rtl-guard` | test cocotb `guard` dengan parameter rilis (`docs/rtl_guard.md`) |
| `make test-rtl-debug` | build debug `DEBUG_FAULT`: injeksi terdeteksi dan dilokalisasi (`docs/rtl_debug_fault.md`) |
| `make check-rtl-release` | build rilis tanpa port/logika `DEBUG_FAULT` (praproses + netlist Yosys, dengan kontrol positif) |
| `make check-rtl-guard-safe` | bukti SAT Yosys: setiap state ilegal → izin 0 dan zeroize, setelah sintesis |
