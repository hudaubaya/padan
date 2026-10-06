# Test padan_avmm (decision + antarmuka Avalon-MM). Dari root: `make test-rtl-avmm`.
SIM           ?= icarus
TOPLEVEL_LANG ?= verilog
REPO_ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
RTL           ?= $(REPO_ROOT)/rtl
SIM_BUILD     ?= sim_build/rtl
COCOTB_RESULTS_FILE ?= results.xml

VERILOG_SOURCES = $(REPO_ROOT)/tb/avmm/tb_avmm.v $(RTL)/padan_avmm.v $(RTL)/decision.v \
                  $(RTL)/template_mem.v $(RTL)/mac_array.v $(RTL)/abft_check.v
COMPILE_ARGS   += -I$(RTL)
ifeq ($(WAVES),1)
COMPILE_ARGS   += -DWAVES
endif
TOPLEVEL        = tb
MODULE          = test_avmm
export PYTHONPATH := $(REPO_ROOT)/model:$(REPO_ROOT)/tb/padan:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
