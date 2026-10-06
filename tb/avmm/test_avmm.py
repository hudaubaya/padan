"""Test cocotb padan_avmm: antarmuka Avalon-MM, keputusan (decision.v), dan keamanan fault.

Semua akses lewat port Avalon-MM, seperti host. Referensi: model/padan.py
(scores, checksum_rows, decide). Parameter rilis: N = 16, D = 128, L = 16.
"""

import os
import random

import numpy as np

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

import padan as P
import padan_data as PD

L = 16
CH = P.D // L
ROWS = P.N + 2
A_ENROLL, A_PROBE, A_CLR, A_MATCH, A_STATUS = 0x000, 0x200, 0x300, 0x301, 0x302
A_GSTAT, A_GLOCK, A_GK = 0x303, 0x304, 0x305
G_OPEN = 0b0011
C_NONE, C_NO_MATCH, C_MATCH, C_FAULT = 0b0000, 0b0101, 0b1010, 0b1111
I8 = (P.INT8_MIN, P.INT8_MAX + 1)
QUICK = os.environ.get("PADAN_QUICK") == "1"
# Siklus dari start diterima sampai keputusan di-commit (docs/rtl_padan.md).
LAT_DECISION = 153


def sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def host_decode(status):
    """Tafsiran host atas STATUS. Hanya kode MATCH dengan idx == ~(~idx) adalah MATCH."""
    code, idx, idx_n = status & 0xF, (status >> 4) & 0xF, (status >> 8) & 0xF
    if code == C_MATCH and idx == (~idx_n & 0xF):
        return (P.MATCH, idx)
    if code == C_NO_MATCH:
        return (P.NO_MATCH, None)
    if code == C_NONE:
        return ("NONE", None)
    return (P.FAULT, None)


def pack(bytes4):
    return sum((int(b) & 0xFF) << (8 * i) for i, b in enumerate(bytes4))


