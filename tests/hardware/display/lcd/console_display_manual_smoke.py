from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.io.display import ConsoleDisplay
from modules.system.utils import append_log, load_settings


def build_display() -> ConsoleDisplay:
    settings = load_settings()
    display_cfg = settings.get("display", {})

    return ConsoleDisplay(
        driver=str(display_cfg.get("driver", "ssd1306")),
        interface=str(display_cfg.get("interface", "i2c")),
        port=int(display_cfg.get("port", 1)),
        address=int(display_cfg.get("address", 60)),
        rotate=int(display_cfg.get("rotate", 0)),
        width=int(display_cfg.get("width", 128)),
        height=int(display_cfg.get("height", 64)),
        spi_port=int(display_cfg.get("spi_port", 0)),
        spi_device=int(display_cfg.get("spi_device", 0)),
        gpio_dc=int(display_cfg.get("gpio_dc", 25)),
        gpio_rst=int(display_cfg.get("gpio_rst", 27)),
        gpio_light=int(display_cfg.get("gpio_light", 18)),
    )


def main() -> None:
    append_log("ConsoleDisplay manual smoke test started.")
    print("[DISPLAY SMOKE] Starting ConsoleDisplay manual smoke test...")

    display = build_display()

    try:
        print("[DISPLAY SMOKE] Showing overlay 1...")
        display.show_block(
            "Smart Desk AI",
            [
                "ConsoleDisplay test",
                "overlay rendering ok",
                "wrapper path check",
            ],
            duration=3.0,
        )
        time.sleep(3.2)

        print("[DISPLAY SMOKE] Showing overlay 2...")
        display.show_block(
            "STATUS",
            [
                "display online",
                "text rendering ok",
                "eyes mode next",
            ],
            duration=3.0,
        )
        time.sleep(3.2)

        print("[DISPLAY SMOKE] Clearing overlay and returning to idle eyes...")
        display.clear_overlay()
        time.sleep(5.0)

        append_log("ConsoleDisplay manual smoke test finished successfully.")
        print("[DISPLAY SMOKE] Finished successfully.")
    except KeyboardInterrupt:
        append_log("ConsoleDisplay manual smoke test interrupted.")
        print("[DISPLAY SMOKE] Interrupted by user.")
    finally:
        display.close()


if __name__ == "__main__":
    main()