"""Periksa laporan Vivado proyek KV260 (docs/fpga_howto.md, langkah build).

    python3 fpga/kv260/check_reports.py <dir_proyek>/reports
    python3 fpga/kv260/check_reports.py --self-test

Dari utilization_hier.rpt (report_utilization -hierarchical), baris pertama
per modul:

    template_mem  RAMB18 + 2 x RAMB36 == 16   satu block RAM 18 Kb per bank lane
                  LUTRAMs == 0
    mac_array     DSP Blocks == 16            satu DSP48E2 per lane 16x8
                  LUTRAMs == 0                probe tetap register
    decision      FFs == 151                  register kedua komparator tidak digabung
    guard         FFs == 103                  register redundan (nilai + komplemen) bertahan

Angka harapan sama dengan tb/padan/infer_check.sh (Yosys). Dari
timing_summary.rpt (report_timing_summary): WNS, WHS, dan WPWS >= 0 dan
"All user specified timing constraints are met."

Format laporan diasumsikan dari Vivado 2022-2024 dan BELUM pernah diuji
terhadap laporan asli (Vivado tidak tersedia di lingkungan pembuatnya).
--self-test hanya memeriksa logika parser terhadap contoh sintetis. Bila tabel
tidak ditemukan, skrip berhenti dengan pesan; periksa manual di GUI.
"""

import pathlib
import re
import sys

EXPECT = [
    ("template_mem", "BRAM18", "==", 16),
    ("template_mem", "LUTRAMs", "==", 0),
    ("mac_array", "DSP Blocks", "==", 16),
    ("mac_array", "LUTRAMs", "==", 0),
    ("decision", "FFs", "==", 151),
    ("guard", "FFs", "==", 103),
]


def hier_table(text):
    """(header, rows) dari tabel utilisasi hierarkis (kolom Instance | Module | ...)."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if ln.lstrip().startswith("|") and cells[:2] == ["Instance", "Module"]:
            rows = []
            for r in lines[i + 1:]:
                if r.lstrip().startswith("+"):
                    continue
                if not r.lstrip().startswith("|"):
                    break
                rows.append([c.strip() for c in r.strip().strip("|").split("|")])
            return cells, rows
    raise SystemExit("tabel utilisasi hierarkis (Instance | Module) tidak ditemukan; periksa manual")


def module_row(header, rows, module):
    """Baris pertama yang kolom Module-nya `module` (atau berakhiran _<module>_N)."""
    for r in rows:
        m = r[1]
        if m == module or re.fullmatch(rf"\S*_{re.escape(module)}(_\d+)?", m):
            row = dict(zip(header, r))
            return {k: v for k, v in row.items()}
    raise SystemExit(f"modul {module} tidak ditemukan di tabel utilisasi; periksa manual")


def num(row, col):
    v = row.get(col)
    if v is None:
        raise SystemExit(f"kolom {col!r} tidak ada di tabel utilisasi; periksa manual")
    return float(v)


def check_util(text, log=print):
    header, rows = hier_table(text)
    ok = True
    for module, col, op, want in EXPECT:
        row = module_row(header, rows, module)
        got = num(row, "RAMB18") + 2 * num(row, "RAMB36") if col == "BRAM18" else num(row, col)
        good = got == want if op == "==" else got >= want
        label = "RAMB18 + 2 x RAMB36" if col == "BRAM18" else col
        log(f"{'PASS' if good else 'FAIL'} {module}: {label} = {got:g} (harapan {op} {want})")
        ok &= good
    top = rows[0]
    log("INFO total " + ", ".join(f"{h} {v}" for h, v in zip(header[2:], top[2:])))
    return ok


def check_timing(text, log=print):
    i = text.find("Design Timing Summary")
    if i < 0:
        raise SystemExit("bagian 'Design Timing Summary' tidak ditemukan; periksa manual")
    lines = text[i:].splitlines()
    h = next((k for k, ln in enumerate(lines) if "WNS(ns)" in ln), None)
    if h is None:
        raise SystemExit("baris kepala WNS(ns) tidak ditemukan; periksa manual")
    # Kepala kolom memuat spasi ("TNS Failing Endpoints"); urutan nilai tetap:
    # WNS TNS TNS-fail TNS-total WHS THS THS-fail THS-total WPWS TPWS ...
    vals = next(ln.split() for ln in lines[h + 1:] if re.match(r"\s*-?\d", ln))
    if len(vals) < 12:
        raise SystemExit(f"baris Design Timing Summary tak terduga: {vals}; periksa manual")
    ok = True
    for k, x in (("WNS(ns)", vals[0]), ("WHS(ns)", vals[4]), ("WPWS(ns)", vals[8])):
        x = float(x)
        good = x >= 0
        log(f"{'PASS' if good else 'FAIL'} timing {k} = {x:g}")
        ok &= good
    met = "All user specified timing constraints are met." in text
    log(f"{'PASS' if met else 'FAIL'} timing: semua constraint terpenuhi")
    return ok and met


def check_dir(d):
    d = pathlib.Path(d)
    ok = check_util((d / "utilization_hier.rpt").read_text())
    ok &= check_timing((d / "timing_summary.rpt").read_text())
    print("PASS laporan Vivado KV260" if ok else "FAIL laporan Vivado KV260")
    return 0 if ok else 1


# ---------------------------------------------------------------- self-test --

UTIL = """\
1. Utilization by Hierarchy
---------------------------

