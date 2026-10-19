# Makefile utama PADAN — menjalankan seluruh pemeriksaan dari root repo.
#
#   make test                      semua pemeriksaan (integritas, model, baseline, audit)
#   make test-baseline             test upstream ketiga baseline TT07
#   make test-baseline-<nama>      satu baseline, mis. test-baseline-tinytpu_0590
#   make check-baseline            baseline tidak berubah dari salinan upstream
#   make test-model                self-test model Python (model/)
#   make check-model-report        docs/padan_model.md sama dengan keluaran model
#   make test-audit                audit baseline RTL + netlist (docs/baseline_audit.md)
#   make test-audit-<a>[-gl]       satu audit: tinytpu, iterative_mac, vector_cim
#   make test-audit-vector_cim-formal  bukti SAT adder CLA #0642 (butuh yosys)
#   make test-rtl                  test cocotb RTL PADAN, parameter rilis (docs/rtl_padan.md)
#   make test-rtl-avmm             test cocotb padan_avmm + decision (docs/rtl_decision.md)
#   make test-rtl-guard            test cocotb guard.v, parameter rilis (docs/rtl_guard.md)
#   make check-rtl-guard-safe      bukti SAT safe-state guard setelah sintesis Yosys
#   make test-rtl-debug            build debug DEBUG_FAULT: injeksi fault terdeteksi dan dilokalisasi
#   make check-rtl-release         build rilis tanpa port/logika DEBUG_FAULT (netlist Yosys)
#   make test-rtl-axil             test cocotb padan_axil (wrapper AXI4-Lite KV260)
#   make test-rtl-mutation         26 mutan RTL harus dibunuh oleh test
#   make check-rtl-infer           Yosys UltraScale+ (K26): block RAM, DSP48E2, FF redundan
#   make test-kv260-scripts        skrip Vivado + host KV260 tanpa Vivado/board (docs/fpga_howto.md)
#   make laporan                   bangun docs/laporan/Laporan_PADAN.docx dari docs/laporan_padan.md
#   make check-laporan             Laporan_PADAN.docx sinkron dengan docs/laporan_padan.md (pandoc)
#   make sky130-cells              unduh model sel sky130_fd_sc_hd untuk simulasi GL
#   make clean                     hapus artefak simulasi
#
# Test baseline dijalankan dengan Makefile upstream masing-masing (tidak
# diubah). Makefile upstream memakai $(PWD), jadi kita `cd` dulu, bukan
# `make -C`. cocotb 1.8 tidak selalu keluar non-zero saat test gagal, jadi
# results.xml diperiksa secara eksplisit.

SHELL        := /bin/bash
SIM          ?= icarus
PYTHON       ?= python3
BASELINE_DIR := rtl/baseline
BASELINES    := tinytpu_0590 iterative_mac_0040 vector_cim_0642
AUDITS       := tinytpu iterative_mac vector_cim
MODELS       := tinytpu iterative_mac vector_cim padan padan_bounds padan_data padan_faults

# Model sel sky130_fd_sc_hd untuk simulasi gate-level, dikunci ke satu commit.
SKY130_SC_HD_URL := https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd
SKY130_SC_HD_REV := 28c101fc5db17bb6cadefa4c2a146693c685f1dc
SKY130_SC_HD     ?= $(CURDIR)/.cache/sky130_fd_sc_hd
# Netlist tapeout semua baseline; sel yang diunduh = gabungan sel yang dipakai.
GL_NETLISTS      := $(wildcard $(BASELINE_DIR)/*/gl/*.v)
GL_CELLS         := $(shell grep -ohE '^ *sky130_fd_sc_hd__[a-z0-9]+_[0-9]+' $(GL_NETLISTS) | \
                      sed -E 's/^ *sky130_fd_sc_hd__(.*)_[0-9]+$$/\1/' | sort -u)
GL_CELLS_HASH    := $(shell echo $(GL_CELLS) | md5sum | cut -c1-8)
SKY130_STAMP     := $(SKY130_SC_HD)/.padan-rev-$(SKY130_SC_HD_REV)-$(GL_CELLS_HASH)

# Target cocotb butuh cocotb-config di PATH (requirements.txt). Tanpa ini make
# gagal dengan pesan samar "No rule to make target '/Makefile.sim'".
define need_cocotb
	@command -v cocotb-config >/dev/null 2>&1 || { \
	  echo "FAIL cocotb tidak ditemukan (cocotb-config tidak ada di PATH)."; \
	  echo "     Pasang dependensi: $(PYTHON) -m pip install -r requirements.txt"; exit 1; }
endef

# $(call check_results,<nama>,<path results.xml>)
define check_results
	@r=$(2); \
	  test -f $$r || { echo "FAIL $(1): $$r tidak ada"; exit 1; }; \
	  grep -q '<testcase' $$r || { echo "FAIL $(1): tidak ada testcase di $$r"; exit 1; }; \
	  ! grep -qE '<(failure|error)' $$r || { echo "FAIL $(1): ada test gagal, lihat $$r"; exit 1; }; \
	  echo "PASS $(1) ($$(grep -c '<testcase' $$r) testcase)"
endef

.PHONY: help test test-baseline check-baseline test-model check-model-report test-audit sky130-cells clean \
        test-rtl test-rtl-avmm test-rtl-guard check-rtl-guard-safe test-rtl-mutation check-rtl-infer \
        test-rtl-debug check-rtl-release test-rtl-axil test-kv260-scripts laporan check-laporan \
        test-audit-vector_cim-formal \
        $(addprefix test-baseline-,$(BASELINES)) \
        $(addprefix test-audit-,$(AUDITS)) $(addsuffix -gl,$(addprefix test-audit-,$(AUDITS)))

help:
	@sed -n '3,24p' $(firstword $(MAKEFILE_LIST)) | sed 's/^# \{0,1\}//'

test: check-baseline test-model check-model-report test-baseline test-audit \
      test-rtl test-rtl-avmm test-rtl-guard check-rtl-guard-safe test-rtl-mutation check-rtl-infer \
      test-rtl-debug check-rtl-release test-rtl-axil test-kv260-scripts check-laporan

test-baseline: $(addprefix test-baseline-,$(BASELINES))

$(addprefix test-baseline-,$(BASELINES)): test-baseline-%:
	@echo "==> baseline $*"
	$(call need_cocotb)
	@cd $(BASELINE_DIR)/$*/test && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,$*,$(BASELINE_DIR)/$*/test/results.xml)

