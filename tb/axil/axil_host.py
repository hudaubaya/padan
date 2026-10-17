"""Master AXI4-Lite untuk test cocotb padan_axil (tb/axil, tb/kv260).

Sinyal didorong dan diperiksa pada sisi turun clock (ReadOnly); handshake
terjadi pada sisi naik berikutnya. READY/VALID slave hanya bergantung pada
state, jadi nilainya stabil di antara dua sisi. Alamat yang diterima metode di sini adalah
alamat WORD padan_avmm; alamat byte AXI = 4 x word.

Monitor protokol (start_monitor) memeriksa aturan AXI di sisi slave: begitu
BVALID/RVALID naik, sinyal itu dan payload-nya (BRESP, RDATA, RRESP) harus tetap
sampai handshake terjadi.
"""

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

OKAY, SLVERR = 0, 2
# Batas tunggu handshake: zeroize boot ~290 siklus, MATCH 153 siklus.
MAX_WAIT = 2000


class AxilHost:
    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.u.s_axi_aclk
        for s in ("awvalid", "wvalid", "bready", "arvalid", "rready", "awaddr", "araddr", "wdata"):
            getattr(dut, s).value = 0
        dut.wstrb.value = 0xF
        dut.tamper_n.value = 1
        self.violations = []

    async def reset(self):
        self.dut.rst_n.value = 0
        await Timer(30, "ns")
        self.dut.rst_n.value = 1
        await FallingEdge(self.clk)

    async def _cycles(self, n):
        for _ in range(n):
            await FallingEdge(self.clk)

    async def _handshake(self, sig):
        """Dipanggil pada sisi turun. Tunggu sampai `sig` = 1 tepat sebelum sisi
        naik (READY/VALID slave hanya bergantung pada state, stabil antar sisi),
        lalu lewati sisi naik itu: handshake terjadi di sana. Kembali pada sisi
        turun berikutnya."""
        for _ in range(MAX_WAIT):
            await ReadOnly()
            hit = sig.value == 1
            await RisingEdge(self.clk)
            await FallingEdge(self.clk)
            if hit:
                return
        raise AssertionError(f"{sig._name} tidak naik dalam {MAX_WAIT} siklus")

    async def _send(self, delay, valid, ready, payload):
        """Satu kanal master: tunggu `delay` siklus, naikkan VALID dengan payload,
        tahan sampai handshake, lalu turunkan."""
        await self._cycles(delay)
        for sig, v in payload:
            sig.value = v
        valid.value = 1
        await self._handshake(ready)
        valid.value = 0

    async def _recv(self, delay, valid, ready, fields):
        """Kanal respons: tunggu VALID, tahan READY rendah `delay` siklus, lalu
        terima. Mengembalikan nilai `fields` pada siklus handshake."""
        for _ in range(MAX_WAIT):
            await ReadOnly()
            if valid.value == 1:
                break
            await RisingEdge(self.clk)
            await FallingEdge(self.clk)
        else:
            raise AssertionError(f"{valid._name} tidak naik dalam {MAX_WAIT} siklus")
        await RisingEdge(self.clk)
        await FallingEdge(self.clk)
        await self._cycles(delay)
        ready.value = 1
        for _ in range(MAX_WAIT):
            await ReadOnly()
            if valid.value == 1:
                got = [f.value.integer for f in fields]
                await RisingEdge(self.clk)
                await FallingEdge(self.clk)
                break
            await RisingEdge(self.clk)
            await FallingEdge(self.clk)
        else:
            raise AssertionError(f"{valid._name} turun sebelum handshake ({ready._name} = 1)")
        ready.value = 0
        return got

    async def write(self, word, data, strb=0xF, aw_delay=0, w_delay=0, b_delay=0):
        """Tulis AXI4-Lite; mengembalikan BRESP."""
        d = self.dut
        await FallingEdge(self.clk)
        aw = cocotb.start_soon(self._send(aw_delay, d.awvalid, d.awready, [(d.awaddr, (word * 4) & 0xFFF)]))
        w = cocotb.start_soon(self._send(w_delay, d.wvalid, d.wready,
                                         [(d.wdata, data & 0xFFFFFFFF), (d.wstrb, strb)]))
        b = cocotb.start_soon(self._recv(b_delay, d.bvalid, d.bready, [d.bresp]))
        await aw
        await w
        (bresp,) = await b
        return bresp

    async def read(self, word, r_delay=0, ar_delay=0):
        """Baca AXI4-Lite; mengembalikan (RDATA, RRESP)."""
        d = self.dut
        await FallingEdge(self.clk)
        ar = cocotb.start_soon(self._send(ar_delay, d.arvalid, d.arready, [(d.araddr, (word * 4) & 0xFFF)]))
        r = cocotb.start_soon(self._recv(r_delay, d.rvalid, d.rready, [d.rdata, d.rresp]))
        await ar
        data, rresp = await r
        return data, rresp

    def start_monitor(self):
        return cocotb.start_soon(self._monitor())

    async def _monitor(self):
        d = self.dut
        prev = None
        while True:
            await FallingEdge(self.clk)          # nilai yang berlaku untuk sisi naik berikutnya
            await ReadOnly()
            cur = {
                "b": (int(d.bvalid.value), int(d.bready.value), int(d.bresp.value)),
                "r": (int(d.rvalid.value), int(d.rready.value), int(d.rdata.value), int(d.rresp.value)),
            }
            if prev is not None:
                for ch in ("b", "r"):
                    pv = prev[ch]
                    if pv[0] == 1 and pv[1] == 0:            # VALID tanpa READY: harus stabil
                        cv = cur[ch]
                        if cv[0] != 1 or cv[2:] != pv[2:]:
                            self.violations.append((ch, pv, cv))
            prev = cur