+------------------------+--------------------+------------+------------+---------+------+------+--------+--------+------+------------+
|        Instance        |       Module       | Total LUTs | Logic LUTs | LUTRAMs | SRLs |  FFs | RAMB36 | RAMB18 | URAM | DSP Blocks |
+------------------------+--------------------+------------+------------+---------+------+------+--------+--------+------+------------+
| padan_bd_wrapper       |              (top) |       5000 |       4900 |      60 |   40 | 4000 |      0 |     16 |    0 |         19 |
|   padan_bd_i           |           padan_bd |       5000 |       4900 |      60 |   40 | 4000 |      0 |     16 |    0 |         19 |
|     padan_0            | padan_bd_padan_0_0 |       4200 |       4189 |       0 |   11 | 2632 |      0 |     16 |    0 |         19 |
|       inst             |         padan_axil |       4200 |       4189 |       0 |   11 | 2632 |      0 |     16 |    0 |         19 |
|         u_core         |         padan_avmm |       4100 |       4089 |       0 |   11 | 2550 |      0 |     16 |    0 |         19 |
|           u_dec        |           decision |        135 |        135 |       0 |    0 |  151 |      0 |      0 |    0 |          0 |
|           u_guard      |              guard |        169 |        169 |       0 |    0 |  103 |      0 |      0 |    0 |          0 |
|           u_mac        |          mac_array |       3100 |       3089 |       0 |   11 | 1866 |      0 |      0 |    0 |         16 |
|           u_mem        |       template_mem |        286 |        286 |       0 |    0 |   86 |      %s |     %s |    0 |          1 |
+------------------------+--------------------+------------+------------+---------+------+------+--------+--------+------+------------+
"""

TIMING = """\
------------------------------------------------------------------------------------------------
| Design Timing Summary
| ---------------------
------------------------------------------------------------------------------------------------

    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
      %s        0.000                      0                 9000        0.010        0.000                      0                 9000        3.500        0.000                       0                  4100


%s
"""


def self_test():
    """Kasus positif harus PASS dan kasus negatif harus FAIL. Keluaran per baris
    disembunyikan supaya FAIL yang disengaja tidak terbaca sebagai kegagalan."""
    met = "All user specified timing constraints are met."
    quiet = lambda *a, **k: None   # noqa: E731
    cases = [
        ("utilisasi normal", check_util, UTIL % ("0", "16"), True),
        ("RAMB18 dikemas 2 per RAMB36", check_util, UTIL % ("8", "0"), True),
        ("RAMB18 hanya 8", check_util, UTIL % ("0", "8"), False),
        ("FF decision 149 (register digabung)", check_util,
         (UTIL % ("0", "16")).replace("|  151 |", "|  149 |"), False),
        ("timing terpenuhi", check_timing, TIMING % ("1.234", met), True),
        ("WNS negatif", check_timing, TIMING % ("-0.100", "Timing constraints are not met."), False),
        ("constraint tidak terpenuhi", check_timing, TIMING % ("0.500", "Timing constraints are not met."), False),
    ]
    for name, fn, text, want in cases:
        got = fn(text, log=quiet)
        if got != want:
            print(f"FAIL check_reports.py --self-test: kasus '{name}' memberi {got}, harapan {want}")
            return 1
    try:
        hier_table("tidak ada tabel")
        print("FAIL check_reports.py --self-test: tabel hilang harus berhenti")
        return 1
    except SystemExit:
        pass
    neg = sum(1 for c in cases if not c[3])
    print(f"PASS check_reports.py --self-test ({len(cases) - neg} kasus harus lolos, {neg} kasus harus ditolak, "
          "1 tabel hilang; parser terhadap contoh sintetis, bukan laporan Vivado asli)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(check_dir(sys.argv[1]))
