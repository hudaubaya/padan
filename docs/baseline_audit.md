# Audit baseline TT07

Ketiga baseline di `rtl/baseline/` diuji **apa adanya** dengan cocotb. Tidak ada
satu baris pun yang diubah: yang diuji adalah commit tapeout (lihat
[`docs/baselines.md`](baselines.md)) dan netlist tapeout dari repo shuttle.
Dokumen ini hanya mencatat temuan. Tidak ada yang diperbaiki di sini.

## Ringkasan

| Baseline | Benar | Salah | Layak dipakai ulang |
|---|---|---|---|
| **TinyTPU #0590** | Array sistolik 2×2 menghitung X·Y benar untuk 400 pasang matriks acak (bit 0 z00 dikecualikan, lihat T2) | `tx_ready` terlambat 1 siklus (T1); bit 0 z00 disampel sebelum akumulasi selesai (T2); akumulator 16 bit overflow untuk 2·255² (T3); operasi kedua tanpa reset salah (T4); register tanpa reset membuat netlist X (T5); 32 latch di jalur data (T6) | Konsep dan kode `mac.v` + `systolic.v` (dengan akumulator diperlebar). Kendali I/O ditulis ulang. |
| **Iterative MAC #0040** | Pengali 7×8 benar untuk 32.768/32.768 pasangan; mode 1 = ⌊a·B/2⁸⌋ + C (mod 2³²) untuk 1.600 operasi acak dan nilai ekstrem | Mode 0 selalu mengeluarkan 0 (I1); mode 0 memakai `uio` sebagai keluaran sekaligus masukan bias (I2); cabang `out_th` mati (I3); hasil >32 bit terpotong tanpa tanda (I4) | Hanya konsep: produk parsial byte-serial dengan pengali sempit. Kode tidak. |
| **Vector CiSRAM #0642** | Dot product 8 elemen eksak: 1.000 vektor acak, 65.536 produk, 122 kasus ekstrem termasuk maksimum 520.200. Adder tree **tidak bisa overflow**. CLA terbukti formal untuk semua input. | Tidak ada cacat fungsional. Aritmetika hanya tak bertanda, padahal test upstream melabeli vektor sebagai "negative" (V1). Tidak ada SRAM (V2). | Ya, kode: `MAC` dan `cla` dapat dipakai langsung. Struktur top-level dapat dipakai sebagai kerangka. |

Cara membaca label keyakinan:

- **[Pasti]** dibuktikan oleh simulasi, bukti formal, atau struktur netlist.
- **[Kemungkinan Besar]** inferensi kuat dari kode, belum disimulasikan khusus.
- **[Menebak]** tentang maksud penulis yang tidak bisa dibuktikan dari repo ini.

## Metode

- **Alat:** Icarus Verilog 12.0, cocotb 1.8.1, Yosys 0.33 (bukti SAT dan
  pemeriksaan sintesis).
- **RTL:** sumber baseline apa adanya, dengan toplevel baru
  [`tb/common/tb_tt.v`](../tb/common/tb_tt.v) (level pin). Ada dua test RTL
  yang juga membaca sinyal internal, ditandai "(RTL, sinyal internal)".
- **Netlist tapeout (GL):** `rtl/baseline/*/gl/*.v` disimulasikan dengan model
  sel sky130_fd_sc_hd (`UNIT_DELAY=#1`, tanpa SDF), dari
  [google/skywater-pdk-libs-sky130_fd_sc_hd](https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd)
  @ `28c101fc`. File test yang sama dijalankan pada RTL dan GL.
- **Model referensi** (`model/`, masing-masing dengan `--self-test`) adalah model
  *maksud* desain (matematika eksak), bukan salinan cacat RTL:
  - `tinytpu.py`: Z = X·Y.
  - `iterative_mac.py`: a×b dan R = ⌊a·B/2⁸⌋ + C.
  - `vector_cim.py`: Σ wᵢ·aᵢ.
- **Konvensi `expect_fail`:** setiap test memeriksa perilaku *yang benar*. Test
  untuk cacat yang sudah terkonfirmasi diberi `expect_fail=True` dan ID temuan.
  - Suite tetap hijau selama cacatnya masih ada. Suite menjadi merah kalau
    perilaku baseline berubah, tanda dokumen ini perlu diperbarui.
  - Semua 16 `expect_fail` (RTL + GL) gagal karena `AssertionError` dari
    assertion perilaku, bukan karena error testbench. Ini diperiksa di log.
