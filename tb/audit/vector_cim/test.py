"""Audit 8-bit Vector Compute-in-SRAM #0642 apa adanya terhadap model/vector_cim.py.

Level pin, RTL dan GL. Setiap test memeriksa perilaku yang *benar*; temuan
terkonfirmasi diberi expect_fail dan ID (V1, ...) dari docs/baseline_audit.md.

Protokol: ui_in = {op[1:0], address[5:0]}, uio_in = data. LOAD_W=00, LOAD_A=01,
READ_S=10, NOP=11. Setelah satu clock READ_S, tiga sisi naik berikutnya
mengeluarkan S[18:16], S[15:8], S[7:0] di uo_out. Input diubah di sisi turun.
"""

import random

import cocotb
import numpy as np
from cocotb.triggers import FallingEdge

import vector_cim as M
from audit_util import VIEW, Record, start

PERIOD_NS = 10
GL = VIEW == "gl"
REC = Record("vector_cim")
LOAD_W, LOAD_A, READ_S, NOP = 0, 1, 2, 3


async def cmd(dut, op, addr=0, data=0):
    dut.ui_in.value = (op << 6) | addr
    dut.uio_in.value = data
    await FallingEdge(dut.clk)
    return int(dut.uo_out.value)


async def load(dut, w=None, a=None):
    for i in range(M.N):
        if w is not None:
            await cmd(dut, LOAD_W, i, int(w[i]))
        if a is not None:
            await cmd(dut, LOAD_A, i, int(a[i]))


async def read_s(dut):
    await cmd(dut, READ_S)
    b = [await cmd(dut, NOP) for _ in range(3)]
    return (b[0] << 16) | (b[1] << 8) | b[2], b


async def dot(dut, w, a):
    await load(dut, w, a)
    return (await read_s(dut))[0]


def extreme_vectors():
    full, zero = [255] * 8, [0] * 8
    cases = [(full, full), (zero, zero), (full, zero), ([128] * 8, [128] * 8),
             ([255] * 7 + [0], full), ([254] * 8, [255] * 8)]
    for i in range(8):                       # satu elemen maksimum di tiap posisi
        one = [0] * 8
        one[i] = 255
        cases.append((one, full))
    for k in range(1, 9):                    # k elemen maksimum: carry di setiap level pohon
        cases.append(([255] * k + [0] * (8 - k), full))
    rng = random.Random(64)
    vals = (0, 1, 127, 128, 129, 254, 255)
    cases += [([rng.choice(vals) for _ in range(8)], [rng.choice(vals) for _ in range(8)])
              for _ in range(100)]
    return cases


@cocotb.test()
async def test_dot_random(dut):
    """Dot product 8 elemen acak penuh 0..255 = model."""
    await start(dut, PERIOD_NS)
    rng = np.random.default_rng(642)
    n = 1000
    for k in range(n):
        w, a = rng.integers(0, 256, 8), rng.integers(0, 256, 8)
        got = await dot(dut, w, a)
        assert got == M.dot(w, a), f"w={w.tolist()} a={a.tolist()}: {got} != {M.dot(w, a)}"
    REC.put("dot_random", n)


@cocotb.test()
async def test_adder_tree_extremes_no_overflow(dut):
    """Nilai ekstrem, termasuk maksimum 8*255*255 = 520200 (< 2^19): eksak, tanpa overflow."""
    await start(dut, PERIOD_NS)
    worst = None
    for w, a in extreme_vectors():
        got, raw = await (_dot_raw(dut, w, a))
        exp = M.dot(w, a)
        assert got == exp, f"w={w} a={a}: {got} != {exp}"
        assert raw[0] >> 3 == 0, "bit 7..3 byte pertama harus 0"
        if w == [255] * 8 and a == [255] * 8:
            worst = raw
    REC.put("extremes", dict(cases=len(extreme_vectors()), worst_bytes=worst,
                             worst=M.dot([255] * 8, [255] * 8), limit_19bit=1 << 19))


async def _dot_raw(dut, w, a):
    await load(dut, w, a)
    return await read_s(dut)


