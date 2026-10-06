"""Periksa skrip Tcl FPGA tanpa Quartus/Platform Designer (make test-fpga-scripts).

Setiap skrip dijalankan di tclsh dengan perintah alat diganti stub yang mencatat
panggilan. Yang dibuktikan: skrip bebas error Tcl, logikanya benar terhadap
input tiruan, dan komponen cocok dengan RTL. Yang TIDAK dibuktikan: bahwa
Platform Designer/Quartus menerima setiap perintah dan properti (perlu alat asli).

1. padan_avmm_hw.tcl: port (nama, arah, lebar) == rtl/padan_avmm.v (Yosys);
   berkas fileset ada dan cukup untuk elaborasi padan_avmm (Yosys hierarchy -check).
2. add_padan.tcl: terhadap GHRD tiruan, koneksi dan alamat yang diharapkan;
   error yang jelas bila LW bridge tidak aktif atau skrip dijalankan dua kali.
3. check_timing.tcl: PASS/FAIL sesuai slack dan Ignored Constraints tiruan.
4. padan_de10_nano.sdc: bebas error Tcl; clock dan port yang dirujuk dicetak.
"""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HW = ROOT / "fpga" / "ip" / "padan_avmm" / "padan_avmm_hw.tcl"
ADD = ROOT / "fpga" / "de10_nano" / "qsys" / "add_padan.tcl"
STA = ROOT / "fpga" / "de10_nano" / "scripts" / "check_timing.tcl"
SDC = ROOT / "fpga" / "de10_nano" / "padan_de10_nano.sdc"
RTL_FILES = ["padan_avmm.v", "guard.v", "decision.v", "template_mem.v", "mac_array.v", "abft_check.v"]


