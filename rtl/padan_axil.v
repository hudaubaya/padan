// padan_axil: slave AXI4-Lite untuk inti PADAN di Kria KV260 (Zynq UltraScale+).
//
// Membungkus padan_avmm (bus Avalon-MM internal) tanpa mengubah perilakunya:
// peta register, izin guard, latensi keputusan, dan semua test inti tetap
// berlaku. Alamat byte AXI = 4 x alamat word padan_avmm (docs/rtl_decision.md);
// span 4 KiB (ADDR_W = 12).
//
// Satu transaksi pada satu waktu. AW dan W boleh datang pada siklus berbeda dan
// dalam urutan apa pun; keduanya disimpan, lalu tulis diteruskan ke inti. Tulis
// yang sudah lengkap didahulukan atas baca yang menunggu.
//
//   Tulis: BRESP = OKAY, atau SLVERR bila WSTRB != 4'b1111. Tulis parsial TIDAK
//          diteruskan ke inti (register PADAN hanya mendukung akses 32 bit).
//          BVALID baru naik setelah inti menerima tulis (waitrequest turun),
//          jadi tulis yang ditahan inti (byte template, zeroize) menahan B.
//   Baca:  RRESP = OKAY. RDATA = readdata inti (STATUS, GUARD_STATUS, atau 0).
//   AWPROT/ARPROT diabaikan.
//
// Nama port mengikuti konvensi s_axi_* sehingga Vivado mengenali antarmuka
// AXI4-Lite saat modul dipakai sebagai module reference di block design
// [Kemungkinan Besar; belum dicoba di Vivado, docs/fpga_howto.md].
`default_nettype none

module padan_axil #(
    parameter ADDR_W    = 12,
    parameter KW        = 4,            // guard.v
    parameter K_DEFAULT = 5,
    parameter FW        = 2,
    parameter FAULT_MAX = 3
) (
    input  wire                s_axi_aclk,
    input  wire                s_axi_aresetn,
    input  wire                tamper_n,       // asinkron, aktif rendah (pin PMOD)
    // Tulis alamat
    input  wire [ADDR_W-1:0]   s_axi_awaddr,
    input  wire [2:0]          s_axi_awprot,
    input  wire                s_axi_awvalid,
    output wire                s_axi_awready,
    // Tulis data
    input  wire [31:0]         s_axi_wdata,
    input  wire [3:0]          s_axi_wstrb,
    input  wire                s_axi_wvalid,
    output wire                s_axi_wready,
    // Respons tulis
    output wire [1:0]          s_axi_bresp,
    output wire                s_axi_bvalid,
    input  wire                s_axi_bready,
    // Baca alamat
    input  wire [ADDR_W-1:0]   s_axi_araddr,
    input  wire [2:0]          s_axi_arprot,
    input  wire                s_axi_arvalid,
    output wire                s_axi_arready,
    // Baca data
    output wire [31:0]         s_axi_rdata,
    output wire [1:0]          s_axi_rresp,
    output wire                s_axi_rvalid,
    input  wire                s_axi_rready
);
    localparam [1:0] OKAY = 2'b00, SLVERR = 2'b10;
    localparam [2:0] S_IDLE = 3'd0, S_WR = 3'd1, S_B = 3'd2, S_RD = 3'd3, S_RWAIT = 3'd4,
                     S_R = 3'd5;

    reg  [2:0]        state;
    reg               aw_full, w_full;
    reg  [9:0]        aw_word, ar_word;
    reg  [31:0]       w_data;
    reg  [3:0]        w_strb;
    reg  [1:0]        bresp;
    reg  [31:0]       rdata;

    wire              wr_ready = aw_full && w_full;

    assign s_axi_awready = (state == S_IDLE) && !aw_full;
    assign s_axi_wready  = (state == S_IDLE) && !w_full;
    assign s_axi_arready = (state == S_IDLE) && !wr_ready;
    assign s_axi_bvalid  = (state == S_B);
    assign s_axi_bresp   = bresp;
    assign s_axi_rvalid  = (state == S_R);
    assign s_axi_rdata   = rdata;
    assign s_axi_rresp   = OKAY;

    // ---- Inti ----
    wire [31:0] avs_readdata;
    wire        avs_readdatavalid, avs_waitrequest;
    wire        avs_write = (state == S_WR);
    wire        avs_read  = (state == S_RD);

    padan_avmm #(.KW(KW), .K_DEFAULT(K_DEFAULT), .FW(FW), .FAULT_MAX(FAULT_MAX)) u_core (
        .clk(s_axi_aclk), .rst_n(s_axi_aresetn), .tamper_n(tamper_n),
        .avs_address(avs_read ? ar_word : aw_word), .avs_read(avs_read),
        .avs_write(avs_write), .avs_writedata(w_data),
        .avs_readdata(avs_readdata), .avs_readdatavalid(avs_readdatavalid),
        .avs_waitrequest(avs_waitrequest));

    always @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            state   <= S_IDLE;
            aw_full <= 1'b0;
            w_full  <= 1'b0;
            aw_word <= 10'd0;
            ar_word <= 10'd0;
            w_data  <= 32'd0;
            w_strb  <= 4'd0;
            bresp   <= OKAY;
            rdata   <= 32'd0;
        end else begin
            case (state)
            S_IDLE: begin
                if (s_axi_awvalid && s_axi_awready) begin
                    aw_word <= s_axi_awaddr[11:2];
                    aw_full <= 1'b1;
                end
                if (s_axi_wvalid && s_axi_wready) begin
                    w_data <= s_axi_wdata;
                    w_strb <= s_axi_wstrb;
                    w_full <= 1'b1;
                end
                if (wr_ready) begin
                    // AW dan W lengkap sejak siklus sebelumnya
                    aw_full <= 1'b0;
                    w_full  <= 1'b0;
                    if (w_strb == 4'b1111) begin
                        state <= S_WR;
                    end else begin
                        bresp <= SLVERR;                // tidak diteruskan ke inti
                        state <= S_B;
                    end
                end else if (s_axi_arvalid && s_axi_arready) begin
                    ar_word <= s_axi_araddr[11:2];
                    state   <= S_RD;
                end
            end
            S_WR: if (!avs_waitrequest) begin           // inti menerima tulis
                bresp <= OKAY;
                state <= S_B;
            end
            S_B:  if (s_axi_bready) state <= S_IDLE;
            S_RD: state <= S_RWAIT;                     // readdata valid siklus berikutnya
            S_RWAIT: if (avs_readdatavalid) begin
                rdata <= avs_readdata;
                state <= S_R;
            end
            S_R:  if (s_axi_rready) state <= S_IDLE;
            default: state <= S_IDLE;
            endcase
        end
    end

    // Port yang tidak dipakai (diakui agar tidak ada peringatan sintesis).
    wire unused = &{1'b0, s_axi_awprot, s_axi_arprot, s_axi_awaddr[1:0], s_axi_araddr[1:0]};
endmodule

`default_nettype wire
