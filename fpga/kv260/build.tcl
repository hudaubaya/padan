# Sintesis, implementasi, bitstream, laporan, dan XSA untuk proyek KV260.
#
#   vivado -mode batch -source fpga/kv260/build.tcl [-tclargs <dir_proyek> [jobs]]
#
# Laporan ditulis ke <dir_proyek>/reports dan diperiksa dengan
#   python3 fpga/kv260/check_reports.py <dir_proyek>/reports
# Skrip ini berhenti dengan error bila run gagal; timing diperiksa
# check_reports.py, bukan di sini.

set HERE [file dirname [file normalize [info script]]]
set ROOT [file normalize [file join $HERE .. ..]]
set PROJ_DIR [expr {[llength $argv] > 0 ? [lindex $argv 0] : [file join $ROOT build kv260]}]
set JOBS     [expr {[llength $argv] > 1 ? [lindex $argv 1] : 4}]
set REP      [file join $PROJ_DIR reports]

open_project [file join $PROJ_DIR padan_kv260.xpr]
file mkdir $REP

reset_run synth_1
launch_runs synth_1 -jobs $JOBS
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synth_1 gagal" }

launch_runs impl_1 -to_step write_bitstream -jobs $JOBS
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "impl_1 gagal" }

open_run impl_1
report_timing_summary -max_paths 10 -file [file join $REP timing_summary.rpt]
report_utilization -hierarchical -file [file join $REP utilization_hier.rpt]
report_utilization -file [file join $REP utilization.rpt]
report_methodology -file [file join $REP methodology.rpt]
report_cdc -file [file join $REP cdc.rpt]

write_hw_platform -fixed -include_bit -force [file join $PROJ_DIR padan_kv260.xsa]
puts "PADAN KV260: bitstream dan laporan di $PROJ_DIR"
