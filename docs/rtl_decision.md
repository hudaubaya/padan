# Keputusan dan antarmuka Avalon-MM

`rtl/decision.v` dan `rtl/padan_avmm.v`, di atas inti dari
[`rtl_padan.md`](rtl_padan.md). Gaya penulisan: [`rtl_style.md`](rtl_style.md).

Label keyakinan:
- **[Pasti]** dibuktikan oleh test di repo ini.
- **[Kemungkinan Besar]** inferensi kuat yang belum dibuktikan di sini.

## Ringkasan

- **`decision.v`:** identifikasi 1:N dengan ambang τ dari aliran skor, dengan
  dua komparator independen.
  - Keputusan ditahan (FAULT) bila ABFT gagal, paritas probe salah, atau kedua
    komparator tidak sepakat.
  - Model: `decide()` di `model/padan.py`.
- **`padan_avmm.v`:** slave Avalon-MM minimal dengan ENROLL, PROBE, MATCH, dan
  STATUS, plus register guard (`docs/rtl_guard.md`). Template, probe, skor, dan
  checksum tidak punya jalur baca.
- **Dua perubahan pada inti:**
  - `mac_array` mendapat paritas per byte probe (`p_err`).
  - `abft_check` mendapat pulsa `err_vld` pada siklus tetap.

## decision.v

| Keluaran | Syarat |
|---|---|
| MATCH(k) | max_j s_j ≥ τ; k = argmax, indeks terkecil bila seri |
| NO_MATCH | max_j s_j < τ. Indeks **tidak** dilaporkan, karena argmax dari penolakan tetap membocorkan identitas terdekat. |
| FAULT | `abft_err` atau `p_err` atau komparator A ≠ B (match atau indeks) |

**Dua komparator independen.** Keduanya membaca aliran skor yang sama dengan
`abft_check`, langsung dari akumulator `mac_array`. Tidak ada register skor di
antara pemeriksaan ABFT dan perbandingan.

| | Komparator A | Komparator B |
|---|---|---|
| argmax | perbandingan bertanda `s > best_a` | bit tanda selisih 33 bit `s − best_b > 0` |
| ambang | `best_a ≥ tau_a` di akhir | OR per baris dari `s − tau ≥ 0` |
| salinan τ | `tau_a = τ` | `tau_bn = ~τ` (komplemen) |

**τ di B disimpan sebagai komplemen.** Tanpa itu, Yosys menggabungkan `tau_a`
dan `tau_b` menjadi satu register walau ada atribut `keep`: 119 FF, bukan 151.
Dengan komplemen, semua 151 register bertahan. [Pasti, Yosys] `make
check-rtl-infer` memeriksa angka 151 itu.

**Kode STATUS.** Jarak Hamming antar kode ≥ 2, dan antara MATCH dan NO_MATCH = 4.

| Kode | Arti |
|---|---|
| `0000` | NONE: belum ada keputusan, atau match sedang berjalan |
| `0101` | NO_MATCH |
| `1010` | MATCH |
| `1111` | FAULT |
| lainnya | **host wajib** menganggapnya FAULT |

Indeks dikeluarkan dua kali: `idx` dari A dan `~idx` dari B. Host hanya menerima
MATCH bila kodenya `1010` **dan** `idx == ~(~idx)`. Flip satu bit pada register
keluaran tidak pernah menghasilkan MATCH yang salah. [Pasti]
`test_fault_decision` membalik 12 bit keluaran di kedua skenario.

## padan_avmm.v

Data 32 bit, alamat word 10 bit.
- **Baca:** `waitrequest` = 0; `readdatavalid` 1 siklus setelahnya.
- **Tulis:** `waitrequest` ditahan sampai inti menerima data.

