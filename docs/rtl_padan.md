# RTL PADAN: mac_array, template_mem, abft_check

Implementasi RTL dari golden model `model/padan.py` (`docs/padan_model.md`).
Gaya penulisan dan alasan inferensi M10K/DSP: [`rtl_style.md`](rtl_style.md).

Label keyakinan:
- **[Pasti]** dibuktikan oleh test di repo ini.
- **[Kemungkinan Besar]** inferensi kuat yang belum dibuktikan di sini.

## Arsitektur

```
 bus (tulis saja) ──► template_mem ──rd_addr/rd_data (16 lane x 16 bit)──► mac_array ──o_vld/o_row/o_data──► abft_check
   bus_wr, clr        16 bank M10K                                         16 MAC 16x8                       S1, S2 (40 bit)
                      generator C, Cw                                      adder tree 16→4→1                 d1, d2, lokalisasi
 bus probe ─────────────────────────────────────────────────────────────►  akumulator 32 bit                  err, loc_vld, loc_idx, chk
```

| Modul | Isi |
|---|---|
| `rtl/template_mem.v` | 16 bank RAM simple dual-port (satu per lane), 144 word × 16 bit: T (baris 0..15, 8 word per baris), C, Cw. Hanya bisa ditulis dari bus. Generator memperbarui C dan Cw pada setiap tulis byte. |
| `rtl/mac_array.v` | 16 lane MAC INT8 (T 16 bit diperluas tanda × p 8 bit), adder tree 2 tingkat, akumulator 32 bit, sequencer 18 baris: 16 skor, C·p, Cw·p. Probe 128 byte di register. |
| `rtl/abft_check.v` | S1 = Σ s_j, S2 = Σ (j+1)s_j dalam 40 bit, d1 = S1 − C·p, d2 = S2 − Cw·p, lokalisasi berurutan d2 = (k+1)·d1 tanpa pembagi. |
| `rtl/padan_defs.vh` | `padan_weight(j) = j + 1`, dipakai generator dan pemeriksa |
| `tb/padan/tb_padan.v` | toplevel test (bukan RTL rilis): menghubungkan ketiga modul dan menyimpan 18 hasil baris |

**Parameter rilis:** N = 16 template, D = 128 byte, L = 16 lane.

### Throughput dan latensi [Pasti]

Diukur di `test_release_params`, relatif ke sisi naik yang menerima `start`:

| Besaran | Nilai |
|---|---|
| Satu dot product D = 128 | 8 siklus (128 / 16 lane) |
| Hasil baris r (r = 0..17) | siklus 12 + 8r |
| `done` tanpa fault | siklus 151 |
| `done` dengan galat | ≤ siklus 167 (lokalisasi maksimal 16 langkah) |
| Biaya ABFT dalam siklus | 2 baris checksum = 16 siklus, +12,5% terhadap 128 siklus skor |
| Tulis 1 byte template (generator) | `bus_ready` kembali 5 siklus setelah diterima: 1 byte per 6 siklus (baca T lama, C, Cw; tulis T, C, Cw) |
| `clr` | `bus_ready` kembali 144 siklus setelah diterima |

### Generator C dan Cw

Tulis T[j,i] = v menghitung delta = v − T_lama[j,i], lalu C_i += delta dan
Cw_i += (j+1)·delta.

- C dan Cw tetap konsisten untuk urutan tulis apa pun, termasuk tulis ulang satu
  template tanpa `clr`. [Pasti] `test_random_pairs`: galeri ganjil ditulis di
  atas galeri sebelumnya tanpa `clr`, dalam urutan acak; satu template ditulis
  ulang sendirian. Isi C/Cw di memori dibandingkan dengan model.
- `clr` mengenolkan semuanya. Itu satu-satunya keadaan awal yang dijamin
  konsisten, karena M10K tidak di-reset.

### Pemeriksa 40 bit, bukan 32 bit

`docs/padan_model.md` bagian 4 menunjukkan bahwa pemeriksa 32 bit salah
menunjuk indeks untuk flip bit 27–31 pada skor atau akumulator. Pemeriksa 40 bit
eksak untuk nilai register 32 bit apa pun. [Pasti] `test_fault_accumulator`
membalik bit 0..31 di semua 18 baris, dan semuanya terlokalisasi benar.

## Verifikasi

Jalankan dengan `make test-rtl`. Test ada di `tb/padan/test_padan.py`, dibandingkan
dengan `model/padan.py`. Semua run memakai parameter rilis.