- **Uji mutasi:** test diperiksa bisa gagal dengan merusak model sementara.
  Ketiga test utama menjadi FAIL:
  - Y tidak ditransposisi (TinyTPU);
  - urutan byte bias ditukar (Iterative MAC);
  - dot product dipotong 18 bit (#0642).
- **Bukti formal:** sanity check memakai ekspektasi yang sengaja dirusak, dan
  Yosys melaporkan "proof did fail".
- **Sumber angka:** semua angka di dokumen ini berasal dari
  `tb/audit/*/audit_<nama>_{rtl,gl}.json`, yang ditulis oleh test. Angka RTL
  dan GL identik, kecuali T5 dan dua test yang hanya berjalan di RTL.

Menjalankan semuanya: `make test-audit` (termasuk dalam `make test`; ±3 menit).

| Target | Isi |
|---|---|
| `make test-audit-tinytpu[-gl]` | 8 test TinyTPU (1 khusus RTL) |
| `make test-audit-iterative_mac[-gl]` | 7 test Iterative MAC (1 khusus RTL) |
| `make test-audit-vector_cim[-gl]` | 8 test Vector CiSRAM |
| `make test-audit-vector_cim-formal` | Bukti SAT `cla` 16/17/18 bit (Yosys) |

---

## TinyTPU #0590 (`tt_um_revenantx86_tinytpu`)

**Protokol (dibaca dari RTL, sama dengan test upstream):**

1. `ui_in[2]` (load_en) naik.
2. Satu clock kemudian 32 bit dikirim satu per clock:
   - X di `ui_in[0]`, baris demi baris: x00, x01, x10, x11;
   - Y di `ui_in[1]`, **kolom demi kolom**: y00, y10, y01, y11 (`mem_y[j]` adalah kolom j);
   - tiap byte LSB dulu.
3. load_en turun.
4. Pulsa `ui_in[3]` (init) satu clock.
5. Keluaran di `uo_out[0]`: z00, z01, z10, z11, masing-masing 16 bit LSB dulu.
   `uo_out[1]` = `tx_ready`.

Komentar test upstream menyebut Y juga "x11x12x21x22". Dengan urutan baris itu,
hasilnya adalah X·Yᵀ, bukan X·Y. [Pasti]

### Yang benar

- **Array sistolik output-stationary benar.** Untuk 400 pasang matriks acak
  (elemen ≤ 180, jadi 2·180² < 2¹⁶), termasuk vektor test upstream, 63 dari 64
  bit keluaran sama dengan X·Y. Kalau keluaran diambil mulai bit data pertama,
  hanya bit 0 z00 yang bisa salah (T2). [Pasti] (`test_systolic_core`, RTL dan GL)
- Feeding miring lewat pipeline alamat (`addr_x_ram[x] <= addr_x_ram[x-1]`) dan
  propagasi `init` antar-MAC sejajar: setiap MAC(i,j) mulai tepat di elemen
  pertamanya. [Pasti] (implisit dari test di atas)
- Untuk nilai ekstrem, hasilnya tepat (X·Y) mod 2¹⁶ di 48/48 kasus. Elemen yang
  muat 16 bit benar, termasuk 255·255 = 65.025 dan 2·181² = 65.522. [Pasti]
  (`test_extreme_wraps_mod_2_16`)
- Netlist tapeout berperilaku sama dengan RTL di semua test, setelah reset ganda (T5). [Pasti]

### Yang salah

- **T1 — `tx_ready` terlambat satu siklus dari data.** [Pasti]
  - Mekanisme: `tinytpu_top.v` meregister ulang `tx_ready` (`tx_ready <= tx_ready_reg`),
    sedangkan `data_out_z` keluar langsung.
  - Akibatnya penerima yang mengambil bit selama `tx_ready=1` kehilangan bit 0
    z00 dan mendapat satu bit 0 ekstra di akhir. Setiap kata tergeser:
    kata_k = (z_k >> 1) | (bit0 z_{k+1}) << 15.
  - Hasil: 40/40 operasi salah.
  - Contoh vektor upstream:
    - model: [[12176, 30245], [14834, 44668]];
    - terbaca: [[38856, 15122], [7417, 22334]].
  - Test: `test_T1_tx_ready_framing`.
- **T2 — bit 0 z00 disampel sebelum akumulasi selesai.** [Pasti]
  - `output_control` mulai TX dari pin `init` yang ditunda 2 register.
    Array sistolik mulai dari `out_init` yang sudah diregister, ditambah
    pipeline memori.
  - Akibatnya bit 0 z00 diambil saat MAC(0,0) baru berisi x00·y00, sebelum
    x01·y10 ditambahkan. Di semua 400 kasus, bit 0 yang keluar = bit 0
    x00·y00.
  - Salah bila x01·y10 ganjil, yaitu x01 dan y10 sama-sama ganjil (peluang
    teoretis 1/4). Teramati: 110/400 operasi salah.
  - Test: `test_T2_result_exact`; mekanisme di `test_systolic_core`.
- **T3 — akumulator 16 bit terlalu sempit.** [Pasti]
  - `out_z` lebarnya 2·D_W = 16 bit, padahal 2·255² = 130.050 butuh 17 bit
    (umumnya 2·D_W + ⌈log₂N⌉).
  - Overflow terpotong diam-diam: 12/48 kasus ekstrem salah. Contoh semua 255:
    130.050 keluar sebagai 64.514.
  - Test: `test_T3_extreme_exact`.
- **T4 — operasi kedua tanpa reset salah.** [Pasti]
  - `bit_counter` dan `ram_counter` di `input_control.v` hanya di-reset oleh `rst`.
    Ada dua cara mengakhiri load, dan keduanya gagal:
    - *Protokol upstream* (load_en turun satu clock setelah bit terakhir): ada
      satu geseran ekstra, sehingga `bit_counter` bertambah 1 per operasi
      (1, 2, 3). Byte operasi berikutnya tergeser, dan operasi ke-2 sampai
      ke-4 salah semua.
    - *load_en turun bersama bit terakhir:* byte terakhir ditulis di IDLE,
      sehingga `ram_counter` tertinggal di 1. Operasi berikutnya menukar baris
      X dan kolom Y; hasilnya Z diputar 180°. Bergantian salah dan benar.
  - Test: `test_T4_back_to_back`, `test_T4_counters_return_to_zero` (RTL,
    sinyal internal).
  - Konsekuensi: setiap operasi butuh reset. [Pasti]
- **T5 — `init_delay` di `output_control.v` tidak di-reset.** [Pasti]
  - Di netlist tapeout, reset tunggal saat start membuat STATE = X, dan semua
    keluaran X selamanya (`test_T5_single_reset`, gagal hanya di GL). Di RTL
    tidak terlihat, karena `if (X)` di Verilog dianggap salah.
  - Semua test lain memakai reset ganda: reset, 3 clock dengan init=0, lalu
    reset lagi.
  - Di silikon, nilai power-up acak bisa memicu satu burst TX palsu setelah
    reset pertama. [Kemungkinan Besar]
- **T6 — 32 latch di jalur data.** [Pasti]
  - `dff_mem.v` memakai `always @(*)` dengan rantai `if / else if / else if`
    yang tidak lengkap. Yosys menyimpulkan latch untuk `data_out`, dan netlist
    tapeout memuat 32 sel `sky130_fd_sc_hd__dlxtn` (4 memori × 8 bit).
  - Simulasi unit-delay tidak memperlihatkan masalah. Latch di jalur data
    menyulitkan STA dan rawan glitch. [Kemungkinan Besar]
- Catatan kecil:
  - `info.yaml` menulis `clock_hz: 50000` (50 kHz), test memakai 25 MHz, dan
    OpenLane memakai `CLOCK_PERIOD = 20` ns. [Pasti]
  - Test upstream tidak punya assertion sama sekali (lihat `docs/baselines.md`).

### Layak dipakai ulang

- **Konsep:** ya. Array sistolik output-stationary dengan feeding miring
  lewat pipeline alamat, dan `init` yang merambat bersama data, terbukti benar.
- **Kode `mac.v` dan `systolic.v`:** layak, dengan dua perubahan:
  - lebarkan `out_z` ke 2·D_W + ⌈log₂N⌉;
  - ganti `k++` (sintaks SystemVerilog di `systolic.v`) bila targetnya Verilog-2005.
- **`input_control.v`, `output_control.v`, `dff_mem.v`:** tulis ulang. Temuan
  T1, T2, T4, T5, dan T6 semuanya ada di ketiga file ini.

---

## Iterative MAC #0040 (`tt_um_rajum_iterativeMAC`)

**Protokol (dibaca dari `temp_b` per state, dipastikan dengan simulasi):**

- Saat reset (sinkron), `ui_in[7]` menjadi mode dan `ui_in[6:0]` menjadi bobot a.
- Sisi naik pertama setelah reset (state 0) tidak termasuk operasi apa pun.
- Mode 1: satu operasi = 4 clock (state 1–4, atau 1, 5, 6, 7):
  - `ui_in` = b1, b2, b3, b4, sehingga B = b1·2²⁴ + b2·2¹⁶ + b3·2⁸ + b4;
  - `uio_in` = c1, c2, c3, c4, sehingga C = c3·2²⁴ + c4·2¹⁶ + c1·2⁸ + c2;
  - hasil R = ⌊a·B/2⁸⌋ + C, mod 2³²;
  - R keluar di `uo_out` MSB dulu selama 4 clock, mulai sisi state 4.
- Operasi berikutnya langsung menyusul tanpa jeda.

Urutan byte bias (c3, c4, c1, c2) dan skala 2⁻⁸ tidak tertulis di
`docs/info.md`; dokumen itu hanya menyebut bias "supplied in different
sequences". Apakah ini disengaja tidak bisa dipastikan. [Menebak]

Test HEAD upstream (`assert uo_out == 6`) memang cocok dengan model ini: byte
MSB hasil pertama untuk input test itu adalah 0x06. [Pasti, dihitung dengan model]

### Yang benar

- **Pengali 7×8 benar untuk semua 128 × 256 = 32.768 pasangan,** dibaca lewat
  pin. Sisi pertama setelah reset menyimpan a·b ke `result[30:16]`. Mode
  dibuat bergantian. [Pasti] (`test_multiplier_7x8_exhaustive`, RTL dan GL)
- **Mode 1: penjumlahan produk parsial dan bias benar.** [Pasti]
  (`test_mode1_mac_random`, `test_mode1_extremes_mod_2_32`)
  - Diuji 1.600 operasi acak (200 nilai a × 8 operasi) dan 75 operasi ekstrem.
    Semuanya tepat ⌊a·B/2⁸⌋ + C mod 2³².
  - Pemotongan `out[14:8]` di state 4 setara dengan floor dari keseluruhan,
    karena suku lain bilangan bulat. Hal ini juga diperiksa model untuk
    20.000 kasus.
  - Di RTL semua state 0–7 dilalui. 1.415 operasi memiliki a·bᵢ ≥ 2048 untuk
    b1–b3, sehingga memakai cabang `out_th`.
- **Mode 0: akumulasi internal berjalan.** Setiap clock
  `sum += a·b·2¹⁶ + c·2⁸` (mod 2³²), diperiksa 200 clock. [Pasti]
  (`test_mode0_internal_sum_accumulates`, RTL, sinyal internal)

### Yang salah

- **I1 — mode 0 ("inference") tidak pernah mengeluarkan hasil.** [Pasti]
  - FSM tetap di state 1, dan `result` hanya digeser (`result << 8`) tanpa
    pernah menerima `sum`. Hanya state 4 dan 7 yang menulis `result <= temp_c`.
  - Dua clock setelah reset, `uo_out` dan `uio_out` selalu 0. Selama 61
    clock dengan input acak, tidak ada satu pun keluaran yang bukan 0.
  - Test: `test_I1_mode0_output_follows_inputs`.
- **I2 — konflik arah `uio` di mode 0.** [Pasti dari kode dan pin]
  - Di mode 0 `uio_oe = 0xFF`, sehingga `uio` menjadi keluaran (`result[23:16]`).
    Padahal state 1 tetap menjumlahkan `uio_in` sebagai bias.
  - Di chip, `uio_in` membaca balik keluarannya sendiri. [Kemungkinan Besar]
  - Test: `test_I2_uio_direction`.
- **I3 — cabang `out_th` tidak berpengaruh.** [Pasti]
  - State 5, 6, dan 7 menghasilkan `temp_b` yang sama dengan state 2, 3, dan 4,
    dan semua jalur tetap melewati empat suku yang sama.
  - `out_th = |out[14:11]` (a·b ≥ 2048) jadi logika mati. Maksudnya mungkin
    deteksi overflow atau saturasi. [Menebak]
- **I4 — overflow 32 bit terpotong tanpa tanda.** [Pasti]
  - ⌊127·(2³²−1)/2⁸⌋ + (2³²−1) melampaui 2³², dan tidak ada flag carry atau saturasi.
  - 201/1.600 operasi acak melampaui 32 bit.
  - Contoh a=127, semua byte 255: hasil eksak 0x17EFFFFFE, keluar 0x7EFFFFFE.
  - Test: `test_I4_mode1_no_silent_overflow`.
- **Tidak ada akumulasi antar-operasi.** `sum <= 0` di setiap state 4, jadi yang
  diakumulasi hanya produk parsial dan bias dalam satu operasi. Untuk
  Σ a·bᵢ, hasil harus diumpankan balik sebagai bias dari luar, dengan latensi
  satu operasi. Ini keterbatasan desain, bukan kesalahan hitung. [Pasti]
- Catatan kecil:
  - Di mode 1, `uio_out = 8'bxx`, jadi nilainya X di RTL. Tidak berbahaya
    karena `uio_oe = 0`. [Pasti]
  - Bobot a hanya bisa diganti lewat reset. [Pasti]
  - Test upstream hanya memeriksa `uo_out == 0`.

### Layak dipakai ulang

- **Konsep:** sebagian. Operand lebar diproses byte demi byte dengan pengali
  7×8 dan adder 32 bit; produk parsial disusun dengan geseran tetap. Ini cara
  menghemat area yang sah, dan aritmetikanya terbukti benar.
- **Kode:** tidak. `multi.v` dan `adder.v` hanya satu baris `assign`. FSM-nya
  punya mode yang rusak (I1, I2), cabang mati (I3), tanpa overflow (I4), dan
  urutan byte bias yang tidak terdokumentasi. Lebih murah menulis ulang dari
  spesifikasi yang jelas.

---

## 8-bit Vector Compute-in-SRAM #0642 (`tt_um_8bit_vector_compute_in_SRAM`)

**Protokol:**

- `ui_in = {op[1:0], address[5:0]}`, `uio_in` = data.
- Opcode: `LOAD_W` = 00, `LOAD_A` = 01, `READ_S` = 10, `NOP` = 11.
- Satu clock `READ_S` menyalin S ke cache. Tiga sisi naik berikutnya
  mengeluarkan S[18:16], S[15:8], dan S[7:0] di `uo_out`.
- Reset asinkron.

### Yang benar

- **Dot product 8 elemen eksak** untuk 1.000 pasang vektor acak penuh 0..255.
  [Pasti] (`test_dot_random`, RTL dan GL)
- **Semua 65.536 produk w·a benar.** Setiap MAC diuji untuk pasangan (w, a)
  dengan w mod 8 = indeks MAC; MAC lain bernilai 0. [Pasti] (`test_products_exhaustive`)
- **Adder tree tidak bisa overflow.**
  - Nilai maksimum 8·255² = 520.200 < 2¹⁹ = 524.288, dan lebar `s_adder_tree`
    adalah 19 bit. Lebarnya tumbuh per level: 16+1, 17+1, 18+1 bit.
  - Maksimum itu memang butuh bit ke-19 (≥ 2¹⁸). Hasilnya keluar sebagai
    0x07, 0xF0, 0x08 (0x7F008).
  - 122 kasus ekstrem eksak:
    - semua 255;
    - satu elemen 255 di tiap posisi;
    - k elemen 255 untuk k = 1..8, yang memicu carry di setiap level;
    - 100 kombinasi acak dari {0, 1, 127, 128, 129, 254, 255}.
  - Lima bit atas byte pertama selalu 0.
  - [Pasti] (`test_adder_tree_extremes_no_overflow`)
- **Adder `cla` terbukti benar untuk semua input** pada ketiga lebar yang
  dipakai. Dengan SAT Yosys, {c_out, s_out} = a + b + c_in untuk 16 bit
  (2³³ input), 17 bit (2³⁵), dan 18 bit (2³⁷). [Pasti] (`make test-audit-vector_cim-formal`)
- Perilaku lain yang terbukti benar (`test_address_out_of_range_ignored`,
  `test_weights_stationary`, `test_read_overlaps_next_load`, `test_reset_clears`):
  - alamat 8–63 diabaikan;
  - bobot tetap tersimpan saat aktivasi diganti 50 kali;
  - vektor berikutnya bisa dimuat selagi 3 byte hasil sebelumnya keluar;
  - reset mengosongkan W, A, dan keluaran.
  - [Pasti]

### Yang salah atau menyesatkan

- **V1 — hanya tak bertanda.** [Pasti] (`test_V1_signed_vectors`)
  - Test upstream melabeli empat vektor sebagai "Negative values (two's
    complement)". Desain maupun nilai harapannya menghitung tanpa tanda,
    jadi test lulus tanpa pernah menguji bilangan negatif.
  - Contoh semua 255: keluar 520.200, padahal tafsiran bertanda (−1·−1·8) = 8.
  - Untuk ML int8 yang umumnya bertanda, perlu mode bertanda.
