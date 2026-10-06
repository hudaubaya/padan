"""Utilitas bersama test audit baseline (tb/audit/*)."""

import json
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

VIEW = os.environ.get("AUDIT_VIEW", "rtl")      # "rtl" atau "gl" (tb/audit/audit.mk)


async def start(dut, period_ns, reset_cycles=5, ui_in=0, uio_in=0):
    """Mulai clock lalu reset (lihat reset())."""
    cocotb.start_soon(Clock(dut.clk, period_ns, units="ns").start())
    await reset(dut, reset_cycles, ui_in, uio_in)


async def reset(dut, cycles=5, ui_in=0, uio_in=0):
    """rst_n=0 selama `cycles` clock (clock berjalan), dilepas di sisi turun.

    Input diubah hanya di sisi turun, jadi selalu stabil di sisi naik.
    """
    dut.ena.value = 1
    dut.ui_in.value = ui_in
    dut.uio_in.value = uio_in
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, cycles)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


class Record:
    """Kumpulkan angka hasil audit ke audit_<nama>_<view>.json (dipakai dokumen)."""

    def __init__(self, name):
        self.path = f"audit_{name}_{VIEW}.json"
        try:
            with open(self.path) as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def put(self, key, value):
        self.data[key] = value
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
