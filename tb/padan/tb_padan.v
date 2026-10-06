// Toplevel testbench PADAN: template_mem + mac_array + abft_check.
// Bukan bagian dari RTL rilis. Hasil baris disimpan di `rows` agar Python
// cukup membacanya sekali setelah `done`.
`timescale 1ns/1ps
module tb #(
    parameter N  = 16,
    parameter D  = 128,
    parameter L  = 16,
    parameter AW = 11,
    parameter RA = 8
) (
    input  wire              rst_n,
    input  wire              bus_wr,
    input  wire [AW-1:0]     bus_addr,
    input  wire [7:0]        bus_wdata,
    input  wire              clr,
    output wire              bus_ready,
    input  wire              p_wr,
    input  wire [6:0]        p_addr,
    input  wire [7:0]        p_wdata,
    input  wire              start,
    output wire              busy,
    output wire              mem_busy,
    output wire              done,
    output wire              err,
    output wire              loc_vld,
    output wire [7:0]        loc_idx,
    output wire              chk,
    output wire [39:0]       d1,
    output wire [39:0]       d2,
    output reg  [(N+2)*32-1:0] rows,
    output reg  [15:0]       n_out      // jumlah hasil baris sejak start
);
    // Clock dibangkitkan di HDL: clock cocotb 1.8 berjalan di Python dan
    // membangunkan Python dua kali per siklus (puluhan kali lebih lambat).
    reg clk = 1'b0;
    always #5 clk = ~clk;

    wire [RA-1:0]   rd_addr;
    wire [L*16-1:0] rd_data;
    wire            mem_lock, o_start, o_vld, chk_busy;
    wire [7:0]      o_row;
    wire [31:0]     o_data;

    template_mem #(.N(N), .D(D), .L(L), .AW(AW), .RA(RA)) u_mem (
        .clk(clk), .rst_n(rst_n),
        .bus_wr(bus_wr), .bus_addr(bus_addr), .bus_wdata(bus_wdata), .clr(clr),
        .bus_ready(bus_ready), .lock(mem_lock), .busy(mem_busy),
        .rd_addr(rd_addr), .rd_data(rd_data));

    mac_array #(.N(N), .D(D), .L(L), .RA(RA)) u_mac (
        .clk(clk), .rst_n(rst_n),
        .p_wr(p_wr), .p_addr(p_addr), .p_wdata(p_wdata),
        .start(start), .hold(mem_busy | chk_busy), .mem_lock(mem_lock), .busy(busy), .o_start(o_start),
        .rd_addr(rd_addr), .rd_data(rd_data),
        .o_vld(o_vld), .o_row(o_row), .o_data(o_data));

    abft_check #(.N(N)) u_chk (
        .clk(clk), .rst_n(rst_n), .start(o_start),
        .i_vld(o_vld), .i_row(o_row), .i_data(o_data),
        .done(done), .busy(chk_busy), .err(err), .loc_vld(loc_vld), .loc_idx(loc_idx), .chk(chk),
        .d1(d1), .d2(d2));

    always @(posedge clk) begin
        if (o_start)
            n_out <= 16'd0;
        else if (o_vld) begin
            rows[o_row*32 +: 32] <= o_data;
            n_out <= n_out + 1'b1;
        end
    end

`ifdef WAVES
    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
    end
`endif
endmodule
