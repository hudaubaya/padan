# Tambahkan padan_avmm ke sistem Platform Designer GHRD DE10-Nano (soc_system.qsys).
#
#   qsys-script --system-file=soc_system.qsys \
#       --search-path="<repo>/fpga/ip/**/*,$" \
#       --script=<repo>/fpga/de10_nano/qsys/add_padan.tcl
#
# Opsional: --cmd="set PADAN_BASE 0x00040000" (offset dari jendela lightweight
# bridge dan dari JTAG master; default 0x00040000).
#
# Yang ditambahkan:
#   padan_0     padan_avmm (fpga/ip/padan_avmm/padan_avmm_hw.tcl)
#   padan_jtag  altera_jtag_avalon_master, khusus untuk System Console
# Koneksi:
#   <clock_source>.clk           -> padan_0.clock, padan_jtag.clk
#   <clock_source>.clk_reset     -> padan_0.reset, padan_jtag.clk_reset
#   <hps>.h2f_lw_axi_master      -> padan_0.s0 @ PADAN_BASE (HPS: 0xFF200000 + PADAN_BASE)
#   padan_jtag.master            -> padan_0.s0 @ PADAN_BASE
#
# padan_0 sengaja TIDAK direset oleh <hps>.h2f_reset: jalur JTAG harus tetap bisa
# dipakai walau HPS tidak boot (tanpa kartu SD), dan perilaku h2f_reset dalam
# keadaan itu belum diverifikasi.
#
# Instance HPS dan clock source dicari menurut kelas (altera_hps, clock_source),
# bukan nama, karena nama instance GHRD berbeda antar versi CD Terasic. Konfigurasi
# HPS (DDR3, pin HPS) tidak disentuh: itu milik GHRD Terasic.
#
# Tidak dijalankan di CI (Platform Designer tidak tersedia). tb/fpga/check_tcl_scripts.py
# menjalankannya dengan stub dan sistem GHRD tiruan.

package require -exact qsys 16.1

if {![info exists PADAN_BASE]} {
    set PADAN_BASE 0x00040000
}

proc padan_find_by_class {cls} {
    set found {}
    foreach inst [get_instances] {
        if {[get_instance_property $inst CLASS_NAME] eq $cls} {
            lappend found $inst
        }
    }
    return $found
}

proc padan_need_one {cls what} {
    set found [padan_find_by_class $cls]
    if {[llength $found] != 1} {
        error "add_padan: harus ada tepat satu $what ($cls), ditemukan [llength $found]: $found"
    }
    return [lindex $found 0]
}

set_validation_property AUTOMATIC_VALIDATION false

foreach inst {padan_0 padan_jtag} {
    if {[lsearch -exact [get_instances] $inst] >= 0} {
        error "add_padan: instance $inst sudah ada; sistem ini sudah dimodifikasi"
    }
}

set hps [padan_need_one altera_hps "HPS"]
set clk [padan_need_one clock_source "clock source"]

set hps_ifs [get_instance_interfaces $hps]
if {[lsearch -exact $hps_ifs h2f_lw_axi_master] < 0} {
    error "add_padan: $hps tidak punya h2f_lw_axi_master; aktifkan lightweight HPS-to-FPGA bridge di parameter HPS"
}

add_instance padan_0 padan_avmm 1.0
add_instance padan_jtag altera_jtag_avalon_master

add_connection $clk.clk padan_0.clock
add_connection $clk.clk padan_jtag.clk
add_connection $clk.clk_reset padan_0.reset
add_connection $clk.clk_reset padan_jtag.clk_reset

add_connection $hps.h2f_lw_axi_master padan_0.s0
set_connection_parameter_value $hps.h2f_lw_axi_master/padan_0.s0 baseAddress $PADAN_BASE

add_connection padan_jtag.master padan_0.s0
set_connection_parameter_value padan_jtag.master/padan_0.s0 baseAddress $PADAN_BASE

set_validation_property AUTOMATIC_VALIDATION true
validate_system
save_system

puts "add_padan: padan_0 @ [format 0x%08X $PADAN_BASE] (HPS: [format 0x%08X [expr {0xFF200000 + $PADAN_BASE}]]), HPS = $hps, clock = $clk"
