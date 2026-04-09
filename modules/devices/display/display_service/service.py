from __future__ import annotations

import random
import threading
import time

from PIL import Image

from .device_factory import DisplayServiceDeviceFactory
from .eyes import DisplayServiceEyes
from .overlay import DisplayServiceOverlay
from .rendering import DisplayServiceRendering
from .utils import LOGGER, DisplayServiceUtils


class DisplayService(
    DisplayServiceDeviceFactory,
    DisplayServiceOverlay,
    DisplayServiceRendering,
    DisplayServiceEyes,
    DisplayServiceUtils,
):
    """
    Premium NeXa display service.

    Responsibilities:
    - initialize the physical display device
    - keep a lightweight render loop alive
    - render transient overlays and persistent idle animation
    - support both monochrome OLED and Waveshare 2-inch LCD
    - provide a stable display API for the runtime and flows
    """

    def __init__(
        self,
        driver: str = "ssd1306",
        interface: str = "i2c",
        port: int = 1,
        address: int = 0x3C,
        rotate: int = 0,
        width: int = 128,
        height: int = 64,
        spi_port: int = 0,
        spi_device: int = 0,
        gpio_dc: int = 25,
        gpio_rst: int = 27,
        gpio_light: int = 18,
    ) -> None:
        self.driver = str(driver or "ssd1306").strip().lower()
        self.interface = str(interface or "i2c").strip().lower()
        self.width = int(width)
        self.height = int(height)
        self.rotate = int(rotate)

        self.device = None
        self.device_width = self.width
        self.device_height = self.height
        self.is_color = self.driver == "waveshare_2inch"

        self.font_title = self._load_font(26 if self.is_color else 11)
        self.font_body = self._load_font(18 if self.is_color else 11)
        self.font_small = self._load_font(14 if self.is_color else 11)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._overlay_title = ""
        self._overlay_lines: list[str] = []
        self._overlay_until = 0.0
        self._overlay_style = "standard"

        self._gaze_pattern = [0, -10, 0, 10, 0, -5, 5, 0]
        self._gaze_index = 0
        self._next_gaze_change = time.time() + 2.0

        self._blink_frames = [1.0, 0.8, 0.45, 0.08, 0.45, 0.8, 1.0]
        self._blink_index = -1
        self._next_blink = time.time() + random.uniform(3.0, 5.0)

        self._last_frame_signature: bytes | None = None

        self.device = self._create_device(
            port=port,
            address=address,
            rotate=rotate,
            width=width,
            height=height,
            spi_port=spi_port,
            spi_device=spi_device,
            gpio_dc=gpio_dc,
            gpio_rst=gpio_rst,
            gpio_light=gpio_light,
        )

        LOGGER.info(
            "Display ready: driver=%s interface=%s size=%sx%s rotate=%s",
            self.driver,
            self.interface,
            self.device_width,
            self.device_height,
            self.rotate,
        )
        print(
            f"[DISPLAY] {self.driver} ready "
            f"({self.device_width}x{self.device_height}, rotate={self.rotate})"
        )

        self._thread = threading.Thread(
            target=self._render_loop,
            name="display-render-loop",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self.device is None:
            return

        try:
            if self.driver == "ssd1306":
                from luma.core.render import canvas

                with canvas(self.device) as draw:
                    draw.rectangle(self.device.bounding_box, outline="black", fill="black")
            elif self.driver == "waveshare_2inch":
                image = Image.new("RGB", (self.device_width, self.device_height), self._bg())
                self._show_image(image, force=True)
                module_exit = getattr(self.device, "module_exit", None)
                if callable(module_exit):
                    module_exit()
        except Exception as error:
            LOGGER.warning("Display close warning: %s", error)


__all__ = ["DisplayService"]