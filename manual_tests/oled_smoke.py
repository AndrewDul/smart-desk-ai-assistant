from __future__ import annotations

import time

from modules.io.display import ConsoleDisplay
from modules.system.utils import append_log, load_settings


def main() -> None:
    settings = load_settings()
    display_cfg = settings.get("display", {})

    display = ConsoleDisplay(
        port=int(display_cfg.get("port", 1)),
        address=int(display_cfg.get("address", 60)),
        rotate=int(display_cfg.get("rotate", 0)),
        width=int(display_cfg.get("width", 128)),
        height=int(display_cfg.get("height", 64)),
    )

    append_log("Manual OLED smoke test started.")

    try:
        display.show_block(
            "DevDul",
            [
                "OLED smoke test",
                "stage 1",
            ],
            duration=2.0,
        )
        time.sleep(2.2)

        display.show_block(
            "STATUS",
            [
                "display online",
                "text rendering ok",
            ],
            duration=2.0,
        )
        time.sleep(2.2)

        display.show_block(
            "REMINDER",
            [
                "drink water",
                "in 10 minutes",
            ],
            duration=2.0,
        )
        time.sleep(2.2)

        display.clear_overlay()
        time.sleep(0.5)

        append_log("Manual OLED smoke test finished successfully.")
        print("OLED smoke test finished.")
    except KeyboardInterrupt:
        append_log("Manual OLED smoke test interrupted.")
        print("OLED smoke test interrupted.")
    finally:
        display.close()


if __name__ == "__main__":
    main()