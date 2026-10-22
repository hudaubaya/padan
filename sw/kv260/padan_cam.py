#!/usr/bin/env python3
"""Demo PADAN dengan webcam USB: wajah -> embedding SFace 128-D -> INT8 -> PADAN.

    python3 padan_cam.py --backend model        # laptop/PC, tanpa board (golden model)
    sudo python3 padan_cam.py                   # KV260, bitstream PADAN sudah dimuat
    python3 padan_cam.py --self-test            # tanpa kamera dan tanpa board

Alur per frame: kamera (OpenCV, V4L2) -> deteksi wajah YuNet -> potong dan
sejajarkan -> embedding SFace (128 float) -> normalisasi L2 -> kuantisasi INT8
dengan rumus model/padan_data.py -> tulis ke PADAN (ENROLL atau PROBE).

D = 128 di PADAN sama dengan panjang embedding SFace, jadi RTL tidak berubah.

Perintah interaktif:
    e <slot> <nama>   enroll: 4 frame berwajah, dirata-rata, ditulis ke slot 0-15
                      dan disimpan di galeri
    ls                daftar slot dan nama di galeri
    d <slot>          hapus satu slot (template nol di PADAN, dihapus dari galeri)
    forget            hapus semua: ENROLL_CLR dan berkas galeri
    v                 verifikasi sekali: MATCH (nama) / NO_MATCH / FAULT
    l [n]             verifikasi berulang n kali (default 10), jeda 1 detik
    c                 cek kuantisasi satu wajah (berapa nilai terpotong di +-127)
    g                 tampilkan status guard
    k <n>             GUARD_K = n (1-15) agar wajah asing tidak cepat mengunci
    lock              kunci tau dan enrollment (GUARD_TAU lalu GUARD_LOCK)
    q                 keluar

Galeri (bawaan: padan_galeri.json di folder skrip; --gallery FILE; --no-gallery
untuk mematikan): setiap enroll menyimpan nama dan template INT8 (128 nilai
hasil kuantisasi, bukan citra dan bukan embedding float). Saat skrip mulai,
galeri ditulis ulang ke PADAN, jadi wajah tetap dikenali setelah skrip, bitstream
(xmutil loadapp), atau board dimulai ulang. PADAN sendiri menghapus template
setiap reset atau tamper; galeri di host adalah satu-satunya salinan yang
bertahan.

Privasi: berkas galeri BERISI DATA BIOMETRIK (template wajah) dan TIDAK
dienkripsi. Berkas dibuat dengan izin 0600 (di bawah sudo: hanya root), dan izin
yang lebih longgar diperketat saat dibaca. Citra kamera tidak pernah disimpan.
Pakai wajah sukarelawan yang memberi persetujuan, termasuk untuk penyimpanan
template; hapus dengan `forget` atau dengan menghapus berkasnya.

Belum teruji dengan kamera atau model ONNX sungguhan (lihat --self-test untuk
yang sudah diuji). Ambang tau 0,363 adalah ambang kosinus SFace float dari
OpenCV; ambang INT8 perlu dikalibrasi ulang dengan wajah nyata.

Butuh: Python 3, NumPy, OpenCV >= 4.5.4 (python3-opencv), dan dua berkas model
OpenCV Zoo di folder skrip ini (atau --yunet/--sface):
    face_detection_yunet_2021dec.onnx
    face_recognition_sface_2021dec.onnx
Backend devmem memakai padan_test.py (folder yang sama). Backend model memakai
model/padan.py dari repo.
"""

import argparse
import json
import os
import pathlib
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import padan_test as PT        # noqa: E402  (DevMem, Padan, alamat register, status_ok)

D, N = 128, 16
ENROLL_FRAMES = 4              # sama dengan ENROLL di model/padan_data.py
CLIP_RMS = 4.0                 # model/padan_data.py
SCALE = 127 / (CLIP_RMS / np.sqrt(D))
TAU_COS = 0.363                # ambang kosinus SFace (OpenCV)
LOCK_MAGIC = 0x4C4F434B        # "LOCK", docs/rtl_decision.md
GALLERY_VERSION = 1
A_LOCK, A_K, A_TAU = 0x304, 0x305, 0x306
C_NO_MATCH, C_MATCH, C_FAULT = 0x5, 0xA, 0xF


