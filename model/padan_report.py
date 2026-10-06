"""Bangun docs/padan_model.md dari model PADAN.

    python3 model/padan_report.py --write docs/padan_model.md
    python3 model/padan_report.py --check docs/padan_model.md   # gagal jika berbeda

Semua angka di dokumen dihasilkan di sini dari padan*.py (deterministik, seed
tetap), jadi dokumen tidak diedit tangan.
"""

import sys

import padan as P
import padan_bounds as PB
import padan_data as PD
import padan_faults as PF

M = "(model)"


def fi(n):
    """Integer gaya Indonesia: 32.768, -2.080.768."""
    return f"{int(n):,}".replace(",", ".")


def fp(x, digits=2):
    """Persen gaya Indonesia: 99,88%."""
    return f"{100 * x:.{digits}f}%".replace(".", ",")


def ff(x, digits=4):
    return f"{x:.{digits}f}".replace(".", ",")


def lst(xs):
    return ", ".join(fi(x) for x in xs)


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def section_bounds():
    rows = []
    for name, why, iv in PB.intervals():
        b = PB.bits_signed(iv)
        rows.append((f"`{name}`", why, fi(iv[0]), fi(iv[1]), b, "ya" if b <= 32 else "**TIDAK**"))
    big = dict((n, iv) for n, _, iv in PB.intervals())
    cwp = big["Cw . p (dan isi akumulatornya)"][1]
    d2 = big["d2 = sum (j+1)s - Cw.p (konservatif)"][1]
    t = table(["Besaran", "Asal", f"Min {M}", f"Maks {M}", f"Bit bertanda {M}", f"Muat 32 bit {M}"], rows)
    lim = table(["Batas", f"Tanpa d1, d2 {M}", f"Dengan d1, d2 konservatif {M}"], [
        (f"D maksimum untuk N = {P.N}", fi(PB.max_D(P.N, False)), fi(PB.max_D(P.N))),
        (f"N maksimum untuk D = {P.D}", fi(PB.max_N(P.D, False)), fi(PB.max_N(P.D))),
    ])
    return f"""## 2. Batas nilai: semua perhitungan muat 32 bit

Analisis interval atas seluruh rentang INT8 [-128, 127] (bukan hanya rentang
kuantisasi [-127, 127]), D = {P.D}, N = {P.N}, bobot total
sum(j+1) = {P.N * (P.N + 1) // 2}. Setiap suku punya batas bawah <= 0 <= batas atas,
jadi isi akumulator di tengah penjumlahan tidak pernah melewati batas jumlah
totalnya. Baris d1, d2 memakai selisih interval (konservatif). Tanpa fault,
nilainya tepat 0. Sumber: `model/padan_bounds.py`.

{t}

- **Semua besaran muat 32 bit bertanda.** [Pasti] Yang terbesar tanpa fault
  adalah `Cw . p` dan `sum (j+1) s_j`, yaitu {fi(cwp)} {M}, 30 bit. Sisa ruang
  terhadap 2^31 - 1 = {fi(2**31 - 1)} adalah {ff((2**31 - 1) / cwp, 2)}x {M}.
  Batas konservatif untuk d2 adalah {fi(d2)} {M} (31 bit). Bahkan selisih
  interval yang paling pesimistis tetap muat.
- **Batas ini ketat.** [Pasti] `self_test()` mencapai ekstremnya dengan golden
  model: T = -128 semua, p = -128 semua memberi `Cw . p` = `sum (j+1) s_j` =
  {fi(cwp)} {M}.
- **Baris checksum tidak muat INT8.** [Pasti] C butuh 12 bit dan Cw butuh 16 bit
  bertanda. Perkalian `Cw_i * p_i` adalah 16x8 bit, bukan 8x8. Jalur checksum
  di RTL perlu pengali dan penyimpanan yang lebih lebar daripada jalur template.
- Ruang sisa untuk memperbesar desain dengan akumulator 32 bit:

{lim}
"""


