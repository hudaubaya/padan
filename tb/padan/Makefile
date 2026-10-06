# Test RTL PADAN. Dari root: `make test-rtl` (dan `make test-rtl-mutation`).
#
# RTL=<dir> menjalankan test terhadap salinan RTL lain (uji mutasi).
SIM           ?= icarus
TOPLEVEL_LANG ?= verilog
REPO_ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
RTL           ?= $(REPO_ROOT)/rtl
SIM_BUILD     ?= sim_build/rtl
COCOTB_RESULTS_FILE ?= results.xml

VERILOG_SOURCES = $(REPO_ROOT)/tb/padan/tb_padan.v \
                  $(RTL)/template_mem.v $(RTL)/mac_array.v $(RTL)/abft_check.v
COMPILE_ARGS   += -I$(RTL)
ifeq ($(WAVES),1)
COMPILE_ARGS   += -DWAVES
endif
TOPLEVEL        = tb
MODULE          = test_padan
export PYTHONPATH := $(REPO_ROOT)/model:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
