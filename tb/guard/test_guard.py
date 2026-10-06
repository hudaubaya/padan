"""Test cocotb guard.v lewat padan_avmm, parameter guard rilis (K = 5, FAULT_MAX = 3).

Semua perintah lewat port Avalon-MM seperti host. Isi memori (16 bank x 144 word:
T, C, Cw) dan register probe dipindai langsung di simulasi untuk membuktikan
zeroize. Fault dan state ilegal disuntik dengan deposit cocotb.
"""

import cocotb
import numpy as np
from cocotb.triggers import FallingEdge, ReadOnly, Timer

import padan as P
import test_avmm as TA
from test_avmm import A_CLR, A_ENROLL, A_GK, A_GLOCK, A_GSTAT, A_MATCH, A_PROBE, A_STATUS, I8

L, CH = 16, P.D // 16
ROWS = P.N * CH + 2 * CH                                   # 144 word per bank
A_GTAU = 0x306
LOCK_MAGIC = 0x4C4F434B
S_ZB, S_OPEN, S_LOCKD, S_LOUT, S_ZH, S_HALT = 0b0000, 0b0011, 0b0101, 0b0110, 0b1001, 0b1010
LEGAL = {S_ZB, S_OPEN, S_LOCKD, S_LOUT, S_ZH, S_HALT}
ILLEGAL = sorted(set(range(16)) - LEGAL)
R_BOOT, R_TAMPER, R_FAULT, R_ILLEGAL = 0, 1, 2, 3
K_DEFAULT, FAULT_MAX = 5, 3
# Zeroize: clear 144 siklus + probe 128 siklus + beberapa siklus kendali.
ZEROIZE_MAX = ROWS + P.D + 16


def gfields(v):
    return dict(state=v & 0xF, fail=(v >> 4) & 0xF, k=(v >> 8) & 0xF, fault=(v >> 12) & 0xF,
                reason=(v >> 16) & 3, tamper=(v >> 18) & 1, zeroizing=(v >> 19) & 1, rest=v >> 20)


def gstate(dut):
    return dut.u.u_guard.state.value.integer


async def gstat(h):
    return gfields(await h.read(A_GSTAT))


async def wait_state(dut, want, limit=ZEROIZE_MAX + 400):
    for _ in range(limit):
        await FallingEdge(dut.u.clk)
        if dut.u.u_guard.state.value.is_resolvable and gstate(dut) == want:
            return
    raise AssertionError(f"guard tidak mencapai state {want:04b} (sekarang {dut.u.u_guard.state.value})")


def mem_dump(dut):
    """Seluruh isi 16 bank x 144 word (T, C, Cw); None untuk word yang belum terdefinisi."""
    out = []
    for l in range(L):
        bank = dut.u.u_mem.g_bank[l].u_ram.mem
        out.append([bank[a].value.integer if bank[a].value.is_resolvable else None
                    for a in range(ROWS)])
    return out


def probe_dump(dut):
    m = dut.u.u_mac
    return (m.probe.value.integer if m.probe.value.is_resolvable else None,
            m.probe_par.value.integer if m.probe_par.value.is_resolvable else None)


def assert_zeroized(dut, what):
    mem = mem_dump(dut)
    bad = [(l, a, v) for l in range(L) for a, v in enumerate(mem[l]) if v != 0]
    assert not bad, f"{what}: {len(bad)} word memori bukan nol, mis. (bank, alamat, nilai) {bad[:4]}"
    probe, par = probe_dump(dut)
    assert probe == 0 and par == 0, f"{what}: probe/paritas bukan nol ({probe}, {par})"


async def fill_random(dut, rng):
    """Isi semua word memori dan probe dengan nilai acak bukan nol (deposit)."""
    for l in range(L):
        bank = dut.u.u_mem.g_bank[l].u_ram.mem
        for a in range(ROWS):
            bank[a].value = int(rng.integers(1, 1 << 16))
    dut.u.u_mac.probe.value = int.from_bytes(rng.integers(1, 256, P.D, dtype=np.uint8).tobytes(), "little")
    dut.u.u_mac.probe_par.value = (1 << P.D) - 1
    await Timer(1, "ns")
    assert all(v for bank in mem_dump(dut) for v in bank), "isi acak tidak terpasang"


async def boot(dut, seed):
    h = TA.Host(dut)
    await h.reset()
    await wait_state(dut, S_OPEN)
    return h, np.random.default_rng(seed)