@cocotb.test()
async def test_products_exhaustive(dut):
    """Semua 65.536 pasangan (w, a) satu MAC; MAC = w mod 8, MAC lain 0."""
    await start(dut, PERIOD_NS)
    await load(dut, [0] * 8, [0] * 8)
    bad = []
    for w in range(256):
        i = w % 8
        await cmd(dut, LOAD_W, i, w)
        for a in range(256):
            await cmd(dut, LOAD_A, i, a)
            got = (await read_s(dut))[0]
            if got != w * a:
                bad.append((i, w, a, got))
        await cmd(dut, LOAD_A, i, 0)
    REC.put("products_wrong", [len(bad), 65536])
    assert not bad, f"{len(bad)} produk salah, contoh {bad[:5]}"


@cocotb.test()
async def test_address_out_of_range_ignored(dut):
    """Alamat 8..63 tidak menulis MAC mana pun (hanya 3 bit bawah yang dipakai)."""
    await start(dut, PERIOD_NS)
    rng = np.random.default_rng(7)
    w, a = rng.integers(0, 256, 8), rng.integers(0, 256, 8)
    await load(dut, w, a)
    for addr in range(8, 64):
        await cmd(dut, LOAD_W, addr, 0xFF)
        await cmd(dut, LOAD_A, addr, 0xFF)
    got = (await read_s(dut))[0]
    assert got == M.dot(w, a), "tulisan ke alamat >= 8 mengubah isi MAC"


@cocotb.test()
async def test_read_overlaps_next_load(dut):
    """Selama 3 byte keluar, vektor berikutnya boleh dimuat (READ_S lalu LOAD langsung)."""
    await start(dut, PERIOD_NS)
    rng = np.random.default_rng(8)
    w, a = rng.integers(0, 256, 8), rng.integers(0, 256, 8)
    await load(dut, w, a)
    await cmd(dut, READ_S)
    for _ in range(20):
        a2 = rng.integers(0, 256, 8)
        out = [await cmd(dut, LOAD_A, i, int(a2[i])) for i in range(3)]
        exp = M.dot(w, a)
        assert (out[0] << 16) | (out[1] << 8) | out[2] == exp
        for i in range(3, 8):
            await cmd(dut, LOAD_A, i, int(a2[i]))
        a = a2
        await cmd(dut, READ_S)


@cocotb.test()
async def test_weights_stationary(dut):
    """Bobot tetap tersimpan saat aktivasi diganti berulang (weight-stationary)."""
    await start(dut, PERIOD_NS)
    rng = np.random.default_rng(9)
    w = rng.integers(0, 256, 8)
    await load(dut, w=w)
    for _ in range(50):
        a = rng.integers(0, 256, 8)
        assert await dot(dut, None, a) == M.dot(w, a)


@cocotb.test()
async def test_reset_clears(dut):
    """Reset (asinkron) mengosongkan W, A, dan cache keluaran."""
    await start(dut, PERIOD_NS)
    await load(dut, [255] * 8, [255] * 8)
    dut.rst_n.value = 0
    await FallingEdge(dut.clk)
    assert int(dut.uo_out.value) == 0
    dut.rst_n.value = 1
    assert (await read_s(dut))[0] == 0


@cocotb.test(expect_fail=True)
async def test_V1_signed_vectors(dut):
    """[V1] Vektor berlabel "negative values (two's complement)" di test upstream = dot bertanda."""
    await start(dut, PERIOD_NS)
    upstream_negative = [
        ([255] * 8, [255] * 8),
        ([128] * 8, [128] * 8),
        ([128, 255] * 4, [255, 128] * 4),
        ([200, 150, 100, 50, 250, 200, 150, 100], [56, 106, 156, 206, 6, 56, 106, 156]),
    ]
    rows = []
    for w, a in upstream_negative:
        got = await dot(dut, w, a)
        rows.append(dict(w=w, a=a, observed=got, unsigned=M.dot(w, a), signed=M.dot_signed(w, a)))
    REC.put("V1_upstream_negative", rows)
    assert all(r["observed"] == r["signed"] for r in rows), rows
