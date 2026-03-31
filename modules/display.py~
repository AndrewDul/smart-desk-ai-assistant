from __future__ import annotations


class ConsoleDisplay:
    def show_block(self, title: str, lines: list[str] | None = None) -> None:
        print("\n" + "=" * 50)
        print(title)
        print("=" * 50)
        if lines:
            for line in lines:
                print(line)
        print()

    def show_status(self, state: dict, timer_status: dict) -> None:
        lines = [
            f"Assistant running: {state.get('assistant_running')}",
            f"Focus mode: {state.get('focus_mode')}",
            f"Break mode: {state.get('break_mode')}",
            f"Current timer: {state.get('current_timer')}",
            f"Timer running: {timer_status.get('running')}",
            f"Timer mode: {timer_status.get('mode')}",
            f"Remaining seconds: {timer_status.get('remaining_seconds')}",
        ]
        self.show_block("SMART DESK STATUS", lines)
