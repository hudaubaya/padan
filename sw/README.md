# sw/

Perangkat lunak host: driver, skrip pengukuran, dan alat analisis.

| Berkas | Isi |
|---|---|
| `kv260/padan_test.py` | Uji PADAN di KV260 lewat `/dev/mem`: 46 kasus dari model (`docs/fpga_howto.md` bagian 7). |
| `kv260/gen_vectors.py`, `padan_vectors.json` | Vektor uji dari golden model. |
| `kv260/padan_cam.py` | Demo webcam: wajah, embedding SFace 128-D, INT8, PADAN. Galeri (nama + template INT8) disimpan di `padan_galeri.json` dengan izin 0600, lalu ditulis ulang ke PADAN setiap skrip mulai. |

**`padan_galeri.json` berisi data biometrik** (template wajah) dan tidak
dienkripsi. Berkas ini diabaikan git (`.gitignore`), dibuat dengan izin 0600,
dan dihapus dengan perintah `forget`. Pakai hanya wajah sukarelawan yang setuju
template-nya disimpan. `--no-gallery` mematikan penyimpanan ke disk.

`padan_cam.py --self-test` (bagian dari `make test-kv260-scripts`) tidak butuh
kamera, OpenCV, atau board. Yang diuji: kuantisasi sama dengan model, pengepakan
word, urutan register terhadap PADAN tiruan, perintah REPL, dan galeri (simpan
0600, sesi baru menulis ulang template, hapus slot, `forget`, berkas rusak
ditolak). Kamera, YuNet/SFace, dan akurasi pada wajah nyata belum diuji.
