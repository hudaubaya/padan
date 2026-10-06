# Test skrip System Console (fpga/de10_nano/sysconsole/padan_test.tcl) melawan RTL.
# Dari root: `make test-fpga-scripts`.
SIM           ?= icarus
TOPLEVEL_LANG ?= verilog
REPO_ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
RTL           ?= $(REPO_ROOT)/rtl
SIM_BUILD     ?= sim_build/rtl
COCOTB_RESULTS_FILE ?= results.xml

VERILOG_SOURCES = $(REPO_ROOT)/tb/avmm/tb_avmm.v $(RTL)/padan_avmm.v $(RTL)/guard.v $(RTL)/decision.v \
                  $(RTL)/template_mem.v $(RTL)/mac_array.v $(RTL)/abft_check.v
COMPILE_ARGS   += -I$(RTL)
TOPLEVEL        = tb
MODULE          = test_sysconsole
export PYTHONPATH := $(REPO_ROOT)/model:$(REPO_ROOT)/tb/avmm:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