| Test | Isi | Jumlah |
|---|---|---|
| `test_release_params` | N, D, L = 16, 128, 16 di semua modul; latensi tabel di atas | 1 run |
| `test_random_pairs` | pasangan (galeri, probe) acak INT8 [−128, 127]: 18 baris identik dengan model, C/Cw di memori identik, d1 = d2 = 0 | 1.001 pasangan, 10 galeri |
| `test_extremes` | T ∈ {−128, 127, bergantian, acak ±ekstrem} × p ∈ {−128, 127, bergantian, 0}; mencapai Cw·p = 285.212.672 dan −282.984.448 | 16 run |
| `test_fault_lanes` | bit flip register produk: setiap lane × setiap bit (0..23), dan setiap lane × setiap baris (0..17) | 672 fault |
| `test_fault_accumulator` | bit flip akumulator: setiap baris (0..17) × setiap bit (0..31), chunk acak | 576 fault |
| `test_fault_memory` | bit flip setiap bit setiap word memori: 16 bank × 144 word × 16 bit (T, C, Cw) | 36.864 fault |
| `test_no_false_alarm` | galeri dan probe dengan banyak nol, tanpa fault | 300 run |

**Kriteria fault.** Untuk setiap fault, nilai galat E dihitung dari nilai
register sebelum dan sesudah flip. Test memeriksa:
- 18 baris = model + E (setelah wrap 32 bit);
- (d1, d2) = (E, (j+1)E) untuk skor j, (−E, 0) untuk C·p, (0, −E) untuk Cw·p;
- `err` = 1;
- skor: `loc_vld` = 1 dan `loc_idx` = j;
- checksum: `loc_vld` = 0 dan `chk` = 1 (tidak ada skor yang disalahkan).

Hasil:
- **Semua 38.112 fault terdeteksi dengan indeks yang benar.** [Pasti]
- **Tidak ada alarm palsu** pada semua run tanpa fault (1.001 + 16 + 300, plus
  run kontrol setelah setiap kampanye fault). [Pasti]
- **Probe untuk test memori tidak punya elemen nol.** Dengan p_i = 0, fault
  T[j,i] tidak mengubah skor, sehingga tidak ada yang bisa atau perlu dideteksi.
  `docs/padan_model.md` mencatat 13.952 kasus seperti itu (model).
- **Fault disuntik dengan deposit cocotb** pada register sasaran, pada sisi
  turun ketika tag pipeline (`p_row/p_ch`, `a_row/a_ch`) menunjuk baris dan
  chunk sasaran. Fault produk berumur satu siklus (transien). Fault akumulator
  dan memori bertahan sampai ditimpa atau dipulihkan.

### Uji mutasi (`make test-rtl-mutation`) [Pasti]

`tb/padan/mutate.py` menyalin `rtl/`, mengganti tepat satu potongan teks, lalu
menjalankan test dalam mode cepat (`PADAN_QUICK=1`). Setiap mutan harus:
- terkompilasi dan menjalankan 7 testcase;
- gagal hanya karena `AssertionError`;
- gagal tepat pada testcase yang diharapkan.

| Mutan | Perubahan | Testcase yang gagal |
|---|---|---|
| `no_c` | matikan C: `d1` selalu 0 | 3 test fault. d1 salah; lokalisasi hilang; fault di jalur C·p tidak terdeteksi. Run tanpa fault tetap lolos. |
| `no_cw` | matikan C_w: `d2` selalu 0 | 3 test fault, dengan alasan yang sama untuk Cw·p |
| `weight_j` | w(j) = j di `padan_defs.vh` (generator dan pemeriksa sama-sama salah) | semua 7. RTL konsisten dan tidak beralarm, tetapi baris Cw·p berbeda dari model pada setiap run. |

Mutan `no_c`/`no_cw` menunjukkan kenapa test tanpa fault saja tidak cukup:
pemeriksa yang setengah mati tetap diam pada data bersih.

### Inferensi (`make check-rtl-infer`)

Yosys `synth_intel_alm -family cyclonev`:
- `template_mem`: 16 `MISTRAL_M10K`, 0 MLAB.
- `mac_array`: 16 `MISTRAL_MUL18X18`, 0 M10K, 0 MLAB.

[Pasti untuk Yosys] Untuk Quartus: [Kemungkinan Besar], belum dijalankan di sini
(lihat `rtl_style.md`).

## Batasan

- **Tidak ada top-level bus** (Avalon/AXI). Antarmuka modul berupa handshake
  level sederhana. Integrator harus:
  - menahan `start` sampai `template_mem` dan `abft_check` selesai (`hold`);
  - menulis probe hanya saat `mac_array` tidak `busy` (tulis saat busy
    diabaikan).
- **Probe p tidak dilindungi ABFT.** p dipakai jalur skor dan jalur checksum
  sekaligus (`docs/padan_model.md` contoh E). Fault pada register probe tidak
  disimulasikan di sini karena memang tidak terdeteksi.
- **Lokalisasi satu galat.** Dua fault sekaligus bisa salah tunjuk (model,
  contoh B). `abft_check` tidak melakukan koreksi.
- **Simulasi RTL saja.** Belum ada sintesis Quartus, timing, atau simulasi
  gate-level FPGA. Target frekuensi belum ditetapkan.
