// Sel fisik dari open_pdks (sky130_ef_sc_hd) yang dipakai netlist baseline
// tetapi tidak ada di repo model sel sky130_fd_sc_hd. decap_12 hanya
// kapasitor decoupling: tidak punya keluaran dan tidak berpengaruh pada logika.

`default_nettype none

module sky130_ef_sc_hd__decap_12 (
    input wire VPWR,
    input wire VGND,
    input wire VPB,
    input wire VNB
);
endmodule
