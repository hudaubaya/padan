"""Audit Iterative MAC #0040 apa adanya terhadap model/iterative_mac.py (level pin, RTL dan GL).

Setiap test memeriksa perilaku yang *benar*; cacat terkonfirmasi diberi
expect_fail dan ID temuan (I1, I2, ...) dari docs/baseline_audit.md.
Input diubah di sisi turun; uo_out disampel di sisi turun berikutnya.
"""

import random

import cocotb
from cocotb.triggers import FallingEdge

import iterative_mac as M
from audit_util import VIEW, Record, reset, start

PERIOD_NS = 100
GL = VIEW == "gl"
REC = Record("iterative_mac")


async def step(dut, ui, uio):
    """Pasang input, lewati satu sisi naik, kembalikan uo_out sesudahnya."""
    dut.ui_in.value = ui
    dut.uio_in.value = uio
    await FallingEdge(dut.clk)
    return int(dut.uo_out.value)


async def run_mode1(dut, a, groups):
    """Reset mode 1 dengan bobot a, jalankan operasi [(bs, cs)], kembalikan hasil 32 bit."""
    await reset(dut, cycles=2, ui_in=0x80 | a)
    seq = [(0, 0)]                                   # sisi pertama: state 0 (tanpa operasi)
    for bs, cs in groups:
        seq += list(zip(bs, cs))
    seq += [(0, 0)] * 3                              # keluarkan 3 byte terakhir
    outs = [await step(dut, ui, uio) for ui, uio in seq]
    res = []
    for g in range(len(groups)):
        k = 4 + 4 * g                                # sisi state 4 operasi g
        res.append(sum(outs[k + i] << (24 - 8 * i) for i in range(4)))
    return res


def rand_groups(rng, n, hi_b=255, hi_c=255):
    return [([rng.randint(0, hi_b) for _ in range(4)], [rng.randint(0, hi_c) for _ in range(4)])
            for _ in range(n)]


@cocotb.test()
async def test_multiplier_7x8_exhaustive(dut):
    """Pengali 7x8: semua 128 x 256 pasangan, dibaca lewat pin.

    Sisi naik pertama setelah reset menyimpan out = a*b ke result[30:16];
    uo_out lalu menampilkan out[14:8] dan out[7:0] di dua siklus berikutnya.
    Mode (ui_in[7]) bergantian agar kedua mode tercakup.
    """
    await start(dut, PERIOD_NS)
    bad = []
    for a in range(128):
        for b in range(256):
            await reset(dut, cycles=1, ui_in=((b & 1) << 7) | a)
            hi = await step(dut, b, 0)
            lo = await step(dut, 0, 0)
            got = (hi << 8) | lo
            if got != M.mul7x8(a, b):
                bad.append((a, b, got))
    REC.put("multiplier_pairs_wrong", [len(bad), 128 * 256])
    assert not bad, f"{len(bad)} produk salah, contoh {bad[:5]}"


@cocotb.test()
async def test_mode1_mac_random(dut):
    """Mode 1: R = floor(a*B/2^8) + C (mod 2^32) untuk operand acak.

    Juga mencatat berapa operasi melewati cabang out_th (state 5..7, RTL) dan
    berapa yang melampaui 32 bit (I4).
    """
    await start(dut, PERIOD_NS)
    rng = random.Random(40)
    n_ops = n_over = n_th = 0
    states = set()
    for _ in range(200):
        a = rng.randrange(128)
        groups = rand_groups(rng, 8)
        if not GL:
            seen = []
            mon = cocotb.start_soon(_watch_state(dut, seen))
        got = await run_mode1(dut, a, groups)
        if not GL:
            mon.kill()
            states |= set(seen)
        for (bs, cs), r in zip(groups, got):
            exact = M.mac(a, bs, cs)
            assert r == exact & M.MASK32, \
                f"a={a} b={bs} c={cs}: {r:#010x} != {exact & M.MASK32:#010x}"
            n_ops += 1
            n_over += exact > M.MASK32
            n_th += any(a * b >= 2048 for b in bs[:3])
    REC.put("mode1_random", dict(ops=n_ops, over_32bit=n_over, ops_with_out_th=n_th,
                                 states_seen=sorted(states) if not GL else None))


