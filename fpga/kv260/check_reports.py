"""Periksa laporan Vivado proyek KV260 (docs/fpga_howto.md bagian 5).

    python3 fpga/kv260/check_reports.py <dir_proyek>/reports
    python3 fpga/kv260/check_reports.py --self-test

1. utilization_hier.rpt (report_utilization -hierarchical), baris pertama per
   modul:

    template_mem  RAMB18 + 2 x RAMB36 == 16   satu block RAM 18 Kb per bank lane
                  LUTRAMs == 0
    mac_array     16 <= DSP Blocks <= 18      16 pengali lane; Vivado boleh
                                              memakai 2 DSP lagi untuk adder `tree`
                  LUTRAMs == 0                probe tetap register
    decision      FFs == 151                  register kedua komparator tidak digabung
    guard         FFs == 103                  register redundan (nilai + komplemen) bertahan

   Yosys (tb/padan/infer_check.sh) memberi tepat 16 DSP untuk mac_array.
   Vivado 2026.1 memberi 18: 16 DSP lane yang menyerap `g_sum4[*].sum` lewat
   kaskade, ditambah `tree0` dan `tree_reg` (adder 4 masukan di ALU DSP).
   Kurang dari 16 berarti ada pengali di fabric; lebih dari 18 belum pernah
   terlihat dan harus dicari penyebabnya.

2. timing_summary.rpt (report_timing_summary): WNS, WHS, WPWS >= 0, "All user
   specified timing constraints are met.", dan clk_pl_0 berperiode 10,000 ns.

3. cdc.rpt (report_cdc): tepat satu perlintasan, dari input port (tamper_n) ke
   clk_pl_0, 1 endpoint, Unsafe/Unknown/No ASYNC_REG = 0.

4. Log sintesis (<dir_proyek>/padan_kv260.runs/*/runme.log): tidak ada FSM
   yang diekstrak di guard atau decision (fsm_encoding = "none"). FSM lain yang
   dikode ulang dicetak sebagai INFO.

Format laporan dicek terhadap laporan asli Vivado 2026.1 (fpga/kv260/testdata,
dari build pengguna 21 Oktober 2026). Versi Vivado lain bisa berbeda; bila
tabel tidak ditemukan, skrip berhenti dengan pesan, periksa manual di GUI.
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
TESTDATA = HERE / "testdata" / "vivado_2026.1"

EXPECT = [
    ("template_mem", "BRAM18", (16, 16)),
    ("template_mem", "LUTRAMs", (0, 0)),
    ("mac_array", "DSP Blocks", (16, 18)),
    ("mac_array", "LUTRAMs", (0, 0)),
    ("decision", "FFs", (151, 151)),
    ("guard", "FFs", (103, 103)),
]
CLOCK, PERIOD = "clk_pl_0", 10.0
NO_FSM = ("guard", "decision")


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
            return dict(zip(header, r))
    raise SystemExit(f"modul {module} tidak ditemukan di tabel utilisasi; periksa manual")


def num(row, col):
    v = row.get(col)
    if v is None:
        raise SystemExit(f"kolom {col!r} tidak ada di tabel utilisasi; periksa manual")
    return float(v)


def want_text(lo, hi):
    return f"== {lo}" if lo == hi else f"{lo}..{hi}"


def check_util(text, log=print):
    header, rows = hier_table(text)
    ok = True
    for module, col, (lo, hi) in EXPECT:
        row = module_row(header, rows, module)
        got = num(row, "RAMB18") + 2 * num(row, "RAMB36") if col == "BRAM18" else num(row, col)
        good = lo <= got <= hi
        label = "RAMB18 + 2 x RAMB36" if col == "BRAM18" else col
        log(f"{'PASS' if good else 'FAIL'} {module}: {label} = {got:g} (harapan {want_text(lo, hi)})")
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


def check_clock(text, log=print):
    """clk_pl_0 di tabel Clock Summary harus berperiode 10,000 ns (100 MHz)."""
    i = text.find("Clock Summary")
    if i < 0:
        raise SystemExit("bagian 'Clock Summary' tidak ditemukan; periksa manual")
    period = None
    for ln in text[i:].splitlines()[1:]:
        if re.match(r"\| [A-Za-z]", ln):
            break                                   # judul bagian berikutnya
        m = re.match(rf"{CLOCK}\s+\{{[^}}]*\}}\s+([\d.]+)\s+([\d.]+)", ln)
        if m:
            period = float(m.group(1))
            break
    if period is None:
        log(f"FAIL clock: {CLOCK} tidak ada di Clock Summary")
        return False
    good = abs(period - PERIOD) < 1e-3
    log(f"{'PASS' if good else 'FAIL'} clock {CLOCK}: periode {period:g} ns (harapan {PERIOD:g} ns, "
        f"{1000 / period:g} MHz)")
    return good


def cdc_rows(text):
    """Baris tabel ringkas report_cdc: (sumber, tujuan, endpoints, safe, unsafe, unknown, no_async)."""
    lines = text.splitlines()
    h = next((k for k, ln in enumerate(lines) if ln.startswith("Severity") and "Unsafe" in ln), None)
    if h is None:
        raise SystemExit("tabel ringkas report_cdc (Severity ... Unsafe) tidak ditemukan; periksa manual")
    rows = []
    for ln in lines[h + 2:]:
        if not ln.strip():
            break
        parts = re.split(r"\s{2,}", ln.strip())
        nums = [int(x) for x in parts[-5:]]         # Endpoints Safe Unsafe Unknown No-ASYNC_REG
        rows.append((parts[1], parts[2], *nums))
    return rows


def check_cdc(text, log=print):
    rows = cdc_rows(text)
    ok = True
    for src, dst, ep, safe, unsafe, unknown, no_async in rows:
        good = unsafe == 0 and unknown == 0 and no_async == 0
        log(f"{'PASS' if good else 'FAIL'} cdc {src} -> {dst}: {ep} endpoint, safe {safe}, unsafe {unsafe}, "
            f"unknown {unknown}, tanpa ASYNC_REG {no_async}")
        ok &= good
    only_tamper = [(r[0], r[1], r[2]) for r in rows] == [("input port clock", CLOCK, 1)]
    log(f"{'PASS' if only_tamper else 'FAIL'} cdc: satu-satunya perlintasan adalah input port -> {CLOCK}, "
        f"1 endpoint (tamper_n)")
    return ok and only_tamper


def check_fsm(logs, log=print):
    """logs: {nama_run: teks runme.log}. guard/decision tidak boleh punya FSM hasil ekstraksi."""
    if not logs:
        log("FAIL fsm: tidak ada padan_kv260.runs/*/runme.log; jalankan grep FSM manual (docs/fpga_howto.md 5a)")
        return False
    ok = True
    for run, text in sorted(logs.items()):
        for m in re.finditer(r"\[Synth 8-3354\] encoded FSM with state register '([^']+)' using encoding "
                             r"'([^']+)' in module '([^']+)'", text):
            reg, enc, mod = m.groups()
            if mod.startswith("sc_"):               # SmartConnect, bukan desain PADAN
                continue
            log(f"INFO fsm {mod}.{reg} dikode ulang ({enc}) [{run}]")
        for m in re.finditer(r"\[Synth 8-802\] inferred FSM for state register '([^']+)' in module '([^']+)'", text):
            reg, mod = m.groups()
            if re.fullmatch(rf"(\S*_)?({'|'.join(NO_FSM)})(_\d+)?", mod):
                log(f"FAIL fsm {mod}.{reg} diekstrak Vivado [{run}]; fsm_encoding = \"none\" tidak dipatuhi")
                ok = False
    if ok:
        log(f"PASS fsm: {' dan '.join(NO_FSM)} tidak dikode ulang ({len(logs)} log sintesis)")
    return ok


def read_logs(reports_dir):
    runs = pathlib.Path(reports_dir).resolve().parent / "padan_kv260.runs"
    return {p.parent.name: p.read_text(errors="replace") for p in sorted(runs.glob("*/runme.log"))}


def check_all(d, log=print):
    d = pathlib.Path(d)
    ok = check_util((d / "utilization_hier.rpt").read_text(), log)
    timing = (d / "timing_summary.rpt").read_text()
    ok &= check_timing(timing, log)
    ok &= check_clock(timing, log)
    ok &= check_cdc((d / "cdc.rpt").read_text(), log)
    ok &= check_fsm(read_logs(d), log)
    return ok


def check_dir(d):
    ok = check_all(d)
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
| padan_bd_i             |           padan_bd |       5000 |       4900 |      60 |   40 | 4000 |      0 |     16 |    0 |         19 |
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

GUARD_FSM = "INFO: [Synth 8-802] inferred FSM for state register 'state_reg' in module 'guard'\n"


def self_test():
    """Kasus positif harus PASS dan kasus negatif harus FAIL. Keluaran per baris
    disembunyikan supaya FAIL yang disengaja tidak terbaca sebagai kegagalan."""
    met = "All user specified timing constraints are met."
    quiet = lambda *a, **k: None   # noqa: E731

    # Laporan asli Vivado 2026.1 (fpga/kv260/testdata): harus lolos apa adanya.
    rep = TESTDATA / "reports"
    if not check_all(rep, log=quiet):
        print("FAIL check_reports.py --self-test: laporan asli Vivado 2026.1 di testdata tidak lolos")
        check_all(rep)
        return 1
    real_util = (rep / "utilization_hier.rpt").read_text()
    real_timing = (rep / "timing_summary.rpt").read_text()
    real_cdc = (rep / "cdc.rpt").read_text()
    real_logs = read_logs(rep)
    mac = "padan_bd_padan_0_0_mac_array |        520 |        509 |       0 |   11 | 1237 |      0 |      0 |    0 |         18 |"
    clk = "clk_pl_0  {0.000 5.000}      10.000          100.000"
    cdc = "False Path          1     1       0        0             0"
    for s, t in ((mac, real_util), (clk, real_timing), (cdc, real_cdc)):
        if t.count(s) != 1:
            print(f"FAIL check_reports.py --self-test: baris acuan tidak ditemukan di testdata: {s!r}")
            return 1

    cases = [
        ("utilisasi sintetis", check_util, UTIL % ("0", "16"), True),
        ("RAMB18 dikemas 2 per RAMB36", check_util, UTIL % ("8", "0"), True),
        ("RAMB18 hanya 8", check_util, UTIL % ("0", "8"), False),
        ("FF decision 149 (register digabung)", check_util,
         (UTIL % ("0", "16")).replace("|  151 |", "|  149 |"), False),
        ("asli: DSP mac_array 15 (pengali di fabric)", check_util, real_util.replace(mac, mac.replace("18 |", "15 |")), False),
        ("asli: DSP mac_array 19", check_util, real_util.replace(mac, mac.replace("18 |", "19 |")), False),
        ("timing sintetis terpenuhi", check_timing, TIMING % ("1.234", met), True),
        ("WNS negatif", check_timing, TIMING % ("-0.100", "Timing constraints are not met."), False),
        ("constraint tidak terpenuhi", check_timing, TIMING % ("0.500", "Timing constraints are not met."), False),
        ("asli: clk_pl_0 8 ns", check_clock, real_timing.replace(clk, "clk_pl_0  {0.000 4.000}      8.000           125.000"), False),
        ("asli: clk_pl_0 hilang", check_clock, real_timing.replace(clk, ""), False),
        ("asli: CDC unsafe", check_cdc, real_cdc.replace(cdc, "False Path          1     0       1        0             0"), False),
        ("asli: CDC tanpa ASYNC_REG", check_cdc, real_cdc.replace(cdc, "False Path          1     1       0        0             1"), False),
        ("asli: CDC kedua", check_cdc, real_cdc.replace(
            "0             0  \n", "0             0  \n"
            "Warning   clk_pl_1          clk_pl_0           No Common Primary Clock              4     0       4        0             0  \n"), False),
        ("asli: FSM guard diekstrak", check_fsm, {**real_logs, "padan_bd_padan_0_0_synth_1":
                                                  real_logs["padan_bd_padan_0_0_synth_1"] + GUARD_FSM}, False),
        ("log sintesis tidak ada", check_fsm, {}, False),
    ]
    for name, fn, arg, want in cases:
        got = fn(arg, log=quiet)
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
    print(f"PASS check_reports.py --self-test (laporan asli Vivado 2026.1 lolos; {len(cases) - neg} kasus harus "
          f"lolos, {neg} kasus harus ditolak, 1 tabel hilang)")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(check_dir(sys.argv[1]))
