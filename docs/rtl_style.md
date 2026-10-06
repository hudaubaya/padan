# Gaya penulisan RTL PADAN

Berlaku untuk `rtl/*.v` dan `rtl/*.vh`. Tidak berlaku untuk `rtl/baseline/`, yang
disalin apa adanya. Targetnya Intel Cyclone V (blok memori M10K, blok DSP
variable-precision) dengan Quartus. Simulasi memakai Icarus Verilog 12.

Label keyakinan:
- **[Pasti]** dibuktikan oleh simulasi atau alat di repo ini.
- **[Kemungkinan Besar]** inferensi kuat yang belum dibuktikan di sini.

> **Batas bukti.** Quartus tidak tersedia di lingkungan ini maupun di CI. Pola
> di bawah adalah template inferensi yang didokumentasikan Intel. Yosys
> `synth_intel_alm -family cyclonev` memetakannya ke 16 M10K dan 16 DSP 18×18
> (`make check-rtl-infer`). [Pasti] Bahwa Quartus akan memetakan hal yang sama
> adalah [Kemungkinan Besar]. Pastikan di laporan fitter Quartus saat proyek
> FPGA dibuat.

## 1. Bahasa dan file

- **Hanya Verilog-2001/2005** (`$clog2`), tanpa SystemVerilog. File yang sama
  dibaca Icarus, Yosys, dan Quartus tanpa flag khusus.
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
  - Register keluaran DSP Cyclone V hanya bisa dipak bila tanpa reset sinkron.
    Reset tambahan memaksa register keluar ke ALM. [Kemungkinan Besar]
  - Isi M10K memang tidak bisa di-reset. Kebenaran datapath dijaga oleh bit
    valid. `template_mem` punya perintah `clr` untuk mengenolkan isi secara
    eksplisit.
- Dalam blok sekuensial hanya ada assignment nonblocking (`<=`).

## 3. Memori → M10K

Pola "Simple Dual-Port RAM (single clock)" dari template HDL Quartus, dalam modul
`padan_sdp_ram`:

```verilog
(* ramstyle = "M10K, no_rw_check" *) reg [DW-1:0] mem [0:DEPTH-1];
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
  - Satu bank = satu M10K (mode 512×20). [Pasti, Yosys]
- **Word 16 bit** karena baris checksum Cw butuh 16 bit dan C butuh 12 bit
  (`docs/padan_model.md` bagian 2). T disimpan diperluas tanda. Kapasitas
  terpakai ±23% per M10K; ini dipilih demi kesederhanaan port.
- **Bus hanya bisa menulis.** Tidak ada mux baca dari bus, jadi isi template
  secara struktural tidak bisa dibaca balik oleh host.

## 4. Pengali → DSP

```verilog
(* multstyle = "dsp" *) reg signed [23:0] prod;
always @(posedge clk)
    prod <= $signed(rd_data[l*16 +: 16]) * p_m;   // 16 x 8 bertanda
```

- **Operand bertanda eksplisit** (`signed` atau `$signed`). Lebar hasil ditulis
  eksplisit: 16 + 8 = 24 bit.
- **Kedua operand berasal dari register:** keluaran M10K (baca terdaftar) dan
  `p_m`.
- **Hasil langsung disimpan ke register tanpa reset dan tanpa enable,** pola
  yang dipak Quartus ke register keluaran DSP. [Kemungkinan Besar]
- **Mode DSP:** 16×8 bertanda memakai mode 18×18 Cyclone V (dua per blok DSP,
  jadi 8 blok untuk 16 lane). [Pasti, Yosys: 16 `MISTRAL_MUL18X18`]

## 5. Register yang tidak boleh menjadi memori

**Probe p** (128 byte, 16 dibaca paralel per siklus) ditulis sebagai **vektor
datar** `reg [D*8-1:0] probe`, bukan array. Versi array dengan
`ramstyle = "logic"` dipetakan Yosys ke 512 sel MLAB [Pasti], karena atribut itu
hanya dikenali Quartus. Vektor datar tidak bergantung pada atribut alat.

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

- **Register redundan diberi `(* preserve, keep *)`.** `preserve` dikenali
  Quartus, sedangkan `keep` dikenali Yosys. Keduanya diperlukan karena sintesis
  menggabungkan register identik (D dan enable sama) menjadi satu, dan dua
  komparator lalu berbagi satu titik gagal.
- **Atribut saja tidak cukup untuk register yang isinya identik.** Yosys
  `opt_merge` tetap menggabungkan `tau_a` dan `tau_b` walau keduanya diberi
  `keep`. [Pasti] Solusinya, salinan kedua disimpan dalam **representasi lain**
  (`tau_bn = ~tau`). Isinya tidak pernah sama, dan fault stuck-at yang sama pada
  kedua salinan muncul sebagai ketidaksepakatan.
  - `make check-rtl-infer` mengunci jumlah FF `decision` (151), sehingga
    penggabungan di masa depan langsung terlihat.
  - Untuk Quartus: periksa laporan "Removed Registers" di Analysis & Synthesis.
    [Kemungkinan Besar] Quartus menghormati `preserve`.
- **Diversitas implementasi:** komparator A memakai perbandingan bertanda,
  komparator B memakai bit tanda selisih 33 bit. Bug sistematis di satu bentuk
  tidak otomatis ada di bentuk lain.
- **Keluaran keamanan dikodekan dengan jarak Hamming ≥ 2.** Kode STATUS
  `0101`/`1010`/`1111`/`0000`, plus indeks ganda (`idx`, `~idx`). Satu flip bit
  tidak menghasilkan MATCH yang salah.
- **Register komparator tidak di-reset;** nilai awalnya diatur oleh `start`.
  Register keputusan (`busy`, `code`, `idx`, `idx_n`) di-reset ke NONE.

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
| `make test-rtl-mutation` | 6 mutan RTL harus dibunuh oleh test (3 inti, 3 decision) |
| `make test-rtl-avmm` | test cocotb `padan_avmm` + `decision` (`docs/rtl_decision.md`) |
| `make check-rtl-infer` | Yosys Cyclone V: 16 M10K, 16 DSP 18×18, tanpa MLAB; `decision` 151 FF |
