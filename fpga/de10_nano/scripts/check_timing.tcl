# Pemeriksaan timing wajib (docs/fpga_howto.md langkah 6).
#
#   quartus_sta -t <repo>/fpga/de10_nano/scripts/check_timing.tcl <proyek> [revisi]
#
# Untuk setiap kondisi operasi yang tersedia (model lambat/cepat, suhu):
#   - worst slack setup, hold, recovery, removal (harus >= 0)
# Lalu:
#   - daftar constraint SDC yang diabaikan (harus kosong)
# Ringkasan ditulis ke padan_timing_check.txt; keluar 1 jika ada pelanggaran.
#
# BELUM PERNAH DIJALANKAN pada Quartus (tidak tersedia di lingkungan pembuatnya).
# Jika satu perintah gagal di versi Quartus Anda, lakukan pemeriksaan yang sama
# lewat GUI Timing Analyzer seperti di docs/fpga_howto.md.

set proj [lindex $argv 0]
set rev  [lindex $argv 1]
if {$proj eq ""} { error "pakai: quartus_sta -t check_timing.tcl <proyek> \[revisi\]" }
if {$rev eq ""} { set rev $proj }

project_open $proj -revision $rev
create_timing_netlist
read_sdc
update_timing_netlist

set out [open padan_timing_check.txt w]
set bad 0

foreach oc [get_available_operating_conditions] {
    set_operating_conditions $oc
    update_timing_netlist
    foreach kind {setup hold recovery removal} {
        # report_timing mengembalikan {jumlah_path worst_slack}
        set r [report_timing -$kind -npaths 1 -detail summary -panel_name "PADAN $kind ($oc)"]
        set npaths [lindex $r 0]
        set slack  [lindex $r 1]
        if {$npaths > 0 && $slack < 0} {
            set verdict PELANGGARAN
            incr bad
        } else {
            set verdict ok
        }
        puts $out [format "%-40s %-9s paths=%-6s slack=%-10s %s" $oc $kind $npaths $slack $verdict]
    }
}

# Constraint yang diabaikan: laporan Timing Analyzer "Ignored Constraints".
report_sdc -ignored_only -panel_name "PADAN Ignored Constraints" -file padan_ignored_constraints.txt
set ignored ""
if {[file exists padan_ignored_constraints.txt]} {
    set f [open padan_ignored_constraints.txt r]
    set ignored [string trim [read $f]]
    close $f
}
if {$ignored ne ""} {
    puts $out "Ignored Constraints TIDAK kosong (lihat padan_ignored_constraints.txt):"
    puts $out $ignored
    incr bad
} else {
    puts $out "Ignored Constraints: kosong"
}

close $out
delete_timing_netlist
project_close

set f [open padan_timing_check.txt r]
puts [read $f]
close $f
if {$bad > 0} {
    puts "PADAN TIMING: FAIL ($bad pelanggaran)"
    exit 1
}
puts "PADAN TIMING: PASS"
