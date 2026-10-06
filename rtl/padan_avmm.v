// padan_avmm: slave Avalon-MM minimal untuk inti PADAN
// (template_mem + mac_array + abft_check + decision + guard).
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
//   0x303            GUARD_STATUS  R      [3:0] state guard, [7:4] fail, [11:8] k,
//                                         [15:12] fault, [17:16] alasan, [18] tamper,
//                                         [19] zeroize berjalan (guard.v)
//   0x304            GUARD_LOCK    W      writedata = 0x4C4F434B ("LOCK"): OPEN -> LOCKD
//   0x305            GUARD_K       W      writedata = k, 1 .. 2^KW-1 (bit lain 0), hanya di OPEN
//   0x306            GUARD_TAU     W      writedata = tau untuk LOCKD (bertanda), hanya di OPEN
//   lainnya          -             -      baca 0, tulis diabaikan
//
// Hanya build debug (`define DEBUG_FAULT, docs/rtl_debug_fault.md); di build rilis
// kedua alamat ini termasuk "lainnya" dan STATUS[31] = 0:
//   0x307            DBG_FAULT     W      [0] aktif, [4:1] lane, [9:5] baris (0..N+1),
//                                         [12:10] chunk, [31:16] delta bertanda; hanya di OPEN
//   0x308            DBG_ABFT      R      [7:0] loc_idx, [8] loc_vld, [9] err, [10] chk,
//                                         [11] pemeriksaan ABFT selesai
//   STATUS[31] = 1 menandai build debug.
//
// Izin dari guard: ENROLL_DATA dan ENROLL_CLR hanya di OPEN; PROBE_DATA dan
// MATCH di OPEN dan LOCKD. Di LOCKD, tau yang ditulis bersama MATCH diabaikan
// dan GUARD_TAU yang dipakai. Tulis yang tidak diizinkan diterima (waitrequest
// turun) tetapi dibuang. Selama zeroize, tulis ditahan (waitrequest) sampai
// zeroize selesai. Di luar OPEN, LOCKD, LOUT, STATUS[11:0] dibaca sebagai NONE
// (0xF00).
//
// Kode: 0000 NONE, 0101 NO_MATCH, 1010 MATCH, 1111 FAULT. Kode lain, atau
// idx != ~(~idx), harus diperlakukan host sebagai FAULT (decision.v).
//
// Tidak ada jalur baca untuk template, probe, skor, atau checksum: readdata
// hanya bisa berisi STATUS, GUARD_STATUS, atau 0. Skor sengaja tidak dikeluarkan
// karena probe basis (p = 127 e_i) akan membocorkan T[j,i] lewat s_j
// (docs/rtl_padan.md).
`default_nettype none

module padan_avmm #(
    parameter N = 16,
    parameter D = 128,
    parameter L = 16,
    parameter KW        = 4,            // guard.v
    parameter K_DEFAULT = 5,
    parameter FW        = 2,
    parameter FAULT_MAX = 3
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              tamper_n,  // asinkron, aktif rendah (KEY0)
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
                     A_STATUS = 10'h302,
                     A_GSTAT  = 10'h303,
                     A_GLOCK  = 10'h304,
                     A_GK     = 10'h305,
                     A_GTAU   = 10'h306;
    localparam [31:0] LOCK_MAGIC = 32'h4C4F_434B;
`ifdef DEBUG_FAULT
    localparam [9:0] A_DBG_FAULT = 10'h307,
                     A_DBG_ABFT  = 10'h308;
    localparam       DEBUG_BUILD   = 1'b1;
