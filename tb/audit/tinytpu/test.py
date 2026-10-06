"""Audit TinyTPU #0590 apa adanya terhadap model/tinytpu.py (level pin, RTL dan GL).

Setiap test memeriksa perilaku yang *benar*. Cacat yang sudah terkonfirmasi
diberi expect_fail dan ID temuan (T1, T2, ...) dari docs/baseline_audit.md.

Protokol (sama dengan test upstream): load_en (ui_in[2]) naik, satu clock
kemudian 32 bit X/Y dikirim satu per clock, load_en turun satu clock setelah
bit terakhir; lalu pulsa init (ui_in[3]) satu clock. Input diubah di sisi turun.
"""

import cocotb
import numpy as np
from cocotb.triggers import FallingEdge

import tinytpu as M
from audit_util import VIEW, Record, reset, start

PERIOD_NS = 40          # sama dengan test upstream
CAPTURE = 90            # siklus yang direkam setelah init
GL = VIEW == "gl"
REC = Record("tinytpu")

# Vektor test upstream (test/test.py): data_x = 0xCA6C61EF, data_y = 0xC42F3B1B
UPSTREAM_X = np.array([[0xEF, 0x61], [0x6C, 0xCA]])
UPSTREAM_Y = np.array([[0x1B, 0x2F], [0x3B, 0xC4]])      # Y dikirim kolom demi kolom


async def clean_reset(dut):
    """Reset, 3 clock tanpa reset, reset lagi.

    output_control.init_delay tidak di-reset (T5): reset tunggal membuat netlist
    tapeout X selamanya. Tiga clock dengan init=0 mengosongkan init_delay, lalu
    reset kedua membersihkan STATE.
    """
    await reset(dut)
    for _ in range(3):
        await FallingEdge(dut.clk)
    await reset(dut)


async def run_op(dut, x, y, drop_with_last=False):
    """Kirim X, Y, pulsa init; kembalikan [(data, tx_ready)] per siklus ('x' -> None)."""
    dx, dy = M.pack_x(x), M.pack_y(y)
    dut.ui_in.value = 0b0100
    await FallingEdge(dut.clk)
    for i in range(32):
        load = 0 if (drop_with_last and i == 31) else 0b0100
        dut.ui_in.value = load | ((dx >> i) & 1) | (((dy >> i) & 1) << 1)
        await FallingEdge(dut.clk)
    dut.ui_in.value = 0
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0b1000
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0
    cap = []
    for _ in range(CAPTURE):
        b = dut.uo_out.value.binstr
        cap.append(tuple(int(c) if c in "01" else None for c in (b[-1], b[-2])))
        await FallingEdge(dut.clk)
    for _ in range(4):
        await FallingEdge(dut.clk)
    return cap


class Frame:
    """Keluaran satu operasi.

    ready: indeks siklus dengan tx_ready=1.
    by_ready: 64 bit yang diambil selama tx_ready=1 (cara penerima yang wajar).
    aligned: 64 bit mulai satu siklus sebelum tx_ready naik (bit pertama yang sebenarnya).
    """

    def __init__(self, cap):
        self.cap = cap
        self.defined = all(d is not None and r is not None for d, r in cap)
        self.ready = [i for i, (_, r) in enumerate(cap) if r == 1]
        ok = self.defined and len(self.ready) == 64 and self.ready == list(
            range(self.ready[0], self.ready[0] + 64))
        self.ok = ok
        if ok:
            f = self.ready[0]
            self.first_data = next((i for i, (d, _) in enumerate(cap) if d == 1), None)
            self.by_ready = [cap[i][0] for i in self.ready]
            self.aligned = [d for d, _ in cap[f - 1:f + 63]]


def bit_errors(bits, z, skip_z00_bit0=False):
    """Indeks bit (0..63) yang berbeda dari Z (16 bit per elemen)."""
    ref = M.z_to_bits(np.asarray(z) & 0xFFFF)
    return [i for i in range(64) if bits[i] != ref[i] and not (skip_z00_bit0 and i == 0)]


def random_cases(seed, n, hi):
    rng = np.random.default_rng(seed)
    cases = [(UPSTREAM_X, UPSTREAM_Y)]
    cases += [(rng.integers(0, hi + 1, (2, 2)), rng.integers(0, hi + 1, (2, 2))) for _ in range(n - 1)]
    return cases


EXTREME_VALUES = (0, 1, 2, 127, 128, 129, 254, 255)


