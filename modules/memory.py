from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from modules.utils import MEMORY_PATH, append_log, load_json, save_json


class SimpleMemory:
    def __init__(self) -> None:
        self.path = MEMORY_PATH

    def remember(self, key: str, value: str) -> None:
        key_clean = self._clean_text(key)
        value_clean = self._clean_text(value)

        if not key_clean or not value_clean:
            append_log("Memory save skipped: empty key or value.")
            return

        memory_data = self._load_memory()

        existing_key = self._find_existing_storage_key(memory_data, key_clean)
        target_key = existing_key if existing_key else key_clean

        memory_data[target_key] = value_clean
        save_json(self.path, memory_data)

        append_log(f"Memory saved: {target_key} -> {value_clean}")

    def recall(self, key: str) -> str | None:
        memory_data = self._load_memory()
        if not memory_data:
            return None

        query = self._clean_text(key)
        if not query:
            return None

        if query in memory_data:
            return memory_data[query]

        normalized_query = self._normalize_key(query)

        for stored_key, stored_value in memory_data.items():
            if self._normalize_key(stored_key) == normalized_query:
                return stored_value

        best_key = self._find_best_match(memory_data, query)
        if best_key is not None:
            append_log(f"Memory fuzzy recall matched '{query}' -> '{best_key}'")
            return memory_data[best_key]

        return None

    def get_all(self) -> dict[str, str]:
        return self._load_memory()

    def _load_memory(self) -> dict[str, str]:
        data = load_json(self.path, {})
        if not isinstance(data, dict):
            return {}

        clean_data: dict[str, str] = {}
        for key, value in data.items():
            key_text = self._clean_text(str(key))
            value_text = self._clean_text(str(value))
            if key_text and value_text:
                clean_data[key_text] = value_text

        return clean_data

    def _find_existing_storage_key(self, memory_data: dict[str, str], new_key: str) -> str | None:
        normalized_new_key = self._normalize_key(new_key)

        for stored_key in memory_data.keys():
            if self._normalize_key(stored_key) == normalized_new_key:
                return stored_key

        return None

    def _find_best_match(self, memory_data: dict[str, str], query: str) -> str | None:
        normalized_query = self._normalize_key(query)
        query_tokens = self._tokenize(normalized_query)

        best_key: str | None = None
        best_score = 0.0

        for stored_key in memory_data.keys():
            normalized_stored_key = self._normalize_key(stored_key)
            stored_tokens = self._tokenize(normalized_stored_key)

            if normalized_query in normalized_stored_key or normalized_stored_key in normalized_query:
                return stored_key

            overlap_score = self._token_overlap_score(query_tokens, stored_tokens)
            similarity_score = SequenceMatcher(None, normalized_query, normalized_stored_key).ratio()

            combined_score = max(overlap_score, similarity_score)

            if combined_score > best_score:
                best_score = combined_score
                best_key = stored_key

        if best_score >= 0.58:
            return best_key

        return None

    @staticmethod
    def _token_overlap_score(left_tokens: list[str], right_tokens: list[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0

        left_set = set(left_tokens)
        right_set = set(right_tokens)

        common = left_set & right_set
        if not common:
            return 0.0

        base = len(common) / max(len(left_set), len(right_set))
        return float(base)

    def _normalize_key(self, text: str) -> str:
        normalized = self._clean_text(text)
        normalized = self._strip_leading_fillers(normalized)
        normalized = self._strip_trailing_fillers(normalized)
        normalized = self._singularize_last_token(normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _clean_text(self, text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def _strip_leading_fillers(self, text: str) -> str:
        fillers = [
            "my ",
            "moje ",
            "moj ",
            "moja ",
            "numer ",
            "number ",
            "the ",
            "a ",
            "an ",
        ]

        result = text
        changed = True

        while changed:
            changed = False
            for filler in fillers:
                if result.startswith(filler):
                    result = result[len(filler):].strip()
                    changed = True

        return result

    def _strip_trailing_fillers(self, text: str) -> str:
        fillers = [
            " prosze",
            " please",
        ]

        result = text
        changed = True

        while changed:
            changed = False
            for filler in fillers:
                if result.endswith(filler):
                    result = result[: -len(filler)].strip()
                    changed = True

        return result

    def _singularize_last_token(self, text: str) -> str:
        tokens = text.split()
        if not tokens:
            return text

        last = tokens[-1]

        english_irregular = {
            "keys": "key",
            "glasses": "glasses",
            "phones": "phone",
            "numbers": "number",
        }
        polish_irregular = {
            "klucze": "klucz",
            "okulary": "okulary",
            "telefony": "telefon",
        }

        if last in english_irregular:
            tokens[-1] = english_irregular[last]
            return " ".join(tokens)

        if last in polish_irregular:
            tokens[-1] = polish_irregular[last]
            return " ".join(tokens)

        if len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
            tokens[-1] = last[:-1]
            return " ".join(tokens)

        return " ".join(tokens)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in text.split() if token]