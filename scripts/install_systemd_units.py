from __future__ import annotations

import argparse
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Install NeXa systemd units.")
    parser.add_argument("--system-dir", default="/etc/systemd/system")
    parser.add_argument("--no-enable", action="store_true")
    parser.add_argument("--start", action="store_true")
    args = parser.parse_args()

    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    from modules.system.deployment import SystemdDeploymentService

    service = SystemdDeploymentService()
    result = service.install_units(
        system_dir=args.system_dir,
        enable=not args.no_enable,
        start=args.start,
    )

    print(f"Installed systemd units into: {args.system_dir}")
    for unit_name in sorted(result.rendered_units):
        print(f"- {unit_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())