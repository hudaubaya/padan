# Constraint PADAN di Kria KV260 (SK-KV260-G). Clock dan reset berasal dari PS
# (pl_clk0, pl_resetn0) di block design, jadi tidak ada create_clock di sini.
#
# tamper_n: PMOD J2 pin 1. PACKAGE_PIN dan IOSTANDARD sama dengan pmod[0] di
# XDC resmi Xilinx Kria-PYNQ (kv260/base/vivado/constraints/base.xdc):
#   H12, Bank 45, som240_1_b13, IO_L4N_AD12N_45, LVCMOS33.
# Bahwa pmod[0] adalah pin fisik 1 di J2 belum dicek dengan skematik carrier
# (docs/fpga_howto.md). Aktif rendah: pull-up internal menahan 1 saat pin
# dibiarkan terbuka; sambungkan pin ke GND (J2 pin 5 atau 11) untuk tamper.
# Pull-up internal lemah: pakai pull-up eksternal (mis. 4,7 kOhm ke 3V3) bila
# kabel panjang: glitch rendah yang tertangkap satu sisi clock sudah memicu
# zeroize permanen sampai reset.
set_property PACKAGE_PIN H12      [get_ports tamper_n]
set_property IOSTANDARD  LVCMOS33 [get_ports tamper_n]
set_property PULLUP      true     [get_ports tamper_n]

# Masukan asinkron; disinkronkan 2-FF di rtl/guard.v (t_sync, ASYNC_REG).
set_false_path -from [get_ports tamper_n]
