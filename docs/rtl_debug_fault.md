# Injeksi fault terkendali host (build debug `DEBUG_FAULT`)

> **Hanya untuk lab.** Build debug adalah alat DoS siap pakai. Setiap injeksi
> adalah FAULT, dan dengan parameter rilis guard melakukan zeroize setelah 3 FAULT.
> Bitstream debug tidak boleh dipakai sebagai perangkat. STATUS[31] = 1 menandai
> build debug, sehingga host dan `padan_test.tcl` bisa menolaknya.
> `status_ok` mewajibkan bit [31:18] = 0, jadi deteksi master otomatis gagal pada
> bitstream debug.

## Antarmuka

Aktif bila `DEBUG_FAULT` didefinisikan saat kompilasi, misalnya
`iverilog -DDEBUG_FAULT` atau `read_verilog -DDEBUG_FAULT`. Tidak ada port
top-level baru: host mengendalikan injeksi lewat bus Avalon-MM.

| Alamat word | Nama | Akses | Isi |
|---|---|---|---|
| `0x307` | DBG_FAULT | W | [0] aktif, [4:1] lane, [9:5] baris (0–15 skor, 16 = C, 17 = Cw), [12:10] chunk, [31:16] delta bertanda |
| `0x308` | DBG_ABFT | R | [7:0] loc_idx, [8] loc_vld, [9] err, [10] chk, [11] pemeriksaan selesai |
| `0x302` | STATUS | R | bit [31] = 1 di build debug |

- **Cara kerja delta.** `mac_array` menambahkan delta ke produk lane `lane` pada
  baris `baris`, chunk `chunk`, di setiap MATCH. Pengaturan ini berlaku sampai
  DBG_FAULT ditulis lagi dengan [0] = 0.
- **Hanya di OPEN.** Tulisan ke DBG_FAULT diterima hanya saat guard OPEN, dan
  injeksi yang sudah aktif tidak berlaku setelah LOCK (atau di LOUT dan HALT).
- **Host tidak bisa membaca residu.** Host hanya membaca hasil lokalisasi (indeks
  dan flag), bukan residu `d1`/`d2`.

### Mengapa delta aditif, bukan nilai pengganti atau XOR

Dengan delta aditif, galat pada skor baris j sama dengan delta (mod 2^24). Residu
ABFT menjadi d1 = delta dan d2 = (j+1)·delta, tidak bergantung pada T maupun p.
[Pasti, aljabar; diuji di `test_delta_is_data_independent`]

Bila produk *diganti* dengan nilai v, residunya menjadi d1 = v − T[j,i]·p_i. Bila
produk di-XOR, galatnya bergantung pada bit-bit produk. Dalam kedua kasus, port
debug akan menjadi kanal pembacaan template.

## Verifikasi

### `make test-rtl-debug` (`tb/debug`, `-DDEBUG_FAULT`) [Pasti, simulasi]

| Test | Isi |
|---|---|
| `test_debug_build_clean` | STATUS[31] = 1. Tanpa injeksi, dengan delta 0, atau dengan bit aktif 0: keputusan sama dengan model dan ABFT bersih. |
| `test_inject_detect_localize` | 16 lane × 18 baris (288 injeksi), chunk dan delta acak termasuk ±1, 32767, −32768. Setiap keputusan FAULT. Galat di baris skor j dilokalisasi ke j (256 kasus); galat di baris C/Cw memberi `chk` tanpa lokalisasi (32 kasus). Setelah injeksi dimatikan, keputusan kembali sama dengan model. |
| `test_delta_is_data_independent` | Untuk 3 template/probe acak, d1 = delta dan d2 = (j+1)·delta persis, dan hasil yang terlihat host identik. |
| `test_inject_only_in_open` | Setelah LOCK, injeksi yang aktif tidak berlaku dan DBG_FAULT baru ditolak. |

Suite ini memakai FAULT_MAX = 65535 supaya ratusan injeksi tidak memicu HALT.
Parameter guard lain sama dengan rilis.

### `make check-rtl-release` (`tb/debug/check_release.py`) [Pasti]

Membuktikan bahwa build rilis tidak memiliki port, register, atau logika injeksi:

1. **Praproses.** Keluaran `iverilog -E` setiap berkas RTL, tanpa komentar, tidak
   memuat "dbg".
2. **Netlist Yosys setelah `hierarchy; proc`.** Pemeriksaan dilakukan sebelum
   optimasi apa pun, jadi ketiadaan nama tidak bisa disebabkan oleh optimasi.
   - Tidak ada port atau net `dbg_*` di modul mana pun.
   - Port `padan_avmm` dan `mac_array` sama persis dengan daftar rilis.
3. **Tidak ada definisi `DEBUG_FAULT`** di `rtl/` atau `fpga/`. Ini mencakup
   `` `define``, `VERILOG_MACRO`, dan bentuk sejenis, sehingga alur Platform
   Designer/Quartus di repo ini selalu membangun versi rilis.

**Kontrol positif.** Pemeriksaan 1 dan 2 dijalankan juga pada build debug dan
harus menemukan jejak di sana; bila tidak, skrip gagal karena pemeriksaannya
kosong. Pada build debug tercatat 35 temuan praproses dan 58 temuan netlist.

**Perilaku bus build rilis.** `tb/avmm` `test_address_scan` menulis `0xA5A5A5A5`
ke 0x307 dan 0x308, lalu memeriksa tiga hal:
- 0x307 dan 0x308 terbaca 0;
- STATUS[31] = 0;
- MATCH sesudahnya tetap sama dengan model.

Pada build debug, tulisan itu mengaktifkan injeksi, sehingga MATCH menjadi FAULT
dan test gagal.

**Pemeriksaan satu kali saat PR ini dibuat (tidak dijalankan di CI).** Hasil
praproses rilis (tanpa komentar) dibandingkan dengan `main` sebelum PR:
- **Lima modul identik baris per baris:** `mac_array`, `abft_check`, `decision`,
  `template_mem`, `guard`.
- **`padan_avmm` berbeda pada tiga hal:**
  - urutan deklarasi `g_cmd`/`k_hi`;
  - urutan koneksi port `abft_check`;
  - STATUS[31] yang kini konstanta `DEBUG_BUILD` = 0.

  Tak satu pun mengubah logika.

## Batas

- **Rilis vs debug hanya dibuktikan pada sumber RTL dan netlist Yosys.** Quartus
  dengan `VERILOG_MACRO DEBUG_FAULT` di `.qsf` milik pengguna di luar repo akan
  membangun versi debug. Pemeriksaan 3 hanya mencakup berkas di repo. Pertahanan
  terakhir adalah STATUS[31].
- **Injeksi hanya pada produk lane.** Fault di memori, probe, akumulator, atau
  decision tetap diuji lewat deposit simulasi (`tb/padan`, `tb/avmm`), bukan
  lewat port ini.
- **Galat pada baris Cw bisa terpotong.** Produk Cw bisa mendekati 2^23, sehingga
  produk + delta bisa wrap di 24 bit. Galatnya tetap bukan nol dan tetap
  terdeteksi, tetapi d2 tidak lagi sama dengan −delta.
