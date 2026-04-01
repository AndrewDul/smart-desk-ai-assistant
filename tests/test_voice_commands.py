from modules.voice_in import VoiceInput

DEVICE_INDEX = 2
USE_GRAMMAR = False


def main() -> None:
    VoiceInput.list_audio_devices()

    voice = VoiceInput(
        device=DEVICE_INDEX,
        use_grammar=USE_GRAMMAR,
    )

    print()
    print(f"Using input device: {voice.device_name}")
    print(f"Using sample rate: {voice.sample_rate}")
    print("Say one command now...")
    print("Examples:")
    print("- show help")
    print("- show status")
    print("- show memory")
    print("- show reminders")
    print("- stop timer")
    print("- exit assistant")
    print()

    command = voice.listen_once(timeout=8, debug=True)

    if command:
        print(f"Recognized command: {command}")
    else:
        print("No valid command recognized.")


if __name__ == "__main__":
    main()
