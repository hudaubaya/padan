"""Periksa skrip Vivado KV260 tanpa Vivado (make test-kv260-scripts).

Setiap skrip dijalankan di tclsh; semua perintah Vivado ditangkap oleh `unknown`
yang mencatat panggilan dan mengembalikan nilai tiruan. Yang dibuktikan: skrip
bebas error Tcl, nilai kunci (part, alamat, clock, port, file RTL) konsisten
dengan RTL dan host, dan pemeriksaan error di skrip benar-benar memicu. Yang
TIDAK dibuktikan: bahwa Vivado menerima setiap perintah, properti, dan VLNV.

1. create_project.tcl: part K26, board part, RTL lengkap (Yosys hierarchy -check),
   M_AXI_HPM0_FPD + pl_clk0, slave padan_0/s_axi, base/range == padan_test.py,
   tamper_n eksternal; error jelas bila board part hilang, segmen alamat tidak
   tunggal, atau clock padan bukan pl_clk0.
2. build.tcl: run synth/impl, laporan yang dibaca check_reports.py; error bila
   run gagal.
3. padan_kv260.xdc: tamper_n = H12/LVCMOS33/PULLUP + false path; tamper_n dan
   port AXI4-Lite ada di rtl/padan_axil.v.
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
KV = ROOT / "fpga" / "kv260"
sys.path.insert(0, str(ROOT / "sw" / "kv260"))
import padan_test as PT   # noqa: E402

STUB = r"""
set ::LOG {}
set ::BOARD {xilinx.com:kv260_som:part0:1.3 xilinx.com:kv260_som:part0:1.4}
set ::SEGS {/zynq_ultra_ps_e_0/Data/SEG_padan_0_reg0}
set ::CLKPINS {/zynq_ultra_ps_e_0/pl_clk0 /padan_0/s_axi_aclk /axi_smc/aclk}
set ::PROGRESS 100%
proc unknown {args} {
    lappend ::LOG $args
    switch -- [lindex $args 0] {
        get_board_parts { return $::BOARD }
        get_bd_addr_segs { return $::SEGS }
        get_bd_pins { if {[lsearch $args -of_objects] >= 0} { return $::CLKPINS }; return [lindex $args end] }
        get_bd_nets { return /pl_clk0_net }
        get_bd_ports { return [lindex $args end] }
        get_files { return /proj/[lindex $args end] }
        make_wrapper { return /proj/padan_bd_wrapper.v }
        get_property { if {[lindex $args 1] eq "PROGRESS"} { return $::PROGRESS } }
        create_bd_cell { return /[lindex $args end] }
    }
    return stub
}
"""


def tcl(script, prelude="", args=()):
    with tempfile.TemporaryDirectory() as d:
        drv = pathlib.Path(d) / "drv.tcl"
        drv.write_text(STUB + prelude + f"\nset argv [list {' '.join(args)}]\n"
                       f"if {{[catch {{source {{{script}}}}} err]}} {{ puts \"@@ERROR $err\" }}\n"
                       "foreach c $::LOG { puts \"@@CMD $c\" }\n")
        r = subprocess.run(["tclsh", str(drv)], capture_output=True, text=True, cwd=d)
    out = r.stdout + r.stderr
    cmds = [ln[6:] for ln in out.splitlines() if ln.startswith("@@CMD ")]
    err = next((ln[8:] for ln in out.splitlines() if ln.startswith("@@ERROR ")), None)
    return err, cmds, out


def fail(msg):
    print(f"FAIL {msg}")
    sys.exit(1)


def find(cmds, pattern):
    return [c for c in cmds if re.search(pattern, c)]


def yosys_ports():
    files = ["padan_axil.v", "padan_avmm.v", "guard.v", "decision.v", "template_mem.v", "mac_array.v",
             "abft_check.v"]
    out = subprocess.run(
        ["yosys", "-q", "-p", f"read_verilog -I{ROOT/'rtl'} {' '.join(str(ROOT/'rtl'/f) for f in files)}; "
         "hierarchy -check -top padan_axil; proc; write_json -"],
        capture_output=True, text=True, check=True).stdout
    return json.loads(out)["modules"]["padan_axil"]["ports"]


# ------------------------------------------------------------ 1. create_project
err, cmds, out = tcl(KV / "create_project.tcl", args=("/tmp/proj",))
if err:
    fail(f"create_project.tcl: {err}\n{out[-2000:]}")
if not find(cmds, r"^create_project padan_kv260 /tmp/proj -part xck26-sfvc784-2LV-c -force$"):
    fail("create_project: part xck26-sfvc784-2LV-c / dir proyek")
if not find(cmds, r"^set_property board_part xilinx.com:kv260_som:part0:1.4 "):
    fail("board part terbaru tidak dipilih")
added = " ".join(c for c in cmds if c.startswith("add_files"))
rtl_added = set(re.findall(r"/rtl/(\w+\.vh?)", added))
need = {"padan_axil.v", "padan_avmm.v", "guard.v", "decision.v", "template_mem.v", "mac_array.v",
        "abft_check.v", "padan_defs.vh"}
if rtl_added != need:
    fail(f"file RTL di proyek {sorted(rtl_added)} != {sorted(need)}")
for f in re.findall(r"(/\S+/rtl/\w+\.vh?)", added):
    if not pathlib.Path(f).exists():
        fail(f"file tidak ada: {f}")
if "padan_kv260.xdc" not in added:
    fail("XDC tidak ditambahkan")
ports = yosys_ports()                     # juga hierarchy -check: file cukup untuk elaborasi
ps = " ".join(find(cmds, r"^set_property -dict"))
for k, v in (("PSU__USE__M_AXI_GP0", "1"), ("PSU__FPGA_PL0_ENABLE", "1"),
             ("PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ", "100"), ("PSU__MAXIGP0__DATA_WIDTH", "32")):
    if not re.search(rf"CONFIG\.{k} \{{?{v}\}}?", ps):
        fail(f"konfigurasi PS {k} != {v}: {ps[:300]}")
if not find(cmds, r"^apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e .*apply_board_preset"):
    fail("preset board PS tidak diterapkan")
if not find(cmds, r"^create_bd_cell -type module -reference padan_axil padan_0$"):
    fail("module reference padan_axil")
axi = find(cmds, r"^apply_bd_automation -rule xilinx.com:bd_rule:axi4 ")
if len(axi) != 1 or "Master /zynq_ultra_ps_e_0/M_AXI_HPM0_FPD" not in axi[0] or "Slave /padan_0/s_axi" not in axi[0]:
    fail(f"otomasi AXI: {axi}")
off = find(cmds, r"^set_property offset ")
rng = find(cmds, r"^set_property range ")
if len(off) != 1 or int(off[0].split()[2], 0) != 0xA0000000:
    fail(f"offset padan_0: {off}")
if len(rng) != 1 or rng[0].split()[2] != "4K" or PT.SPAN != 4096:
    fail(f"range padan_0: {rng} (padan_test.py SPAN = {PT.SPAN})")
host_base = re.search(r'"PADAN_BASE", "(0x[0-9A-Fa-f]+)"', (ROOT / "sw/kv260/padan_test.py").read_text())
if not host_base or int(host_base.group(1), 0) != int(off[0].split()[2], 0):
    fail(f"base host {host_base and host_base.group(1)} != offset block design {off}")
if not find(cmds, r"^create_bd_port -dir I tamper_n$") or \
        not find(cmds, r"^connect_bd_net tamper_n padan_0/tamper_n$"):
    fail("tamper_n tidak dibuat/tersambung sebagai port luar")
if not find(cmds, r"^validate_bd_design$") or not find(cmds, r"^set_property top padan_bd_wrapper "):
    fail("validate/top wrapper")
if not find(cmds, r"BIN_FILE true"):
    fail("bitstream .bin tidak diminta")
print(f"PASS create_project.tcl: {len(cmds)} perintah, part K26, padan_0 @ {off[0].split()[2]}/4K, "
      "RTL lengkap (Yosys hierarchy -check)")

for name, prelude, want in (
        ("board part hilang", "set ::BOARD {}", "board part KV260 SOM tidak ditemukan"),
        ("segmen ganda", "set ::SEGS {a b}", "segmen alamat padan_0 tidak tunggal"),
        ("clock salah", "set ::CLKPINS {/zynq_ultra_ps_e_0/pl_clk1 /padan_0/s_axi_aclk}",
         "tidak tersambung ke pl_clk0")):
    e, _, _ = tcl(KV / "create_project.tcl", prelude)
    if not e or want not in e:
        fail(f"create_project.tcl {name}: error {e!r}, harapan {want!r}")
print("PASS create_project.tcl: 3 kondisi error memberi pesan yang jelas")

# ------------------------------------------------------------------ 2. build
err, cmds, out = tcl(KV / "build.tcl", args=("/tmp/proj", "8"))
if err:
    fail(f"build.tcl: {err}\n{out[-2000:]}")
for pat in (r"^open_project /tmp/proj/padan_kv260.xpr$", r"^launch_runs synth_1 -jobs 8$",
            r"^launch_runs impl_1 -to_step write_bitstream -jobs 8$",
            r"^report_timing_summary .*-file /tmp/proj/reports/timing_summary.rpt$",
            r"^report_utilization -hierarchical -file /tmp/proj/reports/utilization_hier.rpt$",
            r"^write_hw_platform -fixed -include_bit -force /tmp/proj/padan_kv260.xsa$"):
    if not find(cmds, pat):
        fail(f"build.tcl: tidak ada {pat}")
e, _, _ = tcl(KV / "build.tcl", "set ::PROGRESS 50%")
if not e or "synth_1 gagal" not in e:
    fail(f"build.tcl run gagal tidak terdeteksi: {e!r}")
print("PASS build.tcl: run, laporan (nama sama dengan check_reports.py), XSA; run gagal -> error")

# ------------------------------------------------------------------- 3. XDC
err, cmds, out = tcl(KV / "padan_kv260.xdc")
if err:
    fail(f"padan_kv260.xdc: {err}")
want = {"set_property PACKAGE_PIN H12 {get_ports tamper_n}", "set_property IOSTANDARD LVCMOS33 {get_ports tamper_n}",
        "set_property PULLUP true {get_ports tamper_n}", "set_false_path -from {get_ports tamper_n}"}
got = {c.replace("stub", "{get_ports tamper_n}") for c in cmds if not c.startswith("get_ports")}
if got != want:
    fail(f"XDC: {sorted(got)} != {sorted(want)}")
refs = {c.split()[1] for c in cmds if c.startswith("get_ports")}
if not refs <= set(ports) or ports["tamper_n"]["direction"] != "input":
    fail(f"XDC merujuk port {refs}, port padan_axil {sorted(ports)}")
axil = {"s_axi_aclk", "s_axi_aresetn", "s_axi_awaddr", "s_axi_awprot", "s_axi_awvalid", "s_axi_awready",
        "s_axi_wdata", "s_axi_wstrb", "s_axi_wvalid", "s_axi_wready", "s_axi_bresp", "s_axi_bvalid",
        "s_axi_bready", "s_axi_araddr", "s_axi_arprot", "s_axi_arvalid", "s_axi_arready", "s_axi_rdata",
        "s_axi_rresp", "s_axi_rvalid", "s_axi_rready"}
if set(ports) != axil | {"tamper_n"}:
    fail(f"port padan_axil: {sorted(set(ports) ^ (axil | {'tamper_n'}))}")
print("PASS padan_kv260.xdc: tamper_n H12/LVCMOS33/PULLUP + false path; port padan_axil = AXI4-Lite + tamper_n")
print("PASS skrip Vivado KV260 (tclsh + stub; bukan bukti Vivado)")
