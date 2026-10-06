// abft_check: pemeriksaan ABFT atas N skor dan dua baris checksum.
//
//     S1 = sum_j s_j            d1 = S1 - C.p
//     S2 = sum_j w(j) s_j       d2 = S2 - Cw.p          w(j) = j + 1 (padan_defs.vh)
//
// Tanpa fault d1 = d2 = 0. Satu galat E pada s_k memberi d1 = E dan
// d2 = (k+1)E. Lokalisasi mencari k dengan d2 = (k+1)*d1 secara berurutan (tanpa
// pembagi): m = d1, 2*d1, ..., N*d1, maksimal N siklus.
//
// Lebar pemeriksa CW = 40 bit (docs/padan_model.md bagian 4): untuk nilai
// register 32 bit apa pun, |S2| <= 136 * 2^31 < 2^39. d1 dan d2 eksak, jadi
// lokalisasi benar untuk setiap galat tunggal pada skor, termasuk flip bit 27-31
// yang gagal dilokalisasi oleh pemeriksa 32 bit. m memakai LW = 44 bit agar
// (k+1)*d1 tidak wrap untuk d1 apa pun.
//
// start baru sebelum done membatalkan pemeriksaan yang berjalan, jadi mac_array
// ditahan (hold) selama busy.
//
// err_vld: pulsa satu siklus saat err valid, pada siklus TETAP setelah baris
// terakhir (tidak bergantung data atau fault). decision.v memakainya agar
// latensi keputusan tetap; lokalisasi (loc_*) bisa berlanjut sampai N siklus
// sesudahnya dan hanya bersifat diagnostik.
//
// Keluaran (valid saat done, ditahan sampai start berikutnya):
//     err      d1 != 0 atau d2 != 0
//     loc_vld  galat dilokalisasi ke skor loc_idx
//     chk      err && !loc_vld: galat di jalur checksum (C.p / Cw.p), atau
//              lebih dari satu galat; tidak ada skor yang disalahkan
`default_nettype none

module abft_check #(
    parameter N  = 16,
    parameter CW = 40,
    parameter LW = 44
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              start,     // pulsa: mulai perhitungan baru
    input  wire              i_vld,
    input  wire [7:0]        i_row,
    input  wire [31:0]       i_data,
    output reg               done,      // pulsa
    output reg               err_vld,   // pulsa: err valid (siklus tetap)
    output wire              busy,      // start berikutnya harus menunggu sampai 0
    output reg               err,
    output reg               loc_vld,
    output reg  [7:0]        loc_idx,
    output wire              chk,
    output reg  signed [CW-1:0] d1,
    output reg  signed [CW-1:0] d2
);
    `include "padan_defs.vh"

    localparam [1:0] S_ACC = 2'd0, S_DIFF = 2'd1, S_LOC = 2'd2, S_DONE = 2'd3;

    reg  [1:0]              state;
    reg  signed [CW-1:0]    s1, s2;
    reg  signed [31:0]      cp, cwp;
    reg  signed [LW-1:0]    m;          // k * d1 (berlaku untuk k >= 1)
    reg  [7:0]              k;

    wire signed [CW-1:0] x  = {{(CW-32){i_data[31]}}, i_data};
    wire signed [CW-1:0] wx = x * $signed({1'b0, padan_weight(i_row)});
    wire signed [LW-1:0] d1_l = {{(LW-CW){d1[CW-1]}}, d1};
    wire signed [LW-1:0] d2_l = {{(LW-CW){d2[CW-1]}}, d2};

    assign chk  = err && !loc_vld;
    assign busy = (state != S_DONE);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state   <= S_DONE;
            done    <= 1'b0;
            err_vld <= 1'b0;
            err     <= 1'b0;
            loc_vld <= 1'b0;
            loc_idx <= 8'd0;
        end else begin
            done    <= 1'b0;
            err_vld <= 1'b0;
            if (start) begin
                s1      <= {CW{1'b0}};
                s2      <= {CW{1'b0}};
                err     <= 1'b0;
                loc_vld <= 1'b0;
                loc_idx <= 8'd0;
                state   <= S_ACC;
            end else begin
                case (state)
                S_ACC: if (i_vld) begin
                    if (i_row < N) begin
                        s1 <= s1 + x;
                        s2 <= s2 + wx;
                    end else if (i_row == N) begin
                        cp <= i_data;
                    end else begin
                        cwp   <= i_data;
                        state <= S_DIFF;
                    end
                end
                S_DIFF: begin
                    d1    <= s1 - {{(CW-32){cp[31]}}, cp};
                    d2    <= s2 - {{(CW-32){cwp[31]}}, cwp};
                    state <= S_LOC;
                    k     <= 8'd0;
                end
                S_LOC: begin
                    if (k == 0) begin
                        err     <= (d1 != 0) || (d2 != 0);
                        err_vld <= 1'b1;
                    end
                    if ((d1 == 0 && d2 == 0) || k == N) begin
                        done  <= 1'b1;
                        state <= S_DONE;
                    end else if (d1 != 0 && (k == 0 ? d1_l : m) == d2_l) begin
                        loc_vld <= 1'b1;
                        loc_idx <= k;
                        done    <= 1'b1;
                        state   <= S_DONE;
                    end else begin
                        m <= (k == 0 ? d1_l : m) + d1_l;
                        k <= k + 1'b1;
                    end
                end
                default: ;
                endcase
            end
        end
    end
endmodule

`default_nettype wire
