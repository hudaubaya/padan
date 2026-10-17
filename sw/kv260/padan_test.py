#!/usr/bin/env python3
"""Uji PADAN di Kria KV260 dari Linux di PS, lewat AXI4-Lite (rtl/padan_axil.v).

    sudo python3 padan_test.py                  # /dev/mem, base 0xA0000000
    sudo python3 padan_test.py --base 0xA0010000

Hanya pustaka standar Python 3; salin padan_test.py dan padan_vectors.json ke
board. Bitstream harus sudah dimuat (docs/fpga_howto.md). Membaca alamat PL
tanpa bitstream yang sesuai bisa membuat bus AXI menggantung.

Urutan:
  1. Baca-saja: STATUS, GUARD_STATUS, dan beberapa word yang harus 0. Bila tidak
     tampak seperti PADAN, berhenti TANPA menulis apa pun (kode keluar 3).
  2. Tunggu zeroize boot selesai; guard harus OPEN (tanpa LOCK).
  3. Per galeri di padan_vectors.json: ENROLL_CLR, tulis 512 word template,
     pindai 1024 word (semua 0 kecuali STATUS dan GUARD_STATUS), lalu per kasus:
     tulis probe, MATCH(tau), tunggu busy = 0, bandingkan STATUS[11:0] dengan
     nilai dari model/padan.py. Guard harus tetap OPEN.

Skrip tidak menulis GUARD_LOCK, GUARD_K, atau GUARD_TAU. Keluar dari
LOUT/HALT/LOCKD hanya dengan reset PL (memuat ulang bitstream), yang
mengenolkan template.

Hasil akhir dicetak sebagai satu baris "PADAN KV260: PASS ..." atau
"PADAN KV260: FAIL ...". Kode keluar: 0 PASS, 1 FAIL, 2 argumen/akses, 3 bukan
PADAN. Skrip ini hanya membandingkan dengan model; hasilnya adalah bukti hanya
untuk board, bitstream, dan versi repo tempat ia dijalankan.

Akses register selalu 32 bit sejajar (memoryview cast 'I'). padan_axil
menjawab tulis parsial (WSTRB != 1111) dengan SLVERR, yang di Linux bisa
berakhir sebagai SIGBUS; jangan memakai salinan byte (mm[a:b] = ...).

--backend pipe dipakai test CI (tb/kv260): setiap akses dikirim sebagai baris
"@@REQ r|w <alamat> [nilai]" di stdout dan dijawab "@@ACK [nilai]" di stdin.
"""

import argparse
import json
import mmap
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SPAN = 0x1000                       # 1024 word (padan_axil ADDR_W = 12)
WORDS = SPAN // 4
# Alamat word (rtl/padan_avmm.v, docs/rtl_decision.md)
A_ENROLL, A_PROBE, A_CLR, A_MATCH, A_STATUS, A_GSTAT = 0x000, 0x200, 0x300, 0x301, 0x302, 0x303
GSTATES = {0x0: "ZB", 0x3: "OPEN", 0x5: "LOCKD", 0x6: "LOUT", 0x9: "ZH", 0xA: "HALT"}
REASONS = ("BOOT", "TAMPER", "FAULT", "ILLEGAL")
S_OPEN = 0x3


class NotPadan(Exception):
    pass


# ---------------------------------------------------------------- akses bus ---

class DevMem:
    """Jendela /dev/mem 4 KiB pada alamat fisik `base`."""

    def __init__(self, base, path="/dev/mem"):
        if base % mmap.PAGESIZE:
            raise ValueError(f"base {base:#x} harus sejajar halaman ({mmap.PAGESIZE:#x})")
        self.base = base
        flags = os.O_RDWR | getattr(os, "O_SYNC", 0)
        self.fd = os.open(path, flags)
        self.mm = mmap.mmap(self.fd, SPAN, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                            offset=base)
        self.w32 = memoryview(self.mm).cast("I")       # akses 32 bit sejajar

    def read(self, word):
        return self.w32[word]

    def write(self, word, value):
        self.w32[word] = value & 0xFFFFFFFF

    def close(self):
        self.w32.release()
        self.mm.close()
        os.close(self.fd)


class Pipe:
    """Akses lewat stdin/stdout ke proses induk (test CI melawan RTL)."""

    def __init__(self, base):
        self.base = base

    def _req(self, *args):
        print("@@REQ " + " ".join(args), flush=True)
        line = sys.stdin.readline()
        if line.startswith("@@ERR "):
            raise OSError(line[6:].strip())
        if not line.startswith("@@ACK"):
            raise OSError(f"jawaban tak dikenal: {line!r}")
        return line[5:].strip()

    def read(self, word):
        return int(self._req("r", f"0x{self.base + 4 * word:08X}"), 0)

    def write(self, word, value):
        self._req("w", f"0x{self.base + 4 * word:08X}", f"0x{value & 0xFFFFFFFF:08X}")

    def close(self):
        pass


# ------------------------------------------------------------ tafsir status ---

def status_ok(s):
    """STATUS konsisten: bit tak terdefinisi 0, kode valid, idx sesuai kode."""
    if s >> 18 or (s >> 12) & 0xF:
        return False
    code, idx, idxn = s & 0xF, (s >> 4) & 0xF, (s >> 8) & 0xF
    if code == 0xA:
        return idx == (~idxn & 0xF)
    if code in (0x0, 0x5, 0xF):
        return idx == 0 and idxn == 0xF
    return False


def gstat_ok(g):
    return g >> 20 == 0 and (g & 0xF) in GSTATES