def extreme_cases():
    full = np.full((2, 2), 255)
    cases = [
        (np.zeros((2, 2), int), np.zeros((2, 2), int)),
        (full, full),                                       # 130050 di setiap elemen
        (np.eye(2, dtype=int) * 255, full),                 # 65025: muat tepat 16 bit
        (full, np.eye(2, dtype=int)),                       # identitas
        (np.array([[255, 255], [0, 0]]), np.array([[255, 0], [255, 0]])),
        (np.array([[128, 128], [128, 128]]), np.array([[128, 128], [128, 128]])),  # 32768
        (np.array([[181, 181], [181, 181]]), np.array([[181, 181], [181, 181]])),  # 65522
        (np.array([[182, 181], [181, 181]]), np.array([[181, 181], [181, 181]])),  # 65703 > 16 bit
    ]
    rng = np.random.default_rng(7)
    for _ in range(40):
        cases.append((rng.choice(EXTREME_VALUES, (2, 2)), rng.choice(EXTREME_VALUES, (2, 2))))
    return cases


N_RANDOM = 400


async def run_cases(dut, cases):
    out = []
    for x, y in cases:
        await clean_reset(dut)
        out.append((x, y, Frame(await run_op(dut, x, y))))
    return out


@cocotb.test(expect_fail=GL)
async def test_T5_single_reset(dut):
    """[T5] Satu reset saja cukup: keluaran terdefinisi dan benar (gagal hanya di GL).

    Harus test pertama: state simulasi terbawa antar-test, dan test lain memakai
    clean_reset() yang mengosongkan init_delay.
    """
    await start(dut, PERIOD_NS)
    x, y = UPSTREAM_X, UPSTREAM_Y
    fr = Frame(await run_op(dut, x, y))
    REC.put("T5_single_reset_defined", fr.defined)
    assert fr.defined, "keluaran X setelah reset tunggal"
    assert fr.ok and not bit_errors(fr.aligned, M.matmul(x, y), skip_z00_bit0=True)


@cocotb.test()
async def test_systolic_core(dut):
    """Array sistolik menghitung X @ Y benar (selain bit 0 z00, lihat T2).

    Nilai <= 180 agar 2*180^2 < 2^16. Juga memeriksa struktur bingkai keluaran:
    tx_ready tinggi 64 siklus berturut-turut, dan bit 0 z00 sama dengan bit 0
    produk parsial x00*y00 (mekanisme T2).
    """
    await start(dut, PERIOD_NS)
    stats = dict(ops=0, z00_bit0_wrong=0)
    for x, y, fr in await run_cases(dut, random_cases(1, N_RANDOM, 180)):
        z = M.matmul(x, y)
        assert fr.ok, f"bingkai keluaran tidak lengkap untuk X={x.tolist()} Y={y.tolist()}"
        errs = bit_errors(fr.aligned, z, skip_z00_bit0=True)
        assert not errs, f"X={x.tolist()} Y={y.tolist()}: bit salah {errs}"
        assert fr.aligned[0] == (int(x[0, 0]) * int(y[0, 0])) & 1, "bit 0 z00 bukan dari x00*y00"
        stats["ops"] += 1
        stats["z00_bit0_wrong"] += fr.aligned[0] != (int(z[0, 0]) & 1)
    REC.put("core_random", stats)
    dut._log.info("array sistolik: %s", stats)


@cocotb.test(expect_fail=True)
async def test_T2_result_exact(dut):
    """[T2] Seluruh 64 bit (bingkai sejajar) sama dengan X @ Y."""
    await start(dut, PERIOD_NS)
    bad = 0
    cases = random_cases(1, N_RANDOM, 180)
    for x, y, fr in await run_cases(dut, cases):
        bad += bool(bit_errors(fr.aligned, M.matmul(x, y)))
    REC.put("T2_ops_wrong", [bad, len(cases)])
    assert bad == 0, f"{bad}/{len(cases)} operasi salah (bit 0 z00)"


@cocotb.test(expect_fail=True)
async def test_T1_tx_ready_framing(dut):
    """[T1] Bit yang diambil selama tx_ready=1 adalah Z, LSB dulu."""
    await start(dut, PERIOD_NS)
    bad = 0
    cases = random_cases(2, 40, 180)
    for x, y, fr in await run_cases(dut, cases):
        if bit_errors(fr.by_ready, M.matmul(x, y)):
            bad += 1
            if bad == 1:
                obs = M.z_from_bits(fr.by_ready)
                REC.put("T1_example", dict(x=x.tolist(), y=y.tolist(), model=M.matmul(x, y).tolist(),
                                           by_ready=obs.tolist()))
    REC.put("T1_ops_wrong", [bad, len(cases)])
    assert bad == 0, f"{bad}/{len(cases)} operasi salah bila disampel saat tx_ready=1"


