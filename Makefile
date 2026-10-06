# Makefile utama PADAN — menjalankan seluruh pemeriksaan dari root repo.
#
#   make test                      semua pemeriksaan (integritas + test baseline)
#   make test-baseline             test upstream ketiga baseline TT07
#   make test-baseline-<nama>      satu baseline, mis. test-baseline-tinytpu_0590
#   make check-baseline            baseline tidak berubah dari salinan upstream
#   make clean                     hapus artefak simulasi
#
# Test baseline dijalankan dengan Makefile upstream masing-masing (tidak
# diubah). Makefile upstream memakai $(PWD), jadi kita `cd` dulu, bukan
# `make -C`. cocotb 1.8 tidak selalu keluar non-zero saat test gagal, jadi
# results.xml diperiksa secara eksplisit.

SHELL        := /bin/bash
SIM          ?= icarus
BASELINE_DIR := rtl/baseline
BASELINES    := tinytpu_0590 iterative_mac_0040 vector_cim_0642

# $(call check_results,<nama>,<path results.xml>)
define check_results
	@r=$(2); \
	  test -f $$r || { echo "FAIL $(1): $$r tidak ada"; exit 1; }; \
	  grep -q '<testcase' $$r || { echo "FAIL $(1): tidak ada testcase di $$r"; exit 1; }; \
	  ! grep -qE '<(failure|error)' $$r || { echo "FAIL $(1): ada test gagal, lihat $$r"; exit 1; }; \
	  echo "PASS $(1) ($$(grep -c '<testcase' $$r) testcase)"
endef

.PHONY: help test test-baseline check-baseline clean \
        $(addprefix test-baseline-,$(BASELINES))

help:
	@sed -n '3,7p' $(firstword $(MAKEFILE_LIST)) | sed 's/^# \{0,1\}//'

test: check-baseline test-baseline

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

clean:
	@for b in $(BASELINES); do \
	  rm -rf $(BASELINE_DIR)/$$b/test/{sim_build,results.xml,tb.vcd,__pycache__}; \
	done
