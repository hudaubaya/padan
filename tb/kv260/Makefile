# Test host KV260 (sw/kv260/padan_test.py) melawan RTL padan_axil lewat AXI4-Lite.
# Dari root: `make test-kv260-host`.
SIM           ?= icarus
TOPLEVEL_LANG ?= verilog
REPO_ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
RTL           ?= $(REPO_ROOT)/rtl
SIM_BUILD     ?= sim_build/rtl
COCOTB_RESULTS_FILE ?= results.xml

VERILOG_SOURCES = $(REPO_ROOT)/tb/axil/tb_axil.v $(RTL)/padan_axil.v $(RTL)/padan_avmm.v $(RTL)/guard.v \
                  $(RTL)/decision.v $(RTL)/template_mem.v $(RTL)/mac_array.v $(RTL)/abft_check.v
COMPILE_ARGS   += -I$(RTL)
TOPLEVEL        = tb
MODULE          = test_kv260_host
export PYTHONPATH := $(REPO_ROOT)/model:$(REPO_ROOT)/tb/padan:$(REPO_ROOT)/tb/avmm:$(REPO_ROOT)/tb/axil:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
