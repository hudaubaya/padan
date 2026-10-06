// padan_avmm: slave Avalon-MM minimal untuk inti PADAN
// (template_mem + mac_array + abft_check + decision).
//
// Data 32 bit, alamat word 10 bit. Baca: waitrequest selalu 0, readdata valid
// satu siklus kemudian (readdatavalid, read latency tetap 1). Tulis: waitrequest
// ditahan sampai tulis selesai diterima inti.
//
//   Alamat word      Nama          Akses  Isi
//   0x000 - 0x1FF    ENROLL_DATA   W      T[j][4k+b] = writedata[8b+7:8b], j = addr[8:5], k = addr[4:0]
//   0x200 - 0x21F    PROBE_DATA    W      p[4k+b]    = writedata[8b+7:8b], k = addr[4:0]
//   0x300            ENROLL_CLR    W      tulis apa pun: kosongkan T, C, Cw
//   0x301            MATCH         W      writedata = tau (bertanda), mulai identifikasi
//   0x302            STATUS        R      [3:0] kode, [7:4] idx, [11:8] ~idx,
//                                         [16] match berjalan, [17] enroll/clear berjalan
//   lainnya          -             -      baca 0, tulis diabaikan
//
// Kode: 0000 NONE, 0101 NO_MATCH, 1010 MATCH, 1111 FAULT. Kode lain, atau
// idx != ~(~idx), harus diperlakukan host sebagai FAULT (decision.v).
//
// Tidak ada jalur baca untuk template, probe, skor, atau checksum: readdata
// hanya bisa berisi STATUS atau 0. Skor sengaja tidak dikeluarkan karena probe
// basis (p = 127 e_i) akan membocorkan T[j,i] lewat s_j (docs/rtl_padan.md).
`default_nettype none

module padan_avmm #(
    parameter N = 16,
    parameter D = 128,
    parameter L = 16
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire [9:0]        avs_address,
    input  wire              avs_read,
    input  wire              avs_write,
    input  wire [31:0]       avs_writedata,
    output reg  [31:0]       avs_readdata,
    output reg               avs_readdatavalid,
    output wire              avs_waitrequest
);
    localparam [9:0] A_CLR    = 10'h300,
                     A_MATCH  = 10'h301,
                     A_STATUS = 10'h302;

    localparam [2:0] E_IDLE = 3'd0, E_TBYTE = 3'd1, E_PBYTE = 3'd2, E_CLR = 3'd3,
                     E_MATCH = 3'd4, E_ACK = 3'd5;

    // ---- Inti ----
    wire            bus_ready, mem_busy, mem_lock;
    wire [7:0]      rd_addr;
    wire [L*16-1:0] rd_data;
    wire            mac_busy, o_start, o_vld, p_err;
    wire [7:0]      o_row;
    wire [31:0]     o_data;
    wire            err_vld, abft_err;
    wire            dec_busy;
    wire [3:0]      code, idx, idx_n;

    reg  [2:0]      state;
    reg  [1:0]      cnt;                // byte ke-cnt dari word
    reg  [9:0]      w_addr;
    reg  [31:0]     w_data;
    wire [7:0]      w_byte = w_data[cnt*8 +: 8];

    template_mem #(.N(N), .D(D), .L(L)) u_mem (
        .clk(clk), .rst_n(rst_n),
        .bus_wr(state == E_TBYTE), .bus_addr({w_addr[8:0], cnt}), .bus_wdata(w_byte),
        .clr(state == E_CLR), .bus_ready(bus_ready), .lock(mem_lock), .busy(mem_busy),
        .rd_addr(rd_addr), .rd_data(rd_data));

    mac_array #(.N(N), .D(D), .L(L)) u_mac (
        .clk(clk), .rst_n(rst_n),
        .p_wr(state == E_PBYTE && !mac_busy), .p_addr({w_addr[4:0], cnt}), .p_wdata(w_byte),
        .start(state == E_MATCH), .hold(mem_busy || dec_busy), .mem_lock(mem_lock),
        .busy(mac_busy), .o_start(o_start),
        .rd_addr(rd_addr), .rd_data(rd_data),
        .o_vld(o_vld), .o_row(o_row), .o_data(o_data), .p_err(p_err));

    // Lokalisasi abft_check hanya diagnostik; start berikutnya boleh memotongnya
    // setelah keputusan di-commit (hold memakai dec_busy, bukan busy abft_check).
    abft_check #(.N(N)) u_chk (
        .clk(clk), .rst_n(rst_n), .start(o_start),
        .i_vld(o_vld), .i_row(o_row), .i_data(o_data),
        .done(), .err_vld(err_vld), .busy(), .err(abft_err), .loc_vld(), .loc_idx(), .chk(),
        .d1(), .d2());

    decision #(.N(N)) u_dec (
        .clk(clk), .rst_n(rst_n), .start(o_start), .tau(w_data),
        .s_vld(o_vld), .s_row(o_row), .s_data(o_data),
        .abft_err_vld(err_vld), .abft_err(abft_err), .p_err(p_err),
        .busy(dec_busy), .code(code), .idx(idx), .idx_n(idx_n));

    // ---- Engine tulis ----
    assign avs_waitrequest = avs_write && (state != E_ACK);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= E_IDLE;
            cnt   <= 2'd0;
        end else begin
            case (state)
            E_IDLE: if (avs_write) begin
                w_addr <= avs_address;
                w_data <= avs_writedata;
                cnt    <= 2'd0;
                if (avs_address[9] == 1'b0)
                    state <= E_TBYTE;
                else if (avs_address[9:5] == 5'b10000)
                    state <= E_PBYTE;
                else if (avs_address == A_CLR)
                    state <= E_CLR;
                else if (avs_address == A_MATCH)
                    state <= E_MATCH;
                else
                    state <= E_ACK;                  // diabaikan
            end
            E_TBYTE: if (bus_ready) begin            // byte diterima template_mem
                cnt <= cnt + 1'b1;
                if (cnt == 2'd3)
                    state <= E_ACK;
            end
            E_PBYTE: if (!mac_busy) begin            // byte ditulis ke probe
                cnt <= cnt + 1'b1;
                if (cnt == 2'd3)
                    state <= E_ACK;
            end
            E_CLR:   if (bus_ready) state <= E_ACK;
            E_MATCH: if (o_start)   state <= E_ACK;
            E_ACK:   state <= E_IDLE;
            default: state <= E_IDLE;
            endcase
        end
    end

    // ---- Baca: hanya STATUS ----
    wire [31:0] status = {14'd0, mem_busy, dec_busy, 4'd0, idx_n, idx, code};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            avs_readdata      <= 32'd0;
            avs_readdatavalid <= 1'b0;
        end else begin
            avs_readdatavalid <= avs_read;
            avs_readdata      <= (avs_read && avs_address == A_STATUS) ? status : 32'd0;
        end
    end
endmodule

`default_nettype wire
