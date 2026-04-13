from __future__ import annotations

import pathlib
import sys


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.system.deployment import SystemdDeploymentService

    service = SystemdDeploymentService()
    result = service.write_units()

    print(f"Rendered systemd units into: {result.output_dir}")
    for unit_name, unit_path in sorted(result.unit_paths.items()):
        print(f"- {unit_name}: {unit_path}")

    print("\nRemaining scope after deployment artifacts:")
    for item in service.describe_remaining_scope():
        print(f"- {item}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())