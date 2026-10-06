# Model PADAN: skor INT8 dengan ABFT

Dokumen ini **dihasilkan** oleh `python3 model/padan_report.py --write docs/padan_model.md`.
Jangan disunting tangan. `make check-model-report` (bagian dari `make test`)
gagal jika dokumen tidak sama dengan keluaran model.

**Label:**
- Setiap angka hasil diberi label **(model)**. Setiap tabel hasil ditandai
  **[model]**, dan setiap kolom angkanya berlabel (model).
- Angka-angka ini berasal dari golden model Python, bukan dari RTL, FPGA, atau
  silikon. Parameter masukan (D, N, τ, seed) adalah spesifikasi.
- Label keyakinan: **[Pasti]** dibuktikan secara aljabar atau oleh model secara
  exhaustive; **[Kemungkinan Besar]** inferensi kuat; **[Menebak]** tidak dipakai
  di sini.

## 1. Golden model

`model/padan.py`, dengan D = 128, N = 16, T dan p INT8, akumulator 32 bit:

```
s_j  = Σ_i T[j,i]·p_i                  skor
C_i  = Σ_j T[j,i]                      baris checksum (saat enrolment)
Cw_i = Σ_j (j+1)·T[j,i]                baris checksum berbobot
d1   = Σ_j s_j       − C·p             pemeriksaan ABFT: tanpa fault d1 = d2 = 0
d2   = Σ_j (j+1)·s_j − Cw·p
k    = d2/d1 − 1                       lokalisasi satu galat (jika 1 ≤ d2/d1 ≤ N)
```

Galat e pada s_k memberi d1 = e dan d2 = (k+1)·e. Semua aritmetika eksak (int
Python/NumPy int64). Register 32 bit dimodelkan dengan `wrap()` (modulo 2³²).

| File | Isi |
|---|---|
| `model/padan.py` | golden model: skor, checksum, pemeriksaan, lokalisasi |
| `model/padan_bounds.py` | analisis batas nilai (bagian 2) |
| `model/padan_data.py` | data sintetis, INT8 vs float, FAR/FRR (bagian 3) |
| `model/padan_faults.py` | simulasi fault dan contoh fault ganda (bagian 4–5) |
| `model/padan_report.py` | pembangun dokumen ini |

Setiap file punya `--self-test`, dijalankan oleh `make test-model`.

## 2. Batas nilai: semua perhitungan muat 32 bit

Analisis interval atas seluruh rentang INT8 [-128, 127] (bukan hanya rentang
kuantisasi [-127, 127]), D = 128, N = 16, bobot total
sum(j+1) = 136. Setiap suku punya batas bawah <= 0 <= batas atas,
jadi isi akumulator di tengah penjumlahan tidak pernah melewati batas jumlah
totalnya. Baris d1, d2 memakai selisih interval (konservatif). Tanpa fault,
nilainya tepat 0. Sumber: `model/padan_bounds.py`.

| Besaran | Asal | Min (model) | Maks (model) | Bit bertanda (model) | Muat 32 bit (model) |
|---|---|---|---|---|---|
| `T[j,i], p[i]` | INT8 | -128 | 127 | 8 | ya |
| `T[j,i] * p[i]` | produk | -16.256 | 16.384 | 16 | ya |
| `s_j (dan isi akumulatornya)` | 128 produk | -2.080.768 | 2.097.152 | 23 | ya |
| `C_i` | 16 elemen T | -2.048 | 2.032 | 12 | ya |
| `Cw_i` | bobot 1..16, total 136 | -17.408 | 17.272 | 16 | ya |
| `C_i * p_i` |  | -260.096 | 262.144 | 20 | ya |
| `C . p (dan isi akumulatornya)` | 128 suku | -33.292.288 | 33.554.432 | 27 | ya |
| `Cw_i * p_i` |  | -2.210.816 | 2.228.224 | 23 | ya |
| `Cw . p (dan isi akumulatornya)` | 128 suku | -282.984.448 | 285.212.672 | 30 | ya |
| `(j+1) * s_j` |  | -33.292.288 | 33.554.432 | 27 | ya |
| `sum_j s_j (dan isi akumulatornya)` | 16 skor | -33.292.288 | 33.554.432 | 27 | ya |
| `sum_j (j+1) s_j (dan isi akumulatornya)` | bobot total 136 | -282.984.448 | 285.212.672 | 30 | ya |
| `d1 = sum s - C.p (konservatif)` | selisih interval | -66.846.720 | 66.846.720 | 27 | ya |
| `d2 = sum (j+1)s - Cw.p (konservatif)` | selisih interval | -568.197.120 | 568.197.120 | 31 | ya |

