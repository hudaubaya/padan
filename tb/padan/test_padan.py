"""Test cocotb RTL PADAN (template_mem + mac_array + abft_check) terhadap model/padan.py.

Parameter rilis: N = 16 template, D = 128 byte, L = 16 lane, 8 siklus per dot product.
PADAN_QUICK=1 memperkecil jumlah kasus (dipakai uji mutasi).
"""

import os
import random

import numpy as np

import cocotb
from cocotb.triggers import FallingEdge, First, ReadOnly, RisingEdge, Timer

import padan as P

QUICK = os.environ.get("PADAN_QUICK") == "1"
L = 16
CH = P.D // L
ROWS = P.N + 2                      # skor 0..N-1, C.p, Cw.p
ROW_C, ROW_CW = P.N, P.N + 1
# Latensi relatif ke sisi naik yang menerima start (docs/rtl_padan.md):
# baris r keluar pada siklus 12 + 8r (alamat 1 + 8r + 7, lalu M, P, T1, T2, A);
# tanpa fault, done pada siklus 151 (baris terakhir 148, lalu S_ACC, S_DIFF, S_LOC).
LAT_ROW0 = 12
LAT_DONE = LAT_ROW0 + CH * (ROWS - 1) + 3
I8 = (P.INT8_MIN, P.INT8_MAX + 1)


def sx(v, bits):
    """Tafsirkan integer tak bertanda `bits` bit sebagai two's complement."""
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def expected_rows(T, p):
    C, Cw = P.checksum_rows(T)
    return [int(x) for x in P.scores(T, p)] + [int(C @ p), int(Cw @ p)]


class Padan:
    def __init__(self, dut):
        self.dut = dut
        self.runs = 0
        self.clean_runs = 0
        for s in ("bus_wr", "bus_addr", "bus_wdata", "clr", "p_wr", "p_addr", "p_wdata", "start"):
            getattr(dut, s).value = 0

    async def reset(self):
        self.dut.rst_n.value = 0
        for _ in range(3):
            await RisingEdge(self.dut.clk)
        self.dut.rst_n.value = 1
        await RisingEdge(self.dut.clk)

    async def _bus(self, **drive):
        """Satu permintaan bus. Sinyal hanya dinaikkan di sisi turun saat bus_ready,
        jadi diterima tepat sekali pada sisi naik berikutnya."""
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            if d.bus_ready.value == 1:
                break
        for k, v in drive.items():
            getattr(d, k).value = v
        await RisingEdge(d.clk)
        d.bus_wr.value = 0
        d.clr.value = 0

    async def clear(self):
        await self._bus(clr=1)
        await self.idle()

    async def idle(self):
        while True:
            await FallingEdge(self.dut.clk)
            if self.dut.mem_busy.value == 0:
                return

    async def write_template(self, T, order=None, rows=None):
        d = self.dut
        cells = [(j, i) for j in (rows if rows is not None else range(P.N)) for i in range(P.D)]
        if order is not None:
            order.shuffle(cells)
        for j, i in cells:
            await self._bus(bus_wr=1, bus_addr=j * P.D + i, bus_wdata=int(T[j, i]) & 0xFF)
        await self.idle()

    async def write_probe(self, p):
        d = self.dut
        await FallingEdge(d.clk)
        for i in range(P.D):
            d.p_addr.value = i
            d.p_wdata.value = int(p[i]) & 0xFF
            d.p_wr.value = 1
            await FallingEdge(d.clk)
        d.p_wr.value = 0

    def mem_word(self, lane, addr):
        return self.dut.u_mem.g_bank[lane].u_ram.mem[addr]

    def stored_checksums(self):
        """(C, Cw) seperti tersimpan di bank memori, untuk dibandingkan dengan model."""
        C = np.zeros(P.D, dtype=np.int64)
        Cw = np.zeros(P.D, dtype=np.int64)
        for lane in range(L):
            for c in range(CH):
                C[c * L + lane] = sx(self.mem_word(lane, P.N * CH + c).value.integer, 16)
                Cw[c * L + lane] = sx(self.mem_word(lane, P.N * CH + CH + c).value.integer, 16)
        return C, Cw

    async def run(self, inject=None):
        """Satu start: N+2 baris lalu pemeriksaan ABFT. inject: coroutine fault opsional."""
        d = self.dut
        while True:                                  # start dinaikkan hanya saat pasti diterima
            await FallingEdge(d.clk)
            if d.busy.value == 0 and d.u_mac.hold.value == 0:
                break
        d.start.value = 1
        await RisingEdge(d.clk)
        d.start.value = 0
        if inject is not None:
            cocotb.start_soon(inject)
        done = await First(RisingEdge(d.done), Timer(20, "us"))
        assert done is not None and d.done.value == 1, "abft_check tidak selesai (timeout)"
        await FallingEdge(d.clk)
        v = d.rows.value.integer
        self.runs += 1
        return {
            "rows": [sx(v >> (32 * r), 32) for r in range(ROWS)],
            "n_out": d.n_out.value.integer,
            "err": int(d.err.value), "loc_vld": int(d.loc_vld.value),
            "loc_idx": d.loc_idx.value.integer, "chk": int(d.chk.value),
            "d1": sx(d.d1.value.integer, 40), "d2": sx(d.d2.value.integer, 40),
        }

    def check_clean(self, r, T, p, what):
        exp = expected_rows(T, p)
        assert r["n_out"] == ROWS, f"{what}: {r['n_out']} baris keluar"
        assert r["rows"] == exp, f"{what}: baris RTL {r['rows']} != model {exp}"
        assert (r["err"], r["d1"], r["d2"], r["loc_vld"], r["chk"]) == (0, 0, 0, 0, 0), \
            f"{what}: alarm palsu {r}"
        self.clean_runs += 1

    def check_fault(self, r, T, p, row, E, what):
        """Galat E (eksak) pada baris `row`: skor -> lokalisasi `row`; checksum -> chk."""
        exp = expected_rows(T, p)
        assert E != 0, f"{what}: fault tanpa efek"
        if row < P.N:
            exp[row] = P.wrap(exp[row] + E)
            e = exp[row] - expected_rows(T, p)[row]          # galat setelah wrap 32 bit
            d1, d2 = e, (row + 1) * e
        else:
            exp[row] = P.wrap(exp[row] + E)
            e = exp[row] - expected_rows(T, p)[row]
            d1, d2 = (-e, 0) if row == ROW_C else (0, -e)
        assert r["rows"] == exp, f"{what}: baris RTL != model+galat"
        assert (r["d1"], r["d2"]) == (d1, d2), f"{what}: (d1,d2)={r['d1'], r['d2']} != {(d1, d2)}"
        assert r["err"] == 1, f"{what}: tidak terdeteksi"
        if row < P.N:
            assert (r["loc_vld"], r["loc_idx"]) == (1, row), \
                f"{what}: lokalisasi {r['loc_vld'], r['loc_idx']} != (1, {row})"
        else:
            assert (r["loc_vld"], r["chk"]) == (0, 1), f"{what}: fault checksum menyalahkan skor"