def tcl(prelude, script, cwd, args=()):
    with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as f:
        f.write(prelude + f"\nset argv [list {' '.join(args)}]\nsource {{{script}}}\n")
        path = f.name
    r = subprocess.run(["tclsh", path], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def fail(msg):
    print(f"FAIL {msg}")
    sys.exit(1)


# ---------------------------------------------------------------- 1. _hw.tcl
HW_STUBS = r"""
rename package _package
proc package {args} { if {[lrange $args 0 0] eq "require"} { return 16.1 }; _package {*}$args }
proc set_module_property {k v} { puts "MOD $k $v" }
proc add_fileset {args} {}
proc set_fileset_property {args} {}
proc add_fileset_file {name type kind path args} { puts "FILE $name $type $kind $path" }
proc add_interface {name kind dir} { puts "IF $name $kind $dir" }
proc set_interface_property {i k v} { puts "IFP $i $k $v" }
proc add_interface_port {i name role dir width} { puts "PORT $i $name $role $dir $width" }
"""


def verilog_ports():
    out = subprocess.run(
        ["yosys", "-q", "-p", f"read_verilog -I{ROOT/'rtl'} {' '.join(str(ROOT/'rtl'/f) for f in RTL_FILES)}; "
         "hierarchy -top padan_avmm; proc; write_json -"], capture_output=True, text=True, check=True).stdout
    mod = json.loads(out[out.index("{"):])["modules"]["padan_avmm"]
    return {n: ("Input" if p["direction"] == "input" else "Output", len(p["bits"]))
            for n, p in mod["ports"].items()}


def check_hw():
    rc, out = tcl(HW_STUBS, HW, HW.parent)
    if rc:
        fail(f"padan_avmm_hw.tcl error Tcl:\n{out}")
    ports = {}
    files = set()
    for ln in out.splitlines():
        f = ln.split()
        if f[0] == "PORT":
            ports[f[2]] = (f[4], int(f[5]))
        elif f[0] == "FILE":
            files.add((f[1], f[2], (HW.parent / f[4]).resolve()))
    vp = verilog_ports()
    if ports != vp:
        fail(f"port _hw.tcl {ports} != rtl/padan_avmm.v {vp}")
    paths = {p for _, _, p in files}
    missing = [p for p in paths if not p.exists()]
    if missing:
        fail(f"berkas fileset tidak ada: {missing}")
    vfiles = sorted(str(p) for n, t, p in files if t == "VERILOG")
    r = subprocess.run(["yosys", "-q", "-p", f"read_verilog -I{ROOT/'rtl'} {' '.join(vfiles)}; "
                        "hierarchy -check -top padan_avmm"], capture_output=True, text=True)
    if r.returncode:
        fail(f"fileset tidak cukup untuk elaborasi padan_avmm:\n{r.stderr}")
    print(f"PASS padan_avmm_hw.tcl: {len(ports)} port sama dengan RTL; "
          f"{len(paths)} berkas fileset ada dan cukup (Yosys hierarchy -check)")


# ---------------------------------------------------------- 2. add_padan.tcl
def ghrd_stubs(lw=True, existing=()):
    hps_ifs = "h2f_axi_master h2f_reset clk_reset" + (" h2f_lw_axi_master" if lw else "")
    insts = " ".join(["hps_0 clk_0 sysid_qsys fpga_only_master", *existing])
    return rf"""
rename package _package
proc package {{args}} {{ if {{[lrange $args 0 0] eq "require"}} {{ return 16.1 }}; _package {{*}}$args }}
array set CLS {{hps_0 altera_hps clk_0 clock_source sysid_qsys altera_avalon_sysid_qsys
               fpga_only_master altera_jtag_avalon_master padan_0 padan_avmm padan_jtag altera_jtag_avalon_master}}
set INSTS {{{insts}}}
proc get_instances {{}} {{ return $::INSTS }}
proc get_instance_property {{i k}} {{ return $::CLS($i) }}
proc get_instance_interfaces {{i}} {{ return {{{hps_ifs}}} }}
proc set_validation_property {{args}} {{}}
proc add_instance {{name cls args}} {{ lappend ::INSTS $name; puts "ADD $name $cls" }}
proc add_connection {{a b}} {{ puts "CONN $a $b" }}
proc set_connection_parameter_value {{c k v}} {{ puts "PARAM $c $k $v" }}
proc validate_system {{}} {{ puts "VALIDATE" }}
proc save_system {{args}} {{ puts "SAVE" }}
proc add_interface {{name kind dir}} {{ puts "EXPIF $name $kind $dir" }}
proc set_interface_property {{i k v}} {{ puts "EXPORT $i $k $v" }}
"""


def check_add():
    rc, out = tcl(ghrd_stubs(), ADD, ADD.parent)
    if rc:
        fail(f"add_padan.tcl error pada GHRD tiruan:\n{out}")
    got = {ln for ln in out.splitlines() if ln.split()[0] in ("ADD", "CONN", "PARAM", "SAVE", "EXPIF", "EXPORT")}
    want = {
        "ADD padan_0 padan_avmm", "ADD padan_jtag altera_jtag_avalon_master",
        "CONN clk_0.clk padan_0.clock", "CONN clk_0.clk padan_jtag.clk",
        "CONN clk_0.clk_reset padan_0.reset", "CONN clk_0.clk_reset padan_jtag.clk_reset",
        "CONN hps_0.h2f_lw_axi_master padan_0.s0", "CONN padan_jtag.master padan_0.s0",
        "PARAM hps_0.h2f_lw_axi_master/padan_0.s0 baseAddress 0x00040000",
        "PARAM padan_jtag.master/padan_0.s0 baseAddress 0x00040000",
        "EXPIF padan_tamper conduit end", "EXPORT padan_tamper EXPORT_OF padan_0.tamper",
        "SAVE",
    }
    if got != want:
        fail(f"add_padan.tcl: kurang {sorted(want - got)}, lebih {sorted(got - want)}")
    if "0xFF240000" not in out:
        fail("add_padan.tcl tidak mencetak alamat HPS 0xFF240000")
    rc, out = tcl(ghrd_stubs(lw=False), ADD, ADD.parent)
    if rc == 0 or "h2f_lw_axi_master" not in out:
        fail("add_padan.tcl harus gagal jelas bila LW bridge tidak aktif")
    rc, out = tcl(ghrd_stubs(existing=["padan_0"]), ADD, ADD.parent)
    if rc == 0 or "sudah ada" not in out:
        fail("add_padan.tcl harus menolak sistem yang sudah dimodifikasi")
    print("PASS add_padan.tcl: GHRD tiruan -> 2 instance, 6 koneksi (tanpa h2f_reset), ekspor tamper, "
          "alamat 0x00040000 "
          "(HPS 0xFF240000); gagal jelas tanpa LW bridge dan saat dijalankan dua kali")


# ------------------------------------------------------- 3. check_timing.tcl
def sta_stubs(slacks, ignored):
    return rf"""
proc project_open {{args}} {{}}
proc project_close {{}} {{}}
proc create_timing_netlist {{}} {{}}
proc delete_timing_netlist {{}} {{}}
proc read_sdc {{}} {{}}
proc update_timing_netlist {{}} {{}}
proc get_available_operating_conditions {{}} {{ return {{slow_85c fast_0c}} }}
proc set_operating_conditions {{oc}} {{ set ::OC $oc }}
array set SLACK {{{slacks}}}
proc report_timing {{args}} {{
    set kind [string range [lindex $args 0] 1 end]
    set k "$::OC,$kind"
    if {{[info exists ::SLACK($k)]}} {{ return [list 1 $::SLACK($k)] }}
    return [list 1 1.000]
}}
proc report_sdc {{args}} {{
    set f [open padan_ignored_constraints.txt w]; puts -nonewline $f {{{ignored}}}; close $f
}}
rename exit _exit
proc exit {{code}} {{ puts "EXIT $code"; _exit $code }}
"""


def check_sta():
    with tempfile.TemporaryDirectory() as d:
        cases = [
            ("bersih", "", "", 0, "PADAN TIMING: PASS"),
            ("hold negatif", "fast_0c,hold -0.120", "", 1, "PADAN TIMING: FAIL (1"),
            ("ignored", "", "set_false_path -from [get_ports {SW[*]}]", 1, "PADAN TIMING: FAIL (1"),
        ]
        for name, slacks, ignored, want_rc, want in cases:
            rc, out = tcl(sta_stubs(slacks, ignored), STA, d, args=["proj"])
            if rc != want_rc or want not in out:
                fail(f"check_timing.tcl kasus {name}: rc={rc}, keluaran:\n{out}")
        if out.count("slack=") != 8:
            fail("check_timing.tcl harus memeriksa 4 jenis x 2 kondisi operasi")
    print("PASS check_timing.tcl: logika PASS/FAIL benar untuk slack negatif dan Ignored Constraints "
          "(stub; perintah quartus_sta asli belum dijalankan)")


# ------------------------------------------------------------------- 4. SDC
SDC_STUBS = r"""
set ::CLOCKS {}
set ::PORTS {}
proc get_ports {p} { foreach x $p { lappend ::PORTS $x }; return [list port $p] }
proc get_clocks {c} { return [list clock $c] }
proc create_clock {args} { lappend ::CLOCKS [lindex $args [expr {[lsearch $args -name] + 1}]] }
proc set_input_delay {args} {}
proc set_output_delay {args} {}
proc set_clock_groups {args} {}
proc derive_pll_clocks {} {}
proc derive_clock_uncertainty {} {}
proc set_false_path {args} {}
"""


def check_sdc():
    r = subprocess.run(["tclsh"], input=SDC_STUBS + f"\nsource {{{SDC}}}\nputs \"CLOCKS $::CLOCKS\"\n"
                       "puts \"PORTS [lsort -unique $::PORTS]\"\n", capture_output=True, text=True)
    if r.returncode:
        fail(f"SDC error Tcl:\n{r.stderr}")
    print("PASS padan_de10_nano.sdc bebas error Tcl; " + "; ".join(r.stdout.strip().splitlines()))


if __name__ == "__main__":
    check_hw()
    check_add()
    check_sta()
    check_sdc()
