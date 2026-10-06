"""Pemeriksaan pemakaian DSP dan M10K dari laporan fitter Quartus (docs/fpga_howto.md langkah 5).

    python3 fpga/de10_nano/scripts/check_reports.py <dir output_files> <revisi>

Membaca tabel "Fitter Resource Utilization by Entity" di <revisi>.fit.rpt, lalu
memeriksa baris instance padan_avmm (subtree) dan anaknya:

    padan_avmm   M10Ks == 16     satu M10K per bank lane template_mem
    template_mem M10Ks == 16
    mac_array    DSP Blocks >= 8 16 pengali 16x8 bertanda, dua per blok DSP
                                 dalam mode 18x18; 0 berarti inferensi gagal

Angka total perangkat dari <revisi>.fit.summary ikut dicetak sebagai informasi.

Format laporan diasumsikan dari Quartus Prime Standard/Lite 18-20 dan BELUM
pernah diuji terhadap laporan asli (Quartus tidak tersedia di lingkungan
pembuatnya). --self-test hanya memeriksa logika parser terhadap contoh sintetis.
Jika tabel tidak ditemukan, skrip berhenti dengan pesan, dan pemeriksaan harus
dilakukan manual di GUI.
"""

import pathlib
import re
import sys

EXPECT = [
    ("padan_avmm", "M10Ks", "==", 16),
    ("template_mem", "M10Ks", "==", 16),
    ("mac_array", "DSP Blocks", ">=", 8),
]


def entity_table(text):
    """(header, rows) dari tabel 'Fitter Resource Utilization by Entity'."""
    i = text.find("; Fitter Resource Utilization by Entity")
    if i < 0:
        raise SystemExit("tabel 'Fitter Resource Utilization by Entity' tidak ditemukan; periksa manual")
    lines = text[i:].splitlines()[1:]
    end = next((k for k, ln in enumerate(lines) if not ln.strip()), len(lines))
    rows = [ln for ln in lines[:end] if ln.startswith(";")]
    split = [[c.strip() for c in ln.strip().strip(";").split(";")] for ln in rows]
    return split[0], split[1:]


def instance_row(header, rows, module):
    """Baris pertama yang node-nya memuat '|<module>:' (subtree instance)."""
    for r in rows:
        if re.search(rf"\|{re.escape(module)}:", r[0]):
            return dict(zip(header, r))
    raise SystemExit(f"instance {module} tidak ditemukan di tabel entity; periksa manual")


def number(cell):
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)", cell)
    if not m:
        raise SystemExit(f"nilai tidak numerik: {cell!r}")
    return float(m.group(1))


def check(rpt_text, summary_text="", quiet=False):
    header, rows = entity_table(rpt_text)
    ok = True
    for module, col, op, want in EXPECT:
        if col not in header:
            raise SystemExit(f"kolom '{col}' tidak ada di tabel entity (kolom: {header}); periksa manual")
        got = number(instance_row(header, rows, module)[col])
        good = got == want if op == "==" else got >= want
        ok &= good
        if not quiet:
            print(f"{'PASS' if good else 'FAIL'} {module:13s} {col:10s} = {got:g} (harus {op} {want})")
    for key in ("Total DSP Blocks", "Total RAM Blocks", "Logic utilization"):
        m = re.search(rf"^{key}.*$", summary_text, re.M)
        if m:
            print(f"info  {m.group(0).strip()}")
    return ok


SAMPLE = """\
+--------------------------------------------------------------------------+
; Fitter Resource Utilization by Entity                                    ;
+-------------------------------------+--------------+-------+------------+
; Compilation Hierarchy Node          ; ALMs needed  ; M10Ks ; DSP Blocks ;
+-------------------------------------+--------------+-------+------------+
; |top                                ; 5000.0 (0.0) ; 40    ; 12         ;
;    |soc_system:u0|                  ; 4900.0 (0.0) ; 40    ; 12         ;
;       |padan_avmm:padan_0|          ; 2500.0 (9.0) ; 16    ; 10 (0)     ;
;          |mac_array:u_mac|          ; 1200.0 (1.0) ; 0     ; 8 (8)      ;
;          |template_mem:u_mem|       ; 300.0 (2.0)  ; 16    ; 1 (1)      ;
+-------------------------------------+--------------+-------+------------+

"""


def self_test():
    assert check(SAMPLE, quiet=True)
    bad = SAMPLE.replace("; 16    ; 10 (0)", "; 15    ; 10 (0)")
    assert not check(bad, quiet=True)
    print("check_reports: self-test parser OK (contoh sintetis, bukan laporan Quartus asli)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    out, rev = pathlib.Path(sys.argv[1]), sys.argv[2]
    rpt = (out / f"{rev}.fit.rpt").read_text(errors="replace")
    summ = out / f"{rev}.fit.summary"
    ok = check(rpt, summ.read_text(errors="replace") if summ.exists() else "")
    print("PADAN RESOURCES: PASS" if ok else "PADAN RESOURCES: FAIL")
    sys.exit(0 if ok else 1)
