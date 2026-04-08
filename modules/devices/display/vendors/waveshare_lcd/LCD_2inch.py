from __future__ import annotations

import time
from PIL import Image

from .lcdconfig import RaspberryPi


class LCD_2inch(RaspberryPi):
    """
    Waveshare 2-inch LCD driver wrapper used by NeXa display service.
    """

    width = 240
    height = 320

    def __init__(
        self,
        *,
        spi_port: int = 0,
        spi_device: int = 0,
        spi_freq: int = 40_000_000,
        rst: int = 27,
        dc: int = 25,
        bl: int = 18,
        bl_freq: int = 1000,
    ) -> None:
        super().__init__(
            spi_port=spi_port,
            spi_device=spi_device,
            spi_freq=spi_freq,
            rst=rst,
            dc=dc,
            bl=bl,
            bl_freq=bl_freq,
        )

    def command(self, cmd: int) -> None:
        self.digital_write(self.DC_PIN, False)
        self.spi_writebyte([cmd])

    def data(self, val: int) -> None:
        self.digital_write(self.DC_PIN, True)
        self.spi_writebyte([val])

    def reset(self) -> None:
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.01)
        self.digital_write(self.RST_PIN, False)
        time.sleep(0.01)
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.01)

    def Init(self) -> None:
        self.module_init()
        self.reset()

        self.command(0x36)
        self.data(0x00)

        self.command(0x3A)
        self.data(0x05)

        self.command(0x21)

        self.command(0x2A)
        self.data(0x00)
        self.data(0x00)
        self.data(0x01)
        self.data(0x3F)

        self.command(0x2B)
        self.data(0x00)
        self.data(0x00)
        self.data(0x00)
        self.data(0xEF)

        self.command(0xB2)
        self.data(0x0C)
        self.data(0x0C)
        self.data(0x00)
        self.data(0x33)
        self.data(0x33)

        self.command(0xB7)
        self.data(0x35)

        self.command(0xBB)
        self.data(0x1F)

        self.command(0xC0)
        self.data(0x2C)

        self.command(0xC2)
        self.data(0x01)

        self.command(0xC3)
        self.data(0x12)

        self.command(0xC4)
        self.data(0x20)

        self.command(0xC6)
        self.data(0x0F)

        self.command(0xD0)
        self.data(0xA4)
        self.data(0xA1)

        self.command(0xE0)
        self.data(0xD0)
        self.data(0x08)
        self.data(0x11)
        self.data(0x08)
        self.data(0x0C)
        self.data(0x15)
        self.data(0x39)
        self.data(0x33)
        self.data(0x50)
        self.data(0x36)
        self.data(0x13)
        self.data(0x14)
        self.data(0x29)
        self.data(0x2D)

        self.command(0xE1)
        self.data(0xD0)
        self.data(0x08)
        self.data(0x10)
        self.data(0x08)
        self.data(0x06)
        self.data(0x06)
        self.data(0x39)
        self.data(0x44)
        self.data(0x51)
        self.data(0x0B)
        self.data(0x16)
        self.data(0x14)
        self.data(0x2F)
        self.data(0x31)
        self.command(0x21)

        self.command(0x11)
        self.command(0x29)

    def SetWindows(self, xstart: int, ystart: int, xend: int, yend: int) -> None:
        self.command(0x2A)
        self.data(xstart >> 8)
        self.data(xstart & 0xFF)
        self.data(xend >> 8)
        self.data((xend - 1) & 0xFF)

        self.command(0x2B)
        self.data(ystart >> 8)
        self.data(ystart & 0xFF)
        self.data(yend >> 8)
        self.data((yend - 1) & 0xFF)

        self.command(0x2C)

    def ShowImage(self, image: Image.Image, Xstart: int = 0, Ystart: int = 0) -> None:
        del Xstart, Ystart

        imwidth, imheight = image.size

        if imwidth == self.height and imheight == self.width:
            img = self.np.asarray(image)
            pix = self.np.zeros((self.width, self.height, 2), dtype=self.np.uint8)
            pix[..., [0]] = self.np.add(
                self.np.bitwise_and(img[..., [0]], 0xF8),
                self.np.right_shift(img[..., [1]], 5),
            )
            pix[..., [1]] = self.np.add(
                self.np.bitwise_and(self.np.left_shift(img[..., [1]], 3), 0xE0),
                self.np.right_shift(img[..., [2]], 3),
            )
            pix = pix.flatten().tolist()

            self.command(0x36)
            self.data(0x70)
            self.SetWindows(0, 0, self.height, self.width)
            self.digital_write(self.DC_PIN, True)
            for index in range(0, len(pix), 4096):
                self.spi_writebyte(pix[index:index + 4096])
            return

        img = self.np.asarray(image)
        pix = self.np.zeros((imheight, imwidth, 2), dtype=self.np.uint8)

        pix[..., [0]] = self.np.add(
            self.np.bitwise_and(img[..., [0]], 0xF8),
            self.np.right_shift(img[..., [1]], 5),
        )
        pix[..., [1]] = self.np.add(
            self.np.bitwise_and(self.np.left_shift(img[..., [1]], 3), 0xE0),
            self.np.right_shift(img[..., [2]], 3),
        )

        pix = pix.flatten().tolist()

        self.command(0x36)
        self.data(0x00)
        self.SetWindows(0, 0, self.width, self.height)
        self.digital_write(self.DC_PIN, True)
        for index in range(0, len(pix), 4096):
            self.spi_writebyte(pix[index:index + 4096])

    def clear(self) -> None:
        buffer_data = [0xFF] * (self.width * self.height * 2)
        self.SetWindows(0, 0, self.height, self.width)
        self.digital_write(self.DC_PIN, True)
        for index in range(0, len(buffer_data), 4096):
            self.spi_writebyte(buffer_data[index:index + 4096])