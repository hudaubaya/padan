// Toplevel test padan_avmm (bukan RTL rilis): clock HDL dan penghitung latensi.
`timescale 1ns/1ps
module tb (
    input  wire        rst_n,
    input  wire [9:0]  avs_address,
    input  wire        avs_read,
    input  wire        avs_write,
    input  wire [31:0] avs_writedata,
    output wire [31:0] avs_readdata,
    output wire        avs_readdatavalid,
    output wire        avs_waitrequest,
    output reg  [15:0] lat,            // siklus dari start diterima sampai keputusan di-commit
    output wire        dec_busy
);
    // Clock di HDL: clock cocotb 1.8 membangunkan Python dua kali per siklus.
    reg clk = 1'b0;
    always #5 clk = ~clk;

    padan_avmm u (
        .clk(clk), .rst_n(rst_n),
        .avs_address(avs_address), .avs_read(avs_read), .avs_write(avs_write),
        .avs_writedata(avs_writedata), .avs_readdata(avs_readdata),
        .avs_readdatavalid(avs_readdatavalid), .avs_waitrequest(avs_waitrequest));

    assign dec_busy = u.u_dec.busy;

    always @(posedge clk)
        if (u.o_start)
            lat <= 16'd1;
        else if (u.u_dec.busy)
            lat <= lat + 1'b1;

`ifdef WAVES
    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
    end
`endif
endmodule
