"""Simulasi fault pada golden model PADAN dan cakupan ABFT.

Fault tunggal (bit flip), disuntikkan secara exhaustive per probe:
- skor: bit b (0..31) register s_k setelah selesai dihitung;
- akumulator skor: bit b isi akumulator s_k setelah langkah i (0..D-2),
  sebelum produk berikutnya ditambahkan;
- akumulator checksum: bit b isi akumulator C.p atau Cw.p setelah langkah i;
- bit template: bit b (0..7) T[j,i] setelah baris checksum dihitung saat enrolment.

Pemeriksa: d1, d2 dalam register 32 bit (wrap, seperti perangkat keras). Untuk
perbandingan: pemeriksa 40 bit (eksak untuk semua nilai register 32 bit), dan
pemeriksa 32 bit ditambah cek rentang skor (s di luar batas padan_bounds pasti
salah, dan indeksnya diketahui). Lokalisasi: indeks k = d2/d1 - 1 (padan.localize).

Karena tanpa fault sum s = C.p dan sum (j+1)s = Cw.p secara eksak, galat E pada
s_k memberi d1 = wrap(E), d2 = wrap((k+1)E); galat Ec pada akumulator C.p
memberi d1 = wrap(-Ec), d2 = 0 (dan sebaliknya untuk Cw.p).
"""

import sys

import numpy as np

import padan as P
import padan_bounds as PB
import padan_data as PD

ACC_BITS_RANGE = np.arange(P.ACC_BITS, dtype=np.int64)
TAU_REF = 0.30
WIDE_BITS = 40          # cukup: |sum (j+1) s'_j - Cw.p| <= 136 * 2^31 + 2^29 < 2^39
S_LO, S_HI = dict((n, iv) for n, _, iv in PB.intervals())["s_j (dan isi akumulatornya)"]


def flip(x, b, bits=P.ACC_BITS):
    """Balik bit b register `bits` bit berisi x (two's complement)."""
    return P.wrap(np.asarray(x, dtype=np.int64) ^ (np.int64(1) << b), bits)


def fault_probes(ds, per_id=2, unknown=32):
    """Indeks probe untuk simulasi fault: per_id dari tiap identitas + `unknown` probe tak terdaftar."""
    gen = [k * PD.PROBES_PER_ID + r for k in range(P.N) for r in range(per_id)]
    base = P.N * PD.PROBES_PER_ID
    return gen + [base + u * PD.PROBES_PER_UNKNOWN for u in range(unknown)]


def classify(k, E, s, ti):
    """Hasil per fault untuk galat E pada skor k (array sebentuk).

    Mengembalikan dict array boolean untuk pemeriksa 32 bit, 40 bit, dan 32 bit
    + cek rentang ("rng").
    """
    k = np.broadcast_to(k, E.shape)
    w = k + 1
    out = {"eff": E != 0}
    for tag, bits in (("32", P.ACC_BITS), ("40", WIDE_BITS)):
        d1, d2 = P.wrap(E, bits), P.wrap(w * E, bits)
        loc = P.localize_np(d1, d2)
        out["det" + tag] = (d1 != 0) | (d2 != 0)
        out["ok" + tag] = loc == k
        out["mis" + tag] = (loc >= 0) & (loc != k)
        out["unloc" + tag] = loc == P.LOC_UNLOC
    s = np.broadcast_to(s, E.shape)
    s_new = P.wrap(s + E)
    out_of_range = (s_new < S_LO) | (s_new > S_HI)
    out["detrng"] = out["det32"] | out_of_range
    out["okrng"] = out["ok32"] | out_of_range
    out["misrng"] = out["mis32"] & ~out_of_range
    out["unlocrng"] = out["unloc32"] & ~out_of_range
    out["dec"] = (s_new >= ti) != (s >= ti)
    return out


def tally(acc, res):
    for key, v in res.items():
        acc[key] = acc.get(key, 0) + int(np.count_nonzero(v))
    acc["n"] = acc.get("n", 0) + res["eff"].size
    acc["dec_silent"] = acc.get("dec_silent", 0) + int(np.count_nonzero(res["dec"] & ~res["det32"]))


