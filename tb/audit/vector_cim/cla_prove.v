// Pembungkus bukti formal: `cla` baseline #0642 (tanpa diubah) = a + b + c_in.
`default_nettype none
module cla_prove #(parameter BITS = 16) (
    input  wire [BITS-1:0] a,
    input  wire [BITS-1:0] b,
    input  wire            cin,
    output wire            ok
);
    wire [BITS-1:0] s;
    wire            c;
    cla #(BITS) dut (.a_in(a), .b_in(b), .c_in(cin), .s_out(s), .c_out(c));
    assign ok = ({c, s} == {1'b0, a} + {1'b0, b} + cin);
endmodule
