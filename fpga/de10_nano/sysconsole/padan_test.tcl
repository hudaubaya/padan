# Uji padan_avmm di DE10-Nano lewat JTAG-to-Avalon master (System Console).
#
#   system-console -cli --script=<repo>/fpga/de10_nano/sysconsole/padan_test.tcl
# atau di konsol System Console:
#   source <repo>/fpga/de10_nano/sysconsole/padan_test.tcl
#
# Variabel opsional (variabel Tcl global sebelum source, atau environment):
#   PADAN_BASE    alamat byte padan_0 di peta JTAG master (default 0x00040000,
#                 sama dengan add_padan.tcl)
#   PADAN_MASTER  indeks atau sub-string path service master. Default: deteksi
#                 otomatis, hanya dengan BACA (tidak ada tulis sebelum master dipilih).
#
# Urutan per galeri di padan_vectors.tcl (dari model/padan.py, gen_vectors.py):
#   ENROLL_CLR, tulis 512 word template, pindai 1024 alamat (semua 0 kecuali
#   STATUS dan GUARD_STATUS), lalu untuk setiap kasus: tulis probe, MATCH(tau),
#   tunggu busy = 0, bandingkan STATUS[11:0] dengan nilai dari model.
#
# Guard (rtl/guard.v): skrip butuh state OPEN (enrollment diizinkan), yaitu
# setelah reset/konfigurasi tanpa LOCK. Skrip tidak menulis GUARD_LOCK atau
# GUARD_K. Bila guard bukan OPEN di awal, atau keluar dari OPEN di tengah uji
# (lockout, FAULT berulang, tamper KEY0), skrip berhenti dengan FAIL yang
# menyebut state dan alasannya. Keluar dari LOUT/HALT/LOCKD hanya dengan reset,
# yang mengenolkan template.
#
# Hasil akhir dicetak sebagai satu baris "PADAN SYSCON: PASS ..." atau
# "PADAN SYSCON: FAIL ...". Skrip ini hanya membandingkan dengan model; hasilnya
# adalah bukti hanya untuk board, bitstream, dan versi repo tempat ia dijalankan.

set PADAN_DIR [file dirname [file normalize [info script]]]
source [file join $PADAN_DIR padan_vectors.tcl]

namespace eval padan {
    variable base 0x00040000
    variable m ""
    # Alamat word (rtl/padan_avmm.v)
    variable A_ENROLL 0x000
    variable A_PROBE  0x200
    variable A_CLR    0x300
    variable A_MATCH  0x301
    variable A_STATUS 0x302
    variable A_GSTAT  0x303
    variable WORDS    1024
    variable GSTATES  {0 ZB 3 OPEN 5 LOCKD 6 LOUT 9 ZH 10 HALT}
    variable REASONS  {BOOT TAMPER FAULT ILLEGAL}
}

proc padan::cfg {name default} {
    if {[info exists ::$name]} { return [set ::$name] }
    if {[info exists ::env($name)]} { return $::env($name) }
    return $default
}

proc padan::byte_addr {word} {
    variable base
    return [format 0x%08X [expr {$base + 4 * $word}]]
}

proc padan::wr {word values} {
    variable m
    master_write_32 $m [byte_addr $word] $values
}

proc padan::rd {word {n 1}} {
    variable m
    set out {}
    foreach v [master_read_32 $m [byte_addr $word] $n] {
        lappend out [expr {$v & 0xFFFFFFFF}]
    }
    return $out
}

# STATUS yang konsisten: bit tak terdefinisi 0, kode valid, dan idx sesuai kode.
proc padan::status_ok {s} {
    if {($s >> 18) != 0 || (($s >> 12) & 0xF) != 0} { return 0 }
    set code [expr {$s & 0xF}]
    set idx  [expr {($s >> 4) & 0xF}]
    set idxn [expr {($s >> 8) & 0xF}]
    if {$code == 0xA} { return [expr {$idx == (~$idxn & 0xF)}] }
    # Perbandingan numerik: operator `in` Tcl membandingkan string ("5" != "0x5").
    if {$code == 0x0 || $code == 0x5 || $code == 0xF} { return [expr {$idx == 0 && $idxn == 0xF}] }
    return 0
}

# GUARD_STATUS yang konsisten: bit [31:20] 0 dan state legal.
proc padan::gstat_ok {g} {
    variable GSTATES
    return [expr {($g >> 20) == 0 && [dict exists $GSTATES [expr {$g & 0xF}]]}]
}

proc padan::gstat_text {g} {
    variable GSTATES
    variable REASONS
    set st [expr {$g & 0xF}]
    set name [expr {[dict exists $GSTATES $st] ? [dict get $GSTATES $st] : "ILEGAL($st)"}]
    return [format "%s (gagal %d/%d, fault %d, alasan %s, GUARD_STATUS 0x%08X)" $name \
        [expr {($g >> 4) & 0xF}] [expr {($g >> 8) & 0xF}] [expr {($g >> 12) & 0xF}] \
        [lindex $REASONS [expr {($g >> 16) & 0x3}]] $g]
}

proc padan::looks_like_padan {path} {
    variable m
    variable A_STATUS
    variable A_GSTAT
    if {[catch {
        set m [claim_service master $path "" ""]
        set st [lindex [rd $A_STATUS] 0]
        set g  [lindex [rd $A_GSTAT] 0]
        set z  [concat [rd 0x000] [rd 0x200] [rd 0x306] [rd 0x3FF]]
    } err]} {
        catch {close_service master $m}
        return 0
    }
    close_service master $m
    return [expr {[status_ok $st] && [gstat_ok $g] && $z eq {0 0 0 0}}]
}

