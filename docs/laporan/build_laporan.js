// Pembangun docs/laporan/Laporan_PADAN.docx (laporan proyek dari awal sampai akhir).
//
//     node docs/laporan/build_laporan.js docs/laporan/Laporan_PADAN.docx
//
// Butuh paket npm `docx`. Isi laporan ditulis di sini (bukan dihasilkan dari
// model atau log), jadi angka-angkanya harus diperbarui tangan bila repo berubah.
// Sumber setiap angka: dokumen di docs/ dan log CI pada commit yang disebut di
// halaman judul.
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, AlignmentType, LevelFormat, Footer, Header, PageNumber,
  BorderStyle, TableOfContents,
} = require('docx');

const FONT = 'Calibri';
const PAGE_W = 11906, MARGIN = 1134;                 // A4, margin 2 cm
const CONTENT_W = PAGE_W - 2 * MARGIN;               // 9638 DXA

// ---- helpers ----
// Inline markup: **tebal**, `kode`
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ ...base, text: t.slice(2, -2), bold: true }));
    else out.push(new TextRun({ ...base, text: t.slice(1, -1), font: 'Consolas', size: 19 }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (text, opts = {}) => new Paragraph({ children: runs(text), spacing: { after: 120 }, ...opts });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: false });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const B = (text, level = 0) => new Paragraph({ children: runs(text), numbering: { reference: 'bullets', level }, spacing: { after: 60 } });
const N = (text, ref = 'nums') => new Paragraph({ children: runs(text), numbering: { reference: ref, level: 0 }, spacing: { after: 60 } });

function table(header, rows, widthsPct) {
  const widths = widthsPct.map(p => Math.round(CONTENT_W * p / 100));
  widths[widths.length - 1] = CONTENT_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFBFBF' };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (text, i, head) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    borders,
    shading: head ? { type: ShadingType.CLEAR, color: 'auto', fill: 'DCE6F2' } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: runs(String(text), { size: 19, bold: head || undefined }) })],
  });
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true)) }),
      ...rows.map(r => new TableRow({ children: r.map((c, i) => cell(c, i, false)) })),
    ],
  });
}
const gap = () => new Paragraph({ children: [], spacing: { after: 60 } });

// ---- content ----
const C = [];
C.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 80 },
  children: [new TextRun({ text: 'Laporan Proyek PADAN', bold: true, size: 44 })] }));
C.push(new Paragraph({ spacing: { after: 80 },
  children: [new TextRun({ text: 'Identifikasi 1:N INT8 dengan ABFT, dari model hingga integrasi FPGA DE10-Nano', size: 26, color: '404040' })] }));
C.push(new Paragraph({ spacing: { after: 240 },
  children: [new TextRun({ text: 'Per 6 Oktober 2026 · repositori hudaubaya/padan, branch main @ 258c487', size: 20, color: '606060' })] }));

C.push(H1('Ringkasan'));
C.push(P('PADAN sudah memiliki golden model, RTL lengkap, antarmuka Avalon-MM, penjaga keamanan (guard), dan paket integrasi DE10-Nano. Semuanya terbukti **di simulasi** dan lulus CI. **Belum ada satu pun hasil Quartus, timing, atau board.** Itu adalah risiko terbesar proyek saat ini.'));
C.push(B('**Fungsi:** 16 template × 128 byte INT8, skor s_j = Σ T[j,i]·p_i, keputusan MATCH / NO_MATCH / FAULT dengan latensi tetap 153 siklus.'));
C.push(B('**Keamanan fault:** dari 48.765 fault bit tunggal yang disuntikkan lewat antarmuka bus, tidak satu pun menghasilkan MATCH yang salah.'));
C.push(B('**Keamanan sistem:** pembatas percobaan, LOCK dengan τ terkunci, zeroize saat tamper atau FAULT berulang, dan FSM safe-state yang dibuktikan dengan SAT (Yosys).'));
C.push(B('**Estimasi sumber daya (Yosys):** semua di bawah 10% kapasitas, kecuali blok DSP yang berada di 9,8–17%. Keputusannya masih menunggu Anda.'));
C.push(B('**Status:** 6 PR sudah di-merge ke main. CI terakhir hijau dan log-nya sudah diperiksa untuk setiap target baru.'));