# ----------------------------------------------------------- INT8 dan word ---

def quantize(v):
    """Sama dengan padan_data.quantize: q = clip(round(x * SCALE), -127, 127)."""
    return np.clip(np.rint(np.asarray(v, dtype=np.float64) * SCALE), -127, 127).astype(np.int64)


def tau_int(tau_cos):
    return int(round(tau_cos * SCALE * SCALE))


def normalize(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    n = np.linalg.norm(v)
    if v.size != D or n == 0:
        raise ValueError(f"embedding harus {D} nilai bukan nol, dapat {v.size}")
    return v / n


def words(q):
    """128 byte INT8 -> 32 word 32 bit, byte b di bit [8b+7:8b] (gen_vectors.words)."""
    b = [int(x) & 0xFF for x in q]
    return [b[i] | b[i + 1] << 8 | b[i + 2] << 16 | b[i + 3] << 24 for i in range(0, D, 4)]


def decode(s):
    """STATUS -> ('MATCH', idx) / ('NO_MATCH', None) / ('FAULT', None). Kode lain = FAULT."""
    code = s & 0xF
    if not PT.status_ok(s) or code not in (C_MATCH, C_NO_MATCH):
        return "FAULT", None
    return ("MATCH", (s >> 4) & 0xF) if code == C_MATCH else ("NO_MATCH", None)


# ------------------------------------------------------------------ kamera ---

class Embedder:
    """Webcam + YuNet + SFace. embed() -> (vektor 128 ternormalisasi, kotak wajah) atau None."""

    def __init__(self, cam, yunet, sface, width=640, height=480, score=0.9):
        try:
            import cv2
        except ImportError:
            raise SystemExit("OpenCV tidak ada: sudo apt install python3-opencv (Ubuntu) "
                             "atau pip install opencv-python")
        self.cv2 = cv2
        for f in (yunet, sface):
            if not pathlib.Path(f).is_file():
                raise SystemExit(f"berkas model tidak ada: {f} (unduh dari OpenCV Zoo sebelum acara)")
        api = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(cam, api)
        if not self.cap.isOpened():
            raise SystemExit(f"kamera {cam} tidak bisa dibuka (cek: ls /dev/video*, v4l2-ctl --list-devices)")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        for _ in range(10):                      # buang frame awal (auto-exposure)
            self.cap.read()
        ok, frame = self.cap.read()
        if not ok:
            raise SystemExit("kamera tidak memberi frame")
        h, w = frame.shape[:2]
        self.det = cv2.FaceDetectorYN.create(str(yunet), "", (w, h), score)
        self.rec = cv2.FaceRecognizerSF.create(str(sface), "")
        self.show = False
        self.last = frame

    def frame(self):
        ok, f = self.cap.read()
        if not ok:
            raise RuntimeError("gagal membaca frame kamera")
        self.last = f
        return f

    def embed(self, tries=30):
        cv2 = self.cv2
        for _ in range(tries):
            f = self.frame()
            self.det.setInputSize((f.shape[1], f.shape[0]))
            _, faces = self.det.detect(f)
            if faces is None or len(faces) == 0:
                self.preview(f, None, "tidak ada wajah")
                continue
            face = max(faces, key=lambda r: r[2] * r[3])          # wajah terbesar
            feat = self.rec.feature(self.rec.alignCrop(f, face))
            self.preview(f, face, "")
            return normalize(feat), face
        return None

    def preview(self, f, face, text):
        if not self.show:
            return
        cv2 = self.cv2
        img = f.copy()
        if face is not None:
            x, y, w, h = [int(v) for v in face[:4]]
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 200, 255), 2)
        if text:
            cv2.putText(img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        cv2.imshow("PADAN", img)
        cv2.waitKey(1)

    def close(self):
        self.cap.release()
        if self.show:
            self.cv2.destroyAllWindows()


# ----------------------------------------------------------------- galeri ---

class Gallery:
    """Galeri di disk: slot -> (nama, template INT8 128 nilai). JSON, izin 0600.

    path None = galeri mati (perilaku lama: tidak ada yang ditulis ke disk)."""

    def __init__(self, path):
        self.path = pathlib.Path(path) if path else None
        self.slots = {}

    def load(self, log=print):
        if self.path is None or not self.path.exists():
            return self
        mode = self.path.stat().st_mode & 0o777
        if mode & 0o077:
            log(f"peringatan: izin {self.path} {oct(mode)} terlalu longgar; diubah ke 0o600")
            os.chmod(self.path, 0o600)
        try:
            data = json.loads(self.path.read_text())
            if data.get("version") != GALLERY_VERSION or data.get("D") != D:
                raise ValueError(f"versi/D tidak dikenal: {data.get('version')}/{data.get('D')}")
            if abs(float(data.get("scale", 0)) - SCALE) > 1e-9:
                raise ValueError("SCALE kuantisasi berbeda; template lama tidak sebanding")
            slots = {}
            for k, v in data["slots"].items():
                s, q = int(k), v["q"]
                if not 0 <= s < N or not isinstance(v["name"], str):
                    raise ValueError(f"slot {k} tidak sah")
                if len(q) != D or any(not isinstance(x, int) or not -127 <= x <= 127 for x in q):
                    raise ValueError(f"template slot {k} bukan {D} bilangan bulat -127..127")
                slots[s] = (v["name"], np.array(q, dtype=np.int64))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"galeri {self.path} tidak sah: {e}; perbaiki atau hapus berkasnya")
        self.slots = slots
        return self

    def save(self):
        if self.path is None:
            return
        data = {"version": GALLERY_VERSION, "D": D, "scale": SCALE,
                "slots": {str(s): {"name": n, "q": [int(x) for x in q]}
                          for s, (n, q) in sorted(self.slots.items())}}
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o600)                     # O_CREAT tidak mengubah izin berkas lama
        os.replace(tmp, self.path)               # atomik: berkas tidak pernah setengah tertulis

    def set(self, slot, name, q):
        self.slots[slot] = (name, np.asarray(q, dtype=np.int64))
        self.save()

    def remove(self, slot):
        self.slots.pop(slot, None)
        self.save()

    def forget(self):
        self.slots.clear()
        if self.path is not None and self.path.exists():
            self.path.unlink()

    def names(self):
        return {s: n for s, (n, _) in self.slots.items()}


