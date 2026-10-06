"""Uji mutasi RTL PADAN: setiap mutan harus dibunuh oleh test cocotb.

    python3 tb/padan/mutate.py [nama ...]     (dari root: make test-rtl-mutation)

Mutan suite `padan` dijalankan dengan tb/padan (template_mem + mac_array +
abft_check), mutan suite `avmm` dengan tb/avmm (padan_avmm + decision).

Untuk setiap mutan: salin rtl/ ke <suite>/sim_build/mut_<nama>/rtl, ganti tepat
satu potongan teks, jalankan test dengan PADAN_QUICK=1, lalu periksa:
- semua testcase suite berjalan (mutan terkompilasi, jadi gagal bukan karena error build);
- minimal satu testcase gagal, dan setiap kegagalan adalah AssertionError;
- testcase yang gagal sama dengan yang diharapkan (EXPECT).
"""

import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SUITES = {"padan": (HERE, 7), "avmm": (ROOT / "tb" / "avmm", 7)}

FAULT_TESTS = {"test_fault_lanes", "test_fault_accumulator", "test_fault_memory"}
ALL_TESTS = FAULT_TESTS | {"test_release_params", "test_random_pairs", "test_extremes",
                           "test_no_false_alarm"}

# nama: (file, teks asli, teks mutan, keterangan, testcase yang harus gagal)
# no_c / no_cw: run tanpa fault tetap benar (d1 atau d2 yang dipaksa 0 tidak
# memicu alarm), jadi hanya test fault yang gagal. Galat skor masih terdeteksi
# lewat d yang lain, tetapi lokalisasi rasio hilang, dan fault di jalur C.p
# (atau Cw.p) tidak terdeteksi sama sekali.
MUTANTS = {
    "no_c": (
        "abft_check.v",
        "d1    <= s1 - {{(CW-32){cp[31]}}, cp};",
        "d1    <= {CW{1'b0}};",
        "matikan C: pemeriksaan d1 = sum s - C.p selalu 0",
        FAULT_TESTS,
    ),
    "no_cw": (
        "abft_check.v",
        "d2    <= s2 - {{(CW-32){cwp[31]}}, cwp};",
        "d2    <= {CW{1'b0}};",
        "matikan C_w: pemeriksaan d2 = sum (j+1)s - Cw.p selalu 0",
        FAULT_TESTS,
    ),
    "weight_j": (
        "padan_defs.vh",
        "padan_weight = {1'b0, row} + 9'd1;",
        "padan_weight = {1'b0, row};",
        "salah bobot: w(j) = j, bukan j+1 (generator dan pemeriksa sama-sama salah)",
        # RTL tetap konsisten (tanpa alarm), tetapi setiap run membandingkan baris
        # Cw.p dengan model/padan.py (bobot j+1), jadi semua test gagal.
        ALL_TESTS,
    ),
}

# Mutan suite avmm: penahanan keputusan (decision.v) dimatikan satu per satu.
AVMM_DATAPATH = {"test_fault_datapath", "test_fault_memory"}
AVMM_MUTANTS = {
    "no_agree": (
        "decision.v",
        "if (abft_err || p_err || !agree) begin",
        "if (abft_err || p_err) begin",
        "keputusan tidak ditahan saat komparator A dan B tidak sepakat",
        {"test_fault_decision"},
    ),
    "no_parity": (
        "decision.v",
        "if (abft_err || p_err || !agree) begin",
        "if (abft_err || !agree) begin",
        "keputusan tidak ditahan saat paritas probe salah",
        {"test_fault_probe", "test_fault_decision"},
    ),
    "no_abft": (
        "decision.v",
        "if (abft_err || p_err || !agree) begin",
        "if (p_err || !agree) begin",
        "keputusan tidak ditahan saat ABFT gagal",
        AVMM_DATAPATH | {"test_fault_decision", "test_fixed_latency"},
    ),
}
MUTANTS.update(AVMM_MUTANTS)


def run(name):
    fname, old, new, desc, expect = MUTANTS[name]
    suite = "avmm" if name in AVMM_MUTANTS else "padan"
    tbdir, ntests = SUITES[suite]
    work = tbdir / "sim_build" / f"mut_{name}"
    shutil.rmtree(work, ignore_errors=True)
    rtl = work / "rtl"
    shutil.copytree(ROOT / "rtl", rtl)
    src = (rtl / fname).read_text()
    assert src.count(old) == 1, f"{name}: teks asli harus muncul tepat sekali di {fname}"
    (rtl / fname).write_text(src.replace(old, new))
    results = work / "results.xml"
    log = work / "make.log"
    with open(log, "w") as f:
        subprocess.run(["make", "-C", str(tbdir), f"RTL={rtl}", f"SIM_BUILD={work}/sim",
                        f"COCOTB_RESULTS_FILE={results}", "PADAN_QUICK=1"],
                       stdout=f, stderr=subprocess.STDOUT, check=False)
    assert results.exists(), f"{name}: results.xml tidak ada, lihat {log}"
    cases = ET.parse(results).getroot().iter("testcase")
    status = {c.get("name"): c.find("failure") is None and c.find("error") is None for c in cases}
    failed = {t for t, ok in status.items() if not ok}
    text = log.read_text()
    errors = set(re.findall(r"^\s+(\w+(?:Error|Exception)):", text, re.M))
    print(f"mutan {name} ({suite}): {desc}")
    print(f"  testcase: {len(status)}, gagal: {', '.join(sorted(failed)) or '-'}")
    print(f"  jenis kegagalan: {', '.join(sorted(errors)) or '-'}")
    for t in sorted(failed):
        m = re.search(rf"{t} failed.*?AssertionError: ([^\n]*)", text, re.S)
        print(f"    {t}: {m.group(1).strip() if m else '?'}")
    ok = (len(status) == ntests and failed and errors == {"AssertionError"} and failed == set(expect))
    print(f"  {'KILLED' if ok else 'GAGAL MEMBUNUH / TIDAK SESUAI HARAPAN'}"
          f" (harapan gagal: {', '.join(sorted(expect))})")
    return ok


def main(names):
    names = names or list(MUTANTS)
    bad = [n for n in names if not run(n)]
    if bad:
        print(f"FAIL uji mutasi: {', '.join(bad)}")
        return 1
    print(f"PASS uji mutasi: {len(names)}/{len(names)} mutan dibunuh")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
