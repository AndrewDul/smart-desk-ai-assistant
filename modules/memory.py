from __future__ import annotations

from modules.utils import MEMORY_PATH, append_log, load_json, save_json


class SimpleMemory:
    def __init__(self) -> None:
        self.path = MEMORY_PATH

    def remember(self, key: str, value: str) -> None:
        memory_data = load_json(self.path, {})
        memory_data[key] = value
        save_json(self.path, memory_data)
        append_log(f"Memory saved: {key} -> {value}")

    def recall(self, key: str) -> str | None:
        memory_data = load_json(self.path, {})
        return memory_data.get(key)

    def get_all(self) -> dict:
        return load_json(self.path, {})