def rand_T(rng):
    return rng.integers(*I8, (P.N, P.D))


def rand_p(rng, nonzero=False):
    p = rng.integers(*I8, P.D)
    if nonzero:
        p[p == 0] = 1
    return p


async def setup(dut, seed):
    h = Padan(dut)
    await h.reset()
    await h.clear()
    return h, np.random.default_rng(seed)


@cocotb.test()
async def test_release_params(dut):
    """Parameter rilis dan throughput: satu dot product D = 128 per 8 siklus."""
    assert (int(dut.N.value), int(dut.D.value), int(dut.L.value)) == (16, 128, 16)
    assert (int(dut.u_mac.N.value), int(dut.u_mem.N.value), int(dut.u_chk.N.value)) == (16, 16, 16)
    h, rng = await setup(dut, 1)

    async def busy_cycles(**req):
        """Siklus dari sisi naik yang menerima permintaan bus sampai bus_ready lagi."""
        await h._bus(**req)
        n = 0
        while True:
            await ReadOnly()
            if dut.bus_ready.value == 1:
                return n
            await RisingEdge(dut.clk)
            n += 1

    n_clr = await busy_cycles(clr=1)
    n_wr = await busy_cycles(bus_wr=1, bus_addr=5, bus_wdata=0x80)
    assert (n_clr, n_wr) == (ROWS * CH, 5), f"clr {n_clr} siklus, tulis byte {n_wr} siklus"
    dut._log.info("clr: bus_ready lagi setelah %d siklus; tulis byte: setelah %d siklus", n_clr, n_wr)

    T, p = rand_T(rng), rand_p(rng)
    await h.write_template(T)
    await h.write_probe(p)

    async def count():
        """Siklus (relatif ke sisi naik yang menerima start) tiap hasil baris dan done."""
        await RisingEdge(dut.u_mac.o_start)
        await RisingEdge(dut.clk)                    # siklus 0: start diterima
        cyc, seen = 0, []
        while True:
            await RisingEdge(dut.clk)
            cyc += 1
            await ReadOnly()
            if dut.u_mac.o_vld.value == 1:
                seen.append(cyc)
            if dut.done.value == 1:
                return seen, cyc

    t = cocotb.start_soon(count())
    r = await h.run()
    h.check_clean(r, T, p, "params")
    seen, done = t.result()
    assert seen == [LAT_ROW0 + CH * r for r in range(ROWS)], f"hasil baris pada siklus {seen}"
    assert done == LAT_DONE, f"done pada siklus {done}, harapan {LAT_DONE}"
    dut._log.info("hasil baris 0 pada siklus %d, lalu tiap %d siklus; done pada siklus %d",
                  seen[0], CH, done)


