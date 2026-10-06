// guard: penjaga keamanan inti PADAN (pembatas percobaan, LOCK, penghitung FAULT,
// tamper, zeroize) dengan FSM safe-state.
//
// FSM utama, 4 bit paritas genap (jarak Hamming >= 2 antar state legal):
//     ZB    0000  zeroize saat boot (reset), lalu OPEN
//     OPEN  0011  enrollment, probe, dan match diizinkan
//     LOCKD 0101  template terkunci: probe dan match saja
//     LOUT  0110  lockout setelah K kegagalan berturut-turut: tidak ada operasi
//     ZH    1001  zeroize, lalu HALT
//     HALT  1010  berhenti sampai reset (reset = zeroize boot)
// Kode lain (paritas ganjil, 1100, 1111) adalah state ilegal: -> ZH, alasan
// ILLEGAL. Flip satu bit pada state legal selalu menghasilkan paritas ganjil.
// Jalan keluar dari LOUT dan HALT hanya reset, dan setiap reset mengenolkan
// memori template, checksum, dan probe; jadi reset tidak bisa dipakai untuk
// mengulang percobaan terhadap template yang sama.
//
// Penghitung disimpan bersama komplemennya (x dan x_n). Ketidakcocokan di OPEN,
// LOCKD, atau LOUT -> ZH, alasan ILLEGAL:
//     fail   kegagalan berturut-turut (NO_MATCH); MATCH mengenolkan;
//            fail mencapai k -> LOUT
//     k      batas kegagalan, K_DEFAULT saat boot, dapat diubah hanya di OPEN
//     fault  jumlah FAULT sejak boot (kumulatif, tidak dinolkan oleh MATCH);
//            mencapai FAULT_MAX -> ZH, alasan FAULT
//     tau    ambang keputusan untuk LOCKD (tau_lk), dapat diubah hanya di OPEN;
//            default 0x7FFFFFFF (tidak ada skor yang mencapainya: NO_MATCH)
// Di LOCKD, decision memakai tau_lk, bukan tau yang ditulis host bersama MATCH.
// Tanpa itu host cukup menulis tau = -2^31 untuk mendapat MATCH, menolkan fail,
// dan pembatas percobaan tidak berarti apa-apa.
// Hasil dibaca saat dec_busy turun (decision.v meng-commit kode pada siklus yang
// sama). Hanya hasil yang selesai di OPEN atau LOCKD dihitung. MATCH dengan
// idx != ~idx_n, kode NONE, dan kode tak dikenal dihitung sebagai FAULT.
//
// Tamper: tamper_n aktif rendah (KEY0 DE10-Nano), asinkron, disinkronkan 2-FF.
// Tamper di state mana pun kecuali HALT -> ZH, alasan TAMPER.
//
// Zeroize (ZB dan ZH):
//     Z_WAIT   tunggu template_mem, mac_array, dan decision diam
//     Z_CLR    minta clr template_mem sampai diterima (mem_busy naik)
//     Z_CWAIT  tunggu clear selesai: T, C, Cw nol (template_mem.v)
//     Z_PROBE  tulis 0 ke D byte probe, satu byte per siklus
//     Z_DONE   ZB -> OPEN (penghitung default), ZH -> HALT
// Selama zeroize semua izin 0, jadi engine bus tidak bisa menulis template,
// probe, atau memulai match (padan_avmm.v). Match yang sudah berjalan
// diselesaikan dulu (Z_WAIT) dan hasilnya tidak dihitung.
//
// Penghitung dan LOCK volatil: tidak ada memori non-volatil. Konsekuensinya
// (perlu enroll ulang setelah setiap reset) ada di docs/rtl_guard.md.
`default_nettype none

module guard #(
    parameter KW        = 4,            // lebar fail dan k
    parameter K_DEFAULT = 5,            // 1 .. 2^KW-1
    parameter FW        = 2,            // lebar fault
    parameter FAULT_MAX = 3,            // 1 .. 2^FW-1
    parameter D         = 128,          // byte probe
    parameter PAW       = 7             // log2(D)
) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              tamper_n,      // asinkron, aktif rendah
    // Perintah dari engine bus (pulsa satu siklus)
    input  wire              lock_req,
    input  wire              k_req,
    input  wire [KW-1:0]     k_val,
    input  wire              tau_req,
    input  wire [31:0]       tau_val,
    // Keadaan inti
    input  wire              mem_busy,
    input  wire              mac_busy,
    input  wire              dec_busy,
    input  wire [3:0]        code,
    input  wire [3:0]        idx,
    input  wire [3:0]        idx_n,
    // Izin untuk engine bus
    output wire              allow_enroll,  // ENROLL_DATA dan ENROLL_CLR
    output wire              allow_probe,
    output wire              allow_match,
    output wire              allow_status,  // kode/idx decision boleh dibaca
    output wire              zeroizing,
    output wire              tau_fixed,     // LOCKD: decision memakai tau_lock
    output wire [31:0]       tau_lock,
    // Zeroize: mengambil alih clr template_mem dan tulis probe
    output wire              z_clr,
    output wire              z_pwr,
    output wire [PAW-1:0]    z_paddr,
    output wire [31:0]       status
);
    localparam [3:0] S_ZB = 4'b0000, S_OPEN = 4'b0011, S_LOCKD = 4'b0101,
                     S_LOUT = 4'b0110, S_ZH = 4'b1001, S_HALT = 4'b1010;

    localparam [1:0] R_BOOT = 2'd0, R_TAMPER = 2'd1, R_FAULT = 2'd2, R_ILLEGAL = 2'd3;

    localparam [2:0] Z_WAIT = 3'd0, Z_CLR = 3'd1, Z_CWAIT = 3'd2, Z_PROBE = 3'd3,
                     Z_DONE = 3'd4;

    localparam [3:0] C_NO_MATCH = 4'b0101, C_MATCH = 4'b1010;

    localparam [KW-1:0] K_INIT = K_DEFAULT;
    localparam [31:0]   TAU_INIT = 32'h7FFF_FFFF;

    // fsm_encoding none: Yosys tidak boleh mengode ulang (state ilegal hilang).
    // syn_encoding user, safe: Quartus memakai kode ini dan menjaga logika
    // pemulihan (belum diverifikasi di Quartus, docs/rtl_guard.md).
    (* fsm_encoding = "none", syn_encoding = "user, safe", preserve, keep *)
    reg  [3:0]       state;
    (* preserve, keep *) reg [KW-1:0] fail, fail_n, k, k_n;
    (* preserve, keep *) reg [FW-1:0] fault, fault_n;
    (* preserve, keep *) reg [31:0]   tau_lk, tau_lk_n;
    reg  [1:0]       reason;
    (* fsm_encoding = "none" *)
    reg  [2:0]       zs;
    reg  [PAW-1:0]   zcnt;
    reg              dbq;

    // ---- Tamper: sinkronisasi 2-FF ----
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED_IF_ASYNCHRONOUS",
       preserve, keep *)
    reg  [1:0]       t_sync;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) t_sync <= 2'b11;
        else        t_sync <= {t_sync[0], tamper_n};
    wire tamper = !t_sync[1];

    // ---- Dekode ----
    // Pemeriksaan ilegal ditulis eksplisit (paritas + dua kode genap tak terpakai),
    // bukan hanya sebagai cabang default.
    wire st_illegal = (^state) || (state == 4'b1100) || (state == 4'b1111);
    wire ctr_bad    = (fail != ~fail_n) || (k != ~k_n) || (fault != ~fault_n) ||
                      (tau_lk != ~tau_lk_n);

    assign allow_enroll = (state == S_OPEN);
    assign allow_probe  = (state == S_OPEN) || (state == S_LOCKD);
    assign allow_match  = (state == S_OPEN) || (state == S_LOCKD);
    assign allow_status = (state == S_OPEN) || (state == S_LOCKD) || (state == S_LOUT);
    assign zeroizing    = (state == S_ZB) || (state == S_ZH);
    assign tau_fixed    = (state == S_LOCKD);
    assign tau_lock     = tau_lk;
    assign z_clr        = zeroizing && (zs == Z_CLR);
    assign z_pwr        = zeroizing && (zs == Z_PROBE);
    assign z_paddr      = zcnt;

    // ---- Hasil decision ----
    wire res      = dbq && !dec_busy;
    wire counting = (state == S_OPEN) || (state == S_LOCKD);
    wire r_match  = (code == C_MATCH) && (idx == ~idx_n);
    wire r_fail   = (code == C_NO_MATCH);
    wire r_fault  = !r_match && !r_fail;

    wire [KW:0] fail_inc  = {1'b0, fail} + 1'b1;
    wire [FW:0] fault_inc = {1'b0, fault} + 1'b1;
    wire        fail_hit  = fail_inc >= {1'b0, k};
    wire        fault_hit = fault_inc >= FAULT_MAX;

    task go_zh(input [1:0] why);
        begin
            state  <= S_ZH;
            reason <= why;
            zs     <= Z_WAIT;
            zcnt   <= {PAW{1'b0}};
        end
    endtask

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state   <= S_ZB;
            reason  <= R_BOOT;
            fail    <= {KW{1'b0}};
            fail_n  <= {KW{1'b1}};
            k       <= K_INIT;
            k_n     <= ~K_INIT;
            fault   <= {FW{1'b0}};
            fault_n <= {FW{1'b1}};
            tau_lk  <= TAU_INIT;
            tau_lk_n <= ~TAU_INIT;
            zs      <= Z_WAIT;
            zcnt    <= {PAW{1'b0}};
            dbq     <= 1'b0;
        end else begin
            dbq <= dec_busy;
            if (st_illegal) begin
                go_zh(R_ILLEGAL);
            end else case (state)
            S_ZB, S_ZH: begin
                if (tamper && state == S_ZB) begin
                    go_zh(R_TAMPER);
                end else case (zs)
                Z_WAIT:  if (!mem_busy && !mac_busy && !dec_busy) zs <= Z_CLR;
                Z_CLR:   if (mem_busy) zs <= Z_CWAIT;            // clr diterima
                Z_CWAIT: if (!mem_busy) zs <= Z_PROBE;
                Z_PROBE: begin
                    zcnt <= zcnt + 1'b1;
                    if (zcnt == D - 1)
                        zs <= Z_DONE;
                end
                Z_DONE: begin
                    zs <= Z_WAIT;
                    if (state == S_ZB) begin
                        state   <= S_OPEN;
                        fail    <= {KW{1'b0}};
                        fail_n  <= {KW{1'b1}};
                        k       <= K_INIT;
                        k_n     <= ~K_INIT;
                        fault   <= {FW{1'b0}};
                        fault_n <= {FW{1'b1}};
                        tau_lk  <= TAU_INIT;
                        tau_lk_n <= ~TAU_INIT;
                    end else begin
                        state <= S_HALT;
                    end
                end
                default: begin                                   // sequencer ilegal: ulang
                    zs   <= Z_WAIT;
                    zcnt <= {PAW{1'b0}};
                end
                endcase
            end
            S_OPEN, S_LOCKD, S_LOUT: begin
                if (tamper) begin
                    go_zh(R_TAMPER);
                end else if (ctr_bad) begin
                    go_zh(R_ILLEGAL);
                end else begin
                    // LOCK dan K tidak bersaing dengan hasil: keduanya diproses
                    // pada siklus yang sama. LOUT/ZH karena hasil menang atas LOCK.
                    if (state == S_OPEN && lock_req)
                        state <= S_LOCKD;
                    if (state == S_OPEN && k_req && k_val != {KW{1'b0}}) begin
                        k   <= k_val;
                        k_n <= ~k_val;
                    end
                    if (state == S_OPEN && tau_req) begin
                        tau_lk   <= tau_val;
                        tau_lk_n <= ~tau_val;
                    end
                    if (res && counting && r_fault) begin
                        fault   <= fault_inc[FW-1:0];
                        fault_n <= ~fault_inc[FW-1:0];
                        if (fault_hit)
                            go_zh(R_FAULT);
                    end else if (res && counting && r_fail) begin
                        fail   <= fail_inc[KW-1:0];
                        fail_n <= ~fail_inc[KW-1:0];
                        if (fail_hit)
                            state <= S_LOUT;
                    end else if (res && counting && r_match) begin
                        fail   <= {KW{1'b0}};
                        fail_n <= {KW{1'b1}};
                    end
                end
            end
            S_HALT: ;
            default: go_zh(R_ILLEGAL);
            endcase
        end
    end

    // ---- Status (GUARD_STATUS) ----
    // Medan 4 bit; untuk KW/FW > 4 hanya 4 bit bawah yang terlihat.
    wire [15:0] fail16  = fail;
    wire [15:0] k16     = k;
    wire [15:0] fault16 = fault;
    assign status = {12'd0, zeroizing, tamper, reason, fault16[3:0], k16[3:0], fail16[3:0], state};
endmodule

`default_nettype wire
