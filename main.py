from __future__ import annotations

from modules.assistant_logic import CoreAssistant


def main() -> None:
    assistant = CoreAssistant()
    assistant.boot()

    try:
        while True:
            print("\nListening for speech...")
            heard_text = assistant.voice_in.listen(
                timeout=assistant.voice_listen_timeout,
                debug=assistant.voice_debug,
            )

            if not heard_text:
                print("No speech recognized.")
                continue

            print(f"Heard: {heard_text}")

            should_continue = assistant.handle_command(heard_text)
            if not should_continue:
                break

    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")

    finally:
        assistant.shutdown()


if __name__ == "__main__":
    main()