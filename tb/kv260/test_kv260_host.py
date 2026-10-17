"""Jalankan sw/kv260/padan_test.py (skrip host KV260 asli, tanpa diubah) melawan
RTL padan_axil.

Skrip dijalankan dengan --backend pipe: setiap baca/tulis 32 bit dikirim ke test
ini, yang menjalankannya sebagai transaksi AXI4-Lite (AxilHost dari tb/axil).
Peta alamat tiruan: padan_axil di BASE (4 KiB); alamat lain dibaca 0xDEADBEEF
dan tulis ke sana adalah error, sehingga pemeriksaan "bukan PADAN" ikut diuji.

Ini membuktikan logika skrip, alamat, pengemasan word, vektor model, dan
protokol AXI wrapper terhadap RTL. Ini BUKAN hasil board: PS, interkoneksi
AXI, /dev/mem, dan timing tidak tercakup.
"""

import os
import pathlib
import queue
import subprocess
import sys
import tempfile
import threading

import cocotb
from cocotb.triggers import Timer

from axil_host import OKAY, AxilHost
from test_avmm import A_GLOCK, A_MATCH

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "sw" / "kv260" / "padan_test.py"
BASE = 0xA0000000


class Bridge:
    def __init__(self, host, on_match=None):
        self.host, self.on_match = host, on_match
        self.stats = {"write": 0, "read": 0, "match": 0}
        self.log = []

    def word(self, addr):
        a = int(addr, 0) - BASE
        return a // 4 if 0 <= a < 0x1000 and a % 4 == 0 else None

    async def handle(self, op, args):
        w = self.word(args[0])
        if op == "r":
            self.stats["read"] += 1
            if w is None:
                return "0xDEADBEEF"
            data, rresp = await self.host.read(w)
            assert rresp == OKAY, f"RRESP {rresp} di {args[0]}"
            return f"0x{data:08X}"
        if op == "w":
            if w is None:
                raise ValueError(f"tulis ke alamat di luar padan_axil: {args[0]}")
            if w == A_MATCH:
                self.stats["match"] += 1
                if self.on_match is not None:
                    await self.on_match(self.stats["match"])
            bresp = await self.host.write(w, int(args[1], 0))
            assert bresp == OKAY, f"BRESP {bresp} di {args[0]}"
            self.stats["write"] += 1
            return ""
        raise ValueError(f"op tak dikenal: {op}")


async def run_script(dut, on_match=None, args=(), before=None):
    host = AxilHost(dut)
    mon = host.start_monitor()
    await host.reset()
    if before is not None:
        await before(host)
    br = Bridge(host, on_match)
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--backend", "pipe", *args],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env={**os.environ, "PADAN_BASE": f"0x{BASE:08X}"})
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(ln) for ln in proc.stdout] + [lines.put(None)],
                     daemon=True).start()
    while True:
        try:
            line = lines.get_nowait()
        except queue.Empty:
            await Timer(100, "ns")
            continue
        if line is None:
            break
        line = line.rstrip("\n")
        if line.startswith("@@REQ "):
            op, *rest = line[6:].split()
            try:
                reply = "@@ACK " + await br.handle(op, rest)
            except ValueError as e:                 # dikembalikan ke skrip sebagai OSError
                reply = f"@@ERR {e}"
            proc.stdin.write(reply + "\n")
            proc.stdin.flush()
        else:
            br.log.append(line)
            dut._log.info("host: %s", line)
    rc = proc.wait()
    proc.stdin.close()
    proc.stdout.close()
    mon.kill()
    assert host.violations == [], f"pelanggaran protokol AXI: {host.violations[:5]}"
    return rc, br


def verdict(log):
    v = [ln for ln in log if ln.startswith("PADAN KV260:")]
    assert len(v) == 1, f"skrip tidak mencetak satu baris hasil: {log[-5:]}"
    return v[0]