C.push(H2('Cara membaca label'));
C.push(table(['Label', 'Arti'], [
  ['[Pasti]', 'Dibuktikan oleh simulasi, bukti formal, aljabar, atau struktur netlist di repo ini.'],
  ['[Kemungkinan Besar]', 'Inferensi kuat yang belum dibuktikan di sini, misalnya perilaku Quartus.'],
  ['[Menebak]', 'Mengisi celah informasi; perlu dicek.'],
  ['(model)', 'Angka dari golden model Python, bukan dari RTL, FPGA, atau silikon.'],
  ['estimasi Yosys', 'Pemetaan Yosys synth_intel_alm, bukan laporan fitter Quartus.'],
], [22, 78]));
C.push(gap());

C.push(H1('Kronologi'));
C.push(P('Seluruh pekerjaan dilakukan pada 6 Oktober 2026 dalam 6 pull request, masing-masing di-merge setelah CI hijau.'));
C.push(table(['Tahap', 'Commit / PR', 'Isi'], [
  ['1. Kerangka dan baseline', 'c319f85', 'Struktur repo; tiga desain TT07 disalin apa adanya beserta lisensi dan SHA256SUMS'],
  ['2. Audit baseline', 'ecbc278', 'Ketiga baseline diuji apa adanya (RTL dan netlist gate-level) terhadap model Python'],
  ['3. Golden model', 'd1a274d (PR #1)', 'Model integer PADAN, analisis batas 32 bit, data sintetis INT8 vs float, simulasi fault'],
  ['4. RTL inti', '982d2a6 (PR #2)', 'template_mem, mac_array, abft_check + test cocotb dan uji mutasi'],
  ['5. Keputusan dan bus', '4210629 (PR #3)', 'decision (dua komparator), padan_avmm (slave Avalon-MM), paritas probe'],
  ['6. FPGA DE10-Nano', '1ed2f89 (PR #4)', 'Komponen Platform Designer, skrip GHRD, SDC, skrip System Console'],
  ['7. Guard', '811f8ce (PR #5)', 'Pembatas percobaan, LOCK + τ terkunci, FAULT, tamper KEY0, zeroize, safe-state'],
  ['8. Injeksi fault debug', '2e694e4 (PR #6)', 'Port DEBUG_FAULT dan bukti bahwa build rilis tidak memuatnya'],
  ['9. Estimasi sumber daya', '(tanpa commit)', 'Yosys synth_intel_alm per modul; laporan terpisah'],
], [26, 20, 54]));
C.push(gap());

C.push(H1('1. Baseline TT07 dan audit'));
C.push(P('Tiga desain Tiny Tapeout 07 disimpan **tanpa modifikasi** pada commit yang di-tapeout. `make check-baseline` gagal bila satu byte berubah. Audit menguji RTL dan netlist tapeout (sky130) dengan cocotb terhadap model maksud desain.'));
C.push(table(['Baseline', 'Yang benar', 'Cacat yang ditemukan', 'Dipakai ulang'], [
  ['TinyTPU #0590', 'Array sistolik 2×2 benar untuk 400 pasang matriks acak', 'tx_ready terlambat; akumulator 16 bit overflow; operasi kedua tanpa reset salah; 32 latch; register tanpa reset (X di netlist)', 'Konsep mac.v + systolic.v; kendali I/O ditulis ulang'],
  ['Iterative MAC #0040', 'Pengali 7×8 benar untuk 32.768 pasangan', 'Mode 0 selalu 0; uio dipakai dua arah; cabang mati; hasil terpotong', 'Hanya konsep'],
  ['Vector CiSRAM #0642', 'Dot product 8 elemen eksak; CLA terbukti formal (SAT)', 'Tidak ada cacat fungsional; hanya tak bertanda; tidak ada SRAM sungguhan', 'Ya: MAC dan cla'],
], [18, 26, 34, 22]));
C.push(gap());
C.push(P('16 test cacat ditandai expect_fail. Suite menjadi merah bila perilaku baseline berubah, tanda dokumen audit perlu diperbarui. Nomor TT07 belum dicek terhadap tinytapeout.com. [Kemungkinan Besar]'));