- **Semua besaran muat 32 bit bertanda.** [Pasti] Yang terbesar tanpa fault
  adalah `Cw . p` dan `sum (j+1) s_j`, yaitu 285.212.672 (model), 30 bit. Sisa ruang
  terhadap 2^31 - 1 = 2.147.483.647 adalah 7,53x (model).
  Batas konservatif untuk d2 adalah 568.197.120 (model) (31 bit). Bahkan selisih
  interval yang paling pesimistis tetap muat.
- **Batas ini ketat.** [Pasti] `self_test()` mencapai ekstremnya dengan golden
  model: T = -128 semua, p = -128 semua memberi `Cw . p` = `sum (j+1) s_j` =
  285.212.672 (model).
- **Baris checksum tidak muat INT8.** [Pasti] C butuh 12 bit dan Cw butuh 16 bit
  bertanda. Perkalian `Cw_i * p_i` adalah 16x8 bit, bukan 8x8. Jalur checksum
  di RTL perlu pengali dan penyimpanan yang lebih lebar daripada jalur template.
- Ruang sisa untuk memperbesar desain dengan akumulator 32 bit:

| Batas | Tanpa d1, d2 (model) | Dengan d1, d2 konservatif (model) |
|---|---|---|
| D maksimum untuk N = 16 | 963 | 483 |
| N maksimum untuk D = 128 | 44 | 31 |

## 3. Data sintetis: keputusan INT8 vs kemiripan kosinus float

Identitas berkelompok: tiap identitas punya pusat acak c (vektor satuan
128 dimensi). Sampel = normalize(c + σ·u), dengan u vektor satuan acak dan σ
per sampel. Template = normalize(rata-rata sampel enrolment). Float menerima
jika cos ≥ τ. INT8 mengkuantisasi q = clip(round(x·SCALE), −127, 127) dengan
SCALE global, lalu menerima jika s = q_T·q_p ≥ τ_int = round(τ·SCALE²). Sumber:
`model/padan_data.py`.

| Parameter | Nilai (model) |
|---|---|
| Identitas terdaftar (= N template) | 16 |
| Sampel enrolment per template (dirata-rata) | 4 |
| σ intra-kelas per sampel | U(0,6, 2,0) |
| Probe per identitas terdaftar | 200 |
| Identitas tak terdaftar × probe | 64 × 50 |
| Pasangan genuine / impostor | 3.200 / 99.200 |
| SCALE kuantisasi | 127 / (4,0/√D) = 359,21 |
| Seed | 2026 |

| Statistik | Nilai (model) |
|---|---|
| cos genuine: rata-rata / persentil 5 | 0,516 / 0,329 |
| cos impostor: rata-rata / persentil 99,9 | 0,003 / 0,269 |
| Galat kuantisasi abs(s/SCALE² − cos): maks / RMS | 0,0156 / 0,0011 |
| Elemen terpotong (clip) oleh kuantisasi | 0,0047% |
| abs(s) maksimum pada data ini | 105.145 (batas: 2.097.152) |

[model] Tabel keputusan per τ (semua angka: model):

