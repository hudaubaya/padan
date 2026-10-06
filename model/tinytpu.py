"""Model referensi TinyTPU #0590: perkalian matriks 2x2 tak bertanda 8 bit.

Ini model *maksud* desain (Z = X @ Y, eksak, tanpa batas lebar), bukan model
cacat RTL. Format serial yang dipakai baseline (dibaca dari RTL, lihat
docs/baseline_audit.md):

- ``ui_in[0]`` membawa X baris demi baris: x00, x01, x10, x11; tiap byte LSB dulu.
- ``ui_in[1]`` membawa Y kolom demi kolom: y00, y10, y01, y11; tiap byte LSB dulu
  (``mem_y[j]`` di RTL adalah kolom j).
- ``uo_out[0]`` mengeluarkan z00, z01, z10, z11, masing-masing 16 bit, LSB dulu.
"""

import sys

import numpy as np

D_W = 8
N = 2
Z_W = 2 * D_W          # lebar akumulator per MAC di RTL


def matmul(x, y):
    """Z = X @ Y eksak (int64)."""
    return np.asarray(x, dtype=np.int64) @ np.asarray(y, dtype=np.int64)


def pack_x(x):
    """Matriks X -> 32 bit urutan kirim (baris demi baris, LSB dulu)."""
    x = np.asarray(x)
    return sum(int(v) << (8 * i) for i, v in enumerate(x.reshape(-1)))


def pack_y(y):
    """Matriks Y -> 32 bit urutan kirim (kolom demi kolom, LSB dulu)."""
    y = np.asarray(y)
    return sum(int(v) << (8 * i) for i, v in enumerate(y.T.reshape(-1)))


def bits_lsb_first(word, n):
    return [(word >> i) & 1 for i in range(n)]


def z_from_bits(bits):
    """64 bit keluaran serial -> matriks Z 2x2 (16 bit per elemen)."""
    assert len(bits) == N * N * Z_W
    vals = [sum(b << i for i, b in enumerate(bits[k * Z_W:(k + 1) * Z_W])) for k in range(N * N)]
    return np.array(vals, dtype=np.int64).reshape(N, N)


def z_to_bits(z):
    out = []
    for v in np.asarray(z).reshape(-1):
        out += bits_lsb_first(int(v), Z_W)
    return out


def self_test():
    x = [[1, 2], [3, 4]]
    y = [[5, 6], [7, 8]]
    assert matmul(x, y).tolist() == [[19, 22], [43, 50]]
    assert pack_x(x) == 0x04030201
    assert pack_y(y) == 0x08060705          # y00, y10, y01, y11
    z = matmul(x, y)
    assert z_from_bits(z_to_bits(z)).tolist() == z.tolist()
    # nilai ekstrem: 2*255*255 butuh 17 bit, tidak muat di akumulator 16 bit RTL
    big = matmul([[255, 255]] * 2, [[255, 255]] * 2)
    assert int(big.max()) == 130050 and int(big.max()) >= 1 << Z_W
    rng = np.random.default_rng(1)
    for _ in range(1000):
        a = rng.integers(0, 256, (2, 2))
        b = rng.integers(0, 256, (2, 2))
        ref = [[sum(int(a[i, k]) * int(b[k, j]) for k in range(2)) for j in range(2)] for i in range(2)]
        assert matmul(a, b).tolist() == ref
    print("tinytpu model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