@cocotb.test()
async def test_random_pairs(dut):
    """1000 pasangan (galeri, probe) acak INT8 identik dengan model/padan.py."""
    h, rng = await setup(dut, 2)
    galleries, per = (2, 50) if QUICK else (10, 100)
    order = random.Random(2)
    T = None
    for g in range(galleries):
        T_new = rand_T(rng)
        if g % 2 == 0:
            await h.clear()                                  # mulai dari nol
            await h.write_template(T_new, order=order)
        else:
            await h.write_template(T_new, order=order)       # tulis ulang tanpa clear
        T = T_new
        C, Cw = P.checksum_rows(T)
        sC, sCw = h.stored_checksums()
        assert np.array_equal(sC, C) and np.array_equal(sCw, Cw), f"galeri {g}: C/Cw generator != model"
        for k in range(per):
            p = rand_p(rng)
            await h.write_probe(p)
            h.check_clean(await h.run(), T, p, f"galeri {g} probe {k}")
    # Tulis ulang satu template saja: generator harus tetap konsisten.
    j = 7
    T[j] = rand_T(rng)[0]
    await h.write_template(T, rows=[j])
    assert all(np.array_equal(a, b) for a, b in zip(h.stored_checksums(), P.checksum_rows(T)))
    p = rand_p(rng)
    await h.write_probe(p)
    h.check_clean(await h.run(), T, p, "tulis ulang template 7")
    dut._log.info("%d pasangan identik dengan model, tanpa alarm", galleries * per + 1)


@cocotb.test()
async def test_extremes(dut):
    """Nilai ekstrem -128 dan 127, termasuk batas Cw.p = 285.212.672 dan -282.984.448."""
    h, rng = await setup(dut, 3)
    alt = np.where(np.arange(P.D) % 2 == 0, -128, 127)
    cases = {
        "T=-128": np.full((P.N, P.D), -128), "T=127": np.full((P.N, P.D), 127),
        "T bergantian": np.tile(alt, (P.N, 1)),
        "T acak ekstrem": rng.choice([-128, 127], (P.N, P.D)),
    }
    probes = {"p=-128": np.full(P.D, -128), "p=127": np.full(P.D, 127), "p bergantian": alt,
              "p=0": np.zeros(P.D, dtype=np.int64)}
    seen_cwp = set()
    for tn, T in cases.items():
        await h.write_template(T)
        for pn, p in probes.items():
            await h.write_probe(p)
            r = await h.run()
            h.check_clean(r, T, p, f"{tn}, {pn}")
            seen_cwp.add(r["rows"][ROW_CW])
    assert 285212672 in seen_cwp and -282984448 in seen_cwp, "batas Cw.p tidak tercapai"


def lane_fault(dut, lane, row, ch, bit, out):
    async def inj():
        while True:
            await FallingEdge(dut.clk)
            m = dut.u_mac
            if m.p_vld.value == 1 and m.p_row.value.integer == row and m.p_ch.value.integer == ch:
                reg = m.g_lane[lane].prod
                old = reg.value.integer
                reg.value = old ^ (1 << bit)
                out.append(sx(old ^ (1 << bit), 24) - sx(old, 24))
                return
    return inj()