| Alamat word | Nama | Akses | Isi |
|---|---|---|---|
| `0x000`–`0x1FF` | ENROLL_DATA | W | T[j][4k+b] = writedata[8b+7:8b], j = addr[8:5], k = addr[4:0] |
| `0x200`–`0x21F` | PROBE_DATA | W | p[4k+b] = writedata[8b+7:8b] |
| `0x300` | ENROLL_CLR | W | kosongkan T, C, Cw |
| `0x301` | MATCH | W | writedata = τ (bertanda), mulai identifikasi |
| `0x302` | STATUS | R | [3:0] kode, [7:4] idx, [11:8] ~idx, [16] match berjalan, [17] enroll berjalan |
| `0x303` | GUARD_STATUS | R | [3:0] state guard, [7:4] fail, [11:8] k, [15:12] fault, [17:16] alasan, [18] tamper, [19] zeroize berjalan |
| `0x304` | GUARD_LOCK | W | writedata = `0x4C4F434B` ("LOCK"): OPEN → LOCKD |
| `0x305` | GUARD_K | W | writedata = K, 1–15 (bit lain 0), hanya di OPEN |
| `0x306` | GUARD_TAU | W | writedata = τ untuk LOCKD (bertanda), hanya di OPEN |
| lainnya | – | – | baca 0, tulis diabaikan |

**Izin dari guard** (`docs/rtl_guard.md`):
- ENROLL_DATA dan ENROLL_CLR hanya diizinkan di OPEN; PROBE_DATA dan MATCH di
  OPEN dan LOCKD.
- Di LOCKD, τ yang ditulis bersama MATCH diabaikan; decision memakai GUARD_TAU.
- Tulis yang tidak diizinkan tetap diterima (waitrequest turun), tetapi
  dibuang.
- Selama zeroize, tulis ditahan dengan waitrequest sampai zeroize selesai.
- Di luar OPEN, LOCKD, dan LOUT, STATUS[11:0] dibaca sebagai NONE (`0xF00`).

**Skor sengaja tidak bisa dibaca.** Probe basis p = 127·e_i memberi
s_j = 127·T[j,i]. Dengan 128 probe, host bisa merekonstruksi seluruh template
dari skor. [Pasti, aljabar]

### Latensi [Pasti]

| Besaran | Nilai |
|---|---|
| Tulis MATCH saat inti idle | `waitrequest` 2 siklus |
| Start diterima → keputusan di-commit | **153 siklus**, untuk MATCH, NO_MATCH, dan FAULT, dengan atau tanpa fault |
| Tulis ENROLL (4 byte) saat idle | `waitrequest` 22 siklus (generator checksum per byte); 512 word per galeri |
| Tulis PROBE (4 byte) saat idle | `waitrequest` 5 siklus |

Latensi tetap karena `decision` meng-commit pada `err_vld`, yang datang pada
siklus tetap setelah baris terakhir. Lokalisasi ABFT (sampai 16 siklus) hanya
diagnostik dan boleh dipotong oleh MATCH berikutnya. Latensi yang tetap juga
menutup kanal samping waktu antara MATCH dan FAULT.

## Verifikasi (`make test-rtl-avmm`)

`tb/avmm/test_avmm.py` hanya berbicara lewat port Avalon-MM, seperti host.
Guard di suite ini memakai batas maksimum (`tb/avmm/Makefile`: K dan FAULT_MAX
= 65535), supaya ratusan NO_MATCH dan FAULT di kampanye tidak memicu lockout.
Guard dengan parameter rilis diuji di `tb/guard` dan `tb/fpga`.
Penghitung latensi di `tb/avmm/tb_avmm.v` diperiksa pada **setiap** MATCH di
semua test: harus 153.