def run(ds=None, probes=None, tau=TAU_REF):
    ds = ds if ds is not None else PD.make_dataset()
    probes = probes if probes is not None else fault_probes(ds)
    ti = PD.tau_int(tau)
    T = ds["Tq"]
    C, Cw = P.checksum_rows(T)
    j = np.arange(P.N, dtype=np.int64)
    cats = {"score": {}, "acc": {}, "chk": {}, "tmpl": {}}
    per_bit = np.zeros((P.ACC_BITS, 5), dtype=np.int64)     # ok32, mis32, unloc32, ok40, okrng
    for pi in probes:
        p = ds["pq"][pi]
        prefix = np.cumsum(T * p, axis=1)                    # isi akumulator setelah langkah i
        s = prefix[:, -1]
        assert np.array_equal(s, P.scores(T, p)) and P.check(s, C, Cw, p) == (0, 0)

        # Skor: (N, 32)
        E = flip(s[:, None], ACC_BITS_RANGE[None, :]) - s[:, None]
        r = classify(j[:, None], E, s[:, None], ti)
        tally(cats["score"], r)
        per_bit += np.stack([r["ok32"].sum(0), r["mis32"].sum(0), r["unloc32"].sum(0),
                             r["ok40"].sum(0), r["okrng"].sum(0)], axis=1)

        # Akumulator skor: (N, D-1, 32)
        part = prefix[:, :-1, None]
        d = flip(part, ACC_BITS_RANGE[None, None, :]) - part
        E = P.wrap(s[:, None, None] + d) - s[:, None, None]
        tally(cats["acc"], classify(j[:, None, None], E, s[:, None, None], ti))

        # Akumulator checksum C.p dan Cw.p: (D-1, 32) masing-masing.
        for row, which in ((C, 1), (Cw, 2)):
            cpre = np.cumsum(row * p)
            part = cpre[:-1, None]
            Ec = P.wrap(cpre[-1] + flip(part, ACC_BITS_RANGE[None, :]) - part) - cpre[-1]
            d = P.wrap(-Ec)
            d1, d2 = (d, np.zeros_like(d)) if which == 1 else (np.zeros_like(d), d)
            loc = P.localize_np(d1, d2)
            res = {"eff": Ec != 0, "det32": (d1 != 0) | (d2 != 0),
                   "ok32": loc == P.LOC_UNLOC,          # benar: tidak menyalahkan skor mana pun
                   "mis32": loc >= 0, "unloc32": np.zeros_like(Ec, dtype=bool),
                   "dec": np.zeros_like(Ec, dtype=bool)}
            tally(cats["chk"], res)

        # Bit template: (N, D, 8)
        b8 = np.arange(8, dtype=np.int64)
        dT = flip(T[:, :, None], b8[None, None, :], bits=8) - T[:, :, None]
        E = dT * p[None, :, None]
        tally(cats["tmpl"], classify(j[:, None, None], E, s[:, None, None], ti))
    return {"cats": cats, "per_bit": per_bit, "probes": len(probes), "tau": tau}


# --- Contoh fault ganda dan keterbatasan --------------------------------------

def _first(cond):
    idx = np.flatnonzero(cond)
    return int(idx[0]) if len(idx) else None


def demos(ds=None, tau=TAU_REF):
    ds = ds if ds is not None else PD.make_dataset()
    ti = PD.tau_int(tau)
    T = ds["Tq"]
    C, Cw = P.checksum_rows(T)
    out = {"tau": tau, "tau_int": ti}
    base_unknown = P.N * PD.PROBES_PER_ID

    # A. Dua flip bit 31 pada skor a, b dengan (a+1)+(b+1) genap: d1, d2 = 0 mod 2^32.
    pi = base_unknown                                       # probe identitas tak terdaftar
    p = ds["pq"][pi]
    s = P.scores(T, p)
    neg = np.flatnonzero(s < 0)
    a = int(neg[0])
    b = int(next(x for x in neg[1:] if (x - a) % 2 == 0))
    s2 = s.copy()
    s2[[a, b]] = flip(s[[a, b]], 31)
    out["A"] = {"probe": pi, "a": a, "b": b, "s": (int(s[a]), int(s[b])),
                "s_fault": (int(s2[a]), int(s2[b])),
                "d32": P.check(s2, C, Cw, p), "d40": P.check(s2, C, Cw, p, bits=WIDE_BITS),
                "out_of_range": [bool(v < S_LO or v > S_HI) for v in s2[[a, b]]],
                "accept_before": bool((s[[a, b]] >= ti).any()),
                "accept_after": [bool(v) for v in s2[[a, b]] >= ti]}

    # B. Galat sama +2^bit pada s_0 dan s_2: rasio = 2, menyalahkan s_1 yang benar.
    bit = 13
    S = ds["pq"] @ T.T
    pi = _first((((S[:, 0] >> bit) & 1) == 0) & (((S[:, 2] >> bit) & 1) == 0))
    p = ds["pq"][pi]
    s = S[pi]
    s2 = s.copy()
    s2[[0, 2]] = flip(s[[0, 2]], bit)
    d1, d2 = P.check(s2, C, Cw, p)
    k = P.localize(d1, d2)
    fixed = s2.copy()
    fixed[k] -= d1                                          # "koreksi" naif ke indeks hasil lokalisasi
    out["B"] = {"probe": pi, "bit": bit, "d": (d1, d2), "loc": k,
                "s": [int(x) for x in s[:3]], "s_fault": [int(x) for x in s2[:3]],
                "s_fixed": [int(x) for x in fixed[:3]],
                "wrong_after_fix": [int(x) for x in np.flatnonzero(fixed != s)]}

    # C. Galat +e dan -e pada dua skor: d1 = 0 (checksum C saja buta), d2 menangkap.
    a, b, bit = 3, 8, 12
    pi = _first((((S[:, a] >> bit) & 1) == 0) & (((S[:, b] >> bit) & 1) == 1))
    p = ds["pq"][pi]
    s = S[pi]
    s2 = s.copy()
    s2[[a, b]] = flip(s[[a, b]], bit)
    d1, d2 = P.check(s2, C, Cw, p)
    out["C"] = {"probe": pi, "a": a, "b": b, "bit": bit, "E": (int(s2[a] - s[a]), int(s2[b] - s[b])),
                "d": (d1, d2), "loc": P.localize(d1, d2)}

    # D. Dua flip bit di satu baris template yang saling meniadakan untuk probe ini.
    pi = 1
    p = ds["pq"][pi]
    row, bit = 5, 2
    found = None
    for i1 in range(P.D):
        for i2 in range(P.D):
            if (i1 != i2 and p[i1] == p[i2] != 0 and not (T[row, i1] >> bit) & 1
                    and (T[row, i2] >> bit) & 1):
                found = (i1, i2)
                break
        if found:
            break
    i1, i2 = found
    T2 = T.copy()
    T2[row, [i1, i2]] = flip(T[row, [i1, i2]], bit, bits=8)
    S_ok = ds["pq"] @ T.T
    S_bad = ds["pq"] @ T2.T
    det_any = np.any(S_ok != S_bad, axis=1)                # ABFT eksak: terdeteksi iff skor berubah
    out["D"] = {"probe": pi, "row": row, "cols": (i1, i2), "bit": bit, "p": int(p[i1]),
                "d_this": P.check(S_bad[pi], C, Cw, p), "s_changed_this": bool(det_any[pi]),
                "frac_probes_detect": float(det_any.mean()), "n_probes": len(det_any)}

    # E. Fault tunggal pada probe p (dipakai jalur skor dan jalur checksum): tak terdeteksi.
    probes = fault_probes(ds)
    n = changed = undet = 0
    for pi in probes:
        p = ds["pq"][pi]
        s = P.scores(T, p)
        for i in range(P.D):
            for bit in range(8):
                p2 = p.copy()
                p2[i] = flip(p[i], bit, bits=8)
                s2 = P.scores(T, p2)
                n += 1
                undet += P.check(s2, C, Cw, p2) == (0, 0)
                changed += bool(np.any((s2 >= ti) != (s >= ti)))
    out["E"] = {"n": n, "undetected": undet, "decision_changed": changed}
    return out