async def enroll_probe(h, rng, g=3):
    """Galeri acak dan probe = T[g] (MATCH ke g dengan tau = skor maksimum)."""
    T = rng.integers(*I8, (P.N, P.D))
    p = T[g].copy()
    await h.enroll(T)
    await h.probe(p)
    return T, p


async def match_ok(h, T, p, want, tau=None):
    """Jalankan MATCH yang harus menghasilkan `want` (MATCH atau NO_MATCH). tau:
    ambang yang berlaku (default: dari skor maksimum, ditulis bersama MATCH)."""
    s = P.scores(T, p)
    if tau is None:
        tau = int(s.max()) if want == P.MATCH else int(s.max()) + 1
    _, res = await h.match(tau)
    assert res == TA.golden(T, p, tau) and res[0] == want, f"{res} != {want}"


async def refused_match(h, dut):
    """MATCH ditulis tetapi tidak boleh memulai decision."""
    before = await h.read(A_STATUS)
    lat0 = dut.lat.value.integer
    waits = await h.write(A_MATCH, 0)
    for _ in range(TA.LAT_DECISION + 20):
        await FallingEdge(dut.u.clk)
        assert dut.dec_busy.value == 0 and dut.u.u_mac.busy.value == 0, "MATCH tidak ditolak"
    assert dut.lat.value.integer == lat0 and await h.read(A_STATUS) == before
    return waits


@cocotb.test()
async def test_boot_zeroize(dut):
    """Reset mengenolkan seluruh memori template, checksum, dan probe sebelum OPEN;
    tulis host selama zeroize ditahan (waitrequest), lalu dijalankan."""
    h, rng = await boot(dut, 1)
    g = await gstat(h)
    assert g == dict(state=S_OPEN, fail=0, k=K_DEFAULT, fault=0, reason=R_BOOT, tamper=0,
                     zeroizing=0, rest=0), g
    assert_zeroized(dut, "boot pertama")
    T, p = await enroll_probe(h, rng)
    await match_ok(h, T, p, P.MATCH)
    await fill_random(dut, rng)                    # isi sisa: M10K tidak direset oleh rst_n
    await h.reset()
    assert gstate(dut) == S_ZB
    waits = await h.write(A_ENROLL, 0x01020304)    # ditahan sampai zeroize selesai
    assert gstate(dut) == S_OPEN and waits > ROWS + P.D, f"tulis tidak ditahan ({waits} siklus)"
    await wait_state(dut, S_OPEN)
    for _ in range(20):                            # tulis byte selesai
        await FallingEdge(dut.u.clk)
    mem = mem_dump(dut)
    # Hanya T[0, 0..3] (bank 0..3, alamat 0) dan C/Cw kolom 0..3 yang bukan nol.
    nz = {(l, a) for l in range(L) for a in range(ROWS) if mem[l][a] != 0}
    assert nz == {(l, a) for l in range(4) for a in (0, P.N * CH, P.N * CH + CH)}, sorted(nz)
    assert probe_dump(dut) == (0, 0)
    dut._log.info("zeroize boot: %d word memori + %d byte probe nol; tulis ditahan %d siklus",
                  L * ROWS, P.D, waits)


@cocotb.test()
async def test_lockout_after_k(dut):
    """K = 5 kegagalan berturut-turut -> LOUT; MATCH mengenolkan penghitung;
    di LOUT semua operasi ditolak; hanya reset (yang mengenolkan) yang keluar."""
    h, rng = await boot(dut, 2)
    T, p = await enroll_probe(h, rng)
    for i in range(K_DEFAULT - 1):
        await match_ok(h, T, p, P.NO_MATCH)
        assert (await gstat(h))["fail"] == i + 1
    await match_ok(h, T, p, P.MATCH)
    g = await gstat(h)
    assert g["fail"] == 0 and g["state"] == S_OPEN, g
    for i in range(K_DEFAULT - 1):
        await match_ok(h, T, p, P.NO_MATCH)
    assert (await gstat(h))["state"] == S_OPEN
    await match_ok(h, T, p, P.NO_MATCH)            # kegagalan ke-K
    g = await gstat(h)
    assert g["state"] == S_LOUT and g["fail"] == K_DEFAULT, g
    st = await h.read(A_STATUS)
    assert TA.host_decode(st)[0] == P.NO_MATCH, f"STATUS di LOUT: {st:#x}"
    # Semua operasi ditolak.
    mem0, probe0 = mem_dump(dut), probe_dump(dut)
    await refused_match(h, dut)
    await h.write(A_CLR, 0)
    await h.write(A_ENROLL + 5, 0x7F7F7F7F)
    await h.write(A_PROBE + 3, 0x11223344)
    await h.write(A_GK, 15)
    await h.write(A_GLOCK, LOCK_MAGIC)
    assert mem_dump(dut) == mem0 and probe_dump(dut) == probe0, "operasi di LOUT mengubah isi"
    g = await gstat(h)
    assert g["state"] == S_LOUT and g["k"] == K_DEFAULT, g
    # Reset: zeroize, lalu OPEN dengan penghitung default.
    await h.reset()
    await wait_state(dut, S_OPEN)
    assert_zeroized(dut, "reset dari LOUT")
    g = await gstat(h)
    assert g["fail"] == 0 and g["k"] == K_DEFAULT, g


