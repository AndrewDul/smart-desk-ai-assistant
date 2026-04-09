from __future__ import annotations

import traceback

from modules.core.assistant import CoreAssistant
from modules.shared.logging.logger import append_log

from .loop import build_main_loop_state_flags, run_assistant_loop
from .startup import (
    _log_runtime_mode,
    _perform_system_shutdown,
    _run_startup_sequence,
)


def main() -> None:
    assistant = CoreAssistant()
    _run_startup_sequence(assistant)
    _log_runtime_mode(assistant)

    gate_log_times: dict[str, float] = {}
    state_flags = build_main_loop_state_flags()
    fatal_error: Exception | None = None

    try:
        run_assistant_loop(
            assistant,
            state_flags=state_flags,
            gate_log_times=gate_log_times,
        )
    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")
        append_log("Assistant stopped with keyboard interrupt.")
    except Exception as error:
        fatal_error = error
        append_log(f"Fatal runtime error in main loop: {error}")
        append_log(traceback.format_exc())
        print("\nFatal runtime error in main loop:")
        traceback.print_exc()
    finally:
        shutdown_requested = assistant.shutdown_requested

        try:
            assistant.shutdown()
        except Exception as shutdown_error:
            append_log(f"Error during assistant shutdown: {shutdown_error}")
            append_log(traceback.format_exc())
            print("\nError during assistant shutdown:")
            traceback.print_exc()

        if shutdown_requested:
            _perform_system_shutdown(assistant)

        if fatal_error is not None:
            print("Assistant exited after handling a runtime error.")