C.push(H1('2. Golden model dan analisis'));
C.push(P('`model/padan.py` mendefinisikan skor, baris checksum C dan Cw, residu ABFT d1 dan d2, dan lokalisasi k = d2/d1 − 1. Semua angka di bagian ini berlabel (model).'));
C.push(B('**Semua besaran muat 32 bit bertanda.** [Pasti] Yang terbesar tanpa fault adalah Cw·p = 285.212.672 (model, 30 bit), dengan ruang sisa 7,53× terhadap 2^31 − 1.'));
C.push(B('**Baris checksum tidak muat INT8:** C butuh 12 bit dan Cw 16 bit, sehingga lane harus 16×8, bukan 8×8. [Pasti]'));
C.push(B('**INT8 vs float:** kesepakatan keputusan ≥ 99,882% (model) untuk τ 0,15–0,50. Semua beda berada dalam 0,0047 dari ambang. FAR/FRR absolut tidak bermakna untuk biometrik nyata, karena data ini sintetis.'));
C.push(B('**Fault tunggal:** deteksi 100% (model) untuk semua flip efektif. Pemeriksa 32 bit salah tunjuk untuk flip bit 27–31 pada skor; pemeriksa 40 bit atau cek rentang memberi lokalisasi 100%. RTL memakai 40 bit.'));
C.push(B('**Celah yang ditemukan model:** fault pada probe p tidak terlihat oleh ABFT. 65.536 flip tidak terdeteksi, 229 di antaranya mengubah keputusan (model). Celah ini ditutup di RTL dengan paritas per byte.'));
C.push(B('**Fault ganda:** dua flip bit 31 bisa saling meniadakan pada pemeriksa 32 bit, dan dua fault bisa salah lokalisasi. Lokalisasi cukup untuk pelaporan, tidak untuk koreksi otomatis.'));

C.push(H1('3. RTL inti'));
C.push(P('Tiga modul Verilog-2001 dengan parameter rilis N = 16, D = 128, L = 16 lane.'));
C.push(table(['Modul', 'Isi'], [
  ['template_mem', '16 bank M10K × 144 word × 16 bit (T, C, Cw); hanya bisa ditulis; generator memperbarui C dan Cw di setiap tulis byte'],
  ['mac_array', '16 lane MAC 16×8, adder tree, akumulator 32 bit; satu dot product per 8 siklus; 18 baris per MATCH (16 skor + C·p + Cw·p); probe 1.024 bit dengan paritas per byte'],
  ['abft_check', 'S1, S2, d1, d2 dalam 40 bit; lokalisasi tanpa pembagi, maksimal 16 langkah'],
], [20, 80]));
C.push(gap());
C.push(B('**38.112 fault** (lane, akumulator, setiap bit memori) terdeteksi dengan indeks benar; tidak ada alarm palsu pada 1.317 run bersih. [Pasti]'));
C.push(B('**Biaya ABFT:** 16 siklus (+12,5%) untuk dua baris checksum.'));
C.push(B('**Uji mutasi:** mutan no_c, no_cw, dan weight_j terbunuh. Mutan no_c dan no_cw membuktikan bahwa test tanpa fault saja tidak cukup, karena pemeriksa yang setengah mati tetap diam.'));

