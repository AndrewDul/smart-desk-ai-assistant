from __future__ import annotations

from modules.assistant_logic import CoreAssistant


def main() -> None:
    assistant = CoreAssistant()
    assistant.boot()

    try:
        while True:
            print("\nListening for command...")
            command = assistant.voice_in.listen(
                timeout=assistant.voice_listen_timeout,
                debug=assistant.voice_debug,
            )

            if not command:
                print("No valid voice command recognized.")
                continue

            print(f"Voice command: {command}")

            should_continue = assistant.handle_command(command)
            if not should_continue:
                break

    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")

    finally:
        assistant.shutdown()


if __name__ == "__main__":
    main()