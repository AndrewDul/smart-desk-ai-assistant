from __future__ import annotations

import pathlib
import sys


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.runtime.validation import PremiumReleaseGateService

    service = PremiumReleaseGateService()
    result = service.run()

    print("NeXa premium release gate")
    print(f"- verdict: {result.verdict.upper()}")
    print(f"- benchmark path: {result.benchmark_path}")
    print(f"- benchmark window samples: {result.benchmark_window_sample_count}")
    print(f"- runtime status path: {result.runtime_status_path}")
    print(f"- lifecycle state: {result.lifecycle_state or '-'}")
    print(f"- startup mode: {result.startup_mode or '-'}")
    print(f"- primary ready: {result.primary_ready}")
    print(f"- premium ready: {result.premium_ready}")

    print("\nChecklist:")
    for item in result.checklist:
        state = "OK" if item.ok else "FAIL"
        print(f"[{state}] {item.key} ({item.source})")
        print(f"    details: {item.details}")
        if not item.ok and item.remediation:
            print(f"    fix: {item.remediation}")

    if result.failed_check_keys:
        print("\nFailed keys:")
        for key in result.failed_check_keys:
            print(f"- {key}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())