@cocotb.test()
async def test_k_programmable(dut):
    """K hanya bisa diubah di OPEN, hanya ke 1..15 (nilai lain diabaikan)."""
    h, rng = await boot(dut, 3)
    for bad in (0, 16, 0x102, 0xA5A5A5A5):
        await h.write(A_GK, bad)
        assert (await gstat(h))["k"] == K_DEFAULT, f"K = {bad:#x} diterima"
    await h.write(A_GK, 2)
    assert (await gstat(h))["k"] == 2
    T, p = await enroll_probe(h, rng)
    await h.write(A_GLOCK, LOCK_MAGIC)
    await h.write(A_GK, 9)                          # LOCKD: ditolak
    g = await gstat(h)
    assert g["state"] == S_LOCKD and g["k"] == 2, g
    await match_ok(h, T, p, P.NO_MATCH)
    assert (await gstat(h))["state"] == S_LOCKD
    await match_ok(h, T, p, P.NO_MATCH)
    g = await gstat(h)
    assert g["state"] == S_LOUT and g["fail"] == 2, g
    await refused_match(h, dut)


@cocotb.test()
async def test_lock_blocks_enroll(dut):
    """Setelah LOCK, ENROLL_DATA dan ENROLL_CLR tidak mengubah memori (dipindai);
    probe dan match tetap bekerja. LOCK hanya dengan nilai 'LOCK'."""
    h, rng = await boot(dut, 4)
    T, p = await enroll_probe(h, rng)
    p2 = T[7].copy()
    tau_l = min(int(P.scores(T, p).max()), int(P.scores(T, p2).max()))
    await h.write(A_GTAU, tau_l)
    for bad in (0, 1, LOCK_MAGIC ^ 1, 0xA5A5A5A5):
        await h.write(A_GLOCK, bad)
        assert (await gstat(h))["state"] == S_OPEN, f"LOCK diterima dengan {bad:#x}"
    await h.write(A_GLOCK, LOCK_MAGIC)
    assert (await gstat(h))["state"] == S_LOCKD
    mem0 = mem_dump(dut)
    await h.write(A_CLR, 0)
    for a in (0, 1, 0x55, 0x1FF):
        waits = await h.write(A_ENROLL + a, 0x7F80017F)
        assert waits <= 2, f"tulis ditolak harus segera selesai, {waits} siklus"
    await h.write(A_CLR, 0xFFFFFFFF)
    T2 = rng.integers(*I8, (P.N, P.D))
    await h.enroll(T2)                              # enrollment penuh: ditolak semua
    for _ in range(20):
        await FallingEdge(dut.u.clk)
    assert mem_dump(dut) == mem0, "template berubah setelah LOCK"
    # Probe dan match tetap bekerja terhadap template lama.
    await match_ok(h, T, p, P.MATCH, tau_l)
    await h.probe(p2)
    await match_ok(h, T, p2, P.MATCH, tau_l)
    await h.write(A_GLOCK, LOCK_MAGIC)              # LOCK lagi: tetap LOCKD
    assert (await gstat(h))["state"] == S_LOCKD