async def _watch_state(dut, seen):
    while True:
        await FallingEdge(dut.clk)
        seen.append(int(dut.dut.state.value))


@cocotb.test()
async def test_mode1_extremes_mod_2_32(dut):
    """Mode 1, nilai ekstrem: R = (floor(a*B/2^8) + C) mod 2^32 (karakterisasi I4)."""
    await start(dut, PERIOD_NS)
    vals = (0, 1, 127, 128, 254, 255)
    rng = random.Random(41)
    for a in (0, 1, 64, 126, 127):
        groups = [((255,) * 4, (255,) * 4), ((255,) * 4, (0,) * 4), ((0,) * 4, (255,) * 4)]
        groups += [([rng.choice(vals) for _ in range(4)], [rng.choice(vals) for _ in range(4)])
                   for _ in range(12)]
        got = await run_mode1(dut, a, groups)
        for (bs, cs), r in zip(groups, got):
            assert r == M.mac(a, bs, cs) & M.MASK32, f"a={a} b={bs} c={cs}"


@cocotb.test(expect_fail=True)
async def test_I4_mode1_no_silent_overflow(dut):
    """[I4] Hasil yang melampaui 32 bit tidak terpotong diam-diam."""
    await start(dut, PERIOD_NS)
    a, groups = 127, [((255,) * 4, (255,) * 4), ((128, 0, 0, 0), (0, 0, 0x80, 0))]
    got = await run_mode1(dut, a, groups)
    exact = [M.mac(a, bs, cs) for bs, cs in groups]
    REC.put("I4_example", dict(a=a, groups=[list(map(list, g)) for g in groups],
                               exact=[hex(e) for e in exact], observed=[hex(r) for r in got]))
    assert got == exact, f"eksak {[hex(e) for e in exact]}, keluar {[hex(r) for r in got]}"


@cocotb.test(expect_fail=True)
async def test_I1_mode0_output_follows_inputs(dut):
    """[I1] Mode 0: hasil akumulasi terlihat di uo_out/uio_out (tidak selalu 0)."""
    await start(dut, PERIOD_NS)
    rng = random.Random(42)
    await reset(dut, cycles=2, ui_in=0x00 | 100)     # mode 0, a = 100
    outs = []
    for k in range(64):
        uo = await step(dut, rng.randrange(1, 256), rng.randrange(256))
        uio = dut.uio_out.value
        outs.append((uo, int(uio) if uio.is_resolvable else None))
    tail = outs[3:]
    REC.put("I1_mode0_nonzero_outputs", sum(1 for uo, uio in tail if uo or uio))
    assert any(uo or uio for uo, uio in tail), "uo_out dan uio_out selalu 0 di mode 0"


@cocotb.test(skip=GL)
async def test_mode0_internal_sum_accumulates(dut):
    """(RTL, sinyal internal) Mode 0: sum += out<<16 + uio_in<<8 setiap clock.

    Akumulasi memang terjadi di dalam, tetapi `result` tidak pernah menerimanya (I1).
    """
    await start(dut, PERIOD_NS)
    rng = random.Random(43)
    a = 100
    await reset(dut, cycles=2, ui_in=a)
    await step(dut, 0, 0)                            # state 0
    acc = 0
    for _ in range(200):
        b, c = rng.randrange(256), rng.randrange(256)
        await step(dut, b, c)
        acc = (acc + ((a * b) << 16) + (c << 8)) & M.MASK32
        assert int(dut.dut.sum.value) == acc
        assert int(dut.dut.state.value) == 1, "mode 0 tetap di state 1"
        assert int(dut.dut.result.value) == 0


@cocotb.test()
async def test_I2_uio_direction(dut):
    """[I2, karakterisasi] uio_oe = 0xFF di mode 0 dan 0x00 di mode 1.

    Di mode 0 pin uio menjadi keluaran, padahal state 1 tetap menjumlahkan
    uio_in sebagai bias; di chip uio_in membaca balik keluaran sendiri.
    """
    await start(dut, PERIOD_NS)
    oe = {}
    for mode in (0, 1):
        await reset(dut, cycles=2, ui_in=(mode << 7) | 5)
        await step(dut, 3, 0)
        oe[mode] = int(dut.uio_oe.value)
    REC.put("I2_uio_oe", oe)
    assert oe == {0: 0xFF, 1: 0x00}, oe