def self_test():
    ds = PD.make_dataset()
    probes = fault_probes(ds, per_id=1, unknown=2)
    r = run(ds, probes=probes)
    for name in ("score", "acc", "chk"):
        c = r["cats"][name]
        assert c["eff"] == c["n"] and c["det32"] == c["n"], name    # bit flip tunggal: selalu terdeteksi
    t = r["cats"]["tmpl"]
    assert t["det32"] == t["eff"] == t["ok32"]                      # template: deteksi & lokalisasi penuh
    # Analitik, pemeriksa 32 bit: bit 0..26 tidak wrap -> selalu benar. Bit 31: d1 = -2^31,
    # d2 = 0 (k+1 genap) atau -2^31 (k+1 ganjil) -> rasio 1 hanya benar untuk k = 0,
    # salah tunjuk ke s_0 untuk k+1 = 3, 5, .., 15.
    pb, n = r["per_bit"], len(probes)
    assert (pb[:27, 0] == n * P.N).all() and (pb[:27, 1:3] == 0).all()
    assert pb[31].tolist()[:3] == [n, n * (P.N // 2 - 1), n * P.N // 2]
    sc = r["cats"]["score"]
    assert sc["ok32"] + sc["mis32"] + sc["unloc32"] == sc["eff"]
    zeros = sum(int(np.count_nonzero(ds["pq"][pi] == 0)) for pi in probes)
    assert t["n"] - t["eff"] == zeros * P.N * 8 > 0                # tanpa efek tepat saat p_i = 0
    assert r["cats"]["chk"]["mis32"] == 0
    for name in ("score", "acc"):
        c = r["cats"][name]
        assert c["ok40"] == c["okrng"] == c["n"] and c["mis40"] == c["misrng"] == 0, name
    # 40 bit = eksak untuk galat apa pun dari register 32 bit.
    E = np.array([-(1 << 32) + 1, (1 << 32) - 1, -(1 << 31), 1 << 31])
    assert np.array_equal(P.wrap(P.N * E, WIDE_BITS), P.N * E)
    dm = demos(ds)
    assert dm["A"]["d32"] == (0, 0) and dm["A"]["d40"] != (0, 0) and all(dm["A"]["out_of_range"])
    assert dm["B"]["loc"] == 1 and dm["C"]["d"][0] == 0 and dm["C"]["d"][1] != 0
    assert dm["E"]["undetected"] == dm["E"]["n"]
    print("padan_faults model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        import pprint
        r = run()
        pprint.pprint(r["cats"])
        print(r["per_bit"])
        pprint.pprint(demos())
