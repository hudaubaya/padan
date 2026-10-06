// mac_array: L MAC lane, adder tree, akumulator 32 bit.
//
// Satu dot product D elemen selesai per CH = D/L siklus (rilis: 128/16 = 8).
// Lane l mengalikan elemen i = c*L + l pada siklus chunk c. Adder tree
// menjumlahkan L produk, lalu akumulator menjumlahkan CH chunk.
//
// Satu `start` menghitung N+2 baris berurutan dari template_mem:
//     baris 0..N-1   skor   s_j = T[j] . p
//     baris N        C  . p
//     baris N+1      Cw . p
// Setiap hasil keluar sebagai o_vld/o_row/o_data selama satu siklus.
//
// Pipeline (siklus setelah alamat baris r chunk c dikeluarkan):
//     +1  M   data template dari M10K (baca terdaftar), byte probe dipilih
//     +2  P   produk per lane (DSP, register keluaran)
//     +3  T1  jumlah 4 produk (adder tree level 1-2)
//     +4  T2  jumlah 16 produk (adder tree level 3-4)
//     +5  A   akumulator; hasil baris valid saat chunk terakhir masuk
// Register tag (*_vld, *_row, *_ch) berjalan sejajar data. Testbench memakainya
// untuk menyuntik fault pada siklus yang tepat.
//
// Lebar (padan_bounds.py): produk 16x8 bertanda = 24 bit (Cw sampai 16 bit),
// jumlah 16 produk = 28 bit, akumulator 32 bit cukup untuk semua baris.
`default_nettype none

module mac_array #(
    parameter N  = 16,
    parameter D  = 128,
    parameter L  = 16,
    parameter RA = 8
) (
    input  wire              clk,
    input  wire              rst_n,
    // Probe p, tulis byte dari bus (diabaikan selama busy)
    input  wire              p_wr,
    input  wire [6:0]        p_addr,
    input  wire [7:0]        p_wdata,
    // Kendali
    input  wire              start,     // permintaan level, diterima saat !busy && !hold
    input  wire              hold,      // template_mem atau abft_check masih sibuk
    output wire              mem_lock,  // ke template_mem: jangan terima tulis bus
    output reg               busy,
    output wire              o_start,   // pulsa saat start diterima
    // Port baca template_mem
    output wire [RA-1:0]     rd_addr,
    input  wire [L*16-1:0]   rd_data,
    // Hasil
    output wire              o_vld,
    output wire [7:0]        o_row,
    output wire [31:0]       o_data,
    // Paritas probe: 1 jika ada byte probe yang paritasnya salah saat dibaca
    // sejak start terakhir (sticky). Fault pada p tidak terlihat oleh ABFT.
    output reg               p_err
);
    localparam CH   = D / L;
    localparam ROWS = N + 2;            // baris yang dihitung per start
    localparam CB   = $clog2(CH);
    localparam PW   = 24;               // produk 16 x 8 bertanda
    localparam SW   = 28;               // jumlah L = 16 produk
    // Adder tree ditulis untuk L = 16 (4 grup x 4 produk).

    // ---- Probe: register datar, bukan array ----
    // L baca paralel per siklus tidak cocok untuk RAM. Ditulis sebagai vektor
    // agar tidak ada alat yang menginferensinya sebagai memori (Yosys
    // mengabaikan ramstyle = "logic" dan memetakan array ke MLAB).
    reg [D*8-1:0] probe;
    // Paritas genap per byte, ditulis bersama byte-nya dan diperiksa setiap kali
    // byte dibaca lane. p dipakai jalur skor dan jalur checksum sekaligus, jadi
    // fault pada p konsisten di keduanya dan lolos ABFT (docs/padan_model.md
    // contoh E); paritas menutup celah itu untuk flip bit tunggal.
    reg [D-1:0]   probe_par;
    always @(posedge clk)
        if (p_wr && !busy) begin
            probe[p_addr*8 +: 8] <= p_wdata;
            probe_par[p_addr]    <= ^p_wdata;
        end

    // ---- Sequencer ----
    reg              issue;             // alamat valid siklus ini
    reg  [7:0]       row;
    reg  [CB-1:0]    ch;

    assign o_start  = start && !busy && !hold;
    assign mem_lock = busy || start;
    assign rd_addr  = row * CH + ch;

    wire last_issue = (row == ROWS - 1) && (ch == CH - 1);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            issue <= 1'b0;
            row   <= 8'd0;
            ch    <= {CB{1'b0}};
        end else if (o_start) begin
            issue <= 1'b1;
            row   <= 8'd0;
            ch    <= {CB{1'b0}};
        end else if (issue) begin
            if (last_issue)
                issue <= 1'b0;                 // row/ch tetap: rd_addr tetap dalam rentang
            else if (ch == CH - 1) begin
                ch  <= {CB{1'b0}};
                row <= row + 1'b1;
            end else begin
                ch  <= ch + 1'b1;
            end
        end
    end

    // ---- Tag pipeline ----
    reg            m_vld, p_vld, t1_vld, t2_vld, a_vld;
    reg [7:0]      m_row, p_row, t1_row, t2_row, a_row;
    reg [CB-1:0]   m_ch,  p_ch,  t1_ch,  t2_ch,  a_ch;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            {m_vld, p_vld, t1_vld, t2_vld, a_vld} <= 5'd0;
        end else begin
            m_vld  <= issue;
            p_vld  <= m_vld;
            t1_vld <= p_vld;
            t2_vld <= t1_vld;
            a_vld  <= t2_vld;
        end
    end

    always @(posedge clk) begin
        m_row  <= row;    m_ch  <= ch;
        p_row  <= m_row;  p_ch  <= m_ch;
        t1_row <= p_row;  t1_ch <= p_ch;
        t2_row <= t1_row; t2_ch <= t1_ch;
        a_row  <= t2_row; a_ch  <= t2_ch;
    end

    // ---- Lane: pilih byte probe (M), kalikan (P) ----
    // Part-select rd_data dibaca di dalam blok clock, bukan lewat `wire`:
    // di Icarus, wire part-select dari bus 256 bit yang punya 16 driver parsial
    // dievaluasi ulang pada setiap update bank (simulasi beberapa kali lebih
    // lambat, lihat docs/rtl_style.md bagian 8).
    wire [L-1:0] par_bad;              // stage M: paritas byte probe lane l salah

    genvar l;
    generate
        for (l = 0; l < L; l = l + 1) begin : g_lane
            reg  signed [7:0]    p_m;          // byte probe untuk chunk di stage M
            reg                  p_bad;
            (* multstyle = "dsp" *) reg signed [PW-1:0] prod;

            always @(posedge clk) begin
                p_m   <= probe[(ch * L + l)*8 +: 8];   // sejajar dengan baca M10K
                p_bad <= (^probe[(ch * L + l)*8 +: 8]) ^ probe_par[ch * L + l];
                prod  <= $signed(rd_data[l*16 +: 16]) * p_m;
            end
            assign par_bad[l] = p_bad;
        end
    endgenerate

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            p_err <= 1'b0;
        else if (o_start)
            p_err <= 1'b0;
        else if (m_vld && |par_bad)
            p_err <= 1'b1;
    end

    // ---- Adder tree: 16 -> 4 (T1) -> 1 (T2) ----
    // Setiap register ditulis oleh tepat satu blok always (tidak ada array yang
    // elemennya ditulis dari beberapa blok).
    genvar g;
    generate
        for (g = 0; g < 4; g = g + 1) begin : g_sum4
            reg signed [SW-1:0] sum;
            always @(posedge clk)
                sum <= (g_lane[4*g+0].prod + g_lane[4*g+1].prod)
                     + (g_lane[4*g+2].prod + g_lane[4*g+3].prod);
        end
    endgenerate

    reg signed [SW-1:0] tree;
    always @(posedge clk)
        tree <= (g_sum4[0].sum + g_sum4[1].sum) + (g_sum4[2].sum + g_sum4[3].sum);

    // ---- Akumulator 32 bit ----
    reg signed [31:0] acc;
    always @(posedge clk)
        if (t2_vld)
            acc <= (t2_ch == 0 ? 32'sd0 : acc) + tree;

    assign o_vld  = a_vld && (a_ch == CH - 1);
    assign o_row  = a_row;
    assign o_data = acc;

    // busy: dari start diterima sampai baris terakhir keluar.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            busy <= 1'b0;
        else if (o_start)
            busy <= 1'b1;
        else if (o_vld && o_row == ROWS - 1)
            busy <= 1'b0;
    end
endmodule

`default_nettype wire
