from __future__ import annotations

import argparse
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Raspberry Pi boot acceptance for NeXa systemd deployment."
    )
    parser.add_argument("--system-dir", default="/etc/systemd/system")
    parser.add_argument("--allow-degraded", action="store_true")
    parser.add_argument("--show-journal", action="store_true")
    parser.add_argument("--journal-lines", type=int, default=40)
    args = parser.parse_args()

    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.system.deployment import SystemdBootAcceptanceService

    service = SystemdBootAcceptanceService()
    result = service.run(
        system_dir=args.system_dir,
        allow_degraded=args.allow_degraded,
        include_journal=args.show_journal,
        journal_lines=args.journal_lines,
    )

    print("NeXa boot acceptance")
    print(f"- result: {'PASS' if result.ok else 'FAIL'}")
    print(f"- strict premium mode: {result.strict_premium}")
    print(f"- system dir: {result.system_dir}")
    print(f"- runtime status: {result.runtime_status_path}")

    print("\nChecks:")
    for check in result.checks:
        state = "OK" if check.ok else "FAIL"
        print(f"[{state}] {check.key} -> {check.details}")
        if not check.ok and check.remediation:
            print(f"    fix: {check.remediation}")

    if result.unit_states:
        print("\nUnit states:")
        for unit_name, state in result.unit_states.items():
            active_state = state.get("ActiveState", "unknown")
            sub_state = state.get("SubState", "unknown")
            unit_file_state = state.get("UnitFileState", "unknown")
            print(
                f"- {unit_name}: ActiveState={active_state}, "
                f"SubState={sub_state}, UnitFileState={unit_file_state}"
            )

    if args.show_journal and result.journal_tails:
        print("\nJournal tail:")
        for unit_name, tail in result.journal_tails.items():
            print(f"\n--- {unit_name} ---")
            print(tail)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())