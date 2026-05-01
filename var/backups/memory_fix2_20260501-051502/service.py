from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from modules.shared.logging.logger import append_log
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.repositories import MemoryRepository


@dataclass(slots=True)
class MemoryMatch:
    id: str
    key: str
    value: str
    original_text: str
    score: float
    exact: bool = False
    language: str = "unknown"
    normalized_query: str = ""
    normalized_text: str = ""
    record: dict[str, Any] | None = None


class MemoryService:
    """
    Persistent local memory for NeXa.

    The storage model is record-based, not key/value-only.

    Each saved memory keeps:
    - original_text: full phrase spoken by the user
    - normalized_text: searchable normalized phrase
    - tokens: deterministic search tokens
    - language: per-turn language
    - source: voice/runtime/manual/etc.
    - created_at_iso: UTC timestamp
    - confidence: optional source confidence

    Compatibility:
    - remember(key, value) still works for older action flow callers.
    - recall(key) returns the best matching original memory phrase.
    - get_all() returns a dict for older list callers.
    - list_records() exposes the new product-grade record format.
    """

    _EN_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "at",
        "about",
        "do",
        "for",
        "from",
        "have",
        "has",
        "i",
        "in",
        "inside",
        "is",
        "it",
        "me",
        "my",
        "near",
        "of",
        "on",
        "please",
        "recall",
        "remember",
        "tell",
        "the",
        "this",
        "to",
        "under",
        "what",
        "where",
        "you",
    }

    _PL_STOPWORDS = {
        "a",
        "czy",
        "co",
        "dla",
        "gdzie",
        "i",
        "jest",
        "mam",
        "masz",
        "mi",
        "moja",
        "moje",
        "moj",
        "na",
        "nad",
        "nie",
        "o",
        "obok",
        "pamietasz",
        "pod",
        "przy",
        "przypomnij",
        "sa",
        "sie",
        "to",
        "w",
        "we",
        "z",
        "za",
        "ze",
    }

    def __init__(
        self,
        store: JsonStore[Any] | MemoryRepository | None = None,
    ) -> None:
        self.store = store or MemoryRepository()
        self.store.ensure_valid()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def remember(
        self,
        key: str,
        value: str,
        *,
        language: str = "unknown",
        source: str = "legacy_key_value",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key_text = self._compact_original_text(key)
        value_text = self._compact_original_text(value)

        if not key_text or not value_text:
            append_log("Memory save skipped: empty key or value.")
            return

        original_text = self._compose_legacy_memory_text(key_text, value_text)
        self.remember_text(
            original_text,
            language=language,
            source=source,
            confidence=confidence,
            metadata={
                "legacy_key": key_text,
                "legacy_value": value_text,
                **dict(metadata or {}),
            },
        )

    def remember_text(
        self,
        text: str,
        *,
        language: str = "unknown",
        source: str = "voice",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        original_text = self._compact_original_text(text)
        if not original_text:
            append_log("Memory save skipped: empty text.")
            return None

        record = self._build_record(
            original_text=original_text,
            language=language,
            source=source,
            confidence=confidence,
            metadata=metadata,
        )
        if not record["tokens"]:
            append_log("Memory save skipped: no searchable tokens.")
            return None

        records = self._load_records()
        records = [
            existing
            for existing in records
            if not (
                existing.get("language") == record["language"]
                and existing.get("normalized_text") == record["normalized_text"]
            )
        ]
        records.append(record)
        self._save_records(records)

        append_log(
            "Memory saved: "
            f"id={record['id']} language={record['language']} text={record['original_text']}"
        )
        return str(record["id"])

    def store_text(
        self,
        text: str,
        *,
        language: str = "unknown",
        source: str = "voice",
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        return self.remember_text(
            text,
            language=language,
            source=source,
            confidence=confidence,
            metadata=metadata,
        )

    def recall(self, key: str, *, language: str | None = None) -> str | None:
        match = self.match(key, language=language)
        if match is None:
            return None

        query_clean = self._clean_text(key)
        append_log(
            "Memory recall matched "
            f"query={query_clean!r} -> id={match.id} language={match.language} "
            f"score={match.score:.2f}"
        )
        return match.original_text

    def match(self, key: str, *, language: str | None = None) -> MemoryMatch | None:
        records = self._load_records()
        if not records:
            return None
        return self._find_best_record(records, key, language=language)

    def forget(self, key: str, *, language: str | None = None) -> tuple[str | None, str | None]:
        records = self._load_records()
        if not records:
            return None, None

        match = self._find_best_record(records, key, language=language)
        if match is None:
            return None, None

        kept = [record for record in records if str(record.get("id", "")) != match.id]
        self._save_records(kept)

        append_log(f"Memory deleted: id={match.id} text={match.original_text}")
        return match.original_text, match.original_text

    def clear(self) -> int:
        records = self._load_records()
        count = len(records)
        self._save_records([])
        append_log(f"Memory cleared: removed {count} item(s).")
        return count

    def get_all(self) -> dict[str, str]:
        items: dict[str, str] = {}
        for record in self._load_records():
            text = str(record.get("original_text", "") or "").strip()
            if not text:
                continue
            key = text
            if key in items:
                key = str(record.get("id", key))
            items[key] = text
        return items

    def list_records(self, *, language: str | None = None) -> list[dict[str, Any]]:
        records = self._load_records()
        normalized_language = self._normalize_language(language)
        if normalized_language:
            records = [
                record
                for record in records
                if str(record.get("language", "unknown")) == normalized_language
            ]
        return [dict(record) for record in records]

    def list_items(self, *, language: str | None = None) -> list[dict[str, Any]]:
        return self.list_records(language=language)

    def export(self) -> list[dict[str, Any]]:
        return self.list_records()

    def has_any(self) -> bool:
        return bool(self._load_records())

    def count(self, *, language: str | None = None) -> int:
        return len(self.list_records(language=language))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_records(self) -> list[dict[str, Any]]:
        raw_data = self.store.read()

        if isinstance(raw_data, list):
            records = [self._coerce_record(item) for item in raw_data if isinstance(item, dict)]
            return [record for record in records if record is not None]

        if isinstance(raw_data, dict):
            return self._migrate_legacy_dict(raw_data)

        return []

    def _save_records(self, records: list[dict[str, Any]]) -> None:
        cleaned_records = [
            record
            for record in (self._coerce_record(item) for item in records)
            if record is not None
        ]
        self.store.write(cleaned_records)

    def _migrate_legacy_dict(self, data: dict[Any, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for key, value in data.items():
            key_text = self._compact_original_text(str(key))
            value_text = self._compact_original_text(str(value))
            if not key_text or not value_text:
                continue

            original_text = self._compose_legacy_memory_text(key_text, value_text)
            record = self._build_record(
                original_text=original_text,
                language="unknown",
                source="legacy_migration",
                confidence=1.0,
                metadata={
                    "legacy_key": key_text,
                    "legacy_value": value_text,
                },
            )
            records.append(record)

        return records

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _find_best_record(
        self,
        records: list[dict[str, Any]],
        query: str,
        *,
        language: str | None = None,
    ) -> MemoryMatch | None:
        normalized_query = self._clean_text(query)
        if not normalized_query:
            return None

        normalized_language = self._normalize_language(language)
        if normalized_language:
            records = [
                record
                for record in records
                if str(record.get("language", "unknown")) == normalized_language
            ]

        if not records:
            return None

        query_tokens = self._tokenize(normalized_query)
        if not query_tokens:
            return None

        best_match: MemoryMatch | None = None
        best_score = 0.0

        for record in records:
            original_text = str(record.get("original_text", "") or "").strip()
            normalized_text = str(record.get("normalized_text", "") or "").strip()
            record_tokens = [
                str(token)
                for token in list(record.get("tokens", []) or [])
                if str(token).strip()
            ]

            if not original_text or not normalized_text or not record_tokens:
                continue

            if normalized_query == normalized_text:
                return self._to_match(
                    record,
                    score=1.0,
                    exact=True,
                    normalized_query=normalized_query,
                )

            if normalized_query in normalized_text:
                return self._to_match(
                    record,
                    score=0.94,
                    exact=False,
                    normalized_query=normalized_query,
                )

            overlap_score = self._token_overlap_score(query_tokens, record_tokens)
            similarity_score = SequenceMatcher(None, normalized_query, normalized_text).ratio()
            combined_score = max(overlap_score, similarity_score * 0.72)

            if combined_score > best_score:
                best_score = combined_score
                best_match = self._to_match(
                    record,
                    score=combined_score,
                    exact=False,
                    normalized_query=normalized_query,
                )

        if best_match is not None and best_score >= 0.34:
            return best_match

        return None

    def _to_match(
        self,
        record: dict[str, Any],
        *,
        score: float,
        exact: bool,
        normalized_query: str,
    ) -> MemoryMatch:
        original_text = str(record.get("original_text", "") or "").strip()
        normalized_text = str(record.get("normalized_text", "") or "").strip()
        return MemoryMatch(
            id=str(record.get("id", "") or ""),
            key=original_text,
            value=original_text,
            original_text=original_text,
            score=float(score),
            exact=bool(exact),
            language=str(record.get("language", "unknown") or "unknown"),
            normalized_query=normalized_query,
            normalized_text=normalized_text,
            record=dict(record),
        )

    @staticmethod
    def _token_overlap_score(left_tokens: list[str], right_tokens: list[str]) -> float:
        if not left_tokens or not right_tokens:
            return 0.0

        left_variants = set(MemoryService._expand_token_variants(left_tokens))
        right_variants = set(MemoryService._expand_token_variants(right_tokens))
        common = left_variants & right_variants

        if not common:
            return 0.0

        return float(len(common) / max(len(set(left_tokens)), len(set(right_tokens)), 1))

    # ------------------------------------------------------------------
    # Record building
    # ------------------------------------------------------------------

    def _build_record(
        self,
        *,
        original_text: str,
        language: str,
        source: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_text = self._clean_text(original_text)
        normalized_language = self._normalize_language(language) or "unknown"
        tokens = self._tokenize(normalized_text)
        record_id = self._build_record_id(
            language=normalized_language,
            normalized_text=normalized_text,
        )

        return {
            "id": record_id,
            "language": normalized_language,
            "original_text": original_text,
            "normalized_text": normalized_text,
            "tokens": tokens,
            "source": str(source or "unknown").strip() or "unknown",
            "created_at_iso": self._now_iso(),
            "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
            "metadata": dict(metadata or {}),
        }

    def _coerce_record(self, item: dict[str, Any]) -> dict[str, Any] | None:
        original_text = self._compact_original_text(
            item.get("original_text")
            or item.get("text")
            or item.get("value")
            or ""
        )
        if not original_text:
            return None

        language = self._normalize_language(str(item.get("language", "unknown") or "unknown")) or "unknown"
        normalized_text = self._clean_text(item.get("normalized_text") or original_text)
        tokens = [
            str(token).strip()
            for token in list(item.get("tokens", []) or [])
            if str(token).strip()
        ]
        if not tokens:
            tokens = self._tokenize(normalized_text)

        if not tokens:
            return None

        record_id = str(item.get("id", "") or "").strip()
        if not record_id:
            record_id = self._build_record_id(language=language, normalized_text=normalized_text)

        return {
            "id": record_id,
            "language": language,
            "original_text": original_text,
            "normalized_text": normalized_text,
            "tokens": tokens,
            "source": str(item.get("source", "unknown") or "unknown").strip() or "unknown",
            "created_at_iso": str(item.get("created_at_iso", "") or self._now_iso()),
            "confidence": max(0.0, min(1.0, float(item.get("confidence", 1.0) or 0.0))),
            "metadata": dict(item.get("metadata", {}) or {}),
        }

    @staticmethod
    def _build_record_id(*, language: str, normalized_text: str) -> str:
        digest = hashlib.sha1(f"{language}|{normalized_text}".encode("utf-8")).hexdigest()[:16]
        return f"mem_{digest}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _tokenize(self, normalized_text: str) -> list[str]:
        tokens: list[str] = []
        for token in str(normalized_text or "").split():
            cleaned = self._normalize_token(token)
            if not cleaned:
                continue
            if cleaned in self._EN_STOPWORDS or cleaned in self._PL_STOPWORDS:
                continue
            if cleaned not in tokens:
                tokens.append(cleaned)
        return tokens

    @staticmethod
    def _expand_token_variants(tokens: list[str]) -> list[str]:
        variants: list[str] = []
        for token in tokens:
            for variant in MemoryService._token_variants(token):
                if variant and variant not in variants:
                    variants.append(variant)
        return variants

    @staticmethod
    def _token_variants(token: str) -> set[str]:
        cleaned = MemoryService._normalize_token(token)
        variants = {cleaned} if cleaned else set()

        if len(cleaned) > 3:
            if cleaned.endswith("ies"):
                variants.add(cleaned[:-3] + "y")
            if cleaned.endswith("s"):
                variants.add(cleaned[:-1])
            if cleaned.endswith("e"):
                variants.add(cleaned[:-1])
            if cleaned.endswith("ami"):
                variants.add(cleaned[:-3])
            if cleaned.endswith("ach"):
                variants.add(cleaned[:-3])
            if cleaned.endswith("ow"):
                variants.add(cleaned[:-2])

        return {variant for variant in variants if len(variant) >= 2}

    @staticmethod
    def _normalize_token(token: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(token or "").strip().lower())

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        lowered = str(language or "").strip().lower()
        if lowered in {"pl", "polish", "pl-pl", "pl_pl"}:
            return "pl"
        if lowered in {"en", "english", "en-gb", "en_gb", "en-us", "en_us"}:
            return "en"
        return ""

    def _clean_text(self, text: Any) -> str:
        lowered = str(text or "").lower().strip()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _compact_original_text(text: Any) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip())

    @staticmethod
    def _compose_legacy_memory_text(key: str, value: str) -> str:
        key_text = MemoryService._compact_original_text(key)
        value_text = MemoryService._compact_original_text(value)
        if not key_text or not value_text:
            return ""

        if value_text.lower().startswith(
            (
                "in ",
                "on ",
                "at ",
                "under ",
                "inside ",
                "near ",
                "beside ",
                "w ",
                "we ",
                "na ",
                "pod ",
                "przy ",
                "obok ",
            )
        ):
            return f"{key_text} {value_text}"

        return f"{key_text} is {value_text}"


__all__ = ["MemoryMatch", "MemoryService"]
