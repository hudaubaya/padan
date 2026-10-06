# Bagian bersama Makefile audit baseline (docs/baseline_audit.md).
#
# Makefile pemanggil menetapkan TOP, SRC_DIR, SRCS, GL_NETLIST lalu meng-include
# file ini. GATES=yes menyimulasikan netlist tapeout (gl/) dengan model sel
# sky130_fd_sc_hd; tanpa GATES, sumber RTL baseline apa adanya.
SIM           ?= icarus
TOPLEVEL_LANG ?= verilog
REPO_ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
SKY130_SC_HD  ?= $(REPO_ROOT)/.cache/sky130_fd_sc_hd

ifneq ($(GATES),yes)
SIM_BUILD            = sim_build/rtl
COCOTB_RESULTS_FILE ?= results_rtl.xml
VERILOG_SOURCES     += $(addprefix $(SRC_DIR)/,$(SRCS))
COMPILE_ARGS        += -I$(SRC_DIR)
export AUDIT_VIEW   := rtl
else
SIM_BUILD            = sim_build/gl
COCOTB_RESULTS_FILE ?= results_gl.xml
COMPILE_ARGS        += -DGL_TEST -DFUNCTIONAL -DUSE_POWER_PINS -DSIM -DUNIT_DELAY=\#1
COMPILE_ARGS        += -grelative-include
GL_CELL_SOURCES     := $(shell grep -oE '^ *sky130_fd_sc_hd__[a-z0-9]+_[0-9]+' $(GL_NETLIST) | tr -d ' ' | sort -u | \
                         sed -E 's|^sky130_fd_sc_hd__(.*)_([0-9]+)$$|$(SKY130_SC_HD)/cells/\1/sky130_fd_sc_hd__\1_\2.v|')
VERILOG_SOURCES     += $(REPO_ROOT)/tb/common/gl_stubs.v $(GL_CELL_SOURCES) $(GL_NETLIST)
export AUDIT_VIEW   := gl
endif

ifeq ($(WAVES),1)
COMPILE_ARGS += -DWAVES
endif

VERILOG_SOURCES += $(REPO_ROOT)/tb/common/tb_tt.v
COMPILE_ARGS    += -DTT_TOP=$(TOP)
TOPLEVEL         = tb
MODULE           = test
export PYTHONPATH := $(REPO_ROOT)/model:$(REPO_ROOT)/tb/common:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