C.push(H1('4. Keputusan dan antarmuka Avalon-MM'));
C.push(P('`decision.v` memakai dua komparator yang ditulis berbeda (diversitas). τ di komparator B disimpan sebagai komplemen; tanpa itu Yosys menggabungkan register keduanya. `padan_avmm.v` adalah slave Avalon-MM tanpa jalur baca untuk template, probe, atau skor.'));
C.push(table(['Kode STATUS', 'Arti'], [
  ['0000', 'NONE (belum ada keputusan)'],
  ['0101', 'NO_MATCH (tanpa indeks, agar identitas terdekat tidak bocor)'],
  ['1010', 'MATCH; indeks dikeluarkan dua kali (idx dan ~idx)'],
  ['1111', 'FAULT: ABFT gagal, paritas probe salah, atau komparator tidak sepakat'],
], [22, 78]));
C.push(gap());
C.push(B('**814 keputusan** identik dengan model, termasuk seri dan nilai ekstrem.'));
C.push(B('**48.765 fault** (datapath, memori, probe, register komparator, sinyal error, register keluaran): tidak satu pun menghasilkan MATCH yang salah. [Pasti]'));
C.push(B('**Latensi tetap 153 siklus** untuk MATCH, NO_MATCH, dan FAULT, sehingga tidak ada kanal samping waktu.'));
C.push(B('**Mutan no_parity** membuktikan temuan model: satu flip bit probe tanpa paritas membuat impostor MATCH.'));

C.push(H1('5. Integrasi FPGA DE10-Nano'));
C.push(P('Paket integrasi ke GHRD Terasic sudah lengkap, tetapi **belum pernah dikompilasi atau dijalankan di board**. Tidak ada klaim hasil board.'));
C.push(B('Komponen Platform Designer (`padan_avmm_hw.tcl`), skrip `add_padan.tcl` (JTAG master dan lightweight HPS bridge, alamat 0x0004_0000 / HPS 0xFF24_0000), dan SDC pengganti.'));
C.push(B('Skrip System Console: 3 galeri, 46 kasus dari model, dan pemindaian 1.024 alamat.'));
C.push(B('Pemeriksaan wajib setelah kompilasi: DSP/M10K (`check_reports.py`), Ignored Constraints, dan slack (`check_timing.tcl`).'));
C.push(B('**Yang diuji di CI tanpa Quartus:** skrip Tcl dijalankan dengan stub. Skrip System Console dijalankan melawan RTL lewat shim, dan lulus 46/46. JTAG, interkoneksi, dan timing tidak tercakup.'));

C.push(H1('6. Guard: keamanan di tingkat sistem'));
C.push(P('`guard.v` mengendalikan izin bus. Setiap reset melakukan zeroize sebelum perangkat bisa dipakai.'));
C.push(table(['Fungsi', 'Perilaku'], [
  ['Pembatas percobaan', 'K = 5 NO_MATCH berturut-turut → LOUT (keluar hanya lewat reset); MATCH menolkan penghitung'],
  ['LOCK', 'Setelah LOCK, template tidak bisa ditulis atau dihapus; probe dan MATCH tetap bisa'],
  ['τ terkunci', 'Di LOCKD, decision memakai GUARD_TAU, bukan τ dari host'],
  ['FAULT', 'Penghitung kumulatif; FAULT ke-3 → zeroize → HALT'],
  ['Tamper', 'KEY0, sinkronisasi 2-FF → zeroize → HALT'],
  ['Safe-state', 'State 4 bit berparitas genap; kode ilegal atau ketidakcocokan penghitung/komplemen → zeroize → HALT'],
], [24, 76]));
C.push(gap());
C.push(P('**τ terkunci tidak ada di spesifikasi awal.** Tanpanya, host cukup menulis τ = −2^31 untuk mendapat MATCH dan menolkan penghitung, sehingga pembatas percobaan tidak berarti. [Pasti]'));
C.push(B('9 test dengan parameter rilis. Zeroize dibuktikan dengan memindai seluruh 16 × 144 word memori dan register probe di simulasi.'));
C.push(B('Bukti SAT Yosys setelah sintesis: setiap state ilegal mematikan semua izin dan menuju zeroize; ada kontrol negatif.'));
C.push(B('12 mutan guard terbunuh, termasuk clear yang melewatkan baris checksum dan sinkronisasi tamper 1-FF.'));