class Host:
    def __init__(self, dut):
        self.dut = dut
        self.lats = []
        dut.avs_read.value = 0
        dut.avs_write.value = 0
        dut.avs_address.value = 0
        dut.avs_writedata.value = 0
        dut.tamper_n.value = 1

    async def reset(self):
        self.dut.rst_n.value = 0
        await Timer(30, "ns")
        self.dut.rst_n.value = 1
        await FallingEdge(self.dut.u.clk)

    async def write(self, addr, data):
        """Tulis Avalon; mengembalikan jumlah siklus waitrequest."""
        d = self.dut
        await FallingEdge(d.u.clk)
        d.avs_address.value = addr
        d.avs_writedata.value = data & 0xFFFFFFFF
        d.avs_write.value = 1
        waits = 0
        while True:
            await Timer(1, "ns")
            if d.avs_waitrequest.value == 0:
                break
            await FallingEdge(d.u.clk)
            waits += 1
        await RisingEdge(d.u.clk)                    # transaksi selesai di sisi ini
        await FallingEdge(d.u.clk)
        d.avs_write.value = 0
        return waits

    async def read(self, addr):
        d = self.dut
        await FallingEdge(d.u.clk)
        d.avs_address.value = addr
        d.avs_read.value = 1
        await Timer(1, "ns")
        assert d.avs_waitrequest.value == 0, "baca tidak boleh menunggu"
        await FallingEdge(d.u.clk)
        d.avs_read.value = 0
        assert d.avs_readdatavalid.value == 1, "readdatavalid harus 1 satu siklus setelah read"
        return d.avs_readdata.value.integer

    async def enroll(self, T):
        await self.write(A_CLR, 0)
        for j in range(P.N):
            for k in range(P.D // 4):
                await self.write(A_ENROLL + j * 32 + k, pack(T[j, 4 * k:4 * k + 4]))

    async def probe(self, p):
        for k in range(P.D // 4):
            await self.write(A_PROBE + k, pack(p[4 * k:4 * k + 4]))

    async def match(self, tau, inject=None):
        """MATCH lalu baca STATUS setelah commit. inject: coroutine fault opsional."""
        d = self.dut
        if inject is not None:
            cocotb.start_soon(inject)
        await self.write(A_MATCH, tau)
        while d.dec_busy.value == 1:
            await FallingEdge(d.u.clk)
        await ReadOnly()
        lat = d.lat.value.integer
        assert lat == LAT_DECISION, f"latensi {lat} != {LAT_DECISION}"
        self.lats.append(lat)
        status = await self.read(A_STATUS)
        return status, host_decode(status)


def golden(T, p, tau):
    return P.decide(P.scores(T, p), tau)


async def setup(dut, seed):
    h = Host(dut)
    await h.reset()
    return h, np.random.default_rng(seed)


@cocotb.test()
async def test_address_scan(dut):
    """Baca seluruh 1024 alamat word: hanya STATUS dan GUARD_STATUS yang bisa bukan
    nol; STATUS hanya berisi keputusan. Tulis ke alamat baca-saja/kosong, dan
    tulis sampah ke GUARD_LOCK/GUARD_K, tidak mengubah apa pun."""
    h, rng = await setup(dut, 11)
    seen_status = set()
    for g in range(2 if QUICK else 3):
        T = rng.integers(*I8, (P.N, P.D))
        p = T[g + 3].copy()                                  # cocok dengan template g+3
        await h.enroll(T)
        await h.probe(p)
        snapshots = []
        for phase in ("setelah enroll", "setelah match"):
            if phase == "setelah match":
                s = P.scores(T, p)
                status, res = await h.match(int(s.max()))
                gold = golden(T, p, int(s.max()))
                assert res == gold and gold[0] == P.MATCH, f"{res} != {gold}"
            vals = [await h.read(a) for a in range(1024)]
            nonzero = {a: v for a, v in enumerate(vals) if v != 0}
            assert set(nonzero) <= {A_STATUS, A_GSTAT}, \
                f"galeri {g} {phase}: alamat bukan-nol {sorted(nonzero)}"
            assert vals[A_GSTAT] & 0xF == G_OPEN, f"guard tidak OPEN: {vals[A_GSTAT]:#x}"
            st = vals[A_STATUS]
            assert st >> 18 == 0 and (st >> 12) & 0xF == 0, f"bit STATUS tak terdefinisi: {st:#x}"
            snapshots.append(vals)
            seen_status.add(st)
        # Tulis sampah ke STATUS dan alamat kosong: tidak mengubah template.
        g0 = await h.read(A_GSTAT)
        # 0x307/0x308: register DEBUG_FAULT, tidak ada di build rilis.
        for a in [A_STATUS, 0x220, 0x2FF, A_GSTAT, A_GLOCK, A_GK, 0x306, 0x307, 0x308, 0x3FF]:
            await h.write(a, 0xA5A5A5A5)
        assert await h.read(A_GSTAT) == g0, "tulis sampah mengubah guard"
        status, res = await h.match(int(P.scores(T, p).max()))
        assert res == golden(T, p, int(P.scores(T, p).max())), "tulis ke alamat lain mengubah template"
    dut._log.info("1024 alamat dibaca per fase; nilai STATUS yang terlihat: %s",
                  sorted(hex(v) for v in seen_status))


@cocotb.test()
async def test_decisions_vs_model(dut):
    """Keputusan identik dengan model/padan.py decide(): data sintetis, acak, ekstrem, seri."""
    h, rng = await setup(dut, 12)
    n = 0
    # 1. Galeri dan probe dari data sintetis bagian 3 docs/padan_model.md, ambang rilis.
    ds = PD.make_dataset()
    await h.enroll(ds["Tq"])
    idxs = rng.choice(len(ds["pq"]), 60 if QUICK else 400, replace=False)
    for i in idxs:
        p = ds["pq"][i]
        await h.probe(p)
        tau = PD.tau_int(float(rng.choice(PD.TAUS)))
        _, res = await h.match(tau)
        assert res == golden(ds["Tq"], p, tau), f"probe sintetis {i} tau {tau}: {res}"
        n += 1
    # 2. Galeri acak, tau tepat di max, max+1, max-1, acak.
    for g in range(2 if QUICK else 4):
        T = rng.integers(*I8, (P.N, P.D))
        await h.enroll(T)
        for k in range(25 if QUICK else 100):
            p = rng.integers(*I8, P.D)
            await h.probe(p)
            m = int(P.scores(T, p).max())
            tau = int(rng.choice([m, m + 1, m - 1, int(rng.integers(-(1 << 31), 1 << 31))]))
            _, res = await h.match(tau)
            assert res == golden(T, p, tau), f"galeri {g} probe {k} tau {tau}: {res}"
            n += 1
    # 3. Seri: template kembar -> indeks terkecil. Ekstrem -128/127.
    T = rng.integers(*I8, (P.N, P.D))
    T[9] = T[4]
    T[14] = T[4]
    await h.enroll(T)
    await h.probe(T[4])
    for tau in (int(P.scores(T, T[4]).max()), int(P.scores(T, T[4]).max()) + 1):
        _, res = await h.match(tau)
        assert res == golden(T, T[4], tau), f"seri: {res}"
        n += 1
    for tv, pv in ((-128, -128), (127, 127), (-128, 127)):
        T = np.full((P.N, P.D), tv)
        T[P.N - 1] = -tv if tv != -128 else 127
        p = np.full(P.D, pv)
        await h.enroll(T)
        await h.probe(p)
        for tau in (2097152, 2097153, -2080768, 0):
            _, res = await h.match(tau)
            assert res == golden(T, p, tau), f"ekstrem T={tv} p={pv} tau={tau}: {res}"
            n += 1
    dut._log.info("%d keputusan identik dengan model; latensi selalu %d siklus", n, LAT_DECISION)


# ---------------------------------------------------------------- fault -------

def flip_reg(handle, bit, width):
    old = handle.value.integer
    handle.value = old ^ (1 << bit)
    return old


async def restore(handle, old):
    """Pulihkan nilai dan tunggu sampai berlaku: tulisan cocotb baru diterapkan di
    akhir timestep, jadi membaca ulang tanpa menunggu memberi nilai yang masih rusak."""
    handle.value = old
    await Timer(1, "ns")
    assert handle.value.integer == old, "nilai tidak terpulihkan"


async def at_tag(dut, vld, row_sig, ch_sig, row, ch):
    m = dut.u.u_mac
    while True:
        await FallingEdge(dut.u.clk)
        if getattr(m, vld).value == 1 and getattr(m, row_sig).value.integer == row \
                and getattr(m, ch_sig).value.integer == ch:
            return


def inj_lane(dut, lane, row, ch, bit):
    async def f():
        await at_tag(dut, "p_vld", "p_row", "p_ch", row, ch)
        flip_reg(dut.u.u_mac.g_lane[lane].prod, bit, 24)
    return f()


def inj_acc(dut, row, ch, bit):
    async def f():
        await at_tag(dut, "a_vld", "a_row", "a_ch", row, ch)
        flip_reg(dut.u.u_mac.acc, bit, 32)
    return f()


def inj_dec(dut, name, bit, row):
    """Flip register komparator setelah baris `row` masuk ke decision."""
    async def f():
        dec = dut.u.u_dec
        while True:
            await FallingEdge(dut.u.clk)
            if dut.u.u_mac.o_vld.value == 1 and dut.u.u_mac.o_row.value.integer == row:
                break
        await FallingEdge(dut.u.clk)                 # setelah register terbarui
        flip_reg(getattr(dec, name), bit, 32)
    return f()


def inj_at_errvld(dut, path, bit):
    """Flip register (abft err, p_err, dll.) pada siklus err_vld, sebelum commit."""
    async def f():
        while True:
            await FallingEdge(dut.u.clk)
            if dut.u.u_chk.err_vld.value == 1:
                break
        obj = dut.u
        for part in path.split("."):
            obj = getattr(obj, part)
        flip_reg(obj, bit, 1)
    return f()


class Campaign:
    """Mencatat hasil setiap fault terhadap keputusan golden skenario."""

    def __init__(self, name, gold):
        self.name, self.gold = name, gold
        self.counts = {}

    def check(self, res, what):
        assert res[0] != "NONE", f"{self.name} {what}: tidak ada keputusan"
        if res[0] == P.MATCH:
            assert res == self.gold, f"{self.name} {what}: MATCH salah {res}, golden {self.gold}"
        kind = "FAULT" if res[0] == P.FAULT else ("sama dengan golden" if res == self.gold else "NO_MATCH")
        self.counts[kind] = self.counts.get(kind, 0) + 1


async def scenario(h, rng, kind):
    """Galeri + probe dengan tau di batas: impostor (golden NO_MATCH, tau = max+1)
    atau genuine (golden MATCH, tau = max)."""
    T = rng.integers(*I8, (P.N, P.D))
    if kind == "impostor":
        p = rng.integers(*I8, P.D)
        p[p == 0] = 1
        tau = int(P.scores(T, p).max()) + 1
    else:
        p = T[6].copy()
        p[p == 0] = 1
        tau = int(P.scores(T, p).max())
    await h.enroll(T)
    await h.probe(p)
    gold = golden(T, p, tau)
    assert gold[0] == (P.NO_MATCH if kind == "impostor" else P.MATCH)
    _, res = await h.match(tau)
    assert res == gold
    return T, p, tau, Campaign(kind, gold)


async def run_campaign(dut, seed, body):
    h, rng = await setup(dut, seed)
    summary = []
    for kind in ("impostor", "genuine"):
        T, p, tau, camp = await scenario(h, rng, kind)
        n = await body(h, rng, T, p, tau, camp)
        _, res = await h.match(tau)                    # kontrol setelah kampanye
        assert res == camp.gold, "run bersih setelah kampanye berbeda"
        summary.append(f"{kind}: {n} fault, {camp.counts}")
    dut._log.info("; ".join(summary))


@cocotb.test()
async def test_fault_datapath(dut):
    """Fault lane dan akumulator tidak pernah menghasilkan MATCH yang salah."""
    async def body(h, rng, T, p, tau, camp):
        n = 0
        lanes = [(l, b) for l in range(L) for b in range(24)]
        accs = [(r, b) for r in range(ROWS) for b in range(32)]
        if QUICK:
            lanes, accs = lanes[::9], accs[::9]
        for lane, bit in lanes:
            row, ch = int(rng.integers(ROWS)), int(rng.integers(CH))
            _, res = await h.match(tau, inj_lane(h.dut, lane, row, ch, bit))
            camp.check(res, f"lane {lane} baris {row} bit {bit}")
            assert res[0] == P.FAULT, f"lane {lane} baris {row} bit {bit}: {res}"
            n += 1
        for row, bit in accs:
            _, res = await h.match(tau, inj_acc(h.dut, row, int(rng.integers(CH)), bit))
            camp.check(res, f"akumulator baris {row} bit {bit}")
            assert res[0] == P.FAULT, f"akumulator baris {row} bit {bit}: {res}"
            n += 1
        return n
    await run_campaign(dut, 21, body)


@cocotb.test()
async def test_fault_memory(dut):
    """Flip setiap bit memori template/checksum: tidak pernah MATCH yang salah.
    Skenario impostor: semua bit; genuine: setiap bit ke-5 (atau sampel di mode cepat)."""
    async def body(h, rng, T, p, tau, camp):
        mem = h.dut.u.u_mem
        cells = [(lane, a, b) for lane in range(L) for a in range(ROWS * CH) for b in range(16)]
        stride = 1 if camp.name == "impostor" else 5
        if QUICK:
            stride = 97
        n = 0
        for lane, addr, bit in cells[::stride]:
            w = mem.g_bank[lane].u_ram.mem[addr]
            old = flip_reg(w, bit, 16)
            _, res = await h.match(tau)
            camp.check(res, f"memori bank {lane} alamat {addr} bit {bit}")
            assert res[0] == P.FAULT, f"memori bank {lane} alamat {addr} bit {bit}: {res}"
            await restore(w, old)
            n += 1
        return n
    await run_campaign(dut, 22, body)


@cocotb.test()
async def test_fault_probe(dut):
    """Flip setiap bit probe (1024) dan setiap bit paritasnya (128): selalu FAULT
    atau keputusan golden. Tanpa paritas, ABFT tidak melihat fault ini."""
    async def body(h, rng, T, p, tau, camp):
        mac = h.dut.u.u_mac
        bits = [("probe", b) for b in range(P.D * 8)] + [("probe_par", b) for b in range(P.D)]
        if QUICK:
            bits = bits[::23]
        n = 0
        for name, bit in bits:
            reg = getattr(mac, name)
            old = reg.value.integer
            reg.value = old ^ (1 << bit)
            _, res = await h.match(tau)
            camp.check(res, f"{name} bit {bit}")
            assert res[0] == P.FAULT, f"{name} bit {bit}: paritas tidak mendeteksi ({res})"
            await restore(reg, old)
            n += 1
        return n
    await run_campaign(dut, 23, body)


@cocotb.test()
async def test_fault_decision(dut):
    """Fault di komparator A/B (tau, best, idx, flag), di sinyal err/p_err sebelum
    commit, dan di register keluaran setelah commit."""
    regs = [("tau_a", 32), ("tau_bn", 32), ("best_a", 32), ("best_b", 32),
            ("idx_a", 4), ("idx_b", 4), ("any_a", 1), ("hit_b", 1)]

    async def body(h, rng, T, p, tau, camp):
        n = 0
        for name, width in regs:
            for bit in range(width):
                if QUICK and bit % 7:
                    continue
                row = int(rng.integers(P.N))
                _, res = await h.match(tau, inj_dec(h.dut, name, bit, row))
                camp.check(res, f"{name} bit {bit} setelah baris {row}")
                n += 1
        for path in ("u_chk.err", "u_mac.p_err"):
            _, res = await h.match(tau, inj_at_errvld(h.dut, path, 0))
            camp.check(res, path)
            assert res[0] == P.FAULT, f"{path}: tidak FAULT"
            n += 1
        # Register keluaran setelah commit: flip lalu baca STATUS.
        dec = h.dut.u.u_dec
        for name in ("code", "idx", "idx_n"):
            for bit in range(4):
                await h.match(tau)
                old = flip_reg(getattr(dec, name), bit, 4)
                res = host_decode(await h.read(A_STATUS))
                camp.check(res, f"keluaran {name} bit {bit}")
                await restore(getattr(dec, name), old)
                n += 1
        return n
    await run_campaign(dut, 24, body)


@cocotb.test()
async def test_fixed_latency(dut):
    """Latensi start -> keputusan sama untuk MATCH, NO_MATCH, dan FAULT; tulis MATCH
    diterima dalam jumlah siklus yang sama saat inti idle."""
    h, rng = await setup(dut, 25)
    T = rng.integers(*I8, (P.N, P.D))
    await h.enroll(T)
    w_enroll = {await h.write(A_ENROLL + 37, pack(T[1, 20:24])) for _ in range(3)}
    w_probe = {await h.write(A_PROBE + 5, 0x01020304) for _ in range(3)}
    assert len(w_enroll) == 1 and len(w_probe) == 1, f"tunggu tulis berbeda: {w_enroll} {w_probe}"
    waits, kinds = set(), set()
    for k in range(40):
        p = T[k % P.N] if k % 3 == 0 else rng.integers(*I8, P.D)
        await h.probe(p)
        m = int(P.scores(T, p).max())
        tau = m if k % 2 == 0 else m + 1
        inject = inj_acc(dut, int(rng.integers(ROWS)), 0, int(rng.integers(32))) if k % 5 == 4 else None
        await FallingEdge(dut.u.clk)
        while dut.u.u_chk.busy.value == 1:        # lokalisasi diagnostik run sebelumnya
            await FallingEdge(dut.u.clk)
        if inject is not None:
            cocotb.start_soon(inject)
        waits.add(await h.write(A_MATCH, tau))
        while dut.dec_busy.value == 1:
            await FallingEdge(dut.u.clk)
        await ReadOnly()
        assert dut.lat.value.integer == LAT_DECISION
        res = host_decode(await h.read(A_STATUS))
        kinds.add(res[0])
    assert kinds == {P.MATCH, P.NO_MATCH, P.FAULT}, f"jenis keputusan yang teruji: {kinds}"
    assert len(waits) == 1, f"siklus tunggu MATCH berbeda-beda: {waits}"
    dut._log.info("latensi keputusan %d siklus untuk %s; waitrequest saat idle: MATCH %d, "
                  "ENROLL (4 byte) %d, PROBE (4 byte) %d siklus",
                  LAT_DECISION, sorted(kinds), waits.pop(), w_enroll.pop(), w_probe.pop())
