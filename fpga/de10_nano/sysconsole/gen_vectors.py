"""Bangkitkan padan_vectors.tcl untuk padan_test.tcl dari model/padan.py.

    python3 fpga/de10_nano/sysconsole/gen_vectors.py --write   # tulis padan_vectors.tcl
    python3 fpga/de10_nano/sysconsole/gen_vectors.py --check   # gagal jika berbeda

Isi (deterministik, seed tetap):
  g0  galeri sintetis docs/padan_model.md bagian 3 (16 identitas), 24 probe
      (12 identitas terdaftar, 12 tak terdaftar) dengan tau rilis bergiliran
  g1  galeri INT8 acak + template kembar (seri), tau = max / max+1 / max-1
  g2  galeri ekstrem -128/127, tau di batas skor

Setiap kasus menyimpan STATUS yang diharapkan (12 bit bawah: kode, idx, ~idx),
dihitung dengan decide() di model/padan.py.
"""

import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "model"))

import padan as P          # noqa: E402
import padan_data as PD    # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "padan_vectors.tcl"
C_NO_MATCH, C_MATCH = 0x5, 0xA


def words(bytes_):
    b = [int(x) & 0xFF for x in bytes_]
    return [b[i] | b[i + 1] << 8 | b[i + 2] << 16 | b[i + 3] << 24 for i in range(0, len(b), 4)]


def expected_status(T, p, tau):
    res, k = P.decide(P.scores(T, p), tau)
    if res == P.MATCH:
        return C_MATCH | k << 4 | ((~k) & 0xF) << 8
    return C_NO_MATCH | 0xF << 8


def hexlist(ws, per_line=8):
    lines = [" ".join(f"0x{w:08X}" for w in ws[i:i + per_line]) for i in range(0, len(ws), per_line)]
    return "{\n    " + "\n    ".join(lines) + "\n}"


def galleries():
    rng = np.random.default_rng(2027)
    out = []

    ds = PD.make_dataset()
    gen = [k * PD.PROBES_PER_ID + 7 for k in range(0, P.N, P.N // 12 + 1)][:12]
    unk = [P.N * PD.PROBES_PER_ID + u * PD.PROBES_PER_UNKNOWN + 3 for u in range(12)]
    cases = []
    for n, i in enumerate(gen + unk):
        tau = PD.tau_int(PD.TAUS[n % len(PD.TAUS)])
        cases.append((ds["pq"][i], tau, f"probe sintetis {i}, tau {PD.TAUS[n % len(PD.TAUS)]}"))
    out.append(("sintetis (docs/padan_model.md bagian 3)", ds["Tq"], cases))

    T = rng.integers(P.INT8_MIN, P.INT8_MAX + 1, (P.N, P.D))
    T[11] = T[2]
    cases = []
    for k in range(6):
        p = T[2] if k == 0 else rng.integers(P.INT8_MIN, P.INT8_MAX + 1, P.D)
        m = int(P.scores(T, p).max())
        for tau, why in ((m, "max"), (m + 1, "max+1"), (m - 1, "max-1")):
            cases.append((p, tau, f"acak {k}, tau = {why}" + (" (seri 2/11)" if k == 0 else "")))
    out.append(("acak + template kembar", T, cases))

    T = np.full((P.N, P.D), -128)
    T[P.N - 1] = 127
    cases = []
    for pv in (-128, 127):
        p = np.full(P.D, pv)
        for tau in (2097152, 2097153, -2080768, 0):
            cases.append((p, tau, f"ekstrem p = {pv}, tau = {tau}"))
    out.append(("ekstrem -128/127", T, cases))
    return out


def build():
    lines = [
        "# Dihasilkan oleh fpga/de10_nano/sysconsole/gen_vectors.py dari model/padan.py.",
        "# Jangan disunting tangan.",
        "",
        "array unset PADAN_VEC",
    ]
    gs = galleries()
    lines.append(f"set PADAN_VEC(galleries) {len(gs)}")
    for g, (name, T, cases) in enumerate(gs):
        lines.append(f'set PADAN_VEC(g{g},name) "{name}"')
        lines.append(f"set PADAN_VEC(g{g},T) {hexlist(words(T.reshape(-1)))}")
        lines.append(f"set PADAN_VEC(g{g},cases) {len(cases)}")
        for c, (p, tau, note) in enumerate(cases):
            lines.append(f"set PADAN_VEC(g{g},c{c},p) {hexlist(words(p))}")
            lines.append(f"set PADAN_VEC(g{g},c{c},tau) 0x{tau & 0xFFFFFFFF:08X}")
            lines.append(f"set PADAN_VEC(g{g},c{c},status) 0x{expected_status(T, p, tau):03X}")
            lines.append(f'set PADAN_VEC(g{g},c{c},note) "{note}"')
    return "\n".join(lines) + "\n"


def summary():
    gs = galleries()
    n = sum(len(c) for _, _, c in gs)
    match = sum(expected_status(T, p, tau) & 0xF == C_MATCH for _, T, cs in gs for p, tau, _ in cs)
    return len(gs), n, match


def main(argv):
    text = build()
    if argv[1:] == ["--write"]:
        OUT.write_text(text)
    elif argv[1:] == ["--check"]:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"FAIL {OUT.relative_to(ROOT)} tidak sama dengan keluaran model; jalankan "
                  f"python3 {pathlib.Path(__file__).relative_to(ROOT)} --write")
            return 1
        g, n, m = summary()
        print(f"PASS {OUT.relative_to(ROOT)} sama dengan keluaran model ({g} galeri, {n} kasus, {m} MATCH)")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