@cocotb.test()
async def test_script_passes_on_rtl(dut):
    """Skrip lengkap: identifikasi baca-saja, 3 galeri, pindai alamat, 46 kasus =
    model, guard rilis (K = 5): urutan vektor tidak memicu lockout."""
    rc, br = await run_script(dut)
    assert rc == 0, f"skrip keluar dengan {rc}"
    assert any(ln.startswith("PADAN: guard OPEN") for ln in br.log), br.log[:5]
    v = verdict(br.log)
    assert v.startswith("PADAN KV260: PASS (46 kasus, 3 galeri"), v
    assert br.stats["match"] == 46
    dut._log.info("%s; transaksi AXI: %s", v, br.stats)


@cocotb.test()
async def test_script_detects_fault(dut):
    """Bit memori template dibalik sebelum MATCH pertama: skrip harus FAIL. FAULT
    ke-3 (FAULT_MAX) memicu zeroize dan HALT: skrip berhenti dengan pesan guard."""
    mem = dut.u.u_core.u_mem

    async def corrupt(n):
        if n == 1:
            w = mem.g_bank[3].u_ram.mem[5 * 8 + 2]       # T[5, 2*16+3]
            w.value = w.value.integer ^ 0x4
            await Timer(1, "ns")

    rc, br = await run_script(dut, on_match=corrupt)
    assert rc == 1, rc
    v = verdict(br.log)
    fails = [ln for ln in br.log if ln.startswith("FAIL galeri 0")]
    assert v.startswith("PADAN KV260: FAIL"), v
    assert len(fails) == 3, fails
    assert all("STATUS 0x00000F0F" in ln for ln in fails[:2]), fails
    assert "STATUS 0x00000F00" in fails[2], fails
    guard = [ln for ln in br.log if ln.startswith("FAIL guard keluar dari OPEN")]
    assert len(guard) == 1 and "HALT" in guard[0] and "alasan FAULT" in guard[0], guard
    assert "dihentikan, guard HALT" in v, v
    assert not any(ln.startswith(("FAIL galeri 1", "FAIL galeri 2", "PADAN: galeri")) for ln in br.log)


@cocotb.test()
async def test_wrong_base_writes_nothing(dut):
    """Base salah (bukan padan_axil): skrip berhenti dengan kode 3 tanpa satu tulis pun."""
    rc, br = await run_script(dut, args=("--base", f"0x{BASE + 0x10000:08X}"))
    assert rc == 3, rc
    assert "bukan PADAN" in verdict(br.log)
    assert br.stats["write"] == 0, br.stats


@cocotb.test()
async def test_script_refuses_locked(dut):
    """Guard LOCKD sebelum skrip: tidak ada tulis, FAIL menyebut state guard."""
    async def lock(host):
        assert await host.write(A_GLOCK, 0x4C4F434B) == OKAY

    rc, br = await run_script(dut, before=lock)
    assert rc == 1, rc
    v = verdict(br.log)
    assert v.startswith("PADAN KV260: FAIL (guard bukan OPEN: LOCKD"), v
    assert br.stats["write"] == 0 and br.stats["match"] == 0, br.stats


@cocotb.test()
async def test_devmem_backend_layout(dut):
    """Backend /dev/mem diuji pada berkas biasa: word i ada di offset base + 4i,
    little-endian, akses lewat memoryview 32 bit. (Tidak menyentuh RTL.)"""
    sys.path.insert(0, str(SCRIPT.parent))
    import padan_test as PT
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(bytes(3 * 4096))
        path = f.name
    try:
        bus = PT.DevMem(4096, path)
        bus.write(0x302, 0x11223344)
        bus.write(0x3FF, 0xFFFFFFFF + 6)                 # dipotong ke 32 bit
        assert bus.read(0x302) == 0x11223344
        assert bus.w32.itemsize == 4 and bus.w32.format == "I"
        bus.close()
        raw = pathlib.Path(path).read_bytes()
        assert raw[4096 + 4 * 0x302:4096 + 4 * 0x303] == bytes([0x44, 0x33, 0x22, 0x11])
        assert raw[4096 + 4 * 0x3FF:4096 + 4 * 0x400] == bytes([5, 0, 0, 0])
        assert raw.count(0) == len(raw) - 5
        try:
            PT.DevMem(4096 + 4, path)
            raise AssertionError("base tak sejajar halaman harus ditolak")
        except ValueError:
            pass
    finally:
        os.unlink(path)