# Isi file harus sama dengan SHA256SUMS, dan himpunan file yang dilacak git di
# rtl/baseline/ harus sama dengan daftar di SHA256SUMS (tidak ada file tambahan).
check-baseline:
	@echo "==> integritas baseline"
	@cd $(BASELINE_DIR) && sha256sum --check --quiet --strict SHA256SUMS
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  diff <(cd $(BASELINE_DIR) && git ls-files | grep -vx SHA256SUMS | LC_ALL=C sort) \
	       <(cut -c67- $(BASELINE_DIR)/SHA256SUMS | LC_ALL=C sort) \
	  || { echo "FAIL check-baseline: file di rtl/baseline/ tidak sama dengan SHA256SUMS"; exit 1; }; \
	fi
	@echo "PASS check-baseline ($$(wc -l < $(BASELINE_DIR)/SHA256SUMS) file)"

test-model:
	@for m in $(MODELS); do \
	  echo "==> model $$m"; $(PYTHON) model/$$m.py --self-test || exit 1; \
	done

# Dokumen hasil model PADAN dibangun dari model; gagal jika tidak sinkron.
check-model-report:
	@echo "==> laporan model PADAN"
	@$(PYTHON) model/padan_report.py --check docs/padan_model.md

# Audit baseline apa adanya terhadap model Python. Cacat terkonfirmasi ditandai
# expect_fail di test (lihat docs/baseline_audit.md), jadi suite hijau selama
# perilaku baseline sama dengan yang didokumentasikan.
test-audit: $(addprefix test-audit-,$(AUDITS)) $(addsuffix -gl,$(addprefix test-audit-,$(AUDITS))) \
            test-audit-vector_cim-formal

$(addprefix test-audit-,$(AUDITS)): test-audit-%:
	@echo "==> audit $* (RTL)"
	$(call need_cocotb)
	@cd tb/audit/$* && rm -f results_rtl.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,audit-$*,tb/audit/$*/results_rtl.xml)

$(addsuffix -gl,$(addprefix test-audit-,$(AUDITS))): test-audit-%-gl: $(SKY130_STAMP)
	@echo "==> audit $* (netlist gate-level tapeout)"
	$(call need_cocotb)
	@cd tb/audit/$* && rm -f results_gl.xml && \
	  $(MAKE) --no-print-directory SIM=$(SIM) GATES=yes SKY130_SC_HD=$(SKY130_SC_HD)
	$(call check_results,audit-$*-gl,tb/audit/$*/results_gl.xml)

test-audit-vector_cim-formal:
	@echo "==> audit vector_cim (bukti SAT adder CLA, Yosys)"
	@tb/audit/vector_cim/cla_prove.sh

# RTL PADAN (rtl/*.v): test cocotb, uji mutasi, dan pemeriksaan inferensi.
test-rtl:
	@echo "==> RTL PADAN (template_mem + mac_array + abft_check)"
	$(call need_cocotb)
	@cd tb/padan && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,rtl-padan,tb/padan/results.xml)

test-rtl-avmm:
	@echo "==> RTL PADAN Avalon-MM (padan_avmm + decision)"
	$(call need_cocotb)
	@cd tb/avmm && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,rtl-avmm,tb/avmm/results.xml)

test-rtl-guard:
	@echo "==> RTL PADAN guard (lockout, LOCK, FAULT, tamper, zeroize, safe-state)"
	$(call need_cocotb)
	@cd tb/guard && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,rtl-guard,tb/guard/results.xml)

test-rtl-axil:
	@echo "==> RTL PADAN AXI4-Lite (padan_axil, top KV260)"
	$(call need_cocotb)
	@cd tb/axil && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,rtl-axil,tb/axil/results.xml)