`else
    localparam       DEBUG_BUILD   = 1'b0;
`endif

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
    wire            allow_enroll, allow_probe, allow_match, allow_status, zeroizing;
    wire            tau_fixed;
    wire [31:0]     tau_lock;
    wire            z_clr, z_pwr;
    wire [6:0]      z_paddr;
    wire [31:0]     g_status;

    reg  [2:0]      state;
    reg  [1:0]      cnt;                // byte ke-cnt dari word
    reg  [9:0]      w_addr;
    reg  [31:0]     w_data;
    wire [7:0]      w_byte = w_data[cnt*8 +: 8];

    // Perintah guard (dan register debug) diambil saat tulis diterima di E_IDLE
    // (lalu E_ACK).
    wire        g_cmd = (state == E_IDLE) && avs_write && !zeroizing;
    wire [31:0] k_hi  = avs_writedata >> KW;

`ifdef DEBUG_FAULT
    // ---- Injeksi fault (build debug saja) ----
    // Host hanya membaca hasil lokalisasi (indeks dan flag), bukan d1/d2.
    reg               dbg_en;
    reg  [3:0]        dbg_lane;
    reg  [7:0]        dbg_row;
    reg  [2:0]        dbg_ch;
    reg  signed [15:0] dbg_delta;
    wire              dbg_chk_busy, dbg_loc_vld, dbg_chk;
    wire [7:0]        dbg_loc_idx;
    wire [31:0]       dbg_abft = {20'd0, !dbg_chk_busy, dbg_chk, abft_err, dbg_loc_vld,
                                  dbg_loc_idx};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dbg_en    <= 1'b0;
            dbg_lane  <= 4'd0;
            dbg_row   <= 8'd0;
            dbg_ch    <= 3'd0;
            dbg_delta <= 16'sd0;
        end else if (g_cmd && avs_address == A_DBG_FAULT && allow_enroll) begin
            dbg_en    <= avs_writedata[0];
            dbg_lane  <= avs_writedata[4:1];
            dbg_row   <= {3'd0, avs_writedata[9:5]};
            dbg_ch    <= avs_writedata[12:10];
            dbg_delta <= avs_writedata[31:16];
        end
    end
`endif

    template_mem #(.N(N), .D(D), .L(L)) u_mem (
        .clk(clk), .rst_n(rst_n),
        .bus_wr(state == E_TBYTE && allow_enroll), .bus_addr({w_addr[8:0], cnt}),
        .bus_wdata(w_byte), .clr((state == E_CLR && allow_enroll) || z_clr),
        .bus_ready(bus_ready), .lock(mem_lock), .busy(mem_busy),
        .rd_addr(rd_addr), .rd_data(rd_data));

    mac_array #(.N(N), .D(D), .L(L)) u_mac (
        .clk(clk), .rst_n(rst_n),
        .p_wr(zeroizing ? z_pwr : (state == E_PBYTE && allow_probe && !mac_busy)),
        .p_addr(zeroizing ? z_paddr : {w_addr[4:0], cnt}),
        .p_wdata(zeroizing ? 8'd0 : w_byte),
        .start(state == E_MATCH && allow_match), .hold(mem_busy || dec_busy),
        .mem_lock(mem_lock),
        .busy(mac_busy), .o_start(o_start),
        .rd_addr(rd_addr), .rd_data(rd_data),
        .o_vld(o_vld), .o_row(o_row), .o_data(o_data), .p_err(p_err)
`ifdef DEBUG_FAULT
        ,
        // Injeksi hanya di OPEN: setelah LOCK (atau di LOUT/HALT) delta tidak berlaku.
        .dbg_en(dbg_en && allow_enroll), .dbg_lane(dbg_lane), .dbg_row(dbg_row),
        .dbg_ch(dbg_ch), .dbg_delta(dbg_delta)
`endif
        );

    // Lokalisasi abft_check hanya diagnostik; start berikutnya boleh memotongnya
    // setelah keputusan di-commit (hold memakai dec_busy, bukan busy abft_check).
    abft_check #(.N(N)) u_chk (
        .clk(clk), .rst_n(rst_n), .start(o_start),
        .i_vld(o_vld), .i_row(o_row), .i_data(o_data),
        .done(), .err_vld(err_vld), .err(abft_err),
