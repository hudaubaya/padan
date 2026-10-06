"""Golden model integer PADAN: skor template x probe INT8 dengan ABFT.

    s_j   = sum_i T[j,i] * p[i]          T: N x D INT8, p: D INT8, akumulator 32 bit
    C_i   = sum_j T[j,i]                 baris checksum
    Cw_i  = sum_j (j+1) * T[j,i]         baris checksum berbobot
    d1    = sum_j s_j         - C  . p
    d2    = sum_j (j+1) * s_j - Cw . p

Tanpa fault d1 = d2 = 0. Satu galat e pada s_k memberi d1 = e dan
d2 = (k+1) * e, jadi indeks k = d2/d1 - 1 (rasio dua selisih).

Semua aritmetika di sini integer Python/NumPy int64 (eksak). Register perangkat
keras 32 bit dimodelkan dengan wrap() (two's complement, modulo 2^32).
Batas nilai yang menjamin tidak ada wrap tanpa fault: model/padan_bounds.py.
"""

import sys

import numpy as np

D = 128                 # dimensi vektor fitur
N = 16                  # jumlah template per galeri
INT8_MIN, INT8_MAX = -128, 127
ACC_BITS = 32           # lebar akumulator skor dan pemeriksa ABFT
WEIGHTS = np.arange(1, N + 1, dtype=np.int64)   # bobot (j+1)

# Hasil localize()
LOC_OK = -2             # d1 = d2 = 0: tidak ada galat terdeteksi
LOC_UNLOC = -1          # galat terdeteksi, rasio bukan indeks skor 1..N


def wrap(x, bits=ACC_BITS):
    """Tafsirkan x sebagai register two's complement `bits` bit (int atau array)."""
    if bits is None:
        return x
    half = 1 << (bits - 1)
    return ((x + half) & ((1 << bits) - 1)) - half


def as_int8(a):
    a = np.asarray(a, dtype=np.int64)
    assert a.min(initial=0) >= INT8_MIN and a.max(initial=0) <= INT8_MAX, "di luar INT8"
    return a


def scores(T, p):
    """s = T @ p, eksak (int64). Tanpa fault nilainya muat 32 bit (padan_bounds)."""
    return as_int8(T) @ as_int8(p)


def checksum_rows(T):
    """(C, Cw): C_i = sum_j T[j,i], Cw_i = sum_j (j+1) T[j,i]. Dihitung saat enrolment."""
    T = as_int8(T)
    w = np.arange(1, T.shape[0] + 1, dtype=np.int64)
    return T.sum(axis=0), w @ T


def check(s, C, Cw, p, bits=ACC_BITS):
    """(d1, d2) dari skor s (nilai register) dan baris checksum.

    bits=32 memodelkan pemeriksa dengan register 32 bit (hasil modulo 2^32);
    bits=None memodelkan pemeriksa cukup lebar (eksak).
    """
    s = np.asarray(s, dtype=np.int64)
    p = as_int8(p)
    w = np.arange(1, len(s) + 1, dtype=np.int64)
    d1 = int(s.sum()) - int(np.asarray(C) @ p)
    d2 = int(w @ s) - int(np.asarray(Cw) @ p)
    return wrap(d1, bits), wrap(d2, bits)


def localize(d1, d2, n=N):
    """Indeks skor yang salah dari rasio d2/d1, atau LOC_OK / LOC_UNLOC."""
    if d1 == 0 and d2 == 0:
        return LOC_OK
    if d1 != 0 and d2 % d1 == 0 and 1 <= d2 // d1 <= n:
        return d2 // d1 - 1
    return LOC_UNLOC


def localize_np(d1, d2, n=N):
    """localize() untuk array int64."""
    d1 = np.asarray(d1, dtype=np.int64)
    d2 = np.asarray(d2, dtype=np.int64)
    safe = np.where(d1 == 0, 1, d1)
    r = d2 // safe
    good = (d1 != 0) & (d2 % safe == 0) & (r >= 1) & (r <= n)
    return np.where((d1 == 0) & (d2 == 0), LOC_OK, np.where(good, r - 1, LOC_UNLOC))


# Keputusan (rtl/decision.v): identifikasi 1:N dengan ambang.
MATCH, NO_MATCH, FAULT = "MATCH", "NO_MATCH", "FAULT"


def decide(s, tau_int):
    """(MATCH, k) jika max_j s_j >= tau_int, dengan k = argmax (indeks terkecil bila
    seri); selain itu (NO_MATCH, None). Indeks tidak dilaporkan untuk NO_MATCH."""
    s = np.asarray(s, dtype=np.int64)
    k = int(np.argmax(s))                       # np.argmax: indeks pertama bila seri
    return (MATCH, k) if int(s[k]) >= tau_int else (NO_MATCH, None)


def self_test():
    # Contoh kecil yang bisa dihitung tangan (N=3, D=2).
    T = np.array([[1, 2], [3, -4], [-5, 6]])
    p = np.array([7, -1])
    s = scores(T, p)
    assert s.tolist() == [5, 25, -41]
    C, Cw = checksum_rows(T)
    assert C.tolist() == [-1, 4] and Cw.tolist() == [-8, 12]   # 1*1+2*3+3*(-5), 1*2+2*(-4)+3*6
    assert check(s, C, Cw, p) == (0, 0)
    s_bad = s.copy()
    s_bad[1] += 9
    assert check(s_bad, C, Cw, p) == (9, 18)
    assert localize(9, 18, n=3) == 1

    rng = np.random.default_rng(2)
    T = rng.integers(INT8_MIN, INT8_MAX + 1, (N, D))
    C, Cw = checksum_rows(T)
    for _ in range(200):
        p = rng.integers(INT8_MIN, INT8_MAX + 1, D)
        s = scores(T, p)
        assert check(s, C, Cw, p) == (0, 0)
        assert np.array_equal(wrap(s), s)                       # tanpa wrap
        # Satu galat di skor mana pun, nilai mana pun yang tidak overflow: terlokalisasi.
        k = int(rng.integers(N))
        e = int(rng.integers(-(1 << 20), 1 << 20)) or 1
        s_bad = s.copy()
        s_bad[k] += e
        d1, d2 = check(s_bad, C, Cw, p, bits=None)
        assert (d1, d2) == (e, (k + 1) * e) and localize(d1, d2) == k
        # Dua galat di skor berbeda tidak pernah saling meniadakan secara eksak:
        # det [[1, 1], [a+1, b+1]] = b - a != 0.
        a, b = rng.choice(N, 2, replace=False)
        ea, eb = (int(v) or 1 for v in rng.integers(-1000, 1000, 2))
        s_bad = s.copy()
        s_bad[a] += ea
        s_bad[b] += eb
        assert check(s_bad, C, Cw, p, bits=None) != (0, 0)

    assert decide([5, 9, 9, 1], 9) == (MATCH, 1)          # seri: indeks terkecil
    assert decide([5, 9, 9, 1], 10) == (NO_MATCH, None)
    assert decide([-7, -3, -3], -3) == (MATCH, 1)

    assert wrap(1 << 31) == -(1 << 31) and wrap(-(1 << 31) - 1) == (1 << 31) - 1
    d1 = np.array([0, 5, 5, -3, 7, 0])
    d2 = np.array([0, 10, 11, -48, 7 * 17, 4])
    assert localize_np(d1, d2).tolist() == [LOC_OK, 1, LOC_UNLOC, 15, LOC_UNLOC, LOC_UNLOC]
    assert [localize(int(x), int(y)) for x, y in zip(d1, d2)] == localize_np(d1, d2).tolist()
    print("padan model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
