# Buat proyek Vivado PADAN untuk Kria KV260 (Zynq UltraScale+ K26).
#
#   vivado -mode batch -source fpga/kv260/create_project.tcl [-tclargs <dir_proyek>]
#
# Block design: zynq_ultra_ps_e (preset board) -> M_AXI_HPM0_FPD -> AXI
# SmartConnect -> padan_axil (module reference, rtl/padan_axil.v). Clock pl_clk0
# 100 MHz, reset dari proc_sys_reset (otomasi Vivado). tamper_n adalah port
# luar ke PMOD (padan_kv260.xdc). Alamat padan_0: 0xA000_0000, 4 KiB; sama
# dengan default sw/kv260/padan_test.py.
#
# Belum pernah dijalankan di Vivado asli. CI hanya menjalankannya di tclsh
# dengan stub (tb/kv260/check_tcl.py). Lihat docs/fpga_howto.md.

set HERE [file dirname [file normalize [info script]]]
set ROOT [file normalize [file join $HERE .. ..]]
set PROJ_DIR [expr {[llength $argv] > 0 ? [lindex $argv 0] : [file join $ROOT build kv260]}]

set PART      xck26-sfvc784-2LV-c
set BASE      0xA0000000
set RANGE     4K
set FCLK_MHZ  100
set RTL_FILES {padan_axil.v padan_avmm.v guard.v decision.v template_mem.v mac_array.v abft_check.v}

create_project padan_kv260 $PROJ_DIR -part $PART -force

# Board part SOM K26 (board file Kria dari Vivado XHub). Preset board mengatur
# DDR, MIO, dan clock PS; tanpa itu PS tidak boot dengan konfigurasi yang benar.
set bp [lindex [lsort [get_board_parts -quiet *kv260_som*]] end]
if {$bp eq ""} {
    error "board part KV260 SOM tidak ditemukan: pasang board file Kria (Vivado > Tools > XHub Stores)"
}
set_property board_part $bp [current_project]

# RTL
set srcs {}
foreach f $RTL_FILES { lappend srcs [file join $ROOT rtl $f] }
add_files -norecurse $srcs
add_files -norecurse [file join $ROOT rtl padan_defs.vh]
set_property file_type {Verilog Header} [get_files padan_defs.vh]
set_property include_dirs [list [file join $ROOT rtl]] [current_fileset]
add_files -fileset constrs_1 -norecurse [file join $HERE padan_kv260.xdc]

# Block design
create_bd_design padan_bd
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e zynq_ultra_ps_e_0]
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} $ps
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {1} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {0} \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH {32} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $FCLK_MHZ \
] $ps

set padan [create_bd_cell -type module -reference padan_axil padan_0]

apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list \
    Clk_master {Auto} \
    Clk_slave  {Auto} \
    Clk_xbar   {Auto} \
    Master     {/zynq_ultra_ps_e_0/M_AXI_HPM0_FPD} \
    Slave      {/padan_0/s_axi} \
    intc_ip    {New AXI SmartConnect} \
    master_apm {0} \
] [get_bd_intf_pins padan_0/s_axi]

# pl_clk0 satu-satunya clock PL, jadi otomasi harus memakainya; periksa.
set clk_net [get_bd_nets -of_objects [get_bd_pins padan_0/s_axi_aclk]]
if {[lsearch [get_bd_pins -of_objects $clk_net] */pl_clk0] < 0} {
    error "padan_0/s_axi_aclk tidak tersambung ke pl_clk0: $clk_net"
}

create_bd_port -dir I tamper_n
connect_bd_net [get_bd_ports tamper_n] [get_bd_pins padan_0/tamper_n]

# Alamat tetap: jangan biarkan otomasi memilih.
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces zynq_ultra_ps_e_0/Data] -filter {NAME =~ *padan_0*}]
if {[llength $seg] != 1} { error "segmen alamat padan_0 tidak tunggal: $seg" }
set_property offset $BASE  $seg
set_property range  $RANGE $seg

validate_bd_design
save_bd_design

set bd [get_files padan_bd.bd]
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
set_property top padan_bd_wrapper [current_fileset]

# Bitstream juga dalam format .bin untuk fpgautil/xmutil di Linux KV260.
set_property STEPS.WRITE_BITSTREAM.ARGS.BIN_FILE true [get_runs impl_1]

puts "PADAN KV260: proyek dibuat di $PROJ_DIR (part $PART, board $bp, padan_0 @ $BASE/$RANGE)"
