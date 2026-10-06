# Makefile utama PADAN — menjalankan seluruh pemeriksaan dari root repo.
#
#   make test                      semua pemeriksaan (integritas, model, baseline, audit)
#   make test-baseline             test upstream ketiga baseline TT07
#   make test-baseline-<nama>      satu baseline, mis. test-baseline-tinytpu_0590
#   make check-baseline            baseline tidak berubah dari salinan upstream
#   make test-model                self-test model Python (model/)
#   make test-audit                audit baseline RTL + netlist (docs/baseline_audit.md)
#   make test-audit-<a>[-gl]       satu audit: tinytpu, iterative_mac, vector_cim
#   make test-audit-vector_cim-formal  bukti SAT adder CLA #0642 (butuh yosys)
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
MODELS       := tinytpu iterative_mac vector_cim

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

# $(call check_results,<nama>,<path results.xml>)
define check_results
	@r=$(2); \
	  test -f $$r || { echo "FAIL $(1): $$r tidak ada"; exit 1; }; \
	  grep -q '<testcase' $$r || { echo "FAIL $(1): tidak ada testcase di $$r"; exit 1; }; \
	  ! grep -qE '<(failure|error)' $$r || { echo "FAIL $(1): ada test gagal, lihat $$r"; exit 1; }; \
	  echo "PASS $(1) ($$(grep -c '<testcase' $$r) testcase)"
endef

.PHONY: help test test-baseline check-baseline test-model test-audit sky130-cells clean \
        test-audit-vector_cim-formal \
        $(addprefix test-baseline-,$(BASELINES)) \
        $(addprefix test-audit-,$(AUDITS)) $(addsuffix -gl,$(addprefix test-audit-,$(AUDITS)))

help:
	@sed -n '3,12p' $(firstword $(MAKEFILE_LIST)) | sed 's/^# \{0,1\}//'

test: check-baseline test-model test-baseline test-audit

test-baseline: $(addprefix test-baseline-,$(BASELINES))

$(addprefix test-baseline-,$(BASELINES)): test-baseline-%:
	@echo "==> baseline $*"
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

# Audit baseline apa adanya terhadap model Python. Cacat terkonfirmasi ditandai
# expect_fail di test (lihat docs/baseline_audit.md), jadi suite hijau selama
# perilaku baseline sama dengan yang didokumentasikan.
test-audit: $(addprefix test-audit-,$(AUDITS)) $(addsuffix -gl,$(addprefix test-audit-,$(AUDITS))) \
            test-audit-vector_cim-formal

$(addprefix test-audit-,$(AUDITS)): test-audit-%:
	@echo "==> audit $* (RTL)"
	@cd tb/audit/$* && rm -f results_rtl.xml && $(MAKE) --no-print-directory SIM=$(SIM)
	$(call check_results,audit-$*,tb/audit/$*/results_rtl.xml)

$(addsuffix -gl,$(addprefix test-audit-,$(AUDITS))): test-audit-%-gl: $(SKY130_STAMP)
	@echo "==> audit $* (netlist gate-level tapeout)"
	@cd tb/audit/$* && rm -f results_gl.xml && \
	  $(MAKE) --no-print-directory SIM=$(SIM) GATES=yes SKY130_SC_HD=$(SKY130_SC_HD)
	$(call check_results,audit-$*-gl,tb/audit/$*/results_gl.xml)

test-audit-vector_cim-formal:
	@echo "==> audit vector_cim (bukti SAT adder CLA, Yosys)"
	@tb/audit/vector_cim/cla_prove.sh

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
	@for a in $(AUDITS); do \
	  rm -rf tb/audit/$$a/{sim_build,results_rtl.xml,results_gl.xml,audit_*.json,tb.vcd,__pycache__}; \
	done