@cocotb.test()
async def test_tau_locked(dut):
    """Di LOCKD decision memakai GUARD_TAU, bukan tau yang ditulis bersama MATCH:
    tau = -2^31 dari host tidak menghasilkan MATCH dan tidak menolkan penghitung,
    jadi lockout tetap terjadi. GUARD_TAU tidak bisa diubah di LOCKD. Tanpa
    GUARD_TAU, default 0x7FFFFFFF: tidak ada MATCH."""
    h, rng = await boot(dut, 9)
    T, p = await enroll_probe(h, rng)
    top = int(P.scores(T, p).max())
    await h.write(A_GLOCK, LOCK_MAGIC)               # tanpa GUARD_TAU
    _, res = await h.match(-(1 << 31))
    assert res == (P.NO_MATCH, None), f"default tau: {res}"
    await h.reset()                                  # zeroize; enroll ulang
    await wait_state(dut, S_OPEN)
    await h.enroll(T)
    await h.probe(p)
    await h.write(A_GTAU, top + 1)                   # probe ini tidak boleh lolos
    _, res = await h.match(-(1 << 31))               # OPEN: tau dari host berlaku
    assert res == TA.golden(T, p, -(1 << 31)) and res[0] == P.MATCH, res
    await h.write(A_GLOCK, LOCK_MAGIC)
    await h.write(A_GTAU, -(1 << 31) & 0xFFFFFFFF)  # LOCKD: ditolak
    for i in range(K_DEFAULT):
        _, res = await h.match(-(1 << 31))
        assert res == TA.golden(T, p, top + 1) == (P.NO_MATCH, None), f"percobaan {i}: {res}"
    g = await gstat(h)
    assert g["state"] == S_LOUT and g["fail"] == K_DEFAULT, g


async def tamper_pulse(dut, cycles):
    dut.tamper_n.value = 0
    for _ in range(cycles):
        await FallingEdge(dut.u.clk)
    dut.tamper_n.value = 1


@cocotb.test()
async def test_tamper_zeroize(dut):
    """Tamper (2-FF sinkron) -> ZH -> memori, checksum, probe nol -> HALT;
    STATUS tidak lagi menunjukkan keputusan; semua permintaan ditolak."""
    h, rng = await boot(dut, 5)
    T, p = await enroll_probe(h, rng)
    await h.write(A_GTAU, int(P.scores(T, p).max()))
    await h.write(A_GLOCK, LOCK_MAGIC)
    await match_ok(h, T, p, P.MATCH)
    assert TA.host_decode(await h.read(A_STATUS))[0] == P.MATCH
    # Sinkronisasi: tamper_n turun setelah sisi turun; state berubah pada sisi naik ke-3.
    await FallingEdge(dut.u.clk)
    dut.tamper_n.value = 0
    for edge in (1, 2):
        await FallingEdge(dut.u.clk)
        assert gstate(dut) == S_LOCKD, f"tamper terlihat setelah {edge} sisi (sinkronisasi 2-FF hilang)"
    await FallingEdge(dut.u.clk)
    assert gstate(dut) == S_ZH, "tamper tidak terlihat setelah 3 sisi"
    dut.tamper_n.value = 1                           # tombol dilepas: zeroize tetap berjalan
    await wait_state(dut, S_HALT)
    assert_zeroized(dut, "tamper")
    g = await gstat(h)
    assert g["state"] == S_HALT and g["reason"] == R_TAMPER and g["zeroizing"] == 0, g
    assert (await h.read(A_STATUS)) & 0xFFF == 0xF00, "keputusan lama masih terbaca setelah tamper"
    # Semua permintaan ditolak, memori tetap nol.
    await refused_match(h, dut)
    await h.write(A_CLR, 0)
    await h.write(A_ENROLL + 7, 0x01010101)
    await h.write(A_PROBE + 7, 0x01010101)
    await h.write(A_GK, 3)
    await h.write(A_GLOCK, LOCK_MAGIC)
    await h.write(A_GTAU, 0)
    await tamper_pulse(dut, 5)                       # tamper lagi di HALT: tetap HALT
    for _ in range(ZEROIZE_MAX):
        await FallingEdge(dut.u.clk)
    assert_zeroized(dut, "permintaan setelah HALT")
    assert gstate(dut) == S_HALT


@cocotb.test()
async def test_tamper_during_activity(dut):
    """Tamper di tengah match, enrollment, tulis probe, dan zeroize boot: hasil akhir
    selalu HALT dengan memori dan probe nol."""
    rng = np.random.default_rng(6)
    h = TA.Host(dut)
    await h.reset()
    # Selama zeroize boot.
    for _ in range(40):
        await FallingEdge(dut.u.clk)
    assert gstate(dut) == S_ZB
    await tamper_pulse(dut, 3)
    await wait_state(dut, S_HALT)
    assert_zeroized(dut, "tamper saat zeroize boot")
    assert (await gstat(h))["reason"] == R_TAMPER
    for what, delay in (("match", 30), ("match", 140), ("enroll", 3), ("enroll", 9), ("probe", 4)):
        await h.reset()
        await wait_state(dut, S_OPEN)
        T, p = await enroll_probe(h, rng)
        if what == "match":
            job = cocotb.start_soon(h.write(A_MATCH, int(P.scores(T, p).max())))
        elif what == "enroll":
            job = cocotb.start_soon(h.enroll(rng.integers(*I8, (P.N, P.D))))
        else:
            job = cocotb.start_soon(h.probe(rng.integers(*I8, P.D)))
        for _ in range(delay):
            await FallingEdge(dut.u.clk)
        await tamper_pulse(dut, 3)
        await wait_state(dut, S_HALT, limit=ZEROIZE_MAX + TA.LAT_DECISION + 400)
        await job                                    # sisa tulis host ditolak
        for _ in range(20):
            await FallingEdge(dut.u.clk)
        assert_zeroized(dut, f"tamper saat {what} (+{delay} siklus)")
        assert gstate(dut) == S_HALT