`ifdef DEBUG_FAULT
        .busy(dbg_chk_busy), .loc_vld(dbg_loc_vld), .loc_idx(dbg_loc_idx), .chk(dbg_chk),
`else
        .busy(), .loc_vld(), .loc_idx(), .chk(),
`endif
        .d1(), .d2());

    decision #(.N(N)) u_dec (
        .clk(clk), .rst_n(rst_n), .start(o_start), .tau(tau_fixed ? tau_lock : w_data),
        .s_vld(o_vld), .s_row(o_row), .s_data(o_data),
        .abft_err_vld(err_vld), .abft_err(abft_err), .p_err(p_err),
        .busy(dec_busy), .code(code), .idx(idx), .idx_n(idx_n));

    // ---- Guard ----
    guard #(.KW(KW), .K_DEFAULT(K_DEFAULT), .FW(FW), .FAULT_MAX(FAULT_MAX), .D(D), .PAW(7))
    u_guard (
        .clk(clk), .rst_n(rst_n), .tamper_n(tamper_n),
        .lock_req(g_cmd && avs_address == A_GLOCK && avs_writedata == LOCK_MAGIC),
        .k_req(g_cmd && avs_address == A_GK && k_hi == 32'd0), .k_val(avs_writedata[KW-1:0]),
        .tau_req(g_cmd && avs_address == A_GTAU), .tau_val(avs_writedata),
        .mem_busy(mem_busy), .mac_busy(mac_busy), .dec_busy(dec_busy),
        .code(code), .idx(idx), .idx_n(idx_n),
        .allow_enroll(allow_enroll), .allow_probe(allow_probe), .allow_match(allow_match),
        .allow_status(allow_status), .zeroizing(zeroizing),
        .tau_fixed(tau_fixed), .tau_lock(tau_lock),
        .z_clr(z_clr), .z_pwr(z_pwr), .z_paddr(z_paddr), .status(g_status));

    // ---- Engine tulis ----
    // Operasi yang tidak (lagi) diizinkan guard langsung ke E_ACK: tulis dibuang.
    // Ini juga melepas E_MATCH bila guard berpindah state saat start ditahan.
    assign avs_waitrequest = avs_write && (state != E_ACK);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= E_IDLE;
            cnt   <= 2'd0;
        end else begin
            case (state)
            E_IDLE: if (avs_write && !zeroizing) begin
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
            E_TBYTE: if (!allow_enroll) begin
                state <= E_ACK;
            end else if (bus_ready) begin            // byte diterima template_mem
                cnt <= cnt + 1'b1;
                if (cnt == 2'd3)
                    state <= E_ACK;
            end
            E_PBYTE: if (!allow_probe) begin
                state <= E_ACK;
            end else if (!mac_busy) begin            // byte ditulis ke probe
                cnt <= cnt + 1'b1;
                if (cnt == 2'd3)
                    state <= E_ACK;
            end
            E_CLR:   if (!allow_enroll || bus_ready) state <= E_ACK;
            E_MATCH: if (!allow_match || o_start) state <= E_ACK;
            E_ACK:   state <= E_IDLE;
            default: state <= E_IDLE;
            endcase
        end
    end

    // ---- Baca: hanya STATUS dan GUARD_STATUS ----
    wire [11:0] result = allow_status ? {idx_n, idx, code} : 12'hF00;   // NONE
    wire [31:0] status = {DEBUG_BUILD, 13'd0, mem_busy, dec_busy, 4'd0, result};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            avs_readdata      <= 32'd0;
            avs_readdatavalid <= 1'b0;
        end else begin
            avs_readdatavalid <= avs_read;
            avs_readdata      <= !avs_read                ? 32'd0    :
                                 (avs_address == A_STATUS) ? status   :
                                 (avs_address == A_GSTAT)  ? g_status :
`ifdef DEBUG_FAULT
                                 (avs_address == A_DBG_ABFT) ? dbg_abft :
`endif
                                 32'd0;
        end
    end
endmodule

`default_nettype wire
