import os

from migen.fhdl.std import *
from migen.genlib.record import *
from migen.flow.actor import *
from migen.actorlib.fifo import SyncFIFO, AsyncFIFO
from migen.genlib.misc import WaitTimer

from misoclib.com.liteeth.common import *

class UDPStreamer(Module):
    def __init__(self, ip_address, udp_port, fifo_depth=1024):
        self.sink = sink = Sink([("data", 8)])
        self.source = source = Source(eth_udp_user_description(8))

        # # #

        self.submodules.fifo = fifo = SyncFIFO([("data", 8)], fifo_depth)
        self.comb += Record.connect(sink, fifo.sink)

        self.submodules.level = level = FlipFlop(max=fifo_depth+1)
        self.comb += level.d.eq(fifo.fifo.level)

        self.submodules.counter = counter = Counter(max=fifo_depth)

        self.submodules.flush_timer = WaitTimer(10000)
        flush = Signal()
        self.comb += [
            flush.eq((fifo.fifo.level > 0) & self.flush_timer.done)
        ]

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
          self.flush_timer.wait.eq(1),
            If((fifo.fifo.level >= 256) | flush,
                level.ce.eq(1),
                counter.reset.eq(1),
                NextState("SEND")
            )
        )
        fsm.act("SEND",
            source.stb.eq(fifo.source.stb),
            source.sop.eq(counter.value == 0),
            If(level.q == 0,
                source.eop.eq(1),
            ).Else(
                source.eop.eq(counter.value == (level.q-1)),
            ),
            source.src_port.eq(udp_port),
            source.dst_port.eq(udp_port),
            source.ip_address.eq(ip_address),
            If(level.q == 0,
                source.length.eq(1),
            ).Else(
                source.length.eq(level.q),
            ),
            source.data.eq(fifo.source.data),
            fifo.source.ack.eq(source.ack),
            If(source.stb & source.ack,
                counter.ce.eq(1),
                If(source.eop,
                    NextState("IDLE")
                )
            )
        )


class USBStreamer(Module):
    def __init__(self, platform, pads, debug_scope=False):
        self.sink = sink = Sink([("data", 8)])

        # # #

        self.clock_domains.cd_usb = ClockDomain()
        self.comb += [
          self.cd_usb.clk.eq(pads.ifclk),
          self.cd_usb.rst.eq(ResetSignal()) # XXX FIXME
        ]

        self.submodules.fifo = fifo = RenameClockDomains(AsyncFIFO([("data", 8)], 4),
                                          {"write": "sys", "read": "usb"})
        self.comb += Record.connect(sink, fifo.sink)

        self.specials += Instance("fx2_jpeg_streamer",
                                  # clk, rst
                                  i_rst=ResetSignal("usb"),
                                  i_clk=ClockSignal("usb"),

                                  # jpeg encoder interface
                                  i_sink_stb=fifo.source.stb,
                                  i_sink_data=fifo.source.data,
                                  o_sink_ack=fifo.source.ack,

                                  # cypress fx2 slave fifo interface
                                  io_fx2_data=pads.data,
                                  i_fx2_full_n=pads.flagb,
                                  i_fx2_empty_n=pads.flagc,
                                  o_fx2_addr=pads.addr,
                                  o_fx2_cs_n=pads.cs_n,
                                  o_fx2_wr_n=pads.wr_n,
                                  o_fx2_rd_n=pads.rd_n,
                                  o_fx2_oe_n=pads.oe_n,
                                  o_fx2_pktend_n=pads.pktend_n
        )

        # add VHDL sources
        platform.add_source_dir(os.path.join(platform.soc_ext_path, "hdl", "streamer", "vhdl"))

        # Add a debugging litescope to the interface.
        if debug_scope:
            from misoclib.tools.litescope.frontend.la import LiteScopeLA
            debug = (
                pads.flagb,
                pads.flagc,
                pads.addr,
                pads.cs_n,
                pads.wr_n,
                pads.rd_n,
                pads.oe_n,
                pads.pktend_n,
            )
            self.submodules.la = LiteScopeLA(debug, 4096)