| τ | τ_int (model) | FAR float (model) | FAR INT8 (model) | FRR float (model) | FRR INT8 (model) | Kesepakatan (model) | Pasangan beda (model) | maks abs(cos − τ) beda (model) |
|---|---|---|---|---|---|---|---|---|
| 0,15 | 19.355 | 4,948% | 4,949% | 0,00% | 0,00% | 99,882% | 121 | 0,0029 |
| 0,20 | 25.806 | 1,268% | 1,270% | 0,09% | 0,09% | 99,959% | 42 | 0,0021 |
| 0,25 | 32.258 | 0,225% | 0,224% | 0,53% | 0,53% | 99,995% | 5 | 0,0011 |
| 0,30 | 38.710 | 0,022% | 0,023% | 2,62% | 2,66% | 99,998% | 2 | 0,0008 |
| 0,35 | 45.161 | 0,001% | 0,001% | 7,66% | 7,69% | 99,995% | 5 | 0,0014 |
| 0,40 | 51.613 | 0,000% | 0,000% | 17,16% | 17,16% | 99,994% | 6 | 0,0015 |
| 0,50 | 64.516 | 0,000% | 0,000% | 46,06% | 46,12% | 99,992% | 8 | 0,0047 |

- **Kesepakatan INT8 vs float ≥ 99,882% (model) untuk semua τ yang diuji.**
  [Pasti, untuk data ini] Semua pasangan yang keputusannya berbeda berada dalam
  0,0047 (model) dari τ. Perbedaannya murni pembulatan di sekitar ambang.
- FAR = 0 berarti 0 dari 99.200 pasangan impostor (model). Batas atas 95%
  (aturan tiga) ≈ 3/99.200 = 0,0030% (model). Resolusi FRR adalah
  1/3.200 (model).
- **FAR/FRR absolut tidak bermakna untuk wajah atau biometrik nyata.** [Pasti]
  Nilainya ditentukan oleh σ dan jumlah identitas sintetis yang dipilih di sini.
  Yang bermakna adalah selisih INT8 terhadap float pada data yang sama.
- SCALE global tetap (bukan per vektor) dipakai agar s sebanding dengan cos
  untuk semua template. [Kemungkinan Besar] Skala per vektor membuat τ_int
  berbeda per template.

## 4. Simulasi fault tunggal: cakupan deteksi dan lokalisasi

Bit flip tunggal disuntikkan secara exhaustive untuk 64 probe (model):
32 dari identitas terdaftar (2 per identitas) dan 32 dari
identitas tak terdaftar. Galeri yang dipakai adalah galeri INT8 dari bagian 3.
"Keputusan berubah" diukur pada τ = 0,30 (τ_int = 38.710 (model)).
Sumber: `model/padan_faults.py`.

- **Pemeriksa 32 bit:** d1, d2 dihitung dalam register 32 bit (wrap), sesuai
  bagian 2.
- **Pemeriksa 40 bit:** lebar yang cukup agar d1, d2 eksak untuk nilai register
  32 bit apa pun: abs(d2) ≤ 136·2³¹ + 2²⁹ < 2³⁹.
- **Cek rentang:** skor di luar [-2.080.768, 2.097.152] (model) pasti salah, dan
  indeksnya langsung diketahui.
- **Lokalisasi benar** untuk fault di akumulator checksum berarti tidak ada
  skor yang disalahkan (fault ada di jalur pemeriksa).
- **Persentase** dihitung terhadap fault efektif, yaitu yang mengubah skor atau
  nilai checksum.

[model] Cakupan per lokasi fault (semua angka: model):

| Lokasi fault | Disuntik (model) | Tanpa efek (model) | Efektif (model) | Terdeteksi (model) | Lokalisasi benar, 32 bit (model) | Salah tunjuk, 32 bit (model) | Tak terlokalisasi, 32 bit (model) | Lokalisasi benar, 40 bit (model) | Lokalisasi benar, 32 bit + cek rentang (model) | Keputusan berubah (model) | Keputusan berubah & tak terdeteksi (model) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Skor s_k (N × 32 bit) | 32.768 | 0 | 32.768 | 100,00% | 90,02% | 2,94% | 7,04% | 100,00% | 100,00% | 25,64% | 0 |
| Akumulator s_k, langkah 0..D−2 (N × 127 × 32) | 4.161.536 | 0 | 4.161.536 | 100,00% | 90,05% | 2,93% | 7,03% | 100,00% | 100,00% | 25,37% | 0 |
| Akumulator C·p dan Cw·p (2 × 127 × 32) | 520.192 | 0 | 520.192 | 100,00% | 100,00% | 0,00% | 0,00% | — | — | 0,00% | 0 |
| Bit template T[j,i] (N × D × 8) | 1.048.576 | 13.952 | 1.034.624 | 100,00% | 100,00% | 0,00% | 0,00% | 100,00% | 100,00% | 0,02% | 0 |

