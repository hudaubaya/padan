# SDC untuk GHRD DE10-Nano (top DE10_NANO_SoC_GHRD) dengan padan_avmm.
#
# Dipakai SEBAGAI PENGGANTI SDC bawaan GHRD (docs/fpga_howto.md langkah 4), bukan
# tambahan, supaya clock yang sama tidak didefinisikan dua kali. Nama port
# mengikuti top GHRD Terasic. Kalau satu nama tidak cocok, constraint-nya muncul
# di laporan "Ignored Constraints"; pemeriksaan wajib di docs/fpga_howto.md
# menuntut laporan itu kosong.
#
# padan_avmm sepenuhnya sinkron terhadap clock clock_source GHRD (FPGA_CLK1_50,
# 50 MHz) dan tidak butuh constraint khusus: tidak ada CDC, multicycle, atau
# false path di dalamnya. Reset dilepas lewat sinkronisasi Platform Designer
# (synchronousEdges DEASSERT di padan_avmm_hw.tcl).

# ---- Clock board, 50 MHz ----
create_clock -name FPGA_CLK1_50 -period 20.000 [get_ports {FPGA_CLK1_50}]
create_clock -name FPGA_CLK2_50 -period 20.000 [get_ports {FPGA_CLK2_50}]
create_clock -name FPGA_CLK3_50 -period 20.000 [get_ports {FPGA_CLK3_50}]

# ---- JTAG (USB-Blaster II, System Console / JTAG-to-Avalon master) ----
create_clock -name altera_reserved_tck -period 40.000 [get_ports {altera_reserved_tck}]
set_input_delay  -clock altera_reserved_tck -clock_fall 3 [get_ports {altera_reserved_tdi}]
set_input_delay  -clock altera_reserved_tck -clock_fall 3 [get_ports {altera_reserved_tms}]
set_output_delay -clock altera_reserved_tck 3 [get_ports {altera_reserved_tdo}]
# Lintas domain tck <-> clock sistem ditangani FIFO/sinkronisasi di IP JTAG.
set_clock_groups -asynchronous -group [get_clocks {altera_reserved_tck}]

# ---- Clock turunan (PLL HPS/FPGA) dan ketidakpastian ----
derive_pll_clocks
derive_clock_uncertainty

# ---- IO lambat tanpa hubungan timing dengan logika ----
set_false_path -from [get_ports {KEY[*]}] -to *
set_false_path -from [get_ports {SW[*]}] -to *
set_false_path -from * -to [get_ports {LED[*]}]