proc padan::pick_master {} {
    set paths [get_service_paths master]
    set want [cfg PADAN_MASTER ""]
    if {$want ne ""} {
        if {[string is integer -strict $want]} {
            set path [lindex $paths $want]
        } else {
            set path [lindex $paths [lsearch -glob $paths *$want*]]
        }
        if {$path eq ""} { error "PADAN_MASTER=$want tidak cocok dengan: $paths" }
        return $path
    }
    set hits {}
    foreach p $paths {
        if {[looks_like_padan $p]} { lappend hits $p }
    }
    if {[llength $hits] != 1} {
        puts "Service master:"
        set i 0
        foreach p $paths { puts "  \[$i\] $p"; incr i }
        error "deteksi otomatis menemukan [llength $hits] master yang cocok; set PADAN_MASTER (indeks atau sub-string)"
    }
    return [lindex $hits 0]
}

proc padan::status {} {
    variable A_STATUS
    return [lindex [rd $A_STATUS] 0]
}

proc padan::gstat {} {
    variable A_GSTAT
    return [lindex [rd $A_GSTAT] 0]
}

# Tunggu zeroize boot selesai; kembalikan GUARD_STATUS.
proc padan::wait_guard {} {
    for {set i 0} {$i < 1000} {incr i} {
        set g [gstat]
        if {![gstat_ok $g]} {
            error [format "GUARD_STATUS tidak valid: 0x%08X (master ini bukan padan_0?)" $g]
        }
        if {(($g >> 19) & 1) == 0} { return $g }
    }
    error "guard tetap zeroize setelah 1000 baca: [gstat_text $g]"
}

proc padan::wait_idle {} {
    for {set i 0} {$i < 1000} {incr i} {
        set s [status]
        if {(($s >> 16) & 0x3) == 0} { return $s }
    }
    error "STATUS tetap busy setelah 1000 baca: [format 0x%08X $s]"
}

proc padan::scan {} {
    variable WORDS
    variable A_STATUS
    variable A_GSTAT
    set bad {}
    set i 0
    foreach v [rd 0 $WORDS] {
        if {$i != $A_STATUS && $i != $A_GSTAT && $v != 0} { lappend bad [format "0x%03X=0x%08X" $i $v] }
        incr i
    }
    return $bad
}

proc padan::main {} {
    variable base
    variable m
    variable A_ENROLL
    variable A_PROBE
    variable A_CLR
    variable A_MATCH
    global PADAN_VEC

    set base [expr {[cfg PADAN_BASE 0x00040000]}]
    set path [pick_master]
    puts "PADAN: master $path, base [format 0x%08X $base]"
    set m [claim_service master $path "" ""]

    set g0 [wait_guard]
    puts "PADAN: guard [gstat_text $g0]"
    if {($g0 & 0xF) != 3} {
        close_service master $m
        puts "PADAN SYSCON: FAIL (guard bukan OPEN: [gstat_text $g0]; reset board untuk zeroize dan kembali ke OPEN)"
        return 1
    }

    set fails 0
    set ncase 0
    set halted ""
    for {set g 0} {$g < $PADAN_VEC(galleries) && $halted eq ""} {incr g} {
        wr $A_CLR 0
        wait_idle
        wr $A_ENROLL $PADAN_VEC(g$g,T)
        wait_idle
        set bad [scan]
        if {[llength $bad] > 0} {
            puts "FAIL galeri $g: alamat selain STATUS tidak nol: [lrange $bad 0 7]"
            incr fails
        }
        for {set c 0} {$c < $PADAN_VEC(g$g,cases)} {incr c} {
            wr $A_PROBE $PADAN_VEC(g$g,c$c,p)
            wr $A_MATCH $PADAN_VEC(g$g,c$c,tau)
            set s [wait_idle]
            set want [expr {$PADAN_VEC(g$g,c$c,status)}]
            incr ncase
            if {($s & 0xFFF) != $want || ![status_ok $s]} {
                puts [format "FAIL galeri %d kasus %d (%s): STATUS 0x%08X, model 0x%03X" \
                    $g $c $PADAN_VEC(g$g,c$c,note) $s $want]
                incr fails
            }
            set gs [gstat]
            if {($gs & 0xF) != 3} {
                set halted [gstat_text [wait_guard]]
                puts "FAIL guard keluar dari OPEN setelah galeri $g kasus $c: $halted"
                incr fails
                break
            }
        }
        if {$halted eq ""} {
            puts "PADAN: galeri $g ($PADAN_VEC(g$g,name)): $PADAN_VEC(g$g,cases) kasus selesai"
        }
    }
    close_service master $m

    if {$fails == 0} {
        puts "PADAN SYSCON: PASS ($ncase kasus, $PADAN_VEC(galleries) galeri, pindai alamat bersih)"
    } elseif {$halted ne ""} {
        puts "PADAN SYSCON: FAIL ($fails kegagalan dari $ncase kasus; dihentikan, guard $halted)"
    } else {
        puts "PADAN SYSCON: FAIL ($fails kegagalan dari $ncase kasus dan $PADAN_VEC(galleries) pindaian)"
    }
    return $fails
}

padan::main
