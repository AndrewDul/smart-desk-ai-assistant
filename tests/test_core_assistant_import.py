from __future__ import annotations

import unittest


class CoreAssistantImportTests(unittest.TestCase):
    def test_modules_core_assistant_imports_cleanly(self) -> None:
        from modules.core.assistant import CoreAssistant

        self.assertTrue(callable(CoreAssistant))


if __name__ == "__main__":
    unittest.main()