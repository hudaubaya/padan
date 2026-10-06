"""Test build debug (DEBUG_FAULT): injeksi fault terkendali host lewat DBG_FAULT,
deteksi (STATUS = FAULT) dan lokalisasi ABFT (DBG_ABFT) dibaca lewat Avalon-MM.

Build: tb/debug/Makefile (-DDEBUG_FAULT, FAULT_MAX = 65535 supaya ratusan injeksi
tidak memicu HALT). Bahwa build rilis tidak punya port dan logika ini dibuktikan
terpisah oleh tb/debug/check_release.py.
"""

import cocotb
import numpy as np

import padan as P
import test_avmm as TA
from test_avmm import A_GLOCK, C_FAULT, I8

A_DBG_FAULT, A_DBG_ABFT, A_GTAU = 0x307, 0x308, 0x306
LOCK_MAGIC = 0x4C4F434B
L, CH, ROWS = 16, P.D // 16, P.N + 2


def dbg_word(lane, row, ch, delta, en=1):
    return (en & 1) | (lane & 0xF) << 1 | (row & 0x1F) << 5 | (ch & 7) << 10 | (delta & 0xFFFF) << 16


def abft_fields(v):
    return dict(loc_idx=v & 0xFF, loc_vld=(v >> 8) & 1, err=(v >> 9) & 1, chk=(v >> 10) & 1,
                done=(v >> 11) & 1, rest=v >> 12)


async def abft_result(h):
    """Tunggu lokalisasi selesai (hingga N siklus setelah keputusan), lalu baca DBG_ABFT."""
    for _ in range(4 * P.N):
        f = abft_fields(await h.read(A_DBG_ABFT))
        if f["done"]:
            return f
    raise AssertionError("pemeriksaan ABFT tidak selesai")


async def setup(dut, seed):
    h = TA.Host(dut)
    await h.reset()
    rng = np.random.default_rng(seed)
    T = rng.integers(*I8, (P.N, P.D))
    p = rng.integers(*I8, P.D)
    p[p == 0] = 1                                   # setiap lane/chunk ikut terpakai
    await h.enroll(T)
    await h.probe(p)
    return h, rng, T, p


async def inject_and_match(h, T, p, lane, row, ch, delta):
    await h.write(A_DBG_FAULT, dbg_word(lane, row, ch, delta))
    status, res = await h.match(int(P.scores(T, p).max()))
    return status, res, await abft_result(h)


@cocotb.test()
async def test_debug_build_clean(dut):
    """Build debug: STATUS[31] = 1. Tanpa injeksi (atau delta 0) keputusan = model dan
    ABFT bersih."""
    h, rng, T, p = await setup(dut, 1)
    tau = int(P.scores(T, p).max())
    status, res = await h.match(tau)
    assert status >> 31 == 1, f"STATUS[31] harus menandai build debug: {status:#x}"
    assert res == TA.golden(T, p, tau)
    f = await abft_result(h)
    assert f == dict(loc_idx=0, loc_vld=0, err=0, chk=0, done=1, rest=0), f
    for word in (dbg_word(3, 5, 2, 0), dbg_word(3, 5, 2, 100, en=0)):
        await h.write(A_DBG_FAULT, word)
        _, res = await h.match(tau)
        assert res == TA.golden(T, p, tau), f"{word:#x}: {res}"
        f = await abft_result(h)
        assert f["err"] == 0, f"{word:#x}: {f}"


@cocotb.test()
async def test_inject_detect_localize(dut):
    """Setiap lane (16) x setiap baris (16 skor + C + Cw), chunk dan delta acak:
    keputusan selalu FAULT; galat di baris skor j dilokalisasi ke j; galat di baris
    checksum terdeteksi sebagai chk (tidak ada skor yang disalahkan)."""
    h, rng, T, p = await setup(dut, 2)
    n = 0
    for lane in range(L):
        for row in range(ROWS):
            ch = int(rng.integers(0, CH))
            delta = int(rng.choice([1, -1, 32767, -32768, int(rng.integers(-32768, 32768)) or 7]))
            status, res, f = await inject_and_match(h, T, p, lane, row, ch, delta)
            where = f"lane {lane} baris {row} chunk {ch} delta {delta}"
            assert status & 0xF == C_FAULT and res == (P.FAULT, None), f"{where}: tidak FAULT ({res})"
            assert f["err"] == 1, f"{where}: ABFT tidak mendeteksi: {f}"
            if row < P.N:
                assert f["loc_vld"] == 1 and f["loc_idx"] == row and f["chk"] == 0, \
                    f"{where}: lokalisasi salah: {f}"
            else:
                assert f["loc_vld"] == 0 and f["chk"] == 1, f"{where}: checksum: {f}"
            n += 1
    await h.write(A_DBG_FAULT, 0)
    tau = int(P.scores(T, p).max())
    _, res = await h.match(tau)
    assert res == TA.golden(T, p, tau), "injeksi tidak berhenti setelah dimatikan"
    dut._log.info("%d injeksi: semua FAULT, %d dilokalisasi ke barisnya, %d di checksum",
                  n, L * P.N, L * 2)


@cocotb.test()
async def test_delta_is_data_independent(dut):
    """Delta aditif: residu d1 = delta dan d2 = (j+1)*delta untuk template dan probe
    apa pun, jadi lokalisasi yang dibaca host tidak membawa informasi T atau p.
    (d1/d2 dibaca dari dalam simulasi; host tidak punya akses ke keduanya.)"""
    seen = set()
    for seed in (3, 4, 5):
        h, rng, T, p = await setup(dut, seed)
        for lane, row, ch, delta in ((0, 0, 0, 5), (7, 9, 3, -1234), (15, 15, 7, 32767)):
            _, _, f = await inject_and_match(h, T, p, lane, row, ch, delta)
            d1, d2 = dut.u.u_chk.d1.value.signed_integer, dut.u.u_chk.d2.value.signed_integer
            assert (d1, d2) == (delta, (row + 1) * delta), f"seed {seed}: d1/d2 = {(d1, d2)}"
            seen.add((lane, row, ch, delta, f["loc_idx"], f["loc_vld"], f["err"], f["chk"]))
        await h.write(A_DBG_FAULT, 0)
    assert len(seen) == 3, f"hasil yang terlihat host bergantung pada data: {sorted(seen)}"


@cocotb.test()
async def test_inject_only_in_open(dut):
    """Setelah LOCK, injeksi yang sudah aktif tidak berlaku dan DBG_FAULT ditolak."""
    h, rng, T, p = await setup(dut, 6)
    tau = int(P.scores(T, p).max())
    await h.write(A_DBG_FAULT, dbg_word(2, 4, 1, 999))
    _, res = await h.match(tau)
    assert res == (P.FAULT, None)
    await h.write(A_GTAU, tau)
    await h.write(A_GLOCK, LOCK_MAGIC)
    _, res = await h.match(tau)
    assert res == TA.golden(T, p, tau), f"injeksi masih berlaku setelah LOCK: {res}"
    await h.write(A_DBG_FAULT, dbg_word(5, 6, 0, 77))
    assert dut.u.dbg_lane.value.integer == 2, "DBG_FAULT diterima setelah LOCK"
    _, res = await h.match(tau)
    assert res == TA.golden(T, p, tau)