C.push(H1('7. Injeksi fault debug (DEBUG_FAULT)'));
C.push(P('Build debug punya register DBG_FAULT untuk menambahkan delta ke produk satu lane, serta DBG_ABFT untuk membaca hasil lokalisasi. Build rilis **tidak memuat** port, register, atau logikanya.'));
C.push(B('**Delta aditif, bukan pengganti.** Dengan delta aditif, residu ABFT hanya bergantung pada delta dan baris. Dengan nilai pengganti, residu membocorkan T·p. [Pasti, aljabar]'));
C.push(B('288 injeksi (16 lane × 18 baris): semuanya FAULT; 256 dilokalisasi ke barisnya, 32 terdeteksi di baris checksum.'));
C.push(B('Bukti build rilis: hasil praproses dan netlist Yosys sebelum optimasi tidak memuat jejak dbg; build debug dipakai sebagai kontrol positif.'));

C.push(H1('8. Estimasi sumber daya'));
C.push(P('Estimasi Yosys untuk Cyclone V 5CSEBA6U23I7 dengan parameter rilis. Kapasitas perangkat diambil dari ingatan atas tabel Intel dan belum dicek ke datasheet. [Kemungkinan Besar]'));
C.push(table(['Modul', 'LUT (ALUT)', 'FF', 'Pengali', 'Memori'], [
  ['mac_array', '3.109', '1.918', '16 × 18×18', '–'],
  ['abft_check', '462', '291', '1 × 27×27 + 1 × 9×9', '–'],
  ['template_mem', '290', '86', '1 × 18×18', '16 M10K'],
  ['decision', '192', '151', '–', '–'],
  ['guard', '143', '103', '–', '–'],
  ['**padan_avmm (total)**', '**3.924**', '**2.612**', '**19 pengali**', '**16 M10K**'],
], [26, 16, 12, 28, 18]));
C.push(gap());
C.push(table(['Sumber daya', 'Estimasi', '% kapasitas'], [
  ['ALM', '1.962–3.924', '4,7%–9,5%'],
  ['FF', '2.612', '1,6%'],
  ['M10K', '16 blok', '2,9%'],
  ['**Blok DSP**', '**11–19 blok**', '**9,8%–17%**'],
], [34, 33, 33]));
C.push(gap());
C.push(P('**DSP bisa melewati 10%.** Penyebab utamanya 16 pengali lane, yang harus 18×18 karena baris Cw 16 bit; apakah Quartus memasangkan dua per blok belum diketahui. Pengali di `abft_check` dan `template_mem` (3 blok) bisa dihapus dengan geser-tambah. Hasilnya 7,1%–14%.'));

C.push(H1('9. Verifikasi dan CI'));
C.push(P('`make test` menjalankan semua target di bawah, sekitar 25 menit. CI GitHub Actions menjalankannya di setiap PR dan setiap push ke main. Setiap merge dilakukan setelah CI hijau dan log-nya diperiksa.'));
C.push(table(['Target', 'Isi', 'Hasil terakhir'], [
  ['check-baseline, test-baseline, test-audit', 'Integritas baseline, test upstream, audit RTL + gate-level + bukti SAT CLA', 'lulus'],
  ['test-model, check-model-report', 'Self-test model; dokumen model sinkron', 'lulus'],
  ['test-rtl', 'Inti RTL vs model, 38.112 fault', '7/7'],
  ['test-rtl-avmm', 'Bus + decision, 814 keputusan, 48.765 fault', '7/7'],
  ['test-rtl-guard', 'Guard, parameter rilis', '9/9'],
  ['check-rtl-guard-safe', 'Bukti SAT safe-state', '21 bukti'],
  ['test-rtl-mutation', 'Mutan RTL harus terbunuh', '18/18'],
  ['check-rtl-infer', 'M10K/DSP terinferensi; FF decision 151, guard 103', 'lulus'],
  ['test-rtl-debug, check-rtl-release', 'Build debug; bukti build rilis bersih', '4/4; PASS'],
  ['test-fpga-scripts', 'Skrip FPGA tanpa Quartus, System Console vs RTL', '4/4'],
], [30, 50, 20]));
C.push(gap());