[model] Fault skor per posisi bit, pemeriksa 32 bit (bit berurutan dengan hasil sama digabung):

| Bit | Benar, 32 bit (model) | Salah tunjuk, 32 bit (model) | Tak terlokalisasi, 32 bit (model) | Benar, 40 bit (model) | Benar, 32 bit + cek rentang (model) |
|---|---|---|---|---|---|
| 0–26 | 100,0% | 0,0% | 0,0% | 100,0% | 100,0% |
| 27 | 96,9% | 0,0% | 3,1% | 100,0% | 100,0% |
| 28 | 46,7% | 0,0% | 53,3% | 100,0% | 100,0% |
| 29 | 21,3% | 22,4% | 56,3% | 100,0% | 100,0% |
| 30 | 9,5% | 28,0% | 62,5% | 100,0% | 100,0% |
| 31 | 6,2% | 43,8% | 50,0% | 100,0% | 100,0% |

- **Deteksi 100% (model) untuk semua bit flip tunggal yang efektif.** [Pasti]
  Galat E pada satu skor memberi d1 = E mod 2³², dan 0 < abs(E) < 2³². Galat bit
  template memberi E = ΔT·p_i dengan abs(E) ≤ 16.384 (model).
- **Fault template tanpa efek = p_i = 0:** 13.952 (model). Skornya
  tidak berubah untuk probe ini, jadi tidak ada yang perlu dideteksi. Fault itu
  tetap laten di template (lihat contoh D).
- **Lokalisasi 32 bit gagal hanya untuk bit 27–31.** [Pasti]
  - Untuk E = ±2^b, (k+1)·E melewati 32 bit, jadi rasio d2/d1 rusak.
  - Untuk skor: benar 90,02%, salah tunjuk
    2,94%, tak terlokalisasi 7,04%
    (model).
  - **Salah tunjuk paling berbahaya.** Koreksi ke indeks itu merusak skor yang
    benar dan membiarkan skor yang salah.
- **Pemeriksa 40 bit atau cek rentang memberi lokalisasi 100% (model)** untuk fault
  skor dan akumulator skor.
  - Cek rentang lebih murah: membandingkan tiap s_k dengan dua konstanta.
  - Cek rentang menangkap semua flip bit ≥ 22, karena tanpa fault abs(s) ≤ 2²¹ (model).
- **Fault akumulator C·p / Cw·p tidak pernah menyalahkan skor (model).** [Pasti]
  Salah satu dari d1, d2 = 0, jadi rasio bukan indeks 1..N.

## 5. Fault ganda dan keterbatasan

Contoh diambil dari data bagian 3 (τ = 0,30, τ_int = 38.710 (model)).
Sumber: `demos()` di `model/padan_faults.py`.

**Mengapa dua galat skor tidak bisa saling meniadakan secara eksak.** [Pasti]
Galat e_a, e_b pada skor a ≠ b memberi d1 = e_a + e_b dan
d2 = (a+1)e_a + (b+1)e_b. Determinan [[1, 1], [a+1, b+1]] = b − a ≠ 0, jadi
d1 = d2 = 0 hanya jika e_a = e_b = 0. Pembatalan butuh wrap modulo 2³², tiga
fault atau lebih, atau fault di luar skor.

**A. Dua fault yang saling meniadakan (pemeriksa 32 bit).** Probe #3200
berasal dari identitas tak terdaftar. Bit 31 dibalik pada s_0 dan
s_2; (a+1)+(b+1) genap.
- Skor berubah dari -185 dan -24.222 (model) menjadi
  2.147.483.463 dan 2.147.459.426 (model).
- Pemeriksa 32 bit: (d1, d2) = (0, 0) (model), jadi **tidak terdeteksi**.
- Akibatnya kedua impostor **diterima**
  (sebelumnya ditolak) (model): ini false accept
  yang lolos ABFT.
