from __future__ import annotations

from modules.runtime.contracts import DisplayBackend, RuntimeBackendStatus

from .fallbacks import NullDisplay


class RuntimeBuilderDisplayMixin:
    """
    Build the display backend with explicit fallback handling.
    """

    def _build_display(
        self,
        config: dict[str, object],
    ) -> tuple[DisplayBackend, RuntimeBackendStatus]:
        if not bool(config.get("enabled", True)):
            return (
                NullDisplay(),
                RuntimeBackendStatus(
                    component="display",
                    ok=True,
                    selected_backend="null_display",
                    detail="Display disabled in config. Using null display backend.",
                ),
            )

        try:
            display_class = self._import_symbol(
                "modules.devices.display.display_service",
                "DisplayService",
            )
            backend = display_class(
                driver=str(config.get("driver", "ssd1306")),
                interface=str(config.get("interface", "i2c")),
                port=int(config.get("port", 1)),
                address=int(config.get("address", 0x3C)),
                rotate=int(config.get("rotate", 0)),
                width=int(config.get("width", 128)),
                height=int(config.get("height", 64)),
                spi_port=int(config.get("spi_port", 0)),
                spi_device=int(config.get("spi_device", 0)),
                gpio_dc=int(config.get("gpio_dc", 25)),
                gpio_rst=int(config.get("gpio_rst", 27)),
                gpio_light=int(config.get("gpio_light", 18)),
            )
            return (
                backend,
                RuntimeBackendStatus(
                    component="display",
                    ok=True,
                    selected_backend=str(config.get("driver", "ssd1306")),
                    detail="Display backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullDisplay(),
                RuntimeBackendStatus(
                    component="display",
                    ok=False,
                    selected_backend="null_display",
                    detail=f"Display backend failed. Using null display. Error: {error}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderDisplayMixin"]