- **V2 — tidak ada SRAM.** [Pasti, dari netlist]
  - Penyimpanan berupa 158 flip-flop `dfrtp`: 128 bit W/A, 19 bit cache, 8 bit
    keluaran, dan 3 bit kendali. Pengalinya sel logika standar.
  - Jadi ini array MAC digital berbasis register; "compute-in-SRAM" hanya nama.
  - Konsekuensi area: core 72.565 µm², 2×2 tile, 3.859 sel hasil sintesis
    (`stats/metrics.csv` di repo shuttle).
- Catatan kecil:
  - Parameter `MAC_SIZE` ada, tetapi adder tree ditulis manual untuk 8 elemen;
    mengganti parameter akan merusak desain. [Pasti dari kode]
  - Menahan `READ_S` lebih dari satu clock menulis ulang cache dan menahan
    keluaran. [Kemungkinan Besar, dari kode]
  - Alamat 6 bit, tetapi hanya 3 bit yang dipakai.
  - `info.yaml` menulis `clock_hz: 0`.
  - `src/project.v` sisa template.
  - Tidak ada akumulator antar-vektor: setiap `READ_S` hanya memberi Σ untuk
    isi register saat itu.

### Layak dipakai ulang

- **Kode, langsung:**
  - `MAC` (register W/A + pengali, reset asinkron);
  - `cla` (terbukti formal; asal: [Hammersamatom/cla](https://github.com/Hammersamatom/cla),
    tercantum di sumber).
- **Struktur top-level:** decoder opcode, adder tree tiga level dengan lebar
  yang tumbuh, dan readout 3 byte dengan cache. Ini kerangka yang benar.
- **Yang perlu ditambah untuk dipakai sebagai inti ML:**
  - mode bertanda (V1);
  - akumulator antar-vektor;
  - adder tree yang di-generate dari `MAC_SIZE`.
- Ini satu-satunya baseline yang fungsinya benar tanpa syarat.

---

## Ringkasan ID temuan

| ID | Baseline | Temuan | Keyakinan | Test |
|---|---|---|---|---|
| T1 | TinyTPU | `tx_ready` terlambat 1 siklus dari data | Pasti | `test_T1_tx_ready_framing` |
| T2 | TinyTPU | Bit 0 z00 dari produk parsial x00·y00 | Pasti | `test_T2_result_exact` |
| T3 | TinyTPU | Akumulator 16 bit overflow (butuh 17) | Pasti | `test_T3_extreme_exact` |
| T4 | TinyTPU | `bit_counter`/`ram_counter` tidak kembali 0; operasi kedua salah | Pasti | `test_T4_back_to_back`, `test_T4_counters_return_to_zero` |
| T5 | TinyTPU | `init_delay` tanpa reset: netlist X setelah reset tunggal | Pasti (GL) | `test_T5_single_reset` |
| T6 | TinyTPU | 32 latch `dlxtn` dari `dff_mem.data_out` | Pasti (struktur) | — (hitungan sel netlist) |
| I1 | Iterative MAC | Mode 0 selalu mengeluarkan 0 | Pasti | `test_I1_mode0_output_follows_inputs` |
| I2 | Iterative MAC | Mode 0: `uio` keluaran sekaligus bias | Pasti (kode/pin) | `test_I2_uio_direction` |
| I3 | Iterative MAC | Cabang `out_th` mati | Pasti | `test_mode1_mac_random` |
| I4 | Iterative MAC | Overflow 32 bit tanpa tanda | Pasti | `test_I4_mode1_no_silent_overflow` |
| V1 | Vector CiSRAM | Hanya tak bertanda; label "negative" di test upstream menyesatkan | Pasti | `test_V1_signed_vectors` |
| V2 | Vector CiSRAM | Tidak ada SRAM, hanya flip-flop | Pasti (struktur) | — (hitungan sel netlist) |