- Pemeriksa 40 bit menangkapnya: (d1, d2) = (4.294.967.296, 8.589.934.592) (model).
- Cek rentang juga menangkapnya: kedua skor di luar
  [-2.080.768, 2.097.152] (model).

[Pasti] Dengan cek rentang, pembatalan modulo 2³² oleh dua fault skor tidak
mungkin. Kedua skor harus dalam rentang, jadi abs(galat) ≤ 4.177.920 (model)
dan abs(d2) ≤ 31·4.177.920 < 2³¹ (model). Karena d1, d2 tidak bisa wrap,
argumen determinan di atas berlaku.

**B. Salah lokalisasi oleh dua fault.** Probe #0: bit 13
dibalik pada s_0 dan s_2 (keduanya +2^13).
- (d1, d2) = (16.384, 32.768) (model), rasio = 2, sehingga
  lokalisasi menunjuk **s_1**, padahal s_1 benar.
- "Koreksi" s_1 −= d1 mengubah (s_0, s_1, s_2) dari (64.525, 1.564, 12.751) (model)
  menjadi (64.525, -14.820, 12.751) (model).
- Nilai benarnya (56.333, 1.564, 4.559) (model), jadi ketiganya salah setelah
  koreksi.
- Pemeriksa tetap mendeteksi galat. Yang tidak andal untuk fault ganda adalah
  **koreksi otomatis**.

**C. Galat +e dan −e.** Probe #7: bit 12 dibalik pada s_3
dan s_8, dengan galat (4.096, -4.096) (model).
- d1 = 0, jadi checksum C saja **buta** terhadap pasangan ini.
- d2 = -20.480 (model) menangkapnya, tetapi rasio tidak terdefinisi
  (tak terlokalisasi). Inilah alasan Cw diperlukan selain C.

**D. Dua bit template yang saling meniadakan untuk satu probe.**
- Baris 5, kolom 8 dan 79, bit 2:
  +2^2 dan −2^2, dengan p sama = -22 di kedua kolom.
- Untuk probe #1: (d1, d2) = (0, 0) (model), dan skor
  tidak berubah (model). Hasil probe ini benar, tetapi template sudah rusak.
- Fault ini terdeteksi pada 99,03% dari
  6.400 probe (model).
- [Kemungkinan Besar] Pemeriksaan berkala template terhadap C dan Cw saat idle
  akan menangkap fault laten seperti ini tanpa bergantung pada probe.

**E. Keterbatasan fault tunggal: probe p tidak terlindungi.** [Pasti]
- p dipakai oleh jalur skor dan jalur checksum, jadi fault pada p konsisten di
  keduanya dan d1 = d2 = 0.
- Simulasi: 65.536 flip bit p_i (probe bagian 4 × D × 8) (model), semuanya
  tidak terdeteksi: 65.536 (model).
- 229 (model) di antaranya mengubah minimal satu keputusan.
- Probe perlu proteksi terpisah, misalnya paritas/CRC saat diterima dan register
  yang dibaca sekali untuk kedua jalur.

## 6. Implikasi untuk RTL

- **Akumulator skor 32 bit sudah cukup.** [Pasti] Kebutuhannya 23 bit (model), dan
  semua pemeriksaan tanpa fault muat 32 bit (bagian 2).
- **Jalur checksum lebih lebar dari INT8:** Cw 16 bit, C 12 bit (model). [Pasti]
- **Pemeriksa 32 bit perlu cek rentang skor, atau d1/d2 diperlebar ke 40 bit.**
  Tanpa salah satunya, lokalisasi salah tunjuk untuk flip bit tinggi dan dua
  flip bit 31 bisa lolos (bagian 4–5). [Pasti]
- **Lokalisasi cukup untuk pelaporan atau komputasi ulang**, tidak untuk
  koreksi otomatis jika fault ganda mungkin terjadi (contoh B). [Pasti]
- **Probe p dan template laten butuh proteksi di luar ABFT** (contoh D, E). [Pasti]
- Lokalisasi tidak harus memakai pembagi: bandingkan d2 dengan (k+1)·d1 untuk
  k = 0..N−1 (penjumlahan berulang). [Kemungkinan Besar]