def gstat_text(g):
    st = g & 0xF
    return (f"{GSTATES.get(st, f'ILEGAL({st})')} (gagal {(g >> 4) & 0xF}/{(g >> 8) & 0xF}, "
            f"fault {(g >> 12) & 0xF}, alasan {REASONS[(g >> 16) & 3]}, GUARD_STATUS 0x{g:08X})")


# ------------------------------------------------------------------- uji ------

class Padan:
    def __init__(self, bus):
        self.bus = bus

    def rd(self, word):
        return self.bus.read(word) & 0xFFFFFFFF

    def wr(self, word, values):
        for i, v in enumerate(values):
            self.bus.write(word + i, v)

    def identify(self):
        """Hanya baca. NotPadan bila jendela ini bukan padan_axil."""
        st, g = self.rd(A_STATUS), self.rd(A_GSTAT)
        z = [self.rd(a) for a in (0x000, 0x200, 0x306, 0x3FF)]
        if not (status_ok(st) and gstat_ok(g) and z == [0, 0, 0, 0]):
            raise NotPadan(f"STATUS 0x{st:08X}, GUARD_STATUS 0x{g:08X}, word 0/0x200/0x306/0x3FF = "
                           + "/".join(f"0x{v:X}" for v in z))

    def wait_guard(self):
        """Tunggu zeroize selesai; kembalikan GUARD_STATUS."""
        for _ in range(1000):
            g = self.rd(A_GSTAT)
            if not gstat_ok(g):
                raise RuntimeError(f"GUARD_STATUS tidak valid: 0x{g:08X}")
            if not (g >> 19) & 1:
                return g
        raise RuntimeError(f"guard tetap zeroize setelah 1000 baca: {gstat_text(g)}")

    def wait_idle(self):
        for _ in range(1000):
            s = self.rd(A_STATUS)
            if not (s >> 16) & 3:
                return s
        raise RuntimeError(f"STATUS tetap busy setelah 1000 baca: 0x{s:08X}")

    def scan(self):
        return [f"0x{a:03X}=0x{v:08X}" for a in range(WORDS)
                if a not in (A_STATUS, A_GSTAT) and (v := self.rd(a)) != 0]


def run(bus, vectors, log=print):
    """Kembalikan jumlah kegagalan (0 = PASS)."""
    dev = Padan(bus)
    dev.identify()
    g0 = dev.wait_guard()
    log(f"PADAN: guard {gstat_text(g0)}")
    if g0 & 0xF != S_OPEN:
        log(f"PADAN KV260: FAIL (guard bukan OPEN: {gstat_text(g0)}; muat ulang bitstream/reset PL "
            "untuk zeroize dan kembali ke OPEN)")
        return 1
    gals = vectors["galleries"]
    mask = vectors["status_mask"]
    fails = ncase = 0
    halted = ""
    for gi, gal in enumerate(gals):
        dev.wr(A_CLR, [0])
        dev.wait_idle()
        dev.wr(A_ENROLL, gal["T"])
        dev.wait_idle()
        bad = dev.scan()
        if bad:
            log(f"FAIL galeri {gi}: alamat selain STATUS tidak nol: {bad[:8]}")
            fails += 1
        for ci, c in enumerate(gal["cases"]):
            dev.wr(A_PROBE, c["p"])
            dev.wr(A_MATCH, [c["tau"]])
            s = dev.wait_idle()
            ncase += 1
            if s & mask != c["status"] or not status_ok(s):
                log(f"FAIL galeri {gi} kasus {ci} ({c['note']}): STATUS 0x{s:08X}, model 0x{c['status']:03X}")
                fails += 1
            if dev.rd(A_GSTAT) & 0xF != S_OPEN:
                halted = gstat_text(dev.wait_guard())
                log(f"FAIL guard keluar dari OPEN setelah galeri {gi} kasus {ci}: {halted}")
                fails += 1
                break
        if halted:
            break
        log(f"PADAN: galeri {gi} ({gal['name']}): {len(gal['cases'])} kasus selesai")
    if fails == 0:
        log(f"PADAN KV260: PASS ({ncase} kasus, {len(gals)} galeri, pindai alamat bersih)")
    elif halted:
        log(f"PADAN KV260: FAIL ({fails} kegagalan dari {ncase} kasus; dihentikan, guard {halted})")
    else:
        log(f"PADAN KV260: FAIL ({fails} kegagalan dari {ncase} kasus dan {len(gals)} pindaian)")
    return fails


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default=os.environ.get("PADAN_BASE", "0xA0000000"),
                    help="alamat fisik padan_axil (default 0xA0000000, fpga/kv260/create_project.tcl)")
    ap.add_argument("--vectors", default=str(HERE / "padan_vectors.json"))
    ap.add_argument("--backend", choices=("devmem", "pipe"), default="devmem")
    ap.add_argument("--devmem", default="/dev/mem", help=argparse.SUPPRESS)   # test: berkas biasa
    a = ap.parse_args(argv)
    try:
        base = int(a.base, 0)
        vectors = json.loads(pathlib.Path(a.vectors).read_text())
        bus = Pipe(base) if a.backend == "pipe" else DevMem(base, a.devmem)
    except (OSError, ValueError) as e:
        print(f"PADAN KV260: ERROR {e}")
        return 2
    print(f"PADAN: base 0x{base:08X}, backend {a.backend}")
    try:
        return 1 if run(bus, vectors) else 0
    except NotPadan as e:
        print(f"PADAN KV260: ERROR bukan PADAN di 0x{base:08X}; tidak ada yang ditulis ({e})")
        return 3
    except (RuntimeError, OSError) as e:
        print(f"PADAN KV260: FAIL ({e})")
        return 1
    finally:
        bus.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
