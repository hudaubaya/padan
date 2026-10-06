"""Analisis batas nilai PADAN: semua perhitungan tanpa fault muat 32 bit.

Aritmetika interval atas T, p di [-128, 127] (seluruh rentang INT8, bukan hanya
rentang kuantisasi [-127, 127]). Setiap suku penjumlahan punya batas bawah <= 0
<= batas atas, jadi setiap jumlah parsial (isi akumulator di tengah jalan)
terkandung dalam interval jumlah totalnya. Batas yang dilaporkan untuk sebuah
jumlah juga berlaku untuk semua isi akumulator sebelum jumlah itu selesai.

Batas ini ketat: self_test() membangun masukan yang mencapai ekstrem utama.
"""

import sys

import numpy as np

import padan as P


def mul(a, b):
    c = [x * y for x in a for y in b]
    return min(c), max(c)


def scale(k, a):
    """Jumlah k suku yang masing-masing di interval a (k >= 0)."""
    return k * a[0], k * a[1]


def sub(a, b):
    return a[0] - b[1], a[1] - b[0]


def bits_signed(iv):
    """Lebar two's complement terkecil yang memuat interval iv."""
    lo, hi = iv
    b = 1
    while not (-(1 << (b - 1)) <= lo and hi <= (1 << (b - 1)) - 1):
        b += 1
    return b


def intervals(D=P.D, N=P.N):
    """Daftar (nama, rumus, interval) untuk setiap besaran di jalur data dan pemeriksa."""
    i8 = (P.INT8_MIN, P.INT8_MAX)
    W = N * (N + 1) // 2                      # sum_j (j+1)
    prod = mul(i8, i8)
    s = scale(D, prod)
    C = scale(N, i8)
    Cw = scale(W, i8)                         # sum_j (j+1) T[j,i]: bobot positif
    Cp_term = mul(C, i8)
    Cp = scale(D, Cp_term)
    Cwp_term = mul(Cw, i8)
    Cwp = scale(D, Cwp_term)
    ws = mul((1, N), s)                       # (j+1) * s_j
    sum_s = scale(N, s)
    # sum_j (j+1) s_j: bobot positif, jadi intervalnya W kali interval s.
    sum_ws = scale(W, s)
    return [
        ("T[j,i], p[i]", "INT8", i8),
        ("T[j,i] * p[i]", "produk", prod),
        ("s_j (dan isi akumulatornya)", f"{D} produk", s),
        ("C_i", f"{N} elemen T", C),
        ("Cw_i", f"bobot 1..{N}, total {W}", Cw),
        ("C_i * p_i", "", Cp_term),
        ("C . p (dan isi akumulatornya)", f"{D} suku", Cp),
        ("Cw_i * p_i", "", Cwp_term),
        ("Cw . p (dan isi akumulatornya)", f"{D} suku", Cwp),
        ("(j+1) * s_j", "", ws),
        ("sum_j s_j (dan isi akumulatornya)", f"{N} skor", sum_s),
        ("sum_j (j+1) s_j (dan isi akumulatornya)", f"bobot total {W}", sum_ws),
        ("d1 = sum s - C.p (konservatif)", "selisih interval", sub(sum_s, Cp)),
        ("d2 = sum (j+1)s - Cw.p (konservatif)", "selisih interval", sub(sum_ws, Cwp)),
    ]


def fits(D, N, bits=P.ACC_BITS, conservative=True):
    rows = intervals(D, N)
    if not conservative:                       # tanpa fault d1 = d2 = 0
        rows = [r for r in rows if not r[0].startswith("d")]
    return all(bits_signed(iv) <= bits for _, _, iv in rows)


def max_D(N, conservative=True):
    lo, hi = 1, 1 << 16
    assert fits(lo, N, conservative=conservative) and not fits(hi, N, conservative=conservative)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if fits(mid, N, conservative=conservative) else (lo, mid)
    return lo


def max_N(D, conservative=True):
    n = 1
    while fits(D, n + 1, conservative=conservative):
        n += 1
    return n


def self_test():
    rows = {name: iv for name, _, iv in intervals()}
    assert all(bits_signed(iv) <= 32 for iv in rows.values()), "ada besaran > 32 bit"
    assert rows["s_j (dan isi akumulatornya)"] == (-2080768, 2097152)
    assert rows["Cw_i"] == (-17408, 17272)
    assert rows["Cw . p (dan isi akumulatornya)"] == (-282984448, 285212672)
    assert rows["d2 = sum (j+1)s - Cw.p (konservatif)"] == (-568197120, 568197120)

    # Ketat: masukan yang mencapai ekstrem, dihitung dengan golden model.
    T = np.full((P.N, P.D), -128)
    for pv, key in ((-128, 1), (127, 0)):
        p = np.full(P.D, pv)
        s = P.scores(T, p)
        C, Cw = P.checksum_rows(T)
        w_s = int(P.WEIGHTS @ s)
        cwp = int(Cw @ p)
        assert w_s == cwp == rows["Cw . p (dan isi akumulatornya)"][key]
        assert int(s[0]) == rows["s_j (dan isi akumulatornya)"][key]
        assert int(C @ p) == int(s.sum()) == rows["sum_j s_j (dan isi akumulatornya)"][key]
        assert P.check(s, C, Cw, p) == (0, 0)
        assert np.array_equal(P.wrap(s), s) and P.wrap(cwp) == cwp
    assert int(Cw.min()) == -17408 and bits_signed((-17408, 17272)) == 16

    assert fits(128, 16) and not fits(128, 16, bits=29)
    assert max_D(16) == 483 and max_D(16, conservative=False) == 963
    assert max_N(128) == 31 and max_N(128, conservative=False) == 44
    print("padan_bounds model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        for name, why, iv in intervals():
            print(f"{name:45s} [{iv[0]:>13,}, {iv[1]:>13,}]  {bits_signed(iv):2d} bit")
