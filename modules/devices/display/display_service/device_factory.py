from __future__ import annotations


class DisplayServiceDeviceFactory:
    """Display device creation helpers."""

    driver: str
    interface: str
    device_width: int
    device_height: int

    def _create_device(
        self,
        *,
        port: int,
        address: int,
        rotate: int,
        width: int,
        height: int,
        spi_port: int,
        spi_device: int,
        gpio_dc: int,
        gpio_rst: int,
        gpio_light: int,
    ):
        if self.driver == "ssd1306":
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306

            serial = i2c(port=port, address=address)
            device = ssd1306(serial, rotate=rotate, width=width, height=height)
            self.device_width = int(width)
            self.device_height = int(height)
            return device

        if self.driver == "waveshare_2inch":
            from modules.devices.display.vendors.waveshare_lcd.LCD_2inch import LCD_2inch

            device = LCD_2inch(
                spi_port=spi_port,
                spi_device=spi_device,
                rst=gpio_rst,
                dc=gpio_dc,
                bl=gpio_light,
            )
            device.Init()
            device.clear()

            if hasattr(device, "bl_DutyCycle"):
                device.bl_DutyCycle(70)

            # The Waveshare driver renders in panel coordinates,
            # while the PIL composition is prepared in the visible orientation.
            self.device_width = int(device.height)
            self.device_height = int(device.width)
            return device

        raise ValueError(f"Unsupported display driver: {self.driver}")


__all__ = ["DisplayServiceDeviceFactory"]