| Test | Isi |
|---|---|
| `test_address_scan` | 3 galeri × 2 fase (setelah enroll, setelah match): baca seluruh 1.024 alamat. Semua alamat selain STATUS dan GUARD_STATUS bernilai 0, guard OPEN, dan bit STATUS di luar field terdefinisi bernilai 0. Tulis sampah ke STATUS, alamat kosong, GUARD_LOCK, dan GUARD_K tidak mengubah keputusan atau guard. |
| `test_decisions_vs_model` | 814 keputusan identik dengan `decide()`: 400 probe data sintetis (galeri `docs/padan_model.md` bagian 3, τ rilis); 400 probe acak dengan τ = max, max ± 1, atau acak; template kembar (seri → indeks terkecil); nilai ekstrem −128/127. |
| `test_fault_datapath` | flip register produk setiap lane × bit (384) dan akumulator setiap baris × bit (576), per skenario |
| `test_fault_memory` | flip setiap bit memori (T, C, Cw): skenario impostor semua 36.864 bit, genuine setiap bit ke-5 (7.373) |
| `test_fault_probe` | flip setiap bit probe (1.024) dan paritasnya (128), per skenario |
| `test_fault_decision` | flip setiap bit register A/B (τ, best, idx, flag; 138), `abft err` dan `p_err` sebelum commit, dan 12 bit keluaran setelah commit, per skenario |
| `test_fixed_latency` | MATCH, NO_MATCH, dan FAULT bergantian: latensi dan siklus tunggu MATCH sama |

**Skenario fault, dengan τ di batas:**
- **impostor:** τ = max + 1, golden NO_MATCH. Galat ke atas sekecil apa pun pada
  skor terbesar akan melewati ambang.
- **genuine:** τ = max, golden MATCH(k).

**Kriteria fault.** Hasil harus FAULT atau sama dengan golden. MATCH yang
berbeda dari golden adalah kegagalan. Fault lane, akumulator, memori, probe,
`abft err`, dan `p_err` juga harus menghasilkan FAULT.

**Hasil:** 48.765 fault; tidak satu pun menghasilkan MATCH yang salah. [Pasti]

### Uji mutasi (`make test-rtl-mutation`, suite avmm) [Pasti]

| Mutan | Test yang gagal | Bukti |
|---|---|---|
| `no_agree`: tidak menahan saat A ≠ B | `test_fault_decision` | flip bit 0 `tau_a` membuat impostor MATCH |
| `no_parity`: abaikan `p_err` | `test_fault_probe`, `test_fault_decision` | **satu flip bit probe membuat impostor MATCH** |
| `no_abft`: abaikan `abft_err` | datapath, memori, decision, latensi | fault datapath memberi keputusan tanpa FAULT |

Mutan `no_parity` membuktikan di RTL temuan model (`docs/padan_model.md`
contoh E): fault probe lolos ABFT dan bisa menghasilkan false accept. Paritas
menutup celah itu untuk flip satu bit.

## Model fault dan batasnya

**Tercakup** (flip satu bit, transien atau persisten): register produk lane,
akumulator, memori template dan checksum, probe dan paritasnya, register kedua
komparator, `abft err`/`p_err`, serta register keluaran STATUS.

**Tidak tercakup, dan tidak boleh diklaim:**
- **Fault kendali:** sequencer `mac_array`, tag baris (`o_row`), `o_vld`, FSM
  `abft_check`/`padan_avmm`, `err_vld`. Contohnya, flip pada `o_row` bisa membuat
  kedua komparator dan ABFT melihat indeks yang salah secara konsisten. Belum
  disimulasikan. [Kemungkinan Besar] Perlindungannya butuh duplikasi kendali
  atau watchdog.
- **Lebih dari satu fault sekaligus** (`docs/padan_model.md` contoh A–D).
- **Fault di port Avalon sendiri,** di sisi host, clock, atau reset.
- **Serangan oracle:** walau skor tidak bisa dibaca, MATCH/NO_MATCH pada τ
  pilihan host tetap memberi satu bit per query. Pencarian bukit atas probe bisa
  mendekati template. Pembatasan laju atau otentikasi ada di luar modul ini.
  [Kemungkinan Besar]
- **τ ditentukan host** lewat tulis MATCH, tanpa batas bawah. Host yang menulis
  τ sangat kecil akan mendapat MATCH untuk probe apa pun. Kebijakan τ adalah
  tanggung jawab perangkat lunak.
