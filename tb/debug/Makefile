# Test build debug (DEBUG_FAULT): injeksi fault terkendali host. Dari root: `make test-rtl-debug`.
SIM           ?= icarus
TOPLEVEL_LANG ?= verilog
REPO_ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
RTL           ?= $(REPO_ROOT)/rtl
SIM_BUILD     ?= sim_build/rtl
COCOTB_RESULTS_FILE ?= results.xml

VERILOG_SOURCES = $(REPO_ROOT)/tb/avmm/tb_avmm.v $(RTL)/padan_avmm.v $(RTL)/guard.v $(RTL)/decision.v \
                  $(RTL)/template_mem.v $(RTL)/mac_array.v $(RTL)/abft_check.v
COMPILE_ARGS   += -I$(RTL) -DDEBUG_FAULT
# Setiap injeksi adalah FAULT bagi guard; batas maksimum supaya ratusan injeksi
# tidak memicu zeroize/HALT. K tetap rilis (5).
COMPILE_ARGS   += -Ptb.FW=16 -Ptb.FAULT_MAX=65535
TOPLEVEL        = tb
MODULE          = test_debug
export PYTHONPATH := $(REPO_ROOT)/model:$(REPO_ROOT)/tb/padan:$(REPO_ROOT)/tb/avmm:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
