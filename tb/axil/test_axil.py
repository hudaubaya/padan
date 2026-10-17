"""Test cocotb padan_axil: wrapper AXI4-Lite (KV260) di atas padan_avmm.

Semua akses lewat port AXI4-Lite, seperti PS Linux di KV260. Parameter guard
rilis (K = 5, FAULT_MAX = 3). Perilaku inti diuji di tb/avmm dan tb/guard; di
sini yang diuji adalah protokol AXI dan bahwa wrapper meneruskan akses tanpa
mengubah arti register. Monitor memeriksa stabilitas B/R di setiap test.
"""

import cocotb
from cocotb.triggers import FallingEdge

import padan as P
from axil_host import OKAY, SLVERR, AxilHost
from test_avmm import (A_CLR, A_ENROLL, A_GK, A_GLOCK, A_GSTAT, A_MATCH, A_PROBE, A_STATUS,
                       G_OPEN, I8, golden, host_decode, pack)

import numpy as np

S_HALT, R_TAMPER = 0b1010, 1


def gk(v):
    return (v >> 8) & 0xF


class Host(AxilHost):
    async def w(self, word, data, **kw):
        bresp = await self.write(word, data, **kw)
        assert bresp == OKAY, f"tulis {word:#x}: BRESP {bresp}"

    async def r(self, word, **kw):
        data, rresp = await self.read(word, **kw)
        assert rresp == OKAY, f"baca {word:#x}: RRESP {rresp}"
        return data

    async def wait_open(self):
        for _ in range(1000):
            if (await self.r(A_GSTAT)) & 0xF == G_OPEN:
                return
        raise AssertionError("guard tidak pernah OPEN")

    async def enroll(self, T):
        await self.w(A_CLR, 0)
        for j in range(P.N):
            for k in range(P.D // 4):
                await self.w(A_ENROLL + j * 32 + k, pack(T[j, 4 * k:4 * k + 4]))

    async def probe(self, p):
        for k in range(P.D // 4):
            await self.w(A_PROBE + k, pack(p[4 * k:4 * k + 4]))

    async def match(self, tau):
        await self.w(A_MATCH, tau)
        for _ in range(1000):
            if self.dut.dec_busy.value == 0:
                break
            await FallingEdge(self.clk)
        else:
            raise AssertionError("keputusan tidak selesai")
        return host_decode(await self.r(A_STATUS))


async def setup(dut):
    h = Host(dut)
    mon = h.start_monitor()
    await h.reset()
    return h, mon


def done(h, mon):
    mon.kill()
    assert h.violations == [], f"pelanggaran protokol AXI: {h.violations[:5]}"


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_boot_stall_and_order(dut):
    """Tulis selama zeroize boot: B ditahan sampai inti menerima tulis. Lalu
    GUARD_K ditulis dengan semua urutan AW/W dan backpressure B; nilainya
    terlihat di GUARD_STATUS[11:8]."""
    h, mon = await setup(dut)
    t0 = cocotb.utils.get_sim_time("ns")
    await h.w(A_GK, 7)                           # segera setelah reset: zeroize boot
    stall = (cocotb.utils.get_sim_time("ns") - t0) / 10
    assert stall > 200, f"B tidak ditahan selama zeroize ({stall} siklus)"
    g = await h.r(A_GSTAT)
    assert g & 0xF == G_OPEN and gk(g) == 7, f"GUARD_STATUS {g:#x}"
    k = 7
    for i, (aw, wd, bd) in enumerate([(0, 0, 0), (0, 3, 0), (3, 0, 0), (5, 1, 4), (1, 6, 2),
                                      (0, 0, 7), (2, 2, 0)]):
        k = 2 + (k + 3) % 13
        await h.w(A_GK, k, aw_delay=aw, w_delay=wd, b_delay=bd)
        assert gk(await h.r(A_GSTAT, r_delay=i)) == k, f"urutan {aw},{wd},{bd}"
    done(h, mon)


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_partial_strobe_slverr(dut):
    """WSTRB != 1111 -> SLVERR dan tulis tidak diteruskan ke inti."""
    h, mon = await setup(dut)
    await h.wait_open()
    await h.w(A_GK, 4)
    for strb in (0x0, 0x1, 0x3, 0x7, 0xE, 0x8):
        assert await h.write(A_GK, 9, strb=strb, b_delay=strb % 3) == SLVERR, f"strb {strb:#x}"
        assert gk(await h.r(A_GSTAT)) == 4, f"strb {strb:#x} mengubah K"
    # Tulis LOCK parsial juga tidak boleh mengunci.
    assert await h.write(A_GLOCK, 0x4C4F434B, strb=0x7) == SLVERR
    assert (await h.r(A_GSTAT)) & 0xF == G_OPEN
    done(h, mon)


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_read_write_concurrent(dut):
    """AR bersamaan dengan AW+W: keduanya selesai, tidak ada transaksi hilang."""
    h, mon = await setup(dut)
    await h.wait_open()
    await h.w(A_GK, 3)
    # ar_delay 1: AR tiba tepat saat AW+W baru lengkap (tulis didahulukan).
    for i, k in enumerate((6, 11, 2, 8, 4, 13)):
        wr = cocotb.start_soon(h.write(A_GK, k, w_delay=i // 3))
        rd = cocotb.start_soon(h.read(A_GSTAT, r_delay=2, ar_delay=i % 3))
        bresp = await wr
        data, rresp = await rd
        assert bresp == OKAY and rresp == OKAY
        assert data & 0xF == G_OPEN
        assert gk(await h.r(A_GSTAT)) == k
    done(h, mon)


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_address_scan(dut):
    """1024 word lewat AXI: hanya STATUS dan GUARD_STATUS yang bisa bukan nol.
    Bit alamat [1:0] diabaikan."""
    h, mon = await setup(dut)
    await h.wait_open()
    rng = np.random.default_rng(21)
    T = rng.integers(*I8, (P.N, P.D))
    await h.enroll(T)
    await h.probe(T[6])
    tau = int(P.scores(T, T[6]).max())
    assert await h.match(tau) == golden(T, T[6], tau) == (P.MATCH, 6)
    vals = [await h.r(a, r_delay=a % 2) for a in range(1024)]
    nonzero = {a for a, v in enumerate(vals) if v != 0}
    assert nonzero <= {A_STATUS, A_GSTAT}, f"alamat bukan-nol {sorted(nonzero)}"
    # Alamat byte tak sejajar memetakan ke word yang sama.
    for off in (1, 2, 3):
        h_data = await _read_byte(h, A_STATUS * 4 + off)
        assert h_data == vals[A_STATUS], f"offset {off}"
    done(h, mon)


async def _read_byte(h, byte_addr):
    d = h.dut
    await FallingEdge(h.clk)
    ar = cocotb.start_soon(h._send(0, d.arvalid, d.arready, [(d.araddr, byte_addr)]))
    r = cocotb.start_soon(h._recv(0, d.rvalid, d.rready, [d.rdata, d.rresp]))
    await ar
    data, _ = await r
    return data


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_decisions_vs_model(dut):
    """Sampel keputusan lewat AXI identik dengan model/padan.py decide().
    Paling banyak 2 NO_MATCH berturut-turut (K rilis = 5)."""
    h, mon = await setup(dut)
    await h.wait_open()
    rng = np.random.default_rng(22)
    n = 0
    for g in range(2):
        T = rng.integers(*I8, (P.N, P.D))
        await h.enroll(T)
        miss = 0
        for k in range(12):
            if k % 3 == 0:
                p = T[int(rng.integers(P.N))].copy()
            else:
                p = rng.integers(*I8, P.D)
            m = int(P.scores(T, p).max())
            tau = m if miss >= 2 else int(rng.choice([m, m + 1, m - 1]))
            await h.probe(p)
            res = await h.match(tau)
            gold = golden(T, p, tau)
            assert res == gold, f"galeri {g} probe {k} tau {tau}: {res} != {gold}"
            miss = miss + 1 if gold[0] == P.NO_MATCH else 0
            n += 1
    g = await h.r(A_GSTAT)
    assert g & 0xF == G_OPEN, f"guard {g:#x}"
    dut._log.info("%d keputusan lewat AXI identik dengan model", n)
    done(h, mon)


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def test_tamper_pin(dut):
    """tamper_n (pin PMOD) diteruskan wrapper: HALT, alasan TAMPER, tulis
    berikutnya tetap selesai (B OKAY) tanpa efek."""
    h, mon = await setup(dut)
    await h.wait_open()
    await h.w(A_GK, 9)
    await FallingEdge(h.clk)
    dut.tamper_n.value = 0
    for _ in range(400):
        g = await h.r(A_GSTAT)
        if g & 0xF == S_HALT:
            break
    assert g & 0xF == S_HALT and (g >> 16) & 3 == R_TAMPER, f"GUARD_STATUS {g:#x}"
    dut.tamper_n.value = 1
    await h.w(A_GK, 3)
    g2 = await h.r(A_GSTAT)
    assert g2 & 0xF == S_HALT and gk(g2) == gk(g), f"GUARD_STATUS {g2:#x}"
    done(h, mon)
