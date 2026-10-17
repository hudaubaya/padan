// decision: keputusan identifikasi 1:N dari aliran skor, dengan dua komparator
// independen dan penahanan keputusan.
//
//     MATCH(k)   max_j s_j >= tau, k = argmax (indeks terkecil bila seri)
//     NO_MATCH   max_j s_j <  tau (indeks tidak dilaporkan)
//     FAULT      keputusan ditahan: ABFT gagal (abft_err), paritas probe salah
//                (p_err), atau komparator A dan B tidak sepakat
//
// Model: model/padan.py decide().
//
// Komparator A dan B membaca aliran skor yang sama dengan abft_check (keluaran
// akumulator mac_array), jadi tidak ada register skor di antara pemeriksaan ABFT
// dan perbandingan. Keduanya sengaja ditulis berbeda (diversitas) dan punya
// register sendiri, termasuk salinan tau masing-masing:
//     A: perbandingan bertanda langsung (s > best_a, best_a >= tau_a)
//     B: tanda bit selisih 33 bit (s - best_b, s - tau), match sebagai OR per
//        baris; tau disimpan sebagai komplemen (tau_bn = ~tau)
// tau_bn berisi komplemen supaya tidak pernah identik dengan tau_a: tanpa itu
// Yosys menggabungkan kedua register (opt_merge) walau ada atribut keep, dan
// independensinya hilang. dont_touch (Vivado) dan keep (Yosys) tetap dipasang
// untuk register lainnya (rtl_style.md).
//
// Latensi tetap: keputusan di-commit pada pulsa abft_err_vld, yang datang pada
// siklus tetap setelah baris terakhir (abft_check.v), tidak bergantung data,
// tau, atau fault.
//
// Kode status 4 bit, jarak Hamming >= 2 antar kode, dan jarak 4 antara MATCH dan
// NO_MATCH. Flip satu bit pada register kode tidak pernah menghasilkan MATCH;
// host memperlakukan kode lain sebagai FAULT. Indeks dikeluarkan dua kali (idx
// dan ~idx dari komparator berbeda); host memeriksa keduanya.
`default_nettype none

module decision #(
    parameter N = 16
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              start,         // pulsa: run baru (o_start mac_array)
    input  wire [31:0]       tau,           // dibaca saat start
    input  wire              s_vld,
    input  wire [7:0]        s_row,
    input  wire [31:0]       s_data,
    input  wire              abft_err_vld,  // pulsa, siklus tetap
    input  wire              abft_err,
    input  wire              p_err,
    output reg               busy,
    output wire [3:0]        code,
    output reg  [3:0]        idx,           // dari komparator A; 0 kecuali MATCH
    output reg  [3:0]        idx_n          // ~indeks dari komparator B; 4'hF kecuali MATCH
);
    localparam [3:0] C_NONE     = 4'b0000,
                     C_NO_MATCH = 4'b0101,
                     C_MATCH    = 4'b1010,
                     C_FAULT    = 4'b1111;

    // ---- Komparator A ----
    (* keep, dont_touch = "true" *) reg signed [31:0] tau_a;
    (* keep, dont_touch = "true" *) reg signed [31:0] best_a;
    (* keep, dont_touch = "true" *) reg        [3:0]  idx_a;
    (* keep, dont_touch = "true" *) reg               any_a;

    wire signed [31:0] s = s_data;
    wire               row_ok = s_vld && (s_row < N);

    always @(posedge clk) begin
        if (start) begin
            tau_a <= tau;
            any_a <= 1'b0;
            idx_a <= 4'd0;
        end else if (row_ok && (!any_a || s > best_a)) begin
            best_a <= s;
            idx_a  <= s_row[3:0];
            any_a  <= 1'b1;
        end
    end

    wire match_a = any_a && (best_a >= tau_a);

    // ---- Komparator B ----
    (* keep, dont_touch = "true" *) reg        [31:0] tau_bn;     // ~tau
    (* keep, dont_touch = "true" *) reg        [31:0] best_b;
    (* keep, dont_touch = "true" *) reg        [3:0]  idx_b;
    (* keep, dont_touch = "true" *) reg               hit_b;      // ada baris dengan s - tau_b >= 0

    wire [32:0] d_best = {s_data[31], s_data} - {best_b[31], best_b};
    wire [31:0] tau_b  = ~tau_bn;
    wire [32:0] d_tau  = {s_data[31], s_data} - {tau_b[31], tau_b};

    always @(posedge clk) begin
        if (start) begin
            tau_bn <= ~tau;
            best_b <= 32'h8000_0000;             // nilai terkecil
            idx_b  <= 4'd0;
            hit_b  <= 1'b0;
        end else if (row_ok) begin
            if (!d_best[32] && d_best != 33'd0) begin   // s - best_b > 0
                best_b <= s_data;
                idx_b  <= s_row[3:0];
            end
            if (!d_tau[32])                              // s - tau_b >= 0
                hit_b <= 1'b1;
        end
    end

    // ---- Commit ----
    wire agree = (match_a == hit_b) && (idx_a == idx_b);

    // Register keluaran code. Kode legal punya dua setengah yang sama (0101,
    // 1010, ...), jadi dua FF per pasangan bit punya input identik dan Yosys
    // menggabungkannya (synth_xilinx: code[1:0] = code[3:2]); satu flip FF lalu
    // membalik dua bit sekaligus, dan jarak NO_MATCH -> MATCH turun dari 4 ke 2
    // flip. Setengah bawah disimpan terbalik (code_lo_n) sehingga input FF
    // berbeda dan tidak bisa digabung; nilai di port tidak berubah.
    reg [1:0] code_hi;      // code[3:2]
    reg [1:0] code_lo_n;    // ~code[1:0]
    assign code = {code_hi, ~code_lo_n};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy      <= 1'b0;
            code_hi   <= C_NONE[3:2];
            code_lo_n <= ~C_NONE[1:0];
            idx       <= 4'd0;
            idx_n     <= 4'hF;
        end else if (start) begin
            busy      <= 1'b1;
            code_hi   <= C_NONE[3:2];
            code_lo_n <= ~C_NONE[1:0];
            idx       <= 4'd0;
            idx_n     <= 4'hF;
        end else if (busy && abft_err_vld) begin
            busy <= 1'b0;
            if (abft_err || p_err || !agree) begin
                code_hi   <= C_FAULT[3:2];
                code_lo_n <= ~C_FAULT[1:0];
            end else if (match_a) begin
                code_hi   <= C_MATCH[3:2];
                code_lo_n <= ~C_MATCH[1:0];
                idx       <= idx_a;
                idx_n     <= ~idx_b;
            end else begin
                code_hi   <= C_NO_MATCH[3:2];
                code_lo_n <= ~C_NO_MATCH[1:0];
            end
        end
    end
endmodule

`default_nettype wire