def acc_fault(dut, row, ch, bit, out):
    async def inj():
        while True:
            await FallingEdge(dut.clk)
            m = dut.u_mac
            if m.a_vld.value == 1 and m.a_row.value.integer == row and m.a_ch.value.integer == ch:
                old = m.acc.value.integer
                m.acc.value = old ^ (1 << bit)
                out.append(sx(old ^ (1 << bit), 32) - sx(old, 32))
                return
    return inj()


@cocotb.test()
async def test_fault_lanes(dut):
    """Bit flip pada register produk setiap lane: terdeteksi, indeks benar."""
    h, rng = await setup(dut, 4)
    T, p = rand_T(rng), rand_p(rng)
    await h.write_template(T)
    await h.write_probe(p)
    cases = [(l, (l + b) % P.N, b) for l in range(L) for b in range(24)]          # tiap bit tiap lane
    cases += [(l, j, int(rng.integers(24))) for l in range(L) for j in range(ROWS)]  # tiap baris tiap lane
    if QUICK:
        cases = cases[::7]
    for lane, row, bit in cases:
        ch = int(rng.integers(CH))
        E = []
        r = await h.run(lane_fault(dut, lane, row, ch, bit, E))
        assert len(E) == 1, "fault tidak tersuntik"
        h.check_fault(r, T, p, row, E[0], f"lane {lane} baris {row} chunk {ch} bit {bit}")
    h.check_clean(await h.run(), T, p, "setelah fault lane")
    dut._log.info("%d fault lane: semua terdeteksi, indeks benar", len(cases))


@cocotb.test()
async def test_fault_accumulator(dut):
    """Bit flip 0..31 pada akumulator di setiap baris: terdeteksi, indeks benar (termasuk bit 27-31)."""
    h, rng = await setup(dut, 5)
    T, p = rand_T(rng), rand_p(rng)
    await h.write_template(T)
    await h.write_probe(p)
    cases = [(row, bit) for row in range(ROWS) for bit in range(32)]
    if QUICK:
        cases = cases[::5]
    for row, bit in cases:
        ch = int(rng.integers(CH))
        E = []
        r = await h.run(acc_fault(dut, row, ch, bit, E))
        assert len(E) == 1, "fault tidak tersuntik"
        h.check_fault(r, T, p, row, E[0], f"akumulator baris {row} chunk {ch} bit {bit}")
    h.check_clean(await h.run(), T, p, "setelah fault akumulator")
    dut._log.info("%d fault akumulator: semua terdeteksi, indeks benar", len(cases))


@cocotb.test()
async def test_fault_memory(dut):
    """Bit flip pada setiap bit setiap word memori (T, C, Cw): terdeteksi, indeks benar.

    Probe tanpa elemen nol: dengan p_i = 0 fault T[j,i] tidak mengubah skor (model,
    docs/padan_model.md), jadi tidak ada yang perlu dideteksi.
    """
    h, rng = await setup(dut, 6)
    T, p = rand_T(rng), rand_p(rng, nonzero=True)
    await h.write_template(T)
    await h.write_probe(p)
    words = [(lane, addr) for lane in range(L) for addr in range(ROWS * CH)]
    bits = range(16)
    if QUICK:
        words = words[::37]
    n = 0
    for lane, addr in words:
        w = h.mem_word(lane, addr)
        old = w.value.integer
        row, c = divmod(addr, CH)
        i = c * L + lane
        for bit in bits:
            w.value = old ^ (1 << bit)
            r = await h.run()
            delta = sx(old ^ (1 << bit), 16) - sx(old, 16)
            h.check_fault(r, T, p, row, delta * int(p[i]), f"memori bank {lane} alamat {addr} bit {bit}")
            n += 1
        w.value = old
    h.check_clean(await h.run(), T, p, "setelah fault memori")
    dut._log.info("%d fault bit memori: semua terdeteksi, indeks benar", n)


@cocotb.test()
async def test_no_false_alarm(dut):
    """Tanpa fault tidak ada alarm: probe acak (termasuk elemen nol) dan galeri jarang."""
    h, rng = await setup(dut, 7)
    T = rand_T(rng)
    T[rng.random(T.shape) < 0.3] = 0
    await h.write_template(T)
    for k in range(50 if QUICK else 300):
        p = rand_p(rng)
        p[rng.random(P.D) < 0.2] = 0
        await h.write_probe(p)
        h.check_clean(await h.run(), T, p, f"probe {k}")
    dut._log.info("%d run tanpa fault: tidak ada alarm", h.clean_runs)
