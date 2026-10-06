# Komponen Platform Designer untuk rtl/padan_avmm.v (docs/fpga_howto.md).
#
# Satu slave Avalon-MM `s0`: data 32 bit, alamat WORD 10 bit (span 4 KiB),
# waitrequest untuk tulis, readdatavalid satu siklus setelah baca. Tidak ada
# byteenable: hanya akses 32 bit yang didukung (tulis 8/16 bit menulis word
# penuh dengan byte lain tidak terdefinisi).
#
# Berkas RTL diambil langsung dari rtl/ di repo (jalur relatif terhadap berkas
# ini), jadi tidak ada salinan RTL kedua yang bisa menyimpang.
#
# Tidak dijalankan di CI (Platform Designer tidak tersedia). tb/fpga/check_hw_tcl.py
# menjalankannya dengan stub dan memeriksa port terhadap rtl/padan_avmm.v.

package require -exact qsys 16.1

set_module_property NAME padan_avmm
set_module_property VERSION 1.0
set_module_property DISPLAY_NAME "PADAN identifikasi INT8 + ABFT (padan_avmm)"
set_module_property DESCRIPTION "Template memory, 16 MAC INT8, ABFT, keputusan dengan dua komparator"
set_module_property GROUP "PADAN"
set_module_property AUTHOR "PADAN"
set_module_property EDITABLE false
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
set_module_property REPORT_TO_TALKBACK false
set_module_property ALLOW_GREYBOX_GENERATION false

# ---- Berkas ----
set rtl_dir ../../../rtl
set rtl_files {padan_avmm.v decision.v template_mem.v mac_array.v abft_check.v}

foreach fs {QUARTUS_SYNTH SIM_VERILOG} {
    add_fileset $fs $fs "" ""
    set_fileset_property $fs TOP_LEVEL padan_avmm
    set_fileset_property $fs ENABLE_RELATIVE_INCLUDE_PATHS true
    foreach f $rtl_files {
        if {$f eq "padan_avmm.v"} {
            add_fileset_file $f VERILOG PATH $rtl_dir/$f TOP_LEVEL_FILE
        } else {
            add_fileset_file $f VERILOG PATH $rtl_dir/$f
        }
    }
    add_fileset_file padan_defs.vh VERILOG_INCLUDE PATH $rtl_dir/padan_defs.vh
}

# ---- Clock dan reset ----
add_interface clock clock end
set_interface_property clock clockRate 0
add_interface_port clock clk clk Input 1

# rst_n asinkron aktif-rendah di RTL; DEASSERT meminta Platform Designer memasang
# sinkronisasi pelepasan reset.
add_interface reset reset end
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges DEASSERT
add_interface_port reset rst_n reset_n Input 1

# ---- Slave Avalon-MM ----
add_interface s0 avalon end
set_interface_property s0 addressUnits WORDS
set_interface_property s0 associatedClock clock
set_interface_property s0 associatedReset reset
set_interface_property s0 bitsPerSymbol 8
set_interface_property s0 burstOnBurstBoundariesOnly false
set_interface_property s0 explicitAddressSpan 0
set_interface_property s0 holdTime 0
set_interface_property s0 linewrapBursts false
set_interface_property s0 maximumPendingReadTransactions 1
set_interface_property s0 readLatency 0
set_interface_property s0 readWaitTime 0
set_interface_property s0 setupTime 0
set_interface_property s0 timingUnits Cycles
set_interface_property s0 writeWaitTime 0

add_interface_port s0 avs_address       address       Input  10
add_interface_port s0 avs_read          read          Input  1
add_interface_port s0 avs_write         write         Input  1
add_interface_port s0 avs_writedata     writedata     Input  32
add_interface_port s0 avs_readdata      readdata      Output 32
add_interface_port s0 avs_readdatavalid readdatavalid Output 1
add_interface_port s0 avs_waitrequest   waitrequest   Output 1