@cocotb.test()
async def test_fault_threshold(dut):
    """FAULT dihitung kumulatif (MATCH tidak mengenolkan); FAULT ke-3 -> zeroize -> HALT."""
    h, rng = await boot(dut, 7)
    T = rng.integers(*I8, (P.N, P.D))
    p = T[5].copy()
    p[35] = 77                                       # kolom yang dirusak harus terpakai
    await h.enroll(T)
    await h.probe(p)
    word = dut.u.u_mem.g_bank[3].u_ram.mem[5 * CH + 2]      # T[5, 2*16+3] = T[5, 35]
    good = word.value.integer
    for i in range(FAULT_MAX):
        word.value = good ^ 0x4
        await Timer(1, "ns")
        _, res = await h.match(int(P.scores(T, p).max()))
        g = await gstat(h)
        if i == FAULT_MAX - 1:
            # FAULT ke-3 langsung memicu zeroize: STATUS tidak lagi memuat keputusan.
            assert res == ("NONE", None) and g["state"] in (S_ZH, S_HALT), (res, g)
        else:
            assert res == (P.FAULT, None), res
            assert g["state"] == S_OPEN and g["fault"] == i + 1, g
            await TA.restore(word, good)
            await match_ok(h, T, p, P.MATCH)
            assert (await gstat(h))["fault"] == i + 1, "MATCH mengenolkan penghitung FAULT"
    await wait_state(dut, S_HALT)
    assert_zeroized(dut, "ambang FAULT")
    g = await gstat(h)
    assert g["reason"] == R_FAULT and g["fault"] == FAULT_MAX, g
    await refused_match(h, dut)


@cocotb.test()
async def test_illegal_state(dut):
    """Setiap kode state ilegal (termasuk setiap flip satu bit dari state legal),
    setiap ketidakcocokan penghitung/komplemen -> zeroize -> HALT, alasan ILLEGAL.
    Kode sequencer zeroize ilegal -> zeroize diulang dan tetap selesai."""
    assert all((s ^ (1 << b)) in ILLEGAL for s in LEGAL for b in range(4))
    rng = np.random.default_rng(8)
    h = TA.Host(dut)
    g = dut.u.u_guard
    cases = [("state", c) for c in ILLEGAL] + \
            [(r, 1 << b) for r, w in (("fail", 4), ("fail_n", 4), ("k", 4), ("k_n", 4),
                                      ("fault", 2), ("fault_n", 2)) for b in range(w)] + \
            [("tau_lk", 1), ("tau_lk", 1 << 31), ("tau_lk_n", 1 << 16)]
    for start in (S_OPEN, S_LOCKD, S_LOUT):
        for reg, x in (cases if start == S_OPEN else [("state", c) for c in ILLEGAL[::3]]):
            await h.reset()
            await wait_state(dut, S_OPEN)
            if start != S_OPEN:
                g.state.value = start
                await Timer(1, "ns")
            await fill_random(dut, rng)
            sig = getattr(g, reg)
            sig.value = x if reg == "state" else sig.value.integer ^ x
            await Timer(1, "ns")
            await wait_state(dut, S_HALT)
            assert_zeroized(dut, f"{reg} ^ {x:#x} dari {start:04b}")
            assert g.reason.value.integer == R_ILLEGAL, f"{reg}: alasan {g.reason.value}"
    # Sequencer zeroize ilegal di tengah zeroize boot.
    for zs in (5, 6, 7):
        await h.reset()
        for _ in range(60):
            await FallingEdge(dut.u.clk)
        await fill_random(dut, rng)
        g.zs.value = zs
        await Timer(1, "ns")
        await wait_state(dut, S_OPEN)
        assert_zeroized(dut, f"zs = {zs}")
    dut._log.info("%d kasus state/penghitung ilegal + 3 kode sequencer ilegal: semua zeroize",
                  len(cases) + 2 * len(ILLEGAL[::3]))