def section_data():
    ds = PD.make_dataset()
    sm = PD.summary(ds)
    rows = []
    for r in PD.evaluate(ds):
        rows.append((ff(r["tau"], 2), fi(r["tau_int"]), fp(r["far_float"], 3), fp(r["far_int8"], 3),
                     fp(r["frr_float"], 2), fp(r["frr_int8"], 2), fp(r["agree"], 3),
                     fi(r["disagree"]), ff(r["max_gap"])))
    t = table(["τ", f"τ_int {M}", f"FAR float {M}", f"FAR INT8 {M}", f"FRR float {M}",
               f"FRR INT8 {M}", f"Kesepakatan {M}", f"Pasangan beda {M}", f"maks abs(cos − τ) beda {M}"], rows)
    params = table(["Parameter", f"Nilai {M}"], [
        ("Identitas terdaftar (= N template)", P.N),
        ("Sampel enrolment per template (dirata-rata)", PD.ENROLL),
        ("σ intra-kelas per sampel", f"U({ff(PD.SIGMA_LO, 1)}, {ff(PD.SIGMA_HI, 1)})"),
        ("Probe per identitas terdaftar", PD.PROBES_PER_ID),
        ("Identitas tak terdaftar × probe", f"{PD.UNKNOWN} × {PD.PROBES_PER_UNKNOWN}"),
        ("Pasangan genuine / impostor", f"{fi(sm['genuine_pairs'])} / {fi(sm['impostor_pairs'])}"),
        ("SCALE kuantisasi", f"127 / ({ff(PD.CLIP_RMS, 1)}/√D) = {ff(PD.SCALE, 2)}"),
        ("Seed", PD.SEED),
    ])
    stats = table(["Statistik", f"Nilai {M}"], [
        ("cos genuine: rata-rata / persentil 5", f"{ff(sm['cos_gen_mean'], 3)} / {ff(sm['cos_gen_p05'], 3)}"),
        ("cos impostor: rata-rata / persentil 99,9", f"{ff(sm['cos_imp_mean'], 3)} / {ff(sm['cos_imp_p99'], 3)}"),
        ("Galat kuantisasi abs(s/SCALE² − cos): maks / RMS", f"{ff(sm['q_err_max'])} / {ff(sm['q_err_rms'])}"),
        ("Elemen terpotong (clip) oleh kuantisasi", fp(sm["clipped"], 4)),
        ("abs(s) maksimum pada data ini", f"{fi(sm['s_absmax'])} (batas: {fi(PF.S_HI)})"),
    ])
    n_imp = sm["impostor_pairs"]
    rows_eval = PD.evaluate(ds)
    worst = min(r["agree"] for r in rows_eval)
    gap = max(r["max_gap"] for r in rows_eval)
    return f"""## 3. Data sintetis: keputusan INT8 vs kemiripan kosinus float

Identitas berkelompok: tiap identitas punya pusat acak c (vektor satuan
{P.D} dimensi). Sampel = normalize(c + σ·u), dengan u vektor satuan acak dan σ
per sampel. Template = normalize(rata-rata sampel enrolment). Float menerima
jika cos ≥ τ. INT8 mengkuantisasi q = clip(round(x·SCALE), −127, 127) dengan
SCALE global, lalu menerima jika s = q_T·q_p ≥ τ_int = round(τ·SCALE²). Sumber:
`model/padan_data.py`.

{params}

{stats}

[model] Tabel keputusan per τ (semua angka: model):

{t}

- **Kesepakatan INT8 vs float ≥ {fp(worst, 3)} {M} untuk semua τ yang diuji.**
  [Pasti, untuk data ini] Semua pasangan yang keputusannya berbeda berada dalam
  {ff(gap)} {M} dari τ. Perbedaannya murni pembulatan di sekitar ambang.
- FAR = 0 berarti 0 dari {fi(n_imp)} pasangan impostor {M}. Batas atas 95%
  (aturan tiga) ≈ 3/{fi(n_imp)} = {fp(3 / n_imp, 4)} {M}. Resolusi FRR adalah
  1/{fi(sm['genuine_pairs'])} {M}.
- **FAR/FRR absolut tidak bermakna untuk wajah atau biometrik nyata.** [Pasti]
  Nilainya ditentukan oleh σ dan jumlah identitas sintetis yang dipilih di sini.
  Yang bermakna adalah selisih INT8 terhadap float pada data yang sama.
- SCALE global tetap (bukan per vektor) dipakai agar s sebanding dengan cos
  untuk semua template. [Kemungkinan Besar] Skala per vektor membuat τ_int
  berbeda per template.
"""


