from __future__ import annotations

import argparse
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback NeXa systemd units from a backup directory.")
    parser.add_argument("backup_dir")
    parser.add_argument("--system-dir", default="/etc/systemd/system")
    parser.add_argument("--no-enable", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--keep-extra-units", action="store_true")
    args = parser.parse_args()

    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.system.deployment import SystemdDeploymentService

    service = SystemdDeploymentService()
    result = service.rollback_units(
        system_dir=args.system_dir,
        backup_dir=args.backup_dir,
        enable=not args.no_enable,
        start=args.start,
        remove_units_not_in_backup=not args.keep_extra_units,
    )

    print(f"Rolled back systemd units in: {args.system_dir}")
    for unit_name in result.restored_unit_names:
        print(f"- restored: {unit_name}")
    for path in result.removed_unit_paths:
        print(f"- removed: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())