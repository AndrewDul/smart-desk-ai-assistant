from __future__ import annotations

from modules.assistant_logic import CoreAssistant


def main() -> None:
    assistant = CoreAssistant()
    assistant.boot()

    try:
        while True:
            command = assistant.voice_in.listen()

            if not command:
                continue

            should_continue = assistant.handle_command(command)
            if not should_continue:
                break

    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")

    finally:
        assistant.shutdown()


if __name__ == "__main__":
    main()
