# Audit baseline #0590 (TinyTPU). Dari root: `make test-audit-tinytpu[-gl]`.
TOP        := tt_um_revenantx86_tinytpu
SRC_DIR     = $(REPO_ROOT)/rtl/baseline/tinytpu_0590/src
# Urutan sama dengan PROJECT_SOURCES di Makefile upstream
SRCS       := dff_mem.v input_control.v mac.v output_control.v systolic.v tinytpu_top.v \
              tt_um_revenantx86_tinytpu.v
GL_NETLIST  = $(REPO_ROOT)/rtl/baseline/tinytpu_0590/gl/tt_um_revenantx86_tinytpu.v
include ../audit.mk