C.push(H1('10. Batas dan risiko terbuka'));
C.push(N('**Belum ada Quartus, timing, atau board.** Semua klaim fungsional berlaku untuk simulasi RTL. Inferensi DSP/M10K dan logika safe-state baru terbukti untuk Yosys.', 'risks'));
C.push(N('**Template selalu ada di luar chip.** Keadaan guard volatil dan setiap reset menghapus template, jadi host harus mengirim ulang template setiap boot.', 'risks'));
C.push(N('**Pembatas hanya menghitung kegagalan berturut-turut.** Penyerang dengan satu probe sah bisa menyelipkannya setiap 4 percobaan.', 'risks'));
C.push(N('**Fault kendali belum disimulasikan:** sequencer, tag baris, FSM. Flip pada tag baris bisa membuat ABFT dan kedua komparator salah secara konsisten. [Kemungkinan Besar]', 'risks'));
C.push(N('**Fault ganda** bisa salah lokalisasi; lokalisasi tidak boleh dipakai untuk koreksi otomatis.', 'risks'));
C.push(N('**Flip dua bit** bisa membawa LOCKD ke OPEN; flip satu bit selalu tertangkap.', 'risks'));
C.push(N('**Bitstream debug adalah alat DoS** dan bisa dibangun lewat pengaturan Quartus di luar repo. Penandanya STATUS[31] = 1.', 'risks'));
C.push(N('**Hasil INT8 vs float memakai data sintetis;** tidak ada klaim akurasi biometrik nyata.', 'risks'));

C.push(H1('11. Langkah berikutnya'));
C.push(N('**Putuskan soal DSP:** hapus 3 pengali di `abft_check` dan `template_mem` sekarang, atau tunggu fitter Quartus.', 'next'));
C.push(N('**Kompilasi di Quartus** mengikuti `docs/fpga_howto.md`. Lalu jalankan pemeriksaan wajib: DSP/M10K, register yang tidak boleh dihapus, Ignored Constraints, dan slack.', 'next'));
C.push(N('**Uji di board:** jalankan `padan_test.tcl` (target PASS 46/46), lalu uji tamper KEY0 secara manual.', 'next'));
C.push(N('**Pertimbangkan penghitung kegagalan total atau pembatas laju** bila ancaman probe sah relevan.', 'next'));
C.push(N('**Tambah simulasi fault kendali** (sequencer, tag baris) atau duplikasi kendali.', 'next'));

// ---- document ----
const doc = new Document({
  creator: 'PADAN',
  title: 'Laporan Proyek PADAN',
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 30, bold: true, color: '1F3864', font: FONT }, paragraph: { spacing: { before: 320, after: 140 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 24, bold: true, color: '2E5395', font: FONT }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [
      { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      ...['nums', 'risks', 'next'].map(reference => ({ reference, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.',
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] })),
    ],
  },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: 'Laporan Proyek PADAN', size: 16, color: '808080' })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: ['Halaman ', PageNumber.CURRENT, ' dari ', PageNumber.TOTAL_PAGES], size: 16, color: '808080' })] })] }) },
    children: C,
  }],
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(process.argv[2], buf); console.log('ok', buf.length); });
