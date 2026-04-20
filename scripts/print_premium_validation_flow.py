from __future__ import annotations

import pathlib
import sys


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.runtime.validation import PremiumValidationFlowService

    service = PremiumValidationFlowService()
    flow = service.build_flow()

    print("NeXa premium validation flow")
    print(f"- benchmark ok: {flow.benchmark_ok}")
    print(f"- benchmark path: {flow.benchmark_path}")
    print(f"- benchmark window samples: {flow.benchmark_window_sample_count}")
    print(f"- latest turn: {flow.latest_turn_id or '-'}")
    print(f"- priority segments: {', '.join(flow.priority_segments) if flow.priority_segments else '-'}")

    if flow.failed_check_keys:
        print("- current failed checks:")
        for key in flow.failed_check_keys:
            print(f"  - {key}")

    print("\nStages:")
    for stage in flow.stages:
        print(f"\n[{stage.key}] {stage.title}")
        print(f"Goal: {stage.goal}")

        if stage.commands:
            print("Commands:")
            for command in stage.commands:
                sudo_marker = " [sudo]" if command.requires_sudo else ""
                print(f"- {command.label}{sudo_marker}")
                print(f"  {command.command}")

        if stage.scenarios:
            print("Scenarios:")
            for scenario in stage.scenarios:
                print(
                    f"- {scenario.title} [{scenario.key}] "
                    f"targets={','.join(scenario.target_segments)} min_turns={scenario.min_turns}"
                )
                print(f"  objective: {scenario.objective}")
                if scenario.prompts:
                    print("  prompts:")
                    for prompt in scenario.prompts:
                        print(f"    - {prompt}")
                if scenario.expected_signals:
                    print("  expected:")
                    for item in scenario.expected_signals:
                        print(f"    - {item}")

        if stage.notes:
            print("Notes:")
            for note in stage.notes:
                print(f"- {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())