def merge_bits(per_bit):
    """Gabungkan bit berurutan dengan hasil identik: [(b0, b1, row)]."""
    out = []
    for b, row in enumerate(per_bit.tolist()):
        if out and out[-1][2] == row:
            out[-1][1] = b
        else:
            out.append([b, b, row])
    return out


def section_faults():
    r = PF.run()
    c = r["cats"]
    n_pr = r["probes"]

    def row(name, k, ok_label=None):
        x = c[k]
        eff = x["eff"]
        return (name, fi(x["n"]), fi(x["n"] - eff), fi(eff), fp(x["det32"] / eff), fp(x["ok32"] / eff),
                fp(x["mis32"] / eff), fp(x["unloc32"] / eff),
                fp(x["ok40"] / eff) if "ok40" in x else "—",
                fp(x["okrng"] / eff) if "okrng" in x else "—",
                fp(x["dec"] / eff), fi(x["dec_silent"]))

    t = table(["Lokasi fault", f"Disuntik {M}", f"Tanpa efek {M}", f"Efektif {M}", f"Terdeteksi {M}",
               f"Lokalisasi benar, 32 bit {M}", f"Salah tunjuk, 32 bit {M}", f"Tak terlokalisasi, 32 bit {M}",
               f"Lokalisasi benar, 40 bit {M}", f"Lokalisasi benar, 32 bit + cek rentang {M}",
               f"Keputusan berubah {M}", f"Keputusan berubah & tak terdeteksi {M}"], [
        row("Skor s_k (N × 32 bit)", "score"),
        row(f"Akumulator s_k, langkah 0..D−2 (N × {P.D - 1} × 32)", "acc"),
        row(f"Akumulator C·p dan Cw·p (2 × {P.D - 1} × 32)", "chk"),
        row("Bit template T[j,i] (N × D × 8)", "tmpl"),
    ])
    bits = []
    for b0, b1, (ok, mis, unloc, ok40, okr) in merge_bits(r["per_bit"]):
        n = n_pr * P.N                      # per bit; baris gabungan punya nilai identik
        bits.append((f"{b0}" if b0 == b1 else f"{b0}–{b1}", fp(ok / n, 1), fp(mis / n, 1),
                     fp(unloc / n, 1), fp(ok40 / n, 1), fp(okr / n, 1)))
    tb = table(["Bit", f"Benar, 32 bit {M}", f"Salah tunjuk, 32 bit {M}", f"Tak terlokalisasi, 32 bit {M}",
                f"Benar, 40 bit {M}", f"Benar, 32 bit + cek rentang {M}"], bits)
    s = c["score"]
    tm = c["tmpl"]
    return f"""## 4. Simulasi fault tunggal: cakupan deteksi dan lokalisasi

Bit flip tunggal disuntikkan secara exhaustive untuk {n_pr} probe {M}:
{n_pr // 2} dari identitas terdaftar (2 per identitas) dan {n_pr // 2} dari
identitas tak terdaftar. Galeri yang dipakai adalah galeri INT8 dari bagian 3.
"Keputusan berubah" diukur pada τ = {ff(r['tau'], 2)} (τ_int = {fi(PD.tau_int(r['tau']))} {M}).
Sumber: `model/padan_faults.py`.

- **Pemeriksa 32 bit:** d1, d2 dihitung dalam register 32 bit (wrap), sesuai
  bagian 2.
- **Pemeriksa 40 bit:** lebar yang cukup agar d1, d2 eksak untuk nilai register
  32 bit apa pun: abs(d2) ≤ 136·2³¹ + 2²⁹ < 2³⁹.
- **Cek rentang:** skor di luar [{fi(PF.S_LO)}, {fi(PF.S_HI)}] {M} pasti salah, dan
  indeksnya langsung diketahui.
- **Lokalisasi benar** untuk fault di akumulator checksum berarti tidak ada
  skor yang disalahkan (fault ada di jalur pemeriksa).
- **Persentase** dihitung terhadap fault efektif, yaitu yang mengubah skor atau
  nilai checksum.

[model] Cakupan per lokasi fault (semua angka: model):

{t}

[model] Fault skor per posisi bit, pemeriksa 32 bit (bit berurutan dengan hasil sama digabung):

{tb}

- **Deteksi 100% {M} untuk semua bit flip tunggal yang efektif.** [Pasti]
  Galat E pada satu skor memberi d1 = E mod 2³², dan 0 < abs(E) < 2³². Galat bit
  template memberi E = ΔT·p_i dengan abs(E) ≤ 16.384 {M}.
- **Fault template tanpa efek = p_i = 0:** {fi(tm['n'] - tm['eff'])} {M}. Skornya
  tidak berubah untuk probe ini, jadi tidak ada yang perlu dideteksi. Fault itu
  tetap laten di template (lihat contoh D).
- **Lokalisasi 32 bit gagal hanya untuk bit 27–31.** [Pasti]
  - Untuk E = ±2^b, (k+1)·E melewati 32 bit, jadi rasio d2/d1 rusak.
  - Untuk skor: benar {fp(s['ok32'] / s['eff'])}, salah tunjuk
    {fp(s['mis32'] / s['eff'])}, tak terlokalisasi {fp(s['unloc32'] / s['eff'])}
    {M}.
  - **Salah tunjuk paling berbahaya.** Koreksi ke indeks itu merusak skor yang
    benar dan membiarkan skor yang salah.
- **Pemeriksa 40 bit atau cek rentang memberi lokalisasi 100% {M}** untuk fault
  skor dan akumulator skor.
  - Cek rentang lebih murah: membandingkan tiap s_k dengan dua konstanta.
  - Cek rentang menangkap semua flip bit ≥ 22, karena tanpa fault abs(s) ≤ 2²¹ {M}.
- **Fault akumulator C·p / Cw·p tidak pernah menyalahkan skor {M}.** [Pasti]
  Salah satu dari d1, d2 = 0, jadi rasio bukan indeks 1..N.
"""