check-rtl-guard-safe:
	@echo "==> guard safe-state (bukti SAT Yosys)"
	@tb/guard/prove_safe.sh

# Build debug (-DDEBUG_FAULT) dan bukti bahwa build rilis tidak memuatnya.
test-rtl-debug:
	@echo "==> RTL PADAN build debug (injeksi fault DEBUG_FAULT)"
	$(call need_cocotb)
	@cd tb/debug && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,rtl-debug,tb/debug/results.xml)

check-rtl-release:
	@echo "==> build rilis tanpa DEBUG_FAULT (praproses + netlist Yosys)"
	@$(PYTHON) tb/debug/check_release.py

test-rtl-mutation:
	@echo "==> uji mutasi RTL PADAN"
	@$(PYTHON) tb/padan/mutate.py

check-rtl-infer:
	@echo "==> inferensi block RAM/DSP48E2 (Yosys synth_xilinx, UltraScale+)"
	@tb/padan/infer_check.sh

# Skrip KV260 (fpga/kv260, sw/kv260): diperiksa tanpa Vivado dan tanpa board.
# Lihat docs/fpga_howto.md bagian "Yang tidak tercakup CI".
test-kv260-scripts:
	@echo "==> skrip KV260 (Vivado stub + host melawan RTL lewat AXI)"
	$(call need_cocotb)
	@$(PYTHON) sw/kv260/gen_vectors.py --check
	@$(PYTHON) fpga/kv260/check_reports.py --self-test
	@$(PYTHON) tb/kv260/check_tcl.py
	@cd tb/kv260 && rm -f results.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,kv260-host,tb/kv260/results.xml)

# Laporan proyek: Markdown adalah sumbernya, .docx dibangkitkan pandoc dengan
# gaya dari reference.docx (A4, tabel bergaris). Pemeriksaan membandingkan teks
# polos .docx yang di-commit dengan .docx yang dibangun ulang (bukan byte zip),
# jadi tidak bergantung pada stempel waktu di dalam zip.
LAPORAN_MD   := docs/laporan_padan.md
LAPORAN_DOCX := docs/laporan/Laporan_PADAN.docx
LAPORAN_REF  := docs/laporan/reference.docx

laporan:
	pandoc $(LAPORAN_MD) --reference-doc=$(LAPORAN_REF) -o $(LAPORAN_DOCX)

check-laporan:
	@echo "==> laporan .docx sinkron dengan Markdown"
	@tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	  pandoc $(LAPORAN_MD) --reference-doc=$(LAPORAN_REF) -o "$$tmp/l.docx" && \
	  pandoc -t plain "$$tmp/l.docx" -o "$$tmp/baru.txt" && \
	  pandoc -t plain $(LAPORAN_DOCX) -o "$$tmp/repo.txt" && \
	  { diff -u "$$tmp/repo.txt" "$$tmp/baru.txt" > "$$tmp/diff" || \
	    { head -40 "$$tmp/diff"; echo "FAIL $(LAPORAN_DOCX) tidak sinkron dengan $(LAPORAN_MD); jalankan make laporan"; exit 1; }; } && \
	  echo "PASS $(LAPORAN_DOCX) sinkron dengan $(LAPORAN_MD)"

sky130-cells: $(SKY130_STAMP)

$(SKY130_STAMP):
	@echo "==> unduh model sel sky130_fd_sc_hd @ $(SKY130_SC_HD_REV)"
	rm -rf $(SKY130_SC_HD)
	git init -q $(SKY130_SC_HD)
	git -C $(SKY130_SC_HD) remote add origin $(SKY130_SC_HD_URL)
	git -C $(SKY130_SC_HD) sparse-checkout set --no-cone '/models/**' \
	  $(foreach c,$(GL_CELLS),'/cells/$(c)/*.v')
	git -C $(SKY130_SC_HD) fetch -q --depth 1 --filter=blob:none origin $(SKY130_SC_HD_REV)
	git -C $(SKY130_SC_HD) checkout -q FETCH_HEAD
	touch $@

clean:
	@for b in $(BASELINES); do \
	  rm -rf $(BASELINE_DIR)/$$b/test/{sim_build,results.xml,tb.vcd,__pycache__}; \
	done
	@rm -rf tb/padan/{sim_build,results.xml,tb.vcd,__pycache__}
	@rm -rf tb/avmm/{sim_build,results.xml,tb.vcd,__pycache__}
	@rm -rf tb/guard/{sim_build,results.xml,tb.vcd,__pycache__}
	@rm -rf tb/debug/{sim_build,results.xml,tb.vcd,__pycache__}
	@rm -rf tb/axil/{sim_build,results.xml,tb.vcd,__pycache__}
	@rm -rf tb/kv260/{sim_build,results.xml,__pycache__} sw/kv260/__pycache__
	@for a in $(AUDITS); do \
	  rm -rf tb/audit/$$a/{sim_build,results_rtl.xml,results_gl.xml,audit_*.json,tb.vcd,__pycache__}; \
	done