def restore(be, gal, log):
    """Tulis ulang galeri ke PADAN. Di LOCKD enroll ditolak; nama tetap dipakai."""
    if not gal.slots:
        return
    try:
        for s, (_, q) in sorted(gal.slots.items()):
            be.enroll(s, q)
    except RuntimeError as e:
        log(f"galeri tidak ditulis ulang ({e}); nama dari galeri tetap dipakai")
        return
    log(f"galeri {gal.path}: {len(gal.slots)} wajah ditulis ulang ke PADAN: "
        + ", ".join(f"{s}={n}" for s, n in sorted(gal.names().items())))


# ---------------------------------------------------------------- backend ---

class ModelBackend:
    """Golden model (model/padan.py) dengan peniru guard sederhana. Untuk laptop."""

    name = "model"

    def __init__(self, k=5):
        sys.path.insert(0, str(HERE.parents[1] / "model"))
        import padan as P                       # noqa: E402
        self.P = P
        self.T = np.zeros((N, D), dtype=np.int64)
        self.k, self.fail, self.state = k, 0, "OPEN"
        self.tau_lock = None

    def enroll(self, slot, q):
        if self.state != "OPEN":
            raise RuntimeError(f"enroll ditolak: guard {self.state}")
        self.T[slot] = q

    def match(self, q, tau):
        if self.state not in ("OPEN", "LOCKD"):
            raise RuntimeError(f"match ditolak: guard {self.state}; jalankan ulang skrip")
        t = self.tau_lock if self.state == "LOCKD" else tau
        res, k = self.P.decide(self.P.scores(self.T, q), t)
        if res == self.P.MATCH:
            self.fail = 0
            return C_MATCH | k << 4 | ((~k) & 0xF) << 8
        self.fail += 1
        if self.fail >= self.k:
            self.state = "LOUT"
        return C_NO_MATCH | 0xF << 8

    def clear(self):
        if self.state != "OPEN":
            raise RuntimeError(f"ENROLL_CLR ditolak: guard {self.state}")
        self.T[:] = 0

    def set_k(self, k):
        if self.state != "OPEN":
            raise RuntimeError("GUARD_K hanya di OPEN")
        self.k = k

    def lock(self, tau):
        if self.state != "OPEN":
            raise RuntimeError("LOCK hanya dari OPEN")
        self.tau_lock, self.state = tau, "LOCKD"

    def guard(self):
        return f"{self.state} (gagal {self.fail}/{self.k}, model)"

    def scores(self, q):
        return self.P.scores(self.T, q)

    def close(self):
        pass