def section_demos():
    d = PF.demos()
    ti = d["tau_int"]
    A, B, C, Dd, E = d["A"], d["B"], d["C"], d["D"], d["E"]
    return f"""## 5. Fault ganda dan keterbatasan

Contoh diambil dari data bagian 3 (τ = {ff(d['tau'], 2)}, τ_int = {fi(ti)} {M}).
Sumber: `demos()` di `model/padan_faults.py`.

**Mengapa dua galat skor tidak bisa saling meniadakan secara eksak.** [Pasti]
Galat e_a, e_b pada skor a ≠ b memberi d1 = e_a + e_b dan
d2 = (a+1)e_a + (b+1)e_b. Determinan [[1, 1], [a+1, b+1]] = b − a ≠ 0, jadi
d1 = d2 = 0 hanya jika e_a = e_b = 0. Pembatalan butuh wrap modulo 2³², tiga
fault atau lebih, atau fault di luar skor.

**A. Dua fault yang saling meniadakan (pemeriksa 32 bit).** Probe #{A['probe']}
berasal dari identitas tak terdaftar. Bit 31 dibalik pada s_{A['a']} dan
s_{A['b']}; (a+1)+(b+1) genap.
- Skor berubah dari {fi(A['s'][0])} dan {fi(A['s'][1])} {M} menjadi
  {fi(A['s_fault'][0])} dan {fi(A['s_fault'][1])} {M}.
- Pemeriksa 32 bit: (d1, d2) = {A['d32']} {M}, jadi **tidak terdeteksi**.
- Akibatnya kedua impostor **{'diterima' if all(A['accept_after']) else 'tidak semua diterima'}**
  ({'sebelumnya ditolak' if not A['accept_before'] else 'sebelumnya sudah diterima'}) {M}: ini false accept
  yang lolos ABFT.
- Pemeriksa 40 bit menangkapnya: (d1, d2) = ({fi(A['d40'][0])}, {fi(A['d40'][1])}) {M}.
- Cek rentang juga menangkapnya: {'kedua skor' if all(A['out_of_range']) else 'TIDAK semua skor'} di luar
  [{fi(PF.S_LO)}, {fi(PF.S_HI)}] {M}.

[Pasti] Dengan cek rentang, pembatalan modulo 2³² oleh dua fault skor tidak
mungkin. Kedua skor harus dalam rentang, jadi abs(galat) ≤ {fi(PF.S_HI - PF.S_LO)} {M}
dan abs(d2) ≤ 31·{fi(PF.S_HI - PF.S_LO)} < 2³¹ {M}. Karena d1, d2 tidak bisa wrap,
argumen determinan di atas berlaku.

**B. Salah lokalisasi oleh dua fault.** Probe #{B['probe']}: bit {B['bit']}
dibalik pada s_0 dan s_2 (keduanya +2^{B['bit']}).
- (d1, d2) = ({fi(B['d'][0])}, {fi(B['d'][1])}) {M}, rasio = 2, sehingga
  lokalisasi menunjuk **s_{B['loc']}**, padahal s_1 benar.
- "Koreksi" s_1 −= d1 mengubah (s_0, s_1, s_2) dari ({lst(B['s_fault'])}) {M}
  menjadi ({lst(B['s_fixed'])}) {M}.
- Nilai benarnya ({lst(B['s'])}) {M}, jadi ketiganya salah setelah
  koreksi.
- Pemeriksa tetap mendeteksi galat. Yang tidak andal untuk fault ganda adalah
  **koreksi otomatis**.

**C. Galat +e dan −e.** Probe #{C['probe']}: bit {C['bit']} dibalik pada s_{C['a']}
dan s_{C['b']}, dengan galat ({lst(C['E'])}) {M}.
- d1 = {fi(C['d'][0])}, jadi checksum C saja **buta** terhadap pasangan ini.
- d2 = {fi(C['d'][1])} {M} menangkapnya, tetapi rasio tidak terdefinisi
  (tak terlokalisasi). Inilah alasan Cw diperlukan selain C.

**D. Dua bit template yang saling meniadakan untuk satu probe.**
- Baris {Dd['row']}, kolom {Dd['cols'][0]} dan {Dd['cols'][1]}, bit {Dd['bit']}:
  +2^{Dd['bit']} dan −2^{Dd['bit']}, dengan p sama = {Dd['p']} di kedua kolom.
- Untuk probe #{Dd['probe']}: (d1, d2) = {Dd['d_this']} {M}, dan skor
  {'berubah' if Dd['s_changed_this'] else 'tidak berubah'} {M}. Hasil probe ini benar, tetapi template sudah rusak.
- Fault ini terdeteksi pada {fp(Dd['frac_probes_detect'])} dari
  {fi(Dd['n_probes'])} probe {M}.
- [Kemungkinan Besar] Pemeriksaan berkala template terhadap C dan Cw saat idle
  akan menangkap fault laten seperti ini tanpa bergantung pada probe.

**E. Keterbatasan fault tunggal: probe p tidak terlindungi.** [Pasti]
- p dipakai oleh jalur skor dan jalur checksum, jadi fault pada p konsisten di
  keduanya dan d1 = d2 = 0.
- Simulasi: {fi(E['n'])} flip bit p_i (probe bagian 4 × D × 8) {M}, semuanya
  tidak terdeteksi: {fi(E['undetected'])} {M}.
- {fi(E['decision_changed'])} {M} di antaranya mengubah minimal satu keputusan.
- Probe perlu proteksi terpisah, misalnya paritas/CRC saat diterima dan register
  yang dibaca sekali untuk kedua jalur.
"""


def build():
    head = f"""# Model PADAN: skor INT8 dengan ABFT

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

`model/padan.py`, dengan D = {P.D}, N = {P.N}, T dan p INT8, akumulator {P.ACC_BITS} bit:

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
"""
    tail = """## 6. Implikasi untuk RTL

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
"""
    return "\n".join([head, section_bounds(), section_data(), section_faults(), section_demos(), tail])


def main(argv):
    text = build()
    if len(argv) == 3 and argv[1] == "--write":
        open(argv[2], "w").write(text)
    elif len(argv) == 3 and argv[1] == "--check":
        if open(argv[2]).read() != text:
            print(f"FAIL {argv[2]} tidak sama dengan keluaran model; jalankan "
                  f"python3 model/padan_report.py --write {argv[2]}")
            return 1
        print(f"PASS {argv[2]} sama dengan keluaran model")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
