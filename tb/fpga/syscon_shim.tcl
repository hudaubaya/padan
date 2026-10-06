# Shim System Console untuk test: menyediakan get_service_paths, claim_service,
# close_service, master_write_32, master_read_32 dengan protokol baris ke proses
# induk (tb/fpga/test_sysconsole.py), lalu menjalankan skrip yang diberikan.
#
#   tclsh syscon_shim.tcl <skrip.tcl>
#
# Permintaan ke induk lewat stdout:  @@REQ <op> <args...>
# Jawaban dari induk lewat stdin:    @@ACK <nilai...>   atau   @@ERR <pesan>
# Baris stdout lain adalah keluaran skrip dan diteruskan apa adanya.

fconfigure stdout -buffering line

proc shim_req {args} {
    puts "@@REQ $args"
    flush stdout
    if {[gets stdin line] < 0} { error "shim: induk menutup stdin" }
    if {[string match "@@ERR *" $line]} { error [string range $line 6 end] }
    if {![string match "@@ACK*" $line]} { error "shim: jawaban tak dikenal: $line" }
    return [string trim [string range $line 5 end]]
}

proc get_service_paths {type} {
    if {$type ne "master"} { return {} }
    return [shim_req paths]
}
proc claim_service {type path lib {claims ""}} { return [shim_req claim $path] }
proc close_service {type m} { shim_req close $m; return }
proc master_write_32 {m addr values} { shim_req write $m $addr {*}$values; return }
proc master_read_32 {m addr n} {
    set out {}
    foreach v [shim_req read $m $addr $n] { lappend out [format 0x%08x $v] }
    return $out
}

if {[catch {source [lindex $argv 0]} err]} {
    puts "SHIM ERROR: $err"
    puts $::errorInfo
    exit 3
}
exit 0
