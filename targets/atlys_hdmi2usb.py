from targets.atlys_base import *

from hdl import dvisampler
from hdl import framebuffer

from hdl.encoder import EncoderReader, Encoder
from hdl.streamer import USBStreamer

class VideomixerSoC(BaseSoC):
    csr_map = {
        "fb":                  19,
        "dvisampler":          20,
        "dvisampler_edid_mem": 21,
    }
    csr_map.update(BaseSoC.csr_map)

    interrupt_map = {
        "dvisampler": 3,
    }
    interrupt_map.update(BaseSoC.interrupt_map)

    def __init__(self, platform, **kwargs):
        BaseSoC.__init__(self, platform, **kwargs)
        self.submodules.dvisampler = dvisampler.DVISampler(platform.request("dvi_in", 1),
                                                           self.sdram.crossbar.get_master(),
                                                           fifo_depth=512)
        self.submodules.fb = framebuffer.Framebuffer(None, platform.request("dvi_out"),
                                                     self.sdram.crossbar.get_master())
        platform.add_platform_command("""PIN "dviout_pix_bufg.O" CLOCK_DEDICATED_ROUTE = FALSE;""")
        platform.add_platform_command("""
NET "{pix_clk}" TNM_NET = "GRPpix_clk";
TIMESPEC "TSise_sucks7" = FROM "GRPpix_clk" TO "GRPsys_clk" TIG;
TIMESPEC "TSise_sucks8" = FROM "GRPsys_clk" TO "GRPpix_clk" TIG;
""", pix_clk=self.fb.driver.clocking.cd_pix.clk)


class HDMI2USBSoC(VideomixerSoC):
    csr_map = {
        "encoder_reader": 22,
        "encoder":        23,
        "la":             24,
    }
    csr_map.update(VideomixerSoC.csr_map)
    mem_map = {
        "encoder": 0x50000000,  # (shadow @0xd0000000)
    }
    mem_map.update(VideomixerSoC.mem_map)

    def __init__(self, platform, **kwargs):
        VideomixerSoC.__init__(self, platform, **kwargs)

        debug_scope = ("fx2",)

        self.submodules.encoder_reader = EncoderReader(self.sdram.crossbar.get_master())
        self.submodules.encoder = Encoder(platform)
        self.submodules.usb_streamer = USBStreamer(platform, platform.request("fx2"), debug_scope=("fx2" in debug_scope))

        if debug_scope:
            from misoclib.tools.litescope.core.port import LiteScopeTerm
            if "fx2" in debug_scope:
                la = self.usb_streamer.la
                la.trigger.add_port(LiteScopeTerm(la.dw))

        self.comb += [
            platform.request("user_led", 0).eq(self.encoder_reader.source.stb),
            platform.request("user_led", 1).eq(self.encoder_reader.source.ack),
            Record.connect(self.encoder_reader.source, self.encoder.sink),
            Record.connect(self.encoder.source, self.usb_streamer.sink)
        ]
        self.add_wb_slave(mem_decoder(self.mem_map["encoder"]), self.encoder.bus)
        self.add_memory_region("encoder", self.mem_map["encoder"]+self.shadow_base, 0x2000)

        platform.add_platform_command("""
NET "{usb_clk}" TNM_NET = "GRPusb_clk";
TIMESPEC "TSise_sucks9" = FROM "GRPusb_clk" TO "GRPsys_clk" TIG;
TIMESPEC "TSise_sucks10" = FROM "GRPsys_clk" TO "GRPusb_clk" TIG;
""", usb_clk=platform.lookup_request("fx2").ifclk)

    def do_exit(self, vns):
        print(vns)
        self.usb_streamer.la.export(vns, "test/la.csv")

default_subtarget = HDMI2USBSoC
