# Laporan Vivado 2026.1 asli (data uji `check_reports.py --self-test`)

Laporan ini berasal dari build pengguna pada 21 Oktober 2026: Vivado v2026.1
(win64), build 6511674, untuk part `xck26-sfvc784-2LV-c`, dengan proyek dari
`create_project.tcl` dan `build.tcl`. Commit persis build ini tidak dicatat;
RTL terakhir berubah di 65e3eb8 (PR #8).

Berkasnya disunting seminimal mungkin:

- Baris `Host` diganti `<host>`, dan jalur proyek diganti `<repo>`.
- `timing_summary.rpt` dipotong sebelum bagian "Timing Details"; isi aslinya
  ± 2.500 baris jalur.
- `runme.log` hanya memuat baris FSM (`Synth 8-802`, `Synth 8-3354`) dari log
  asli. Baris lain dihapus.
- `dsp_cells.txt` adalah keluaran
  `get_cells -hier -filter {REF_NAME == DSP48E2}` pada `impl_1`.

Isi tabel tidak diubah.
