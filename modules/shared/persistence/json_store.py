from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from modules.shared.persistence.paths import resolve_optional_path

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class JsonReadResult(Generic[T]):
    """
    Structured result returned by safe JSON reads.

    This helps higher layers decide whether the data came from disk
    or whether a fallback default had to be used.
    """

    value: T
    exists: bool
    valid: bool
    path: Path


class JsonStore(Generic[T]):
    """
    Small, safe JSON-backed repository helper.

    I use this class as the single persistence primitive for features such as:
    - memory
    - reminders
    - session state
    - user profile

    Design goals:
    - atomic writes
    - defensive reads
    - deep-copied defaults
    - predictable UTF-8 JSON formatting
    - thread-safe in-process access
    """

    def __init__(
        self,
        path: str | Path,
        default_factory: callable[[], T],
        *,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> None:
        resolved_path = resolve_optional_path(path)
        if resolved_path is None:
            raise ValueError("JsonStore path cannot be None.")

        self._path = resolved_path
        self._default_factory = default_factory
        self._indent = int(indent)
        self._ensure_ascii = bool(ensure_ascii)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def make_default(self) -> T:
        """
        Return a fresh default object.
        """
        return deepcopy(self._default_factory())

    def exists(self) -> bool:
        return self._path.exists()

    def read_result(self) -> JsonReadResult[T]:
        """
        Read JSON safely and return metadata about the operation.
        """
        with self._lock:
            default_value = self.make_default()

            if not self._path.exists():
                return JsonReadResult(
                    value=default_value,
                    exists=False,
                    valid=False,
                    path=self._path,
                )

            try:
                with self._path.open("r", encoding="utf-8") as file:
                    value = json.load(file)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                return JsonReadResult(
                    value=default_value,
                    exists=True,
                    valid=False,
                    path=self._path,
                )

            return JsonReadResult(
                value=cast_json_value(value, default_value),
                exists=True,
                valid=matches_default_type(value, default_value),
                path=self._path,
            )

    def read(self) -> T:
        """
        Read JSON safely and return only the value.
        """
        return self.read_result().value

    def write(self, data: T) -> T:
        """
        Write JSON atomically and return a deep-copied snapshot of the written data.
        """
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)

            payload = deepcopy(data)
            temp_path = self._temporary_path()

            try:
                with temp_path.open("w", encoding="utf-8") as file:
                    json.dump(
                        payload,
                        file,
                        indent=self._indent,
                        ensure_ascii=self._ensure_ascii,
                    )
                    file.flush()
                    os.fsync(file.fileno())

                temp_path.replace(self._path)
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

            return deepcopy(payload)

    def update(self, updater: callable[[T], T]) -> T:
        """
        Read, transform, and write the JSON payload inside one lock.

        The updater receives a deep-copied working value and must return
        the new value to persist.
        """
        with self._lock:
            current_value = self.read()
            working_copy = deepcopy(current_value)
            updated_value = updater(working_copy)
            return self.write(updated_value)

    def ensure_exists(self) -> T:
        """
        Create the backing file with the default value if it does not exist.
        """
        with self._lock:
            if self._path.exists():
                return self.read()
            return self.write(self.make_default())

    def delete_file(self) -> bool:
        """
        Delete the backing JSON file if it exists.
        """
        with self._lock:
            if not self._path.exists():
                return False

            try:
                self._path.unlink()
                return True
            except OSError:
                return False

    def reset(self) -> T:
        """
        Replace the file contents with a fresh default value.
        """
        return self.write(self.make_default())

    def _temporary_path(self) -> Path:
        """
        Build a stable temporary file path next to the target file.

        Keeping the temp file in the same directory makes atomic replace safer
        across filesystems.
        """
        return self._path.with_suffix(f"{self._path.suffix}.tmp")



def matches_default_type(value: Any, default: T) -> bool:
    """
    Return True only when the loaded JSON value matches the expected container type.

    This is stricter than JSON parsing validity and lets higher layers repair files
    that contain syntactically valid JSON but the wrong payload shape.
    """
    if isinstance(default, dict):
        return isinstance(value, dict)

    if isinstance(default, list):
        return isinstance(value, list)

    if isinstance(default, set):
        return isinstance(value, set)

    if isinstance(default, tuple):
        return isinstance(value, tuple)

    return True


def cast_json_value(value: Any, default: T) -> T:
    """
    Keep the loaded JSON value only when it matches the default container type.

    This prevents bugs such as:
    - expecting dict but file contains list
    - expecting list but file contains dict

    Primitive defaults keep the loaded value as-is.
    """
    if isinstance(default, dict):
        return deepcopy(value) if isinstance(value, dict) else deepcopy(default)

    if isinstance(default, list):
        return deepcopy(value) if isinstance(value, list) else deepcopy(default)

    if isinstance(default, set):
        return deepcopy(value) if isinstance(value, set) else deepcopy(default)

    if isinstance(default, tuple):
        return deepcopy(value) if isinstance(value, tuple) else deepcopy(default)

    return deepcopy(value)


def read_json_file(path: str | Path, default: T) -> T:
    """
    Convenience helper for one-off safe JSON reads.
    """
    store = JsonStore(path=path, default_factory=lambda: deepcopy(default))
    return store.read()


def write_json_file(path: str | Path, data: T) -> T:
    """
    Convenience helper for one-off atomic JSON writes.
    """
    store = JsonStore(path=path, default_factory=lambda: deepcopy(data))
    return store.write(data)


__all__ = [
    "JsonStore",
    "JsonReadResult",
    "matches_default_type",
    "cast_json_value",
]