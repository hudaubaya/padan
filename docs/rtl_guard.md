# Guard: pembatas percobaan, LOCK, FAULT, tamper, zeroize

> **Batas pertama yang perlu diketahui.** Semua keadaan guard volatil. Setiap
> reset mengenolkan template, jadi template harus di-enroll ulang dari host
> setelah setiap boot. Artinya salinan template selalu ada di luar chip, dan
> guard tidak melindungi salinan itu. [Pasti] Daftar batas lengkap ada di
> bagian [Batas](#batas).

`rtl/guard.v` berada di dalam `padan_avmm` dan mengendalikan izin engine bus.
Ia tidak menambah jalur baca data: register baru hanya GUARD_STATUS (baca)
serta GUARD_LOCK, GUARD_K, dan GUARD_TAU (tulis). Peta register lengkap ada di
`docs/rtl_decision.md`.

## Ringkasan

| Fungsi | Perilaku |
|---|---|
| Pembatas percobaan | `fail` naik setiap NO_MATCH dan dinolkan oleh MATCH. Bila `fail` mencapai K, guard masuk **LOUT**: tidak ada operasi lagi sampai reset. K = 5 saat boot; GUARD_K (1–15) hanya bisa diubah di OPEN. |
| LOCK enrollment | GUARD_LOCK = `0x4C4F434B` membawa OPEN ke **LOCKD**. ENROLL_DATA, ENROLL_CLR, GUARD_K, dan GUARD_TAU ditolak; probe dan MATCH tetap bisa. |
| τ terkunci | Di LOCKD, decision memakai GUARD_TAU, bukan τ yang ditulis host bersama MATCH. Default `0x7FFFFFFF`: tidak ada MATCH. |
| Penghitung FAULT | Kumulatif sejak boot, tidak dinolkan oleh MATCH. FAULT ke-3 (FAULT_MAX) memicu zeroize, lalu **HALT**. |
| Tamper | `tamper_n` (KEY0, aktif rendah) disinkronkan 2-FF. Tamper di state mana pun kecuali HALT memicu zeroize, lalu HALT. |
| Safe-state | Setiap kode state ilegal, dan setiap ketidakcocokan antara penghitung dan komplemennya, memicu zeroize, lalu HALT. |
| Zeroize | Seluruh memori template (T, C, Cw: 16 bank × 144 word) dan 128 byte probe ditulis nol. |

### Mengapa τ dikunci

Spesifikasi awal tidak meminta ini. Tanpanya, pembatas percobaan bisa ditembus
dengan satu tulis: host menulis MATCH dengan τ = −2³¹. Decision lalu memberi
MATCH untuk probe apa pun, sehingga `fail` kembali nol. [Pasti]

Masalahnya juga lebih besar dari itu. Dengan τ rendah, indeks argmax keluar
untuk setiap probe, dan perangkat menjadi oracle identifikasi tanpa ambang.
Mutan `tau_from_host` membuktikan test menangkap celah ini.

## FSM

| State | Kode | Izin | Keluar |
|---|---|---|---|
| ZB | `0000` | – (zeroize boot) | zeroize selesai → OPEN, penghitung default |
| OPEN | `0011` | enroll, probe, match, status | LOCK → LOCKD; K gagal → LOUT; tamper/FAULT/ilegal → ZH |
| LOCKD | `0101` | probe, match (τ terkunci), status | K gagal → LOUT; tamper/FAULT/ilegal → ZH |
| LOUT | `0110` | status | reset; tamper/ilegal → ZH |
| ZH | `1001` | – (zeroize) | zeroize selesai → HALT |
| HALT | `1010` | – | reset |

**Pengodean state** [Pasti]:
- Semua kode legal berparitas genap. Flip satu bit pada state legal selalu
  menghasilkan kode berparitas ganjil, dan kode itu ilegal.
- Kode ilegal: semua kode berparitas ganjil, ditambah `1100` dan `1111`.
- Deteksinya ditulis sebagai logika eksplisit (`^state`, dua kode tak terpakai),
  bukan hanya cabang `default`.

**Penghitung dengan komplemen.** `fail`, `k`, `fault`, dan `tau_lk` masing-masing
disimpan bersama komplemennya. Di OPEN, LOCKD, dan LOUT, ketidakcocokan dianggap
ilegal.

**Pembacaan hasil.** Hasil dibaca saat `dec_busy` turun, yaitu siklus
ketika decision meng-commit kode. Klasifikasinya:
- **MATCH:** kode MATCH dengan `idx == ~idx_n`.
- **NO_MATCH:** kode NO_MATCH.
- **FAULT:** semua kode lain, termasuk NONE, kode tak dikenal, dan MATCH dengan
  idx tidak konsisten.

Hanya hasil yang selesai di OPEN atau LOCKD dihitung. LOCK dan GUARD_K yang
datang pada siklus yang sama dengan hasil tetap diproses. Bila hasil itu
memicu LOUT atau ZH, transisi karena hasil menang.

## Zeroize

| Langkah | Isi | Siklus |
|---|---|---|
| Z_WAIT | Tunggu `template_mem`, `mac_array`, dan `decision` diam. Match yang sedang berjalan diselesaikan dulu, dan hasilnya tidak dihitung. | 1, atau hingga ±153 bila ada match |
| Z_CLR | Minta `clr` ke `template_mem` sampai diterima | 1–2 |
| Z_CWAIT | Clear 144 alamat × 16 bank: T, C, dan Cw | 144 |
| Z_PROBE | Tulis 0 ke 128 byte probe, satu per siklus. Paritas ikut menjadi 0. | 128 |
| Z_DONE | ZB → OPEN, ZH → HALT | 1 |

**Selama zeroize semua izin bernilai 0.**
- Engine bus menahan tulis baru dengan `waitrequest` hingga zeroize selesai.
- Operasi yang sedang berjalan (tulis byte template, tulis probe, MATCH yang
  menunggu) dibuang di tengah jalan.
- Kode sequencer zeroize yang ilegal (5–7) mengulang zeroize dari awal.

**Yang TIDAK di-zeroize** [Pasti]:
- `best_a`/`best_b` dan `idx_a`/`idx_b` di `decision`, berisi skor dan indeks
  terbaik match terakhir.
- Akumulator `mac_array`.
- Residu `abft_check`.

Register itu tidak punya jalur baca dari bus. STATUS[11:0] dibaca sebagai NONE
(`0xF00`) di ZB, ZH, dan HALT, sehingga keputusan terakhir tidak terlihat
setelah tamper. Sisa nilai itu hanya relevan bagi serangan fisik.

## Verifikasi

### `make test-rtl-guard` (`tb/guard`, parameter rilis K = 5, FAULT_MAX = 3) [Pasti]

Semua perintah dikirim lewat port Avalon-MM. Zeroize dibuktikan dengan
**memindai isi memori di simulasi**: semua 16 bank × 144 word, termasuk baris
C dan Cw, serta register `probe` dan `probe_par`. Sebelum zeroize, memori diisi
nilai acak bukan nol lewat deposit.

| Test | Isi |
|---|---|
| `test_boot_zeroize` | Reset dengan memori dan probe terisi acak menghasilkan semua nol sebelum OPEN. Tulis host selama zeroize ditahan (> 272 siklus) lalu dijalankan; sesudahnya hanya T[0,0..3] dan kolom C/Cw yang terkait yang bukan nol. |
| `test_lockout_after_k` | 4 NO_MATCH, lalu MATCH (fail = 0), lalu 4 NO_MATCH masih OPEN; NO_MATCH ke-5 → LOUT. Di LOUT, MATCH, CLR, ENROLL, PROBE, K, dan LOCK ditolak, dan memori serta probe tidak berubah. Reset → zeroize → OPEN dengan penghitung default. |
| `test_k_programmable` | GUARD_K 0, 16, `0x102`, dan `0xA5A5A5A5` diabaikan. K = 2 diterima di OPEN, ditolak di LOCKD; 2 NO_MATCH → LOUT. |
| `test_lock_blocks_enroll` | LOCK dengan nilai salah diabaikan. Setelah LOCK, ENROLL_DATA (termasuk enrollment penuh 512 word) dan ENROLL_CLR tidak mengubah satu word pun (pindai memori). Probe dan MATCH tetap benar. |
| `test_tau_locked` | Di LOCKD, MATCH dengan τ = −2³¹ dari host tetap NO_MATCH (τ terkunci berlaku), dan 5 percobaan → LOUT. GUARD_TAU ditolak di LOCKD. Tanpa GUARD_TAU, default memberi NO_MATCH. Di OPEN, τ dari host berlaku. |
| `test_tamper_zeroize` | Sinkronisasi diperiksa per siklus: tamper belum terlihat setelah sisi naik ke-1 dan ke-2, dan state menjadi ZH pada sisi ke-3. Lalu HALT dengan memori dan probe nol, alasan TAMPER, STATUS = NONE. Semua permintaan setelahnya ditolak; tamper lagi di HALT tidak mengubah apa pun. |
| `test_tamper_during_activity` | Tamper saat zeroize boot, saat MATCH (+30 dan +140 siklus), saat enrollment (+3 dan +9), dan saat tulis probe: selalu berakhir HALT dengan memori dan probe nol. |
| `test_fault_threshold` | Bit template dibalik → FAULT. Dua FAULT diselingi MATCH: `fault` tetap 1, lalu 2. FAULT ke-3 → zeroize → HALT, alasan FAULT. |
| `test_illegal_state` | Dari OPEN, untuk ke-10 kode ilegal dan setiap flip bit `fail`, `fail_n`, `k`, `k_n`, `fault`, dan `fault_n`, plus tiga flip `tau_lk`/`tau_lk_n`: zeroize → HALT, alasan ILLEGAL, memori nol. Juga dari LOCKD dan LOUT (sampel kode ilegal). Kode sequencer 5–7 di tengah zeroize boot: zeroize diulang dan selesai. |

### `make check-rtl-guard-safe` (`tb/guard/prove_safe.sh`) [Pasti, Yosys]

Bukti SAT Yosys pada `guard` **setelah** `synth -flatten`. Semua input bebas
kecuali `rst_n` = 1. Untuk setiap kode ilegal (10 kode):
- semua izin bernilai 0 pada siklus itu;
- state berikutnya ZH.

Selain itu, HALT tetap HALT untuk semua input.

**Kontrol negatif.** Guard tanpa deteksi ilegal (mutan `illegal_stays`) harus
gagal dibuktikan. Ini memastikan buktinya tidak kosong.

**Cakupan.** Bukti ini hanya untuk sintesis Yosys. Quartus belum diperiksa
(`docs/fpga_howto.md` 6a).

### `make check-rtl-infer` [Pasti, Yosys]

`guard` disintesis dengan `synth_intel_alm` menjadi 103 FF. Jumlah ini adalah
semua register, termasuk pasangan nilai/komplemen, tanpa penggabungan.

### Test lain yang ikut berubah

- **`tb/avmm`:** guard dipasang dengan K = FAULT_MAX = 65535, supaya ratusan
  NO_MATCH dan FAULT di kampanye fault tidak memicu lockout atau HALT.
  `test_address_scan` kini mengizinkan GUARD_STATUS bukan nol dan memeriksa
  bahwa tulis sampah ke GUARD_LOCK, GUARD_K, dan alamat kosong tidak mengubah
  guard.
- **`tb/fpga`:** memakai parameter rilis.
  - `padan_vectors.tcl` diurutkan ulang sehingga paling banyak 2 NO_MATCH
    berturut-turut. `gen_vectors.py` memeriksa batas ini (≤ K − 1).
  - Test fault kini mengharapkan HALT setelah FAULT ke-3.
  - Test baru: skrip menolak berjalan bila guard LOCKD.

### Uji mutasi (`make test-rtl-mutation`, suite guard) [Pasti]

| Mutan | Perubahan | Dibunuh oleh |
|---|---|---|
| `no_lockout` | `fail_hit` tidak memicu LOUT | lockout, k_programmable, tau_locked |
| `lock_ignored` | GUARD_LOCK diabaikan | k_programmable, lock_blocks_enroll, tau_locked, tamper_zeroize |
| `enroll_when_locked` | izin enroll tetap ada di LOCKD | lock_blocks_enroll |
| `tamper_ignored` | tamper = 0 | tamper_zeroize, tamper_during_activity |
| `tamper_1ff` | sinkronisasi hanya 1 FF | tamper_zeroize |
| `no_fault_limit` | ambang FAULT tidak memicu zeroize | fault_threshold |
| `illegal_stays` | deteksi ilegal dan `default` dihapus | illegal_state |
| `tau_from_host` | LOCKD tetap memakai τ dari host | tau_locked |
| `tau_writable_locked` | GUARD_TAU bisa ditulis di LOCKD | tau_locked |
| `no_ctr_check` | ketidakcocokan komplemen diabaikan | illegal_state |
| `clr_skips_checksum` | `template_mem` clear berhenti setelah baris T (C, Cw tidak dinolkan) | 6 test yang memindai memori |
| `no_probe_zero` | zeroize tidak menolkan probe | 6 test yang memindai memori |

Setiap mutan harus menggagalkan **tepat** himpunan test di atas, dan setiap
kegagalan harus berupa `AssertionError`.

## Batas

1. **Volatil.** Penghitung, LOCK, K, dan τ hilang saat reset.
   - Reset selalu mengenolkan memori. Reset tidak bisa dipakai untuk mengulang
     percobaan terhadap template yang sama. [Pasti]
   - Konsekuensinya, template harus dikirim ulang dari host setiap boot. Salinan
     di host adalah titik terlemah dan berada di luar cakupan guard.
   - Reset juga menjadi jalan DoS: siapa pun yang bisa me-reset bisa
     menghapus enrollment.
2. **Pembatas hanya menghitung kegagalan berturut-turut.** MATCH menolkan
   `fail`. Penyerang yang punya satu probe sah bisa menyelipkan probe itu
   setiap 4 percobaan, sehingga jumlah percobaan tidak terbatas. [Pasti, dari
   logika]
   - Bila ancaman ini relevan, perlu penghitung total atau pembatas laju.
3. **OPEN tidak aman.** Di OPEN, enrollment terbuka dan τ datang dari host.
   Perlindungan baru berlaku setelah LOCK. [Pasti]
4. **Flip dua bit bisa membuka kunci.** Jarak Hamming antar state legal
   minimal 2.
   - Flip dua bit `0101` (LOCKD) → `0011` (OPEN) membuka enrollment lagi.
     [Pasti]
   - Flip satu bit selalu tertangkap.
5. **Logika kombinasional tidak dilindungi.** Ini mencakup dekode izin, mux τ,
   dan pemeriksa komplemen. Yang dilindungi hanya isi register.
6. **Tamper.**
   - KEY0 adalah tombol, bukan sensor tamper. Satu tekanan tak sengaja
     menghapus enrollment.
   - Tidak ada filter glitch. Satu pulsa yang tertangkap FF sinkronisasi sudah
     cukup.
   - Port yang tidak terhubung di top kemungkinan besar diikat ke 0
     (`docs/fpga_howto.md` 3b), sehingga perangkat langsung HALT.
   - Serangan fisik (probing, glitch clock/daya, pembacaan bitstream, remanensi
     memori setelah daya mati) tidak dicakup.
7. **Latensi zeroize.** Zeroize menunggu match yang sedang berjalan selesai
   (±153 siklus), lalu ±274 siklus clear dan probe: total sekitar 430 siklus,
   atau ±9 µs pada 50 MHz. [Kemungkinan Besar, dihitung dari jumlah siklus,
   tidak diukur] Selama itu, data masih ada.
8. **Register yang tidak di-zeroize.** Lihat bagian [Zeroize](#zeroize).
9. **FAULT ke-3 tidak terlihat sebagai FAULT di STATUS.** Zeroize langsung
   dimulai dan STATUS menjadi NONE. Host harus membaca GUARD_STATUS (alasan
   FAULT) untuk tahu sebabnya.
10. **Quartus belum diverifikasi.** Belum dibuktikan bahwa Quartus
    mempertahankan pengodean state dan logika safe-state. Bukti SAT hanya
    untuk Yosys. Pemeriksaan manual ada di `docs/fpga_howto.md` 6a.
