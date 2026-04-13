from __future__ import annotations

import pathlib
import sys
import unittest


def main() -> int:
    project_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))

    tests_dir = project_root / "tests"
    if not tests_dir.exists():
        print(f"Missing tests directory: {tests_dir}")
        return 1

    loader = unittest.defaultTestLoader
    suite = loader.discover(start_dir=str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())