class DevmemBackend:
    """PADAN di KV260 lewat /dev/mem (padan_test.DevMem + Padan)."""

    name = "devmem"

    def __init__(self, bus, clear=True):
        self.bus = bus
        self.dev = PT.Padan(bus)
        self.dev.identify()                      # hanya baca; NotPadan bila bukan PADAN
        g = self.dev.wait_guard()
        st = g & 0xF
        if st == PT.S_OPEN and clear:
            self.dev.wr(PT.A_CLR, [0])           # buang template sisa sesi lain
            self.dev.wait_idle()
        elif st not in (PT.S_OPEN, 0x5):         # 0x5 = LOCKD
            raise RuntimeError(f"guard {PT.gstat_text(g)}; muat ulang bitstream untuk reset PL")

    def _state(self):
        return self.dev.wait_guard() & 0xF

    def enroll(self, slot, q):
        if self._state() != PT.S_OPEN:
            raise RuntimeError(f"enroll ditolak: guard {self.guard()}")
        self.dev.wr(PT.A_ENROLL + slot * (D // 4), words(q))
        self.dev.wait_idle()

    def match(self, q, tau):
        if self._state() not in (PT.S_OPEN, 0x5):
            raise RuntimeError(f"match ditolak: guard {self.guard()}; muat ulang bitstream")
        self.dev.wr(PT.A_PROBE, words(q))
        self.dev.wr(PT.A_MATCH, [tau & 0xFFFFFFFF])
        return self.dev.wait_idle()

    def clear(self):
        if self._state() != PT.S_OPEN:
            raise RuntimeError(f"ENROLL_CLR ditolak: guard {self.guard()}")
        self.dev.wr(PT.A_CLR, [0])
        self.dev.wait_idle()

    def set_k(self, k):
        self.dev.wr(A_K, [k])

    def lock(self, tau):
        self.dev.wr(A_TAU, [tau & 0xFFFFFFFF])
        self.dev.wr(A_LOCK, [LOCK_MAGIC])

    def guard(self):
        return PT.gstat_text(self.dev.wait_guard())

    def scores(self, q):
        return None                              # skor tidak pernah keluar dari PADAN

    def close(self):
        self.bus.close()


# ---------------------------------------------------------------- perintah ---

def enroll_vec(emb, log):
    vs = []
    while len(vs) < ENROLL_FRAMES:
        r = emb.embed()
        if r is None:
            log("  tidak ada wajah; ulangi")
            return None
        vs.append(r[0])
        log(f"  frame {len(vs)}/{ENROLL_FRAMES}")
        time.sleep(0.3)
    cos = [float(vs[i] @ vs[j]) for i in range(len(vs)) for j in range(i + 1, len(vs))]
    if min(cos) < 0.5:
        log(f"  peringatan: frame kurang konsisten (kosinus min {min(cos):.2f}); ulangi dengan wajah diam")
    return normalize(np.mean(vs, axis=0))      # template = normalize(rata-rata), seperti model


def verify(be, emb, names, tau, log):
    r = emb.embed()
    if r is None:
        log("tidak ada wajah")
        return
    q = quantize(r[0])
    res, idx = decode(be.match(q, tau))
    extra = ""
    s = be.scores(q)
    if s is not None:
        extra = f"  (model: skor max {int(s.max())}, kosinus ~{s.max() / SCALE**2:.3f})"
    who = f" -> slot {idx}: {names.get(idx, '(tanpa nama)')}" if res == "MATCH" else ""
    log(f"{res}{who}{extra}")
    log(f"guard: {be.guard()}")


def check_quant(emb, log):
    r = emb.embed()
    if r is None:
        log("tidak ada wajah")
        return
    v = r[0]
    q = quantize(v)
    clipped = float(np.mean(np.abs(v * SCALE) > 127.5))
    rec = normalize(q / SCALE)
    log(f"terpotong di +-127: {clipped * 100:.1f}% nilai; kosinus float vs INT8 = {float(v @ rec):.4f}; "
        f"rentang q [{q.min()}, {q.max()}]")


HELP = "perintah: e <slot 0-15> <nama> | ls | d <slot> | forget | v | l [n] | c | g | k <1-15> | lock | q"


def repl(be, emb, tau, gal=None, log=print, inp=input):
    gal = gal if gal is not None else Gallery(None)
    log(f"PADAN cam: backend {be.name}, tau kosinus {tau / SCALE**2:.3f} -> tau_int {tau}; guard {be.guard()}")
    restore(be, gal, log)
    names = gal.names()
    log(HELP)
    while True:
        try:
            parts = inp("padan> ").split()
        except EOFError:
            return
        if not parts:
            continue
        cmd, args = parts[0], parts[1:]
        try:
            if cmd == "q":
                return
            if cmd == "e" and args and args[0].isdigit() and 0 <= int(args[0]) < N:
                slot = int(args[0])
                t = enroll_vec(emb, log)
                if t is not None:
                    q = quantize(t)
                    be.enroll(slot, q)
                    names[slot] = " ".join(args[1:]) or f"slot {slot}"
                    gal.set(slot, names[slot], q)
                    log(f"enroll slot {slot}: {names[slot]}" + (f" (disimpan di {gal.path})" if gal.path else ""))
            elif cmd == "ls":
                log(", ".join(f"{s}={n}" for s, n in sorted(names.items())) or "galeri kosong")
            elif cmd == "d" and args and args[0].isdigit() and 0 <= int(args[0]) < N:
                slot = int(args[0])
                be.enroll(slot, np.zeros(D, dtype=np.int64))   # template nol: skor 0, tidak pernah MATCH (tau > 0)
                names.pop(slot, None)
                gal.remove(slot)
                log(f"slot {slot} dihapus")
            elif cmd == "forget":
                be.clear()
                names.clear()
                gal.forget()
                log("semua template dihapus dari PADAN" + (f" dan {gal.path} dihapus" if gal.path else ""))
            elif cmd == "v":
                verify(be, emb, names, tau, log)
            elif cmd == "l":
                for _ in range(int(args[0]) if args else 10):
                    verify(be, emb, names, tau, log)
                    time.sleep(1.0)
            elif cmd == "c":
                check_quant(emb, log)
            elif cmd == "g":
                log(f"guard: {be.guard()}")
            elif cmd == "k" and args and args[0].isdigit() and 1 <= int(args[0]) <= 15:
                be.set_k(int(args[0]))
                log(f"guard: {be.guard()}")
            elif cmd == "lock":
                be.lock(tau)
                log(f"LOCK: tau dan enrollment dikunci; guard {be.guard()}")
            else:
                log(HELP)
        except RuntimeError as e:
            log(f"GAGAL: {e}")


# --------------------------------------------------------------- self-test ---

class FakeBus:
    """PADAN tiruan berbasis golden model, untuk menguji urutan register backend devmem."""

    def __init__(self):
        sys.path.insert(0, str(HERE.parents[1] / "model"))
        import padan as P
        self.P, self.T, self.p, self.status = P, np.zeros((N, D), dtype=np.int64), np.zeros(D, dtype=np.int64), 0xF00
        self.writes = []

    @staticmethod
    def _bytes(w):
        return [((w >> (8 * b)) & 0xFF) - (256 if (w >> (8 * b + 7)) & 1 else 0) for b in range(4)]

    def read(self, word):
        return {PT.A_STATUS: self.status, PT.A_GSTAT: 0x00000503}.get(word, 0)

    def write(self, word, value):
        self.writes.append((word, value))
        if word < 0x200:
            j, k = word >> 5, word & 0x1F
            self.T[j, 4 * k:4 * k + 4] = self._bytes(value)
        elif word < 0x220:
            k = word - 0x200
            self.p[4 * k:4 * k + 4] = self._bytes(value)
        elif word == PT.A_CLR:
            self.T[:] = 0
        elif word == PT.A_MATCH:
            tau = value - (1 << 32) if value >> 31 else value
            res, k = self.P.decide(self.P.scores(self.T, self.p), tau)
            self.status = (C_MATCH | k << 4 | ((~k) & 0xF) << 8) if res == self.P.MATCH else (C_NO_MATCH | 0xF << 8)

    def close(self):
        pass


def self_test():
    sys.path.insert(0, str(HERE.parents[1] / "model"))
    import padan_data as PD
    assert abs(SCALE - PD.SCALE) < 1e-12, "SCALE berbeda dengan model/padan_data.py"
    rng = np.random.default_rng(7)
    v = normalize(rng.standard_normal(D))
    assert np.array_equal(quantize(v), PD.quantize(v)), "kuantisasi berbeda dengan model"
    assert tau_int(0.363) == PD.tau_int(0.363)
    q = quantize(v)
    back = FakeBus._bytes
    assert [x for w in words(q) for x in back(w)] == [int(x) for x in q], "pengepakan word salah"

    # identitas sintetis: template = normalize(rata-rata 4 sampel), probe = sampel baru
    centers = np.array([normalize(rng.standard_normal(D)) for _ in range(5)])
    samp = lambda c: normalize(c + 0.8 * normalize(rng.standard_normal(D)) / np.sqrt(2))
    temps = [normalize(np.mean([samp(c) for _ in range(ENROLL_FRAMES)], axis=0)) for c in centers]
    tau = tau_int(TAU_COS)
    results = {}
    for be in (ModelBackend(k=15), DevmemBackend(FakeBus())):
        for j, t in enumerate(temps):
            be.enroll(j, quantize(t))
        out = [decode(be.match(quantize(samp(c)), tau)) for c in centers]
        out.append(decode(be.match(quantize(normalize(rng.standard_normal(D))), tau)))
        results[be.name] = out
    assert results["model"] == results["devmem"], results
    assert all(r == ("MATCH", j) for j, r in enumerate(results["model"][:5])), results["model"]
    assert results["model"][5] == ("NO_MATCH", None), results["model"]

    # REPL tanpa kamera: embedder tiruan memberi vektor dari pusat identitas tertentu
    class FakeEmb:
        def __init__(self):
            self.c = centers[0]

        def embed(self):
            return samp(self.c), None

    fe, logs = FakeEmb(), []
    cmds = iter(["e 3 Sukarelawan A", "v", "k 15", "g", "q"])
    repl(ModelBackend(), fe, tau, log=logs.append, inp=lambda _: next(cmds))
    assert any(l.startswith("MATCH -> slot 3: Sukarelawan A") for l in logs), logs

    # galeri: simpan (0600), mulai ulang dengan backend baru (model dan devmem tiruan),
    # hapus slot, forget, izin longgar, berkas rusak, galeri mati
    import tempfile

    def run(be, gal, cmds):
        out, it = [], iter(cmds + ["q"])
        repl(be, fe, tau, gal, log=out.append, inp=lambda _: next(it))
        return out

    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d) / "galeri.json"
        fe.c = centers[1]
        out = run(ModelBackend(), Gallery(path).load(), ["e 5 Sukarelawan B"])
        assert path.stat().st_mode & 0o777 == 0o600, oct(path.stat().st_mode)
        assert not (path.parent / "galeri.json.tmp").exists()
        for be in (ModelBackend(k=15), DevmemBackend(FakeBus())):     # "sesi baru": PADAN kosong
            out = run(be, Gallery(path).load(), ["v"])
            assert any(l.startswith("MATCH -> slot 5: Sukarelawan B") for l in out), (be.name, out)
        fb = FakeBus()
        run(DevmemBackend(fb), Gallery(path).load(), [])
        assert np.array_equal(fb.T[5], Gallery(path).load().slots[5][1]), "galeri tidak ditulis ulang ke PADAN"
        os.chmod(path, 0o644)
        warn = []
        Gallery(path).load(log=warn.append)
        assert path.stat().st_mode & 0o777 == 0o600 and warn, "izin longgar tidak diperketat"
        out = run(ModelBackend(k=15), Gallery(path).load(), ["d 5", "v"])
        assert any(l.startswith("NO_MATCH") for l in out) and not Gallery(path).load().slots, out
        run(ModelBackend(), Gallery(path).load(), ["e 2 C", "forget"])
        assert not path.exists(), "forget tidak menghapus berkas"
        ok = {"version": GALLERY_VERSION, "D": D, "scale": float(SCALE),
              "slots": {"0": {"name": "x", "q": [1] * D}}}
        path.write_text(json.dumps(ok))
        assert Gallery(path).load(log=lambda *_: None).slots[0][0] == "x", "galeri sah ditolak"
        bads = [dict(ok, slots={"0": {"name": "x", "q": [200] + [0] * (D - 1)}}),   # di luar INT8
                dict(ok, slots={"0": {"name": "x", "q": [0] * (D - 1)}}),           # panjang salah
                dict(ok, slots={"16": {"name": "x", "q": [0] * D}}),                # slot di luar 0-15
                dict(ok, scale=1.0)]                                                # SCALE lain
        for bad in [json.dumps(b) for b in bads] + ["bukan json"]:
            path.write_text(bad)
            try:
                Gallery(path).load(log=lambda *_: None)
                raise AssertionError(f"galeri rusak diterima: {bad[:40]}")
            except ValueError:
                pass
        path.unlink()
        run(ModelBackend(), Gallery(None), ["e 1 D"])
        assert not any(pathlib.Path(d).iterdir()), "--no-gallery menulis ke disk"
    print("PASS padan_cam self-test (kuantisasi = model, pengepakan word, backend model = devmem tiruan, REPL, "
          "galeri: simpan 0600, mulai ulang, hapus, forget, berkas rusak ditolak)")


# ------------------------------------------------------------------- main ---

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", choices=("devmem", "model"), default="devmem")
    ap.add_argument("--base", default="0xA0000000", help="alamat fisik padan_axil")
    ap.add_argument("--camera", type=int, default=0, help="indeks kamera (/dev/videoN)")
    ap.add_argument("--yunet", default=str(HERE / "face_detection_yunet_2021dec.onnx"))
    ap.add_argument("--sface", default=str(HERE / "face_recognition_sface_2021dec.onnx"))
    ap.add_argument("--tau", type=float, default=TAU_COS, help="ambang kosinus (default 0,363)")
    ap.add_argument("--show", action="store_true", help="tampilkan jendela kamera (butuh layar)")
    ap.add_argument("--no-clear", action="store_true", help="jangan ENROLL_CLR saat mulai (devmem)")
    ap.add_argument("--gallery", default=str(HERE / "padan_galeri.json"),
                    help="berkas galeri (nama + template INT8, izin 0600)")
    ap.add_argument("--no-gallery", action="store_true", help="jangan baca/tulis galeri di disk")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        self_test()
        return 0
    try:
        gal = Gallery(None if a.no_gallery else a.gallery).load()
    except (OSError, ValueError) as e:
        print(f"PADAN cam: ERROR {e}")
        return 2
    try:
        be = ModelBackend() if a.backend == "model" else DevmemBackend(PT.DevMem(int(a.base, 0)),
                                                                        clear=not a.no_clear)
    except PT.NotPadan as e:
        print(f"PADAN cam: bukan PADAN di {a.base}; tidak ada yang ditulis ({e})")
        return 3
    except (OSError, RuntimeError, ValueError) as e:
        print(f"PADAN cam: ERROR {e}")
        return 2
    emb = Embedder(a.camera, a.yunet, a.sface)
    emb.show = a.show
    try:
        repl(be, emb, tau_int(a.tau), gal)
    finally:
        emb.close()
        be.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