@cocotb.test()
async def test_extreme_wraps_mod_2_16(dut):
    """Nilai ekstrem: hasil = (X @ Y) mod 2^16 (karakterisasi T3)."""
    await start(dut, PERIOD_NS)
    n_over = 0
    for x, y, fr in await run_cases(dut, extreme_cases()):
        z = M.matmul(x, y)
        assert fr.ok
        errs = bit_errors(fr.aligned, z % (1 << 16), skip_z00_bit0=True)
        assert not errs, f"X={x.tolist()} Y={y.tolist()}: bukan mod 2^16, bit {errs}"
        n_over += int((z >= 1 << 16).any())
    REC.put("extreme_cases", [len(extreme_cases()), n_over])


@cocotb.test(expect_fail=True)
async def test_T3_extreme_exact(dut):
    """[T3] Nilai ekstrem: setiap elemen Z eksak (butuh 17 bit untuk 2*255^2)."""
    await start(dut, PERIOD_NS)
    wrong = []
    for x, y, fr in await run_cases(dut, extreme_cases()):
        z = M.matmul(x, y)
        obs = M.z_from_bits(fr.aligned)
        obs[0, 0] = (obs[0, 0] & ~1) | (int(z[0, 0]) & 1)     # abaikan T2
        if (obs != z).any():
            wrong.append(dict(x=x.tolist(), y=y.tolist(), model=z.tolist(), observed=obs.tolist()))
    REC.put("T3_wrong", [len(wrong), len(extreme_cases())])
    if wrong:
        REC.put("T3_example", wrong[0])
    assert not wrong, f"{len(wrong)} kasus ekstrem salah, contoh {wrong[0]}"


@cocotb.test(expect_fail=True)
async def test_T4_back_to_back(dut):
    """[T4] Operasi berikutnya tanpa reset juga benar (dua cara menurunkan load_en)."""
    await start(dut, PERIOD_NS)
    rng = np.random.default_rng(4)
    summary = {}
    for drop in (False, True):
        await clean_reset(dut)
        res = []
        for k in range(4):
            x, y = rng.integers(0, 181, (2, 2)), rng.integers(0, 181, (2, 2))
            fr = Frame(await run_op(dut, x, y, drop_with_last=drop))
            z = M.matmul(x, y)
            obs = M.z_from_bits(fr.aligned) if fr.ok else None
            res.append(dict(model=z.tolist(), observed=None if obs is None else obs.tolist(),
                            ok=fr.ok and not bit_errors(fr.aligned, z, skip_z00_bit0=True)))
        summary["load_en_drop_with_last" if drop else "load_en_drop_after (upstream)"] = res
    REC.put("T4_sequences", summary)
    bad = sum(not r["ok"] for v in summary.values() for r in v[1:])
    assert all(v[0]["ok"] for v in summary.values()), "operasi pertama setelah reset salah"
    assert bad == 0, f"{bad}/6 operasi ke-2..4 salah tanpa reset"


@cocotb.test(expect_fail=True, skip=GL)
async def test_T4_counters_return_to_zero(dut):
    """[T4] (RTL, sinyal internal) bit_counter dan ram_counter kembali 0 setelah tiap load.

    Kedua counter hanya di-reset oleh rst. Protokol upstream (load_en turun satu
    clock setelah bit terakhir) menambah satu geseran ekstra -> bit_counter +1 per
    operasi. load_en turun bersama bit terakhir -> penulisan byte terakhir terjadi
    di IDLE, ram_counter tertinggal di 1 -> baris X/kolom Y tertukar di operasi berikutnya.
    """
    await start(dut, PERIOD_NS)
    ic = dut.dut.tinytpu_top_inst.input_control_inst
    seen = {}
    for drop in (False, True):
        await clean_reset(dut)
        trace = []
        for _ in range(3):
            await run_op(dut, np.ones((2, 2), int), np.ones((2, 2), int), drop_with_last=drop)
            trace.append((int(ic.bit_counter.value), int(ic.ram_counter.value)))
        seen["drop_with_last" if drop else "drop_after (upstream)"] = trace
    REC.put("T4_counters_bit_ram", seen)
    assert all(t == (0, 0) for v in seen.values() for t in v), f"(bit_counter, ram_counter): {seen}"
