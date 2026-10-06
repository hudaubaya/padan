// template_mem: memori template N x D byte (INT8) plus baris checksum C dan Cw.
//
// - Hanya bisa DITULIS dari bus (bus_wr/bus_addr/bus_wdata). Tidak ada jalur
//   baca dari bus: isi template hanya keluar lewat rd_addr/rd_data ke mac_array.
// - Generator checksum: setiap tulis T[j,i] = v memperbarui
//       C_i  += v - T_lama[j,i]
//       Cw_i += w(j) * (v - T_lama[j,i])      w(j) = j + 1 (padan_defs.vh)
//   jadi C dan Cw selalu konsisten dengan isi T, juga saat satu template
//   ditulis ulang tanpa clear. `clr` mengenolkan T, C, dan Cw (keadaan awal
//   yang konsisten).
//
// Organisasi: L bank, satu per lane mac_array. Bank l menyimpan elemen i dengan
// i mod L = l. Word 16 bit per alamat:
//     alamat j*CH + c       T[j, c*L + l] (diperluas tanda)     c = 0..CH-1
//     alamat N*CH + c       C [c*L + l]
//     alamat N*CH + CH + c  Cw[c*L + l]
// Satu baca mengeluarkan 16 lane x 16 bit (satu chunk satu baris) per siklus.
// Setiap bank adalah RAM simple dual-port satu clock (template Quartus),
// dipetakan ke satu M10K (lihat docs/rtl_style.md).
//
// Protokol:
// - bus_wr/clr: permintaan level, diterima pada sisi naik clock saat bus_ready.
//   clr didahulukan atas bus_wr. Satu tulis byte memakai 4 siklus, clr ROWS siklus.
// - lock (dari mac_array): selama 1, tidak ada permintaan bus yang diterima.
// - busy: generator atau clear sedang berjalan, termasuk tulis terakhirnya;
//   mac_array tidak boleh membaca.
// - rd_data valid satu siklus setelah rd_addr (baca terdaftar di M10K).
`default_nettype none

module template_mem #(
    parameter N  = 16,                  // jumlah template
    parameter D  = 128,                 // byte per template
    parameter L  = 16,                  // lane = bank
    parameter AW = 11,                  // log2(N*D), alamat byte bus
    parameter RA = 8                    // log2(ROWS), alamat baca bank
) (
    input  wire              clk,
    input  wire              rst_n,
    // Bus, hanya tulis
    input  wire              bus_wr,
    input  wire [AW-1:0]     bus_addr,  // j*D + i
    input  wire [7:0]        bus_wdata, // T[j,i], INT8
    input  wire              clr,
    output wire              bus_ready,
    input  wire              lock,
    output wire              busy,
    // Port baca mac_array
    input  wire [RA-1:0]     rd_addr,
    output wire [L*16-1:0]   rd_data
);
    `include "padan_defs.vh"

    localparam CH     = D / L;          // chunk per baris
    localparam ROWS   = N * CH + 2 * CH;
    localparam ROW_C  = N * CH;
    localparam ROW_CW = N * CH + CH;
    localparam LB     = $clog2(L);
    localparam CB     = $clog2(CH);
    localparam IB     = $clog2(D);

    localparam [2:0] S_IDLE = 3'd0, S_RD_C = 3'd1, S_WR_C = 3'd2, S_WR_CW = 3'd3,
                     S_CLR  = 3'd4, S_RD_T = 3'd5;

    reg  [2:0]       state;
    reg  [RA-1:0]    g_ra;              // alamat baca generator
    reg  [RA-1:0]    g_wa;              // alamat tulis
    reg  [15:0]      g_wd;              // data tulis
    reg  [L-1:0]     g_we;              // write enable per bank
    reg  [LB-1:0]    g_lane;
    reg  [CB-1:0]    g_ch;
    reg  [7:0]       g_row;
    reg  [15:0]      g_v;               // nilai baru, diperluas tanda
    reg  [15:0]      g_delta;           // v - T_lama

    wire [8:0]       g_w    = padan_weight(g_row);
    // rd_data[g_lane*16 +: 16] dibaca langsung di blok clock (bukan wire): lihat
    // catatan simulasi di mac_array.v.
    // Bobot <= N+1 dan |delta| <= 255: hasil kali muat 16 bit setelah pemotongan
    // mod 2^16, sama dengan aritmetika Cw 16 bit.
    wire [15:0]      g_wdelta = g_delta * {7'd0, g_w};

    // busy mencakup tulis terakhir yang masih tertunda (g_we terdaftar).
    assign busy      = (state != S_IDLE) || (|g_we);
    assign bus_ready = !busy && !lock;

    wire [IB-1:0]    b_i   = bus_addr[IB-1:0];
    wire [AW-IB-1:0] b_row = bus_addr[AW-1:IB];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            g_we  <= {L{1'b0}};
            g_ra  <= {RA{1'b0}};
            g_wa  <= {RA{1'b0}};
            g_wd  <= 16'd0;
        end else begin
            g_we <= {L{1'b0}};
            case (state)
            S_IDLE: begin
                if (bus_ready && clr) begin
                    g_wa  <= {RA{1'b0}};
                    g_wd  <= 16'd0;
                    g_we  <= {L{1'b1}};
                    state <= S_CLR;
                end else if (bus_ready && bus_wr) begin
                    g_lane <= b_i[LB-1:0];
                    g_ch   <= b_i[IB-1:LB];
                    g_row  <= b_row;
                    g_v    <= {{8{bus_wdata[7]}}, bus_wdata};
                    g_ra   <= b_row * CH + b_i[IB-1:LB];     // T lama
                    state  <= S_RD_T;
                end
            end
            S_CLR: begin                                     // tulis 0 ke semua alamat
                if (g_wa == ROWS - 1) begin
                    state <= S_IDLE;
                end else begin
                    g_wa <= g_wa + 1'b1;
                    g_we <= {L{1'b1}};
                end
            end
            S_RD_T: begin                                    // RAM membaca T lama
                g_ra  <= ROW_C + g_ch;
                state <= S_RD_C;
            end
            S_RD_C: begin                                    // q = T lama; RAM membaca C
                g_delta <= g_v - rd_data[g_lane*16 +: 16];
                g_wa    <= g_row * CH + g_ch;                // tulis T baru
                g_wd    <= g_v;
                g_we    <= {{(L-1){1'b0}}, 1'b1} << g_lane;
                g_ra    <= ROW_CW + g_ch;
                state   <= S_WR_C;
            end
            S_WR_C: begin                                    // q = C lama; RAM membaca Cw
                g_wa  <= ROW_C + g_ch;
                g_wd  <= rd_data[g_lane*16 +: 16] + g_delta;  // C += delta
                g_we  <= {{(L-1){1'b0}}, 1'b1} << g_lane;
                state <= S_WR_CW;
            end
            S_WR_CW: begin                                   // q = Cw lama
                g_wa  <= ROW_CW + g_ch;
                g_wd  <= rd_data[g_lane*16 +: 16] + g_wdelta; // Cw += w(j) * delta
                g_we  <= {{(L-1){1'b0}}, 1'b1} << g_lane;
                state <= S_IDLE;
            end
            default: state <= S_IDLE;
            endcase
        end
    end

    // Port baca bank: milik generator saat busy, milik mac_array saat idle.
    wire [RA-1:0] ra = busy ? g_ra : rd_addr;

    genvar l;
    generate
        for (l = 0; l < L; l = l + 1) begin : g_bank
            padan_sdp_ram #(.AW(RA), .DW(16), .DEPTH(ROWS)) u_ram (
                .clk (clk),
                .we  (g_we[l]),
                .wa  (g_wa),
                .wd  (g_wd),
                .ra  (ra),
                .q   (rd_data[l*16 +: 16])
            );
        end
    endgenerate
endmodule

// RAM simple dual-port satu clock: satu port tulis, satu port baca terdaftar,
// tanpa reset dan tanpa inisialisasi. Ini template "Simple Dual-Port RAM (single
// clock)" Quartus. Baca dan tulis ke alamat yang sama pada siklus yang sama
// tidak dipakai oleh template_mem, jadi perilaku read-during-write tidak penting.
module padan_sdp_ram #(
    parameter AW    = 8,
    parameter DW    = 16,
    parameter DEPTH = 1 << AW
) (
    input  wire          clk,
    input  wire          we,
    input  wire [AW-1:0] wa,
    input  wire [DW-1:0] wd,
    input  wire [AW-1:0] ra,
    output reg  [DW-1:0] q
);
    (* ramstyle = "M10K, no_rw_check" *) reg [DW-1:0] mem [0:DEPTH-1];

    always @(posedge clk) begin
        if (we)
            mem[wa] <= wd;
        q <= mem[ra];
    end
endmodule

`default_nettype wire
