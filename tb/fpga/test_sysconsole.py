"""Jalankan fpga/de10_nano/sysconsole/padan_test.tcl (skrip System Console asli,
tanpa diubah) di tclsh melawan RTL padan_avmm.

syscon_shim.tcl menggantikan perintah System Console dengan permintaan ke test
ini, yang menjalankannya sebagai transaksi Avalon-MM (Host dari tb/avmm). Ada
dua service master tiruan:
  /devices/test/(link)/JTAG/other/master   bukan padan (baca 0xDEADBEEF)
  /devices/test/(link)/JTAG/padan/master   padan_0 di RTL, base PADAN_BASE
sehingga deteksi master otomatis di skrip ikut diuji.

Ini membuktikan logika skrip, alamat, pengemasan word, dan vektor model terhadap
RTL. Ini BUKAN hasil board: JTAG, interkoneksi Platform Designer, dan timing
tidak tercakup.
"""

import os
import pathlib
import queue
import subprocess
import threading

import cocotb
from cocotb.triggers import Timer

import test_avmm as TA

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "fpga" / "de10_nano" / "sysconsole" / "padan_test.tcl"
SHIM = ROOT / "tb" / "fpga" / "syscon_shim.tcl"
BASE = 0x00040000
P_OTHER = "/devices/test/(link)/JTAG/other/master"
P_PADAN = "/devices/test/(link)/JTAG/padan/master"


class Bridge:
    """Melayani permintaan shim dengan transaksi Avalon-MM ke RTL."""

    def __init__(self, dut, host, on_match=None):
        self.dut, self.host, self.on_match = dut, host, on_match
        self.claims = {}
        self.log = []
        self.stats = {"write": 0, "read": 0, "match": 0}

    def word(self, addr):
        a = int(addr, 0) - BASE
        if a < 0 or a % 4 or a // 4 >= 1024:
            raise ValueError(f"alamat di luar padan_0: {addr}")
        return a // 4

    async def handle(self, op, args):
        if op == "paths":
            return [P_OTHER, P_PADAN]
        if op == "claim":
            h = f"claim{len(self.claims)}"
            self.claims[h] = args[0]
            return [h]
        if op == "close":
            self.claims.pop(args[0])
            return []
        path = self.claims[args[0]]
        if path == P_OTHER:
            if op == "write":
                raise ValueError("tulis ke master yang bukan padan")
            return ["0xDEADBEEF"] * int(args[2])
        if op == "write":
            w = self.word(args[1])
            for i, v in enumerate(args[2:]):
                if w + i == TA.A_MATCH:
                    self.stats["match"] += 1
                    if self.on_match is not None:
                        await self.on_match(self.stats["match"])
                await self.host.write(w + i, int(v, 0))
                self.stats["write"] += 1
            return []
        if op == "read":
            w = self.word(args[1])
            out = [await self.host.read(w + i) for i in range(int(args[2]))]
            self.stats["read"] += len(out)
            return [str(v) for v in out]
        raise ValueError(f"op tak dikenal: {op}")


async def run_script(dut, on_match=None, env=None):
    host = TA.Host(dut)
    await host.reset()
    bridge = Bridge(dut, host, on_match)
    proc = subprocess.Popen(["tclsh", str(SHIM), str(SCRIPT)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            env={**os.environ, **(env or {})})
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
            op, *args = line[6:].split()
            try:
                reply = "@@ACK " + " ".join(await bridge.handle(op, args))
            except Exception as e:                      # dikembalikan ke skrip sebagai error Tcl
                reply = f"@@ERR {e}"
            proc.stdin.write(reply + "\n")
            proc.stdin.flush()
        else:
            bridge.log.append(line)
            dut._log.info("tcl: %s", line)
    rc = proc.wait()
    return rc, bridge


def verdict(log):
    v = [ln for ln in log if ln.startswith("PADAN SYSCON:")]
    assert len(v) == 1, f"skrip tidak mencetak satu baris hasil: {log[-5:]}"
    return v[0]


@cocotb.test()
async def test_script_passes_on_rtl(dut):
    """Skrip lengkap: deteksi master, 3 galeri, pindai alamat, 46 kasus = model."""
    rc, br = await run_script(dut)
    assert rc == 0, f"tclsh keluar dengan {rc}"
    assert any(P_PADAN in ln for ln in br.log), "skrip tidak memilih master padan"
    v = verdict(br.log)
    assert v.startswith("PADAN SYSCON: PASS (46 kasus, 3 galeri"), v
    assert br.stats["match"] == 46
    dut._log.info("%s; transaksi: %s", v, br.stats)


@cocotb.test()
async def test_script_detects_fault(dut):
    """Bit memori template dibalik setelah galeri 0 di-enroll: skrip harus FAIL.
    Memastikan perbandingan di skrip benar-benar bisa gagal."""
    mem = dut.u.u_mem

    async def corrupt(n):
        if n == 1:                                       # sebelum MATCH pertama
            w = mem.g_bank[3].u_ram.mem[5 * 8 + 2]       # T[5, 2*16+3]
            w.value = w.value.integer ^ 0x4
            await Timer(1, "ns")

    rc, br = await run_script(dut, on_match=corrupt)
    assert rc == 0
    v = verdict(br.log)
    fails = [ln for ln in br.log if ln.startswith("FAIL galeri 0")]
    assert v.startswith("PADAN SYSCON: FAIL"), v
    # Template rusak di galeri 0: setiap kasus galeri 0 yang probe-nya tidak nol di kolom
    # itu harus FAULT (0xF0F); galeri berikutnya di-enroll ulang dan harus lulus.
    assert fails and all("STATUS 0x00000F0F" in ln for ln in fails), fails[:3]
    assert not any(ln.startswith(("FAIL galeri 1", "FAIL galeri 2")) for ln in br.log)
    dut._log.info("%s; contoh: %s", v, fails[0])


@cocotb.test()
async def test_master_override(dut):
    """PADAN_MASTER memilih master secara eksplisit; master salah memberi error yang jelas."""
    rc, br = await run_script(dut, env={"PADAN_MASTER": "other"})
    assert rc == 3, "master yang salah harus menghentikan skrip"
    assert any("tulis ke master yang bukan padan" in ln for ln in br.log), br.log[-5:]
    rc, br = await run_script(dut, env={"PADAN_MASTER": "1"})
    assert rc == 0 and verdict(br.log).startswith("PADAN SYSCON: PASS")
