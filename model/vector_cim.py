"""Model referensi 8-bit Vector Compute-in-SRAM #0642: dot product 8 elemen.

S = sum(w[i] * a[i]), w dan a 8 bit tak bertanda (desain tidak punya mode
bertanda). Hasil dibaca 3 byte MSB dulu; byte pertama memuat S[18:16].
"""

import sys

import numpy as np

N = 8
S_BITS = 19            # lebar s_adder_tree di RTL


def dot(w, a):
    """Dot product eksak tak bertanda."""
    return int(np.dot(np.asarray(w, dtype=np.int64), np.asarray(a, dtype=np.int64)))


def dot_signed(w, a):
    """Tafsiran two's complement (label "negative values" di test upstream)."""
    s = lambda v: np.where(np.asarray(v) >= 128, np.asarray(v) - 256, np.asarray(v))
    return int(np.dot(s(w).astype(np.int64), s(a).astype(np.int64)))


def to_bytes(s):
    """S -> 3 byte urutan baca (MSB dulu)."""
    return [(s >> 16) & 0x07, (s >> 8) & 0xFF, s & 0xFF]


def self_test():
    assert dot([1] * 8, [1, 2, 3, 4, 5, 6, 7, 8]) == 36
    worst = dot([255] * 8, [255] * 8)
    assert worst == 520200 < 1 << S_BITS, "dot maksimum harus muat 19 bit"
    assert worst >= 1 << (S_BITS - 1)           # dan memang butuh bit ke-19
    assert to_bytes(worst) == [0x07, 0xF0, 0x08]           # 0x7F008
    assert dot_signed([255] * 8, [255] * 8) == 8           # (-1)*(-1)*8
    assert dot_signed([128] * 8, [128] * 8) == 8 * 16384
    rng = np.random.default_rng(1)
    for _ in range(1000):
        w, a = rng.integers(0, 256, 8), rng.integers(0, 256, 8)
        assert dot(w, a) == sum(int(x) * int(y) for x, y in zip(w, a))
    print("vector_cim model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
