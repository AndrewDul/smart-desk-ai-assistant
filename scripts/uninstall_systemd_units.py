from __future__ import annotations

import argparse
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove NeXa systemd units from the system directory.")
    parser.add_argument("--system-dir", default="/etc/systemd/system")
    parser.add_argument("--no-disable", action="store_true")
    parser.add_argument("--no-stop", action="store_true")
    args = parser.parse_args()

    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.system.deployment import SystemdDeploymentService

    service = SystemdDeploymentService()
    result = service.uninstall_units(
        system_dir=args.system_dir,
        disable=not args.no_disable,
        stop=not args.no_stop,
    )

    print(f"Removed systemd units from: {args.system_dir}")
    for path in result.removed_unit_paths:
        print(f"- removed: {path}")
    for unit_name in result.missing_unit_names:
        print(f"- missing: {unit_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())