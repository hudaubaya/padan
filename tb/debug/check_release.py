"""Build rilis tidak memiliki port, register, atau logika injeksi fault DEBUG_FAULT.

    python3 tb/debug/check_release.py          (dari root: make check-rtl-release)

Pemeriksaan, untuk build rilis (tanpa define) dan build debug (-DDEBUG_FAULT)
sebagai kontrol positif (setiap pemeriksaan HARUS gagal pada build debug, jadi
pemeriksaan ini tidak kosong):

1. Praproses: keluaran `iverilog -E` setiap berkas rtl/*.v tidak memuat "dbg".
2. Netlist Yosys setelah `hierarchy; proc` (sebelum optimasi apa pun, jadi tidak
   ada yang hilang karena dioptimasi): tidak ada port atau net bernama dbg_* di
   modul mana pun; port padan_avmm dan mac_array sama persis dengan daftar rilis.
3. Tidak ada berkas di rtl/ atau fpga/ yang mendefinisikan DEBUG_FAULT (`define,
   VERILOG_MACRO, atau set_global_assignment), jadi alur Platform Designer/Quartus
   di repo ini selalu membangun versi rilis.

Perilaku bus build rilis (0x307/0x308 dibaca 0, STATUS[31] = 0) diuji di
tb/avmm test_address_scan.
"""

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl"
FILES = ["padan_avmm.v", "guard.v", "decision.v", "template_mem.v", "mac_array.v", "abft_check.v"]

RELEASE_PORTS = {
    "padan_avmm": {"clk", "rst_n", "tamper_n", "avs_address", "avs_read", "avs_write",
                   "avs_writedata", "avs_readdata", "avs_readdatavalid", "avs_waitrequest"},
    "mac_array": {"clk", "rst_n", "p_wr", "p_addr", "p_wdata", "start", "hold", "mem_lock",
                  "busy", "o_start", "rd_addr", "rd_data", "o_vld", "o_row", "o_data", "p_err"},
}
DBG = re.compile(r"dbg", re.I)


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def preprocess_hits(defines):
    """Baris kode (tanpa komentar) hasil praproses yang memuat "dbg"."""
    hits = []
    for f in FILES:
        out = subprocess.run(["iverilog", "-E", "-o", "/dev/stdout", f"-I{RTL}", *defines, str(RTL / f)],
                             capture_output=True, text=True, check=True).stdout
        hits += [f"{f}: {ln.strip()}" for ln in strip_comments(out).splitlines() if DBG.search(ln)]
    return hits


def netlist(defines):
    d = " ".join(defines)
    out = subprocess.run(
        ["yosys", "-q", "-p", f"read_verilog {d} -I{RTL} {' '.join(str(RTL / f) for f in FILES)}; "
         "hierarchy -check -top padan_avmm; proc; write_json -"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out[out.index("{"):])["modules"]


def module_of(name):
    """Nama modul tanpa awalan $paramod$<hash>\\ dari hierarchy Yosys."""
    return name.rsplit("\\", 1)[-1]


def netlist_problems(mods):
    bad = []
    for name, m in mods.items():
        bad += [f"{name}: port {p}" for p in m["ports"] if DBG.search(p)]
        bad += [f"{name}: net {n}" for n in m["netnames"] if DBG.search(n)]
        want = RELEASE_PORTS.get(module_of(name))
        if want is not None and set(m["ports"]) != want:
            bad.append(f"{name}: port {sorted(set(m['ports']) ^ want)} berbeda dari daftar rilis")
    return bad


def macro_definitions():
    pat = re.compile(r"`define\s+DEBUG_FAULT|VERILOG_MACRO.*DEBUG_FAULT|DEBUG_FAULT\s*=", re.I)
    hits = []
    for d in (RTL, ROOT / "fpga"):
        for f in d.rglob("*"):
            if f.is_file() and "baseline" not in f.parts:
                for i, ln in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    if ln.lstrip().startswith(("//", "#")):
                        continue                    # komentar
                    if pat.search(ln):
                        hits.append(f"{f.relative_to(ROOT)}:{i}: {ln.strip()}")
    return hits


def main():
    ok = True
    rel_pp, dbg_pp = preprocess_hits([]), preprocess_hits(["-DDEBUG_FAULT"])
    rel_nl, dbg_nl = netlist_problems(netlist([])), netlist_problems(netlist(["-DDEBUG_FAULT"]))
    checked = {module_of(m) for m in netlist([])} & set(RELEASE_PORTS)
    if checked != set(RELEASE_PORTS):
        print(f"FAIL check_release: modul padan_avmm/mac_array tidak ditemukan di netlist: {checked}")
        return 1
    for what, rel, dbg in (("praproses", rel_pp, dbg_pp), ("netlist Yosys", rel_nl, dbg_nl)):
        if rel:
            ok = False
            print(f"FAIL {what} build rilis memuat jejak debug: {rel[:6]}")
        if not dbg:
            ok = False
            print(f"FAIL {what}: kontrol positif build debug tidak menemukan apa pun (pemeriksaan kosong)")
        if not rel and dbg:
            print(f"PASS {what}: rilis bersih; build debug memuat {len(dbg)} temuan "
                  f"(mis. {dbg[0]})")
    macros = macro_definitions()
    if macros:
        ok = False
        print(f"FAIL DEBUG_FAULT didefinisikan di repo: {macros}")
    else:
        print("PASS tidak ada definisi DEBUG_FAULT di rtl/ atau fpga/")
    print("PADAN RELEASE: PASS" if ok else "PADAN RELEASE: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
