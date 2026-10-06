# model/

Model referensi (Python/NumPy) yang dipakai testbench sebagai golden model.

| File | Isi |
|---|---|
| `tinytpu.py`, `iterative_mac.py`, `vector_cim.py` | model maksud desain baseline TT07 (lihat `docs/baseline_audit.md`) |
| `padan.py` | golden model integer PADAN: skor INT8, baris checksum C dan Cw, pemeriksaan ABFT, lokalisasi |
| `padan_bounds.py` | analisis batas nilai: semua perhitungan muat 32 bit untuk D = 128, N = 16 |
| `padan_data.py` | data sintetis identitas berkelompok, keputusan INT8 vs kosinus float, FAR/FRR |
| `padan_faults.py` | simulasi fault tunggal (skor, akumulator, bit template) dan contoh fault ganda |
| `padan_report.py` | membangun `docs/padan_model.md` dari model di atas |

Setiap model punya `--self-test` (`make test-model`). Hasil model PADAN ada di
[`docs/padan_model.md`](../docs/padan_model.md). Setelah mengubah model, jalankan
`python3 model/padan_report.py --write docs/padan_model.md`.
`make check-model-report` gagal jika dokumen tidak sinkron.
