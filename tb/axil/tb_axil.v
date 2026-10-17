// Toplevel test padan_axil (bukan RTL rilis): clock HDL dan penghitung latensi.
// Parameter guard default = rilis.
`timescale 1ns/1ps
module tb #(
    parameter KW        = 4,
    parameter K_DEFAULT = 5,
    parameter FW        = 2,
    parameter FAULT_MAX = 3
) (
    input  wire        rst_n,
    input  wire        tamper_n,
    input  wire [11:0] awaddr,
    input  wire        awvalid,
    output wire        awready,
    input  wire [31:0] wdata,
    input  wire [3:0]  wstrb,
    input  wire        wvalid,
    output wire        wready,
    output wire [1:0]  bresp,
    output wire        bvalid,
    input  wire        bready,
    input  wire [11:0] araddr,
    input  wire        arvalid,
    output wire        arready,
    output wire [31:0] rdata,
    output wire [1:0]  rresp,
    output wire        rvalid,
    input  wire        rready,
    output wire        dec_busy
);
    // Clock di HDL: clock cocotb 1.8 membangunkan Python dua kali per siklus.
    reg clk = 1'b0;
    always #5 clk = ~clk;

    padan_axil #(.KW(KW), .K_DEFAULT(K_DEFAULT), .FW(FW), .FAULT_MAX(FAULT_MAX)) u (
        .s_axi_aclk(clk), .s_axi_aresetn(rst_n), .tamper_n(tamper_n),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b000), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b000), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));

    assign dec_busy = u.u_core.u_dec.busy;

`ifdef WAVES
    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
    end
`endif
endmodule
