"""Model referensi Iterative MAC #0040.

``docs/info.md`` upstream hanya menyebut: operand 1 (7 bit) dimuat dari
``ui_in[6:0]`` saat reset, operand 2 masuk lewat ``ui_in`` tiap clock,
operand 3 (bias) lewat ``uio_in`` "dalam urutan berbeda", keluaran di ``uo_out``.
Urutan byte di bawah dibaca dari RTL (``temp_b`` per state) dan dipastikan
dengan simulasi; lihat docs/baseline_audit.md.

Mode 1 (``ui_in[7]=1`` saat reset), satu operasi = 4 clock (state 1, 2, 3, 4):

- ``ui_in``  : b1, b2, b3, b4  -> B = b1<<24 | b2<<16 | b3<<8 | b4
- ``uio_in`` : c1, c2, c3, c4  -> C = c3<<24 | c4<<16 | c1<<8 | c2
- hasil      : R = floor(a * B / 2^8) + C   (eksak; RTL memotong ke 32 bit)
- ``uo_out`` : byte R MSB dulu, mulai siklus terakhir operasi itu (4 byte).
"""

import sys

MASK32 = (1 << 32) - 1


def mul7x8(a, b):
    assert 0 <= a < 128 and 0 <= b < 256
    return a * b


def operand_b(bs):
    b1, b2, b3, b4 = bs
    return (b1 << 24) | (b2 << 16) | (b3 << 8) | b4


def operand_c(cs):
    c1, c2, c3, c4 = cs
    return (c3 << 24) | (c4 << 16) | (c1 << 8) | c2


def mac(a, bs, cs):
    """Hasil eksak satu operasi mode 1 (tanpa pemotongan 32 bit)."""
    return (a * operand_b(bs)) // 256 + operand_c(cs)


def mac_rtl_terms(a, bs, cs):
    """Penjumlahan suku per state persis seperti RTL (temp_b), modulo 2^32."""
    (b1, b2, b3, b4), (c1, c2, c3, c4) = bs, cs
    o = [a * b for b in bs]
    s = (o[0] << 16) + (c1 << 8)            # state 1: {1'b0, out, uio_in, 8'd0}
    s += (o[1] << 8) + c2                   # state 2: {9'b0, out, uio_in}
    s += (c3 << 24) + o[2]                  # state 3: {uio_in, 9'd0, out}
    s += (c4 << 16) + (o[3] >> 8)           # state 4: {8'd0, uio_in, 9'd0, out[14:8]}
    return s & MASK32


def to_bytes_msb_first(r):
    return [(r >> s) & 0xFF for s in (24, 16, 8, 0)]


def self_test():
    import random
    rng = random.Random(1)
    assert mul7x8(127, 255) == 32385 < 1 << 15
    for _ in range(20000):
        a = rng.randrange(128)
        bs = [rng.randrange(256) for _ in range(4)]
        cs = [rng.randrange(256) for _ in range(4)]
        # suku-suku RTL = floor(a*B/256) + C (mod 2^32): pemotongan out[14:8] di
        # state 4 sama dengan floor karena suku lain bilangan bulat
        assert mac_rtl_terms(a, bs, cs) == mac(a, bs, cs) & MASK32
    # contoh dari simulasi: a=11, b=(2,3,4,5), c=(0x20,0x30,0x40,0)
    assert mac(11, (2, 3, 4, 5), (0x20, 0x30, 0x40, 0)) == 0x4016415C
    worst = mac(127, (255,) * 4, (255,) * 4)
    assert worst > MASK32                   # bisa melampaui 32 bit
    print("iterative_mac model: self-test OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
