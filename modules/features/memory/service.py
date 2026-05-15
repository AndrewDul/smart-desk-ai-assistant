from __future__ import annotations

import hashlib
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from modules.shared.logging.logger import append_log
from modules.features.memory_v2.face_capture import capture_face_reference_from_vision
from modules.features.memory_v2.store import SQLiteMemoryStore
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import MEMORY_PATH
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
        "leave",
        "left",
        "look",
        "me",
        "my",
        "near",
        "of",
        "on",
        "please",
        "put",
        "recall",
        "remind",
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
        "sobie",
        "lezal",
        "lezy",
        "polozylem",
        "polozylam",
        "powiedz",
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
        *,
        index_store: SQLiteMemoryStore | None = None,
        enable_runtime_index: bool | None = None,
    ) -> None:
        self.store = store or MemoryRepository()
        self.store.ensure_valid()
        self._records_cache: list[dict[str, Any]] | None = None
        self._records_cache_signature: tuple[str, int | None] | None = None
        self.index_store = self._resolve_index_store(
            index_store=index_store,
            enable_runtime_index=enable_runtime_index,
        )
        self._sync_index_from_json()

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
        original_input_text = self._compact_original_text(text)
        original_text = self.prepare_memory_text(original_input_text, language=language)
        if not original_text:
            append_log("Memory save skipped: empty text.")
            return None

        record_metadata = dict(metadata or {})
        if original_input_text and original_input_text != original_text:
            record_metadata.setdefault("raw_transcript", original_input_text)
            record_metadata.setdefault("memory_text_corrected", True)

        record = self._build_record(
            original_text=original_text,
            language=language,
            source=source,
            confidence=confidence,
            metadata=record_metadata,
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

    def prepare_memory_text(
        self,
        text: str,
        *,
        language: str = "unknown",
    ) -> str:
        """Return a display-safe memory phrase before it is stored.

        This is intentionally conservative: normal dictation is preserved,
        while known short Polish ASR glitches are repaired before they become
        permanent memory records.
        """

        compact = self._compact_original_text(text)
        if not compact:
            return ""

        normalized_language = self._normalize_language(language)
        if normalized_language != "pl":
            return compact

        return self._repair_polish_memory_dictation(compact)

    def looks_like_suspicious_memory_text(
        self,
        text: str,
        *,
        language: str = "unknown",
    ) -> bool:
        compact = self._compact_original_text(text)
        if not compact:
            return True

        normalized = self._clean_text(compact)
        if not normalized:
            return True

        normalized_language = self._normalize_language(language)
        if normalized_language == "pl":
            english_false_positives = {
                "clue chest on the corner",
                "close chest on the corner",
                "blue chest on the corner",
                "thank you very much",
                "thanks for watching",
                "speaking in foreign language",
            }
            if normalized in english_false_positives:
                return True

            tokens = normalized.split()
            english_location_words = {
                "clue",
                "chest",
                "corner",
                "phone",
                "desk",
                "table",
                "keys",
                "kitchen",
            }
            if tokens and sum(1 for token in tokens if token in english_location_words) >= max(2, len(tokens) - 1):
                return True

        return False

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
        people_match = self._find_best_indexed_people_query(key, language=language)
        if people_match is not None:
            return people_match

        fact_match = self._find_best_indexed_structured_fact(key, language=language)
        if fact_match is not None:
            return fact_match

        indexed_match = self._find_best_indexed_record(key, language=language)
        if indexed_match is not None:
            return indexed_match

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

    def list_people(self, *, language: str | None = None) -> list[dict[str, Any]]:
        normalized_language = self._normalize_language(language)
        if self.index_store is not None:
            try:
                return self.index_store.list_entities(
                    entity_type="person",
                    language=normalized_language or None,
                )
            except Exception as exc:  # pragma: no cover - defensive runtime fallback
                append_log(f"Memory people index lookup failed: {exc}")
                self.index_store = None

        entities = self._build_entities_from_records(self._load_records())
        if normalized_language:
            entities = [
                entity
                for entity in entities
                if str(entity.get("language", "unknown") or "unknown") == normalized_language
            ]
        return [entity for entity in entities if entity.get("entity_type") == "person"]

    def remember_person(
        self,
        display_name: str,
        *,
        aliases: list[str] | tuple[str, ...] | None = None,
        language: str = "unknown",
        source: str = "person_memory",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        clean_display_name = self._compact_original_text(display_name)
        if not clean_display_name:
            append_log("Person memory save skipped: empty display name.")
            return None

        normalized_language = self._normalize_language(language) or "unknown"
        if normalized_language == "en":
            memory_text = f"I know person: {clean_display_name}"
        else:
            memory_text = f"znam osobę: {clean_display_name}"

        return self.remember_text(
            memory_text,
            language=normalized_language,
            source=source,
            confidence=1.0,
            metadata={
                "memory_kind": "person",
                "display_name": clean_display_name,
                "aliases": list(aliases or []),
                **dict(metadata or {}),
            },
        )

    def prepare_person_face_capture_slot(
        self,
        display_name: str,
        *,
        aliases: list[str] | tuple[str, ...] | None = None,
        language: str = "unknown",
        source: str = "guided_person_enrollment",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        clean_display_name = self._compact_original_text(display_name)
        if not clean_display_name:
            append_log("Person face capture slot skipped: empty display name.")
            return None

        normalized_language = self._normalize_language(language) or "unknown"
        person_record_id = self.remember_person(
            clean_display_name,
            aliases=aliases,
            language=normalized_language,
            source=source,
            metadata={
                "person_scope": "user",
                "enrollment_flow": "voice_guided",
                "face_capture_slot_requested": True,
                **dict(metadata or {}),
            },
        )

        slot: dict[str, Any] = {
            "person_id": str(person_record_id or "").strip(),
            "display_name": clean_display_name,
            "face_capture_ready": False,
        }

        if self.index_store is None:
            append_log("Person face capture slot prepared without SQLite asset index.")
            return slot

        person = self._find_person_entity_by_display_name(
            clean_display_name,
            language=normalized_language,
        )
        if person is None:
            append_log(f"Person face capture slot skipped: person entity not found for {clean_display_name}.")
            return slot

        entity_id = str(person.get("id", "") or "").strip()
        if not entity_id:
            append_log(f"Person face capture slot skipped: empty person entity id for {clean_display_name}.")
            return slot

        face_dir = self.index_store.person_faces_dir(entity_id)
        existing_assets = self.list_person_face_assets(person_entity_id=entity_id)
        next_index = len(existing_assets) + 1
        next_face_path = face_dir / f"face_{next_index:03d}.jpg"

        slot.update(
            {
                "person_entity_id": entity_id,
                "person_faces_dir": str(face_dir),
                "next_face_asset_path": str(next_face_path),
                "existing_face_asset_count": len(existing_assets),
                "face_capture_ready": True,
            }
        )
        append_log(
            "Person face capture slot prepared: "
            f"entity_id={entity_id} dir={face_dir} next_path={next_face_path}"
        )
        return slot

    def remember_person_face_asset(
        self,
        display_name: str,
        asset_path: str | Path,
        *,
        aliases: list[str] | tuple[str, ...] | None = None,
        language: str = "unknown",
        caption: str | None = None,
        source: str = "person_face_asset",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if self.index_store is None:
            append_log("Person face asset save skipped: SQLite memory index is disabled.")
            return None

        clean_display_name = self._compact_original_text(display_name)
        clean_asset_path = self._compact_original_text(str(asset_path))
        if not clean_display_name or not clean_asset_path:
            append_log("Person face asset save skipped: missing display name or asset path.")
            return None

        normalized_language = self._normalize_language(language) or "unknown"
        self.remember_person(
            clean_display_name,
            aliases=aliases,
            language=normalized_language,
            source=source,
            metadata={"has_face_asset": True, **dict(metadata or {})},
        )
        person = self._find_person_entity_by_display_name(
            clean_display_name,
            language=normalized_language,
        )
        if person is None:
            append_log(f"Person face asset save skipped: person entity not found for {clean_display_name}.")
            return None

        entity_id = str(person.get("id", "") or "").strip()
        if not entity_id:
            append_log(f"Person face asset save skipped: empty person entity id for {clean_display_name}.")
            return None

        face_dir = self.index_store.person_faces_dir(entity_id)
        asset = {
            "id": self._build_asset_id(
                entity_id=entity_id,
                asset_type="face_photo",
                path=clean_asset_path,
            ),
            "entity_id": entity_id,
            "asset_type": "face_photo",
            "path": clean_asset_path,
            "caption": self._compact_original_text(caption or clean_display_name),
            "created_at_iso": self._now_iso(),
            "metadata": {
                "source": source,
                "asset_role": "person_face_reference",
                "person_display_name": clean_display_name,
                "person_faces_dir": str(face_dir),
                **dict(metadata or {}),
            },
        }
        try:
            self.index_store.upsert_asset(asset)
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Person face asset save failed: {exc}")
            return None

        append_log(
            "Person face asset saved: "
            f"entity_id={entity_id} path={clean_asset_path}"
        )
        return str(asset["id"])

    def list_person_face_assets(
        self,
        *,
        display_name: str | None = None,
        person_entity_id: str | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.index_store is None:
            return []

        entity_id = str(person_entity_id or "").strip()
        if not entity_id and display_name:
            person = self._find_person_entity_by_display_name(display_name, language=language)
            if person is not None:
                entity_id = str(person.get("id", "") or "").strip()

        if not entity_id:
            return []

        try:
            return self.index_store.list_assets(
                entity_id=entity_id,
                asset_type="face_photo",
            )
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Person face asset lookup failed: {exc}")
            return []

    def capture_person_face_reference(
        self,
        *,
        display_name: str,
        vision_backend: Any,
        aliases: list[str] | tuple[str, ...] | None = None,
        language: str = "unknown",
        source: str = "guided_person_face_capture",
        slot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_display_name = self._compact_original_text(display_name)
        if not clean_display_name:
            return {"ok": False, "reason": "display_name_missing"}

        face_slot = dict(slot or {})
        if not face_slot.get("face_capture_ready"):
            prepared_slot = self.prepare_person_face_capture_slot(
                clean_display_name,
                aliases=aliases,
                language=language,
                source=source,
            )
            face_slot = dict(prepared_slot or {})

        target_path = str(face_slot.get("next_face_asset_path", "") or "").strip()
        if not target_path:
            return {
                "ok": False,
                "reason": "face_slot_unavailable",
                "slot": face_slot,
            }

        result = capture_face_reference_from_vision(
            vision_backend=vision_backend,
            target_path=target_path,
        )
        if not result.ok:
            append_log(f"Person face capture skipped: {result.reason}")
            return {
                "ok": False,
                "reason": result.reason,
                "face_detected": result.face_detected,
                "face_count": result.face_count,
                "face_confidence": result.face_confidence,
                "slot": face_slot,
                "target_path": target_path,
            }

        asset_id = self.remember_person_face_asset(
            clean_display_name,
            result.path,
            aliases=aliases,
            language=language,
            caption=f"{clean_display_name} face reference",
            source=source,
            metadata={
                "capture_backend": result.backend,
                "capture_width": result.width,
                "capture_height": result.height,
                "capture_source": "runtime_vision_backend_latest_frame",
                "face_detected": result.face_detected,
                "face_count": result.face_count,
                "face_confidence": result.face_confidence,
                "face_quality_gate": "runtime_tracking_observation",
            },
        )
        if not asset_id:
            return {
                "ok": False,
                "reason": "asset_record_failed",
                "slot": face_slot,
                "target_path": result.path,
            }

        append_log(
            "Person face reference captured: "
            f"display_name={clean_display_name} path={result.path} asset_id={asset_id}"
        )
        return {
            "ok": True,
            "asset_id": asset_id,
            "path": result.path,
            "width": result.width,
            "height": result.height,
            "backend": result.backend,
            "face_detected": result.face_detected,
            "face_count": result.face_count,
            "face_confidence": result.face_confidence,
            "slot": face_slot,
        }

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
        signature = self._store_signature()
        if (
            self._records_cache is not None
            and self._records_cache_signature == signature
        ):
            return deepcopy(self._records_cache)

        raw_data = self.store.read()

        if isinstance(raw_data, list):
            records = [self._coerce_record(item) for item in raw_data if isinstance(item, dict)]
            loaded_records = [record for record in records if record is not None]
        elif isinstance(raw_data, dict):
            loaded_records = self._migrate_legacy_dict(raw_data)
        else:
            loaded_records = []

        self._records_cache = deepcopy(loaded_records)
        self._records_cache_signature = self._store_signature()
        return deepcopy(loaded_records)

    def _save_records(self, records: list[dict[str, Any]]) -> None:
        cleaned_records = [
            record
            for record in (self._coerce_record(item) for item in records)
            if record is not None
        ]
        self.store.write(cleaned_records)
        self._records_cache = deepcopy(cleaned_records)
        self._records_cache_signature = self._store_signature()
        self._replace_index_records(cleaned_records)

    def _store_signature(self) -> tuple[str, int | None]:
        path = getattr(self.store, "path", None)
        if path is None:
            return ("memory-store", None)

        try:
            resolved_path = str(path)
            stat = path.stat()
        except OSError:
            return (str(path), None)

        return (resolved_path, int(getattr(stat, "st_mtime_ns", 0)))

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
    # SQLite fast index
    # ------------------------------------------------------------------

    def _resolve_index_store(
        self,
        *,
        index_store: SQLiteMemoryStore | None,
        enable_runtime_index: bool | None,
    ) -> SQLiteMemoryStore | None:
        if index_store is not None:
            try:
                index_store.ensure_ready()
                return index_store
            except Exception as exc:  # pragma: no cover - defensive runtime fallback
                append_log(f"Memory SQLite index disabled: {exc}")
                return None

        should_enable = self._uses_default_runtime_store() if enable_runtime_index is None else bool(enable_runtime_index)
        if not should_enable:
            return None

        try:
            runtime_index = SQLiteMemoryStore()
            runtime_index.ensure_ready()
            return runtime_index
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Memory SQLite index disabled: {exc}")
            return None

    def _uses_default_runtime_store(self) -> bool:
        path = getattr(self.store, "path", None)
        if path is None:
            return False

        try:
            return Path(path).resolve() == MEMORY_PATH.resolve()
        except OSError:
            return False

    def _sync_index_from_json(self) -> None:
        if self.index_store is None:
            return

        try:
            self._replace_index_records(self._load_records())
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Memory SQLite index sync failed: {exc}")
            self.index_store = None

    def _replace_index_records(self, records: list[dict[str, Any]]) -> None:
        if self.index_store is None:
            return

        try:
            self.index_store.replace_all_records(records)
            self.index_store.replace_all_entities(self._build_entities_from_records(records))
            self.index_store.replace_all_facts(self._build_facts_from_records(records))
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Memory SQLite index update failed: {exc}")
            self.index_store = None

    def _find_best_indexed_people_query(
        self,
        key: str,
        *,
        language: str | None = None,
    ) -> MemoryMatch | None:
        normalized_query = self._clean_text(key)
        if not self._looks_like_people_list_query(normalized_query):
            return None

        normalized_language = self._normalize_language(language) or "unknown"
        people = self.list_people(language=None)
        answer = self._format_known_people_answer(people, language=normalized_language)
        return MemoryMatch(
            id="memory_people_list",
            key=normalized_query,
            value=answer,
            original_text=answer,
            score=1.0,
            exact=True,
            language=normalized_language,
            normalized_query=normalized_query,
            normalized_text=normalized_query,
            record={"people": people},
        )

    def _find_best_indexed_structured_fact(
        self,
        key: str,
        *,
        language: str | None = None,
    ) -> MemoryMatch | None:
        if self.index_store is None:
            return None

        normalized_query = self._clean_text(key)
        if not normalized_query:
            return None

        query_tokens = self._tokenize(normalized_query)
        if not query_tokens:
            return None

        query_plan = self._detect_fact_query(normalized_query, query_tokens)
        if query_plan is None:
            return None

        relation = str(query_plan.get("relation", "") or "").strip()
        subject_tokens = list(query_plan.get("subject_tokens", []) or [])
        value_tokens = list(query_plan.get("value_tokens", []) or [])
        normalized_language = self._normalize_language(language)

        try:
            facts = self.index_store.find_facts(
                relation=relation,
                subject_tokens=self._expand_token_variants(subject_tokens),
                value_tokens=self._expand_token_variants(value_tokens),
                language=normalized_language or None,
                limit=16,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Memory SQLite fact lookup failed: {exc}")
            self.index_store = None
            return None

        if not facts:
            return None

        fact = facts[0]
        source_text = str(fact.get("source_original_text", "") or "").strip()
        if not source_text:
            source_text = self._compose_fact_answer(fact)
        if not source_text:
            return None

        normalized_text = self._clean_text(source_text)
        return MemoryMatch(
            id=str(fact.get("source_record_id") or fact.get("id") or ""),
            key=source_text,
            value=source_text,
            original_text=source_text,
            score=0.98,
            exact=False,
            language=str(fact.get("language", "unknown") or "unknown"),
            normalized_query=normalized_query,
            normalized_text=normalized_text,
            record={"fact": dict(fact)},
        )

    def _find_best_indexed_record(
        self,
        key: str,
        *,
        language: str | None = None,
    ) -> MemoryMatch | None:
        if self.index_store is None:
            return None

        normalized_query = self._clean_text(key)
        if not normalized_query:
            return None

        query_tokens = self._tokenize(normalized_query)
        if not query_tokens:
            return None

        expanded_tokens = self._expand_token_variants(query_tokens)
        normalized_language = self._normalize_language(language)
        try:
            candidates = self.index_store.find_candidate_records(
                tokens=expanded_tokens,
                language=normalized_language or None,
                limit=64,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime fallback
            append_log(f"Memory SQLite index lookup failed: {exc}")
            self.index_store = None
            return None

        if not candidates:
            return None

        return self._find_best_record(candidates, key, language=language)

    # ------------------------------------------------------------------
    # Structured entity extraction
    # ------------------------------------------------------------------

    def _build_entities_from_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        entities_by_id: dict[str, dict[str, Any]] = {}
        for record in records:
            for entity in self._extract_structured_entities(record):
                entity_id = str(entity.get("id", "") or "")
                if entity_id:
                    entities_by_id[entity_id] = entity
        return list(entities_by_id.values())

    def _extract_structured_entities(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        metadata = dict(record.get("metadata", {}) or {})
        if metadata.get("memory_kind") == "person":
            entity = self._person_entity_from_metadata(record, metadata)
            if entity is not None:
                entities.append(entity)

        name_fact = self._extract_name_fact(record)
        if name_fact is not None and str(name_fact.get("subject_text")) == "user":
            entity = self._person_entity_from_name_fact(record, name_fact)
            if entity is not None:
                entities.append(entity)

        return entities

    def _person_entity_from_metadata(
        self,
        record: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        display_name = self._compact_original_text(metadata.get("display_name", ""))
        if not display_name:
            return None

        aliases = [str(alias) for alias in list(metadata.get("aliases", []) or [])]
        return self._build_person_entity(
            display_name=display_name,
            language=str(record.get("language", "unknown") or "unknown"),
            aliases=aliases,
            record=record,
            metadata={
                "source": "person_memory_metadata",
                "source_record_id": str(record.get("id", "") or ""),
            },
        )

    def _person_entity_from_name_fact(
        self,
        record: dict[str, Any],
        name_fact: dict[str, Any],
    ) -> dict[str, Any] | None:
        display_name = self._display_name_from_value(str(name_fact.get("value_text", "") or ""))
        if not display_name:
            return None

        language = str(record.get("language", "unknown") or "unknown")
        aliases = ["user", "me", "myself"] if self._normalize_language(language) == "en" else ["user", "mnie", "sobie", "ja"]
        return self._build_person_entity(
            display_name=display_name,
            language=language,
            aliases=aliases,
            record=record,
            metadata={
                "source": "user_name_fact",
                "person_scope": "user",
                "source_record_id": str(record.get("id", "") or ""),
            },
        )

    def _build_person_entity(
        self,
        *,
        display_name: str,
        language: str,
        aliases: list[str],
        record: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        clean_name = self._compact_original_text(display_name)
        normalized_name = self._normalize_fact_subject(clean_name)
        normalized_language = self._normalize_language(language) or "unknown"
        if not clean_name or not normalized_name:
            return None

        clean_aliases = sorted({
            alias
            for alias in (self._normalize_fact_subject(alias) for alias in aliases + [clean_name, normalized_name])
            if alias
        })
        entity_id = self._build_entity_id(
            entity_type="person",
            display_name=normalized_name,
            language=normalized_language,
        )
        return {
            "id": entity_id,
            "entity_type": "person",
            "display_name": clean_name,
            "aliases": clean_aliases,
            "language": normalized_language,
            "created_at_iso": str(record.get("created_at_iso", "") or self._now_iso()),
            "metadata": dict(metadata or {}),
        }

    def _format_known_people_answer(
        self,
        people: list[dict[str, Any]],
        *,
        language: str,
    ) -> str:
        names: list[str] = []
        for person in people:
            name = str(person.get("display_name", "") or "").strip()
            if name and name not in names:
                names.append(name)

        if not names:
            return "I do not know any people yet." if language == "en" else "Nie znam jeszcze żadnych osób."

        preview = ", ".join(names[:8])
        if len(names) > 8:
            preview += f" i jeszcze {len(names) - 8}" if language != "en" else f" and {len(names) - 8} more"
        return f"I know: {preview}." if language == "en" else f"Znam: {preview}."

    @staticmethod
    def _display_name_from_value(value: str) -> str:
        clean = " ".join(str(value or "").split()).strip()
        if not clean:
            return ""
        return " ".join(part[:1].upper() + part[1:] for part in clean.split())

    def _find_person_entity_by_display_name(
        self,
        display_name: str,
        *,
        language: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_name = self._normalize_fact_subject(display_name)
        if not normalized_name:
            return None

        normalized_language = self._normalize_language(language)
        candidate_groups = [self.list_people(language=normalized_language)]
        if normalized_language is not None:
            candidate_groups.append(self.list_people(language=None))

        for people in candidate_groups:
            for person in people:
                names = [
                    str(person.get("display_name", "") or ""),
                    *[str(alias) for alias in list(person.get("aliases", []) or [])],
                ]
                normalized_names = {
                    value
                    for value in (self._normalize_fact_subject(name) for name in names)
                    if value
                }
                if normalized_name in normalized_names:
                    return dict(person)
        return None

    @staticmethod
    def _build_asset_id(
        *,
        entity_id: str,
        asset_type: str,
        path: str,
    ) -> str:
        digest = hashlib.sha1(
            f"{entity_id}|{asset_type}|{path}".encode("utf-8")
        ).hexdigest()[:16]
        return f"asset_{digest}"

    @staticmethod
    def _build_entity_id(
        *,
        entity_type: str,
        display_name: str,
        language: str,
    ) -> str:
        digest = hashlib.sha1(
            f"{language}|{entity_type}|{display_name}".encode("utf-8")
        ).hexdigest()[:16]
        return f"entity_{digest}"

    # ------------------------------------------------------------------
    # Structured fact extraction
    # ------------------------------------------------------------------

    def _build_facts_from_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for record in records:
            facts.extend(self._extract_structured_facts(record))
        return facts

    def _extract_structured_facts(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        extractors = (
            self._extract_location_fact,
            self._extract_preference_fact,
            self._extract_name_fact,
            self._extract_ownership_fact,
        )
        facts: list[dict[str, Any]] = []
        for extractor in extractors:
            fact = extractor(record)
            if fact is not None:
                facts.append(fact)
        return facts

    def _extract_location_fact(self, record: dict[str, Any]) -> dict[str, Any] | None:
        normalized_text = str(record.get("normalized_text", "") or "").strip()
        if not normalized_text:
            normalized_text = self._clean_text(record.get("original_text", ""))
        if not normalized_text:
            return None

        language = self._normalize_language(str(record.get("language", "") or "")) or "unknown"
        match: re.Match[str] | None = None
        if language == "pl":
            patterns = (
                r"^(?P<subject>.+?) (?:jest|sa) (?P<prep>w|we|na|pod|przy|obok|nad|za) (?P<place>.+)$",
                r"^mam (?P<subject>.+?) (?P<prep>w|we|na|pod|przy|obok|nad|za) (?P<place>.+)$",
            )
        elif language == "en":
            patterns = (
                r"^(?:my |the |a |an )?(?P<subject>.+?) (?:is|are) (?P<prep>in|on|under|inside|near|beside|at) (?:the |a |an |my )?(?P<place>.+)$",
                r"^i have (?:my |the |a |an )?(?P<subject>.+?) (?P<prep>in|on|under|inside|near|beside|at) (?:the |a |an |my )?(?P<place>.+)$",
            )
        else:
            patterns = (
                r"^(?P<subject>.+?) (?:is|are|jest|sa) (?P<prep>in|on|under|inside|near|beside|at|w|we|na|pod|przy|obok|nad|za) (?P<place>.+)$",
            )

        for pattern in patterns:
            match = re.match(pattern, normalized_text)
            if match is not None:
                break

        if match is None:
            return None

        subject = self._normalize_fact_subject(match.group("subject"))
        place = self._normalize_fact_value(match.group("place"))
        prep = self._normalize_fact_value(match.group("prep"))
        if not subject or not place or not prep:
            return None

        value_text = f"{prep} {place}".strip()
        return self._build_structured_fact(
            record=record,
            subject_text=subject,
            relation="location",
            value_text=value_text,
            source="memory_text_location_extractor",
        )

    def _extract_preference_fact(self, record: dict[str, Any]) -> dict[str, Any] | None:
        normalized_text = self._record_normalized_text(record)
        if not normalized_text:
            return None

        language = self._normalize_language(str(record.get("language", "") or "")) or "unknown"
        if language == "pl":
            patterns = (
                r"^(?:ja )?lubie (?P<value>.+)$",
                r"^interesuje sie (?P<value>.+)$",
                r"^moje hobby to (?P<value>.+)$",
            )
        elif language == "en":
            patterns = (
                r"^i like (?P<value>.+)$",
                r"^my hobby is (?P<value>.+)$",
                r"^i am interested in (?P<value>.+)$",
            )
        else:
            patterns = (
                r"^(?:i like|lubie) (?P<value>.+)$",
            )

        match = self._match_first(patterns, normalized_text)
        if match is None:
            return None

        value = self._normalize_fact_value(match.group("value"))
        if not value:
            return None

        return self._build_structured_fact(
            record=record,
            subject_text="user",
            relation="likes",
            value_text=value,
            source="memory_text_preference_extractor",
        )

    def _extract_name_fact(self, record: dict[str, Any]) -> dict[str, Any] | None:
        normalized_text = self._record_normalized_text(record)
        if not normalized_text:
            return None

        language = self._normalize_language(str(record.get("language", "") or "")) or "unknown"
        if language == "pl":
            patterns = (
                r"^mam na imie (?P<value>.+)$",
                r"^nazywam sie (?P<value>.+)$",
            )
        elif language == "en":
            patterns = (
                r"^my name is (?P<value>.+)$",
                r"^call me (?P<value>.+)$",
            )
        else:
            patterns = (
                r"^(?:my name is|mam na imie|nazywam sie) (?P<value>.+)$",
            )

        match = self._match_first(patterns, normalized_text)
        if match is None:
            return None

        value = self._normalize_fact_value(match.group("value"))
        if not value:
            return None

        return self._build_structured_fact(
            record=record,
            subject_text="user",
            relation="name",
            value_text=value,
            source="memory_text_name_extractor",
        )

    def _extract_ownership_fact(self, record: dict[str, Any]) -> dict[str, Any] | None:
        normalized_text = self._record_normalized_text(record)
        if not normalized_text:
            return None

        language = self._normalize_language(str(record.get("language", "") or "")) or "unknown"
        if language == "pl":
            patterns = (
                r"^to jest (?:moj|moja|moje) (?P<subject>.+)$",
                r"^(?P<subject>.+?) jest (?:moj|moja|moje)$",
                r"^(?P<subject>.+?) nalezy do (?P<owner>.+)$",
            )
        elif language == "en":
            patterns = (
                r"^this is my (?P<subject>.+)$",
                r"^(?P<subject>.+?) is mine$",
                r"^(?P<subject>.+?) belongs to (?P<owner>.+)$",
            )
        else:
            patterns = (
                r"^(?:this is my|to jest moj|to jest moja|to jest moje) (?P<subject>.+)$",
            )

        match = self._match_first(patterns, normalized_text)
        if match is None:
            return None

        subject = self._normalize_fact_subject(match.group("subject"))
        owner = self._normalize_fact_value(match.groupdict().get("owner") or "user")
        if not subject or not owner:
            return None

        return self._build_structured_fact(
            record=record,
            subject_text=subject,
            relation="owned_by",
            value_text=owner,
            source="memory_text_ownership_extractor",
        )

    def _record_normalized_text(self, record: dict[str, Any]) -> str:
        normalized_text = str(record.get("normalized_text", "") or "").strip()
        if normalized_text:
            return normalized_text
        return self._clean_text(record.get("original_text", ""))

    @staticmethod
    def _match_first(patterns: tuple[str, ...], text: str) -> re.Match[str] | None:
        for pattern in patterns:
            match = re.match(pattern, text)
            if match is not None:
                return match
        return None

    def _build_structured_fact(
        self,
        *,
        record: dict[str, Any],
        subject_text: str,
        relation: str,
        value_text: str,
        source: str,
    ) -> dict[str, Any] | None:
        subject = self._normalize_fact_subject(subject_text)
        value = self._normalize_fact_value(value_text)
        clean_relation = str(relation or "").strip()
        language = self._normalize_language(str(record.get("language", "") or "")) or "unknown"
        if not subject or not value or not clean_relation:
            return None

        fact_id = self._build_fact_id(
            subject_text=subject,
            relation=clean_relation,
            value_text=value,
            language=language,
        )
        return {
            "id": fact_id,
            "subject_entity_id": None,
            "subject_text": subject,
            "relation": clean_relation,
            "value_text": value,
            "language": language,
            "source_record_id": str(record.get("id", "") or ""),
            "confidence": max(0.0, min(1.0, float(record.get("confidence", 1.0) or 0.0))),
            "created_at_iso": str(record.get("created_at_iso", "") or self._now_iso()),
            "metadata": {
                "source": source,
                "source_text": str(record.get("original_text", "") or ""),
            },
        }

    def _normalize_fact_subject(self, text: str) -> str:
        tokens = self._tokenize(self._clean_text(text))
        return " ".join(tokens).strip()

    def _normalize_fact_value(self, text: str) -> str:
        cleaned = self._clean_text(text)
        tokens = [
            token
            for token in cleaned.split()
            if token not in {"the", "a", "an", "my", "moj", "moja", "moje"}
        ]
        return " ".join(tokens).strip()

    def _compose_fact_answer(self, fact: dict[str, Any]) -> str:
        subject = str(fact.get("subject_text", "") or "").strip()
        value = str(fact.get("value_text", "") or "").strip()
        relation = str(fact.get("relation", "") or "").strip()
        language = str(fact.get("language", "unknown") or "unknown")
        if not subject or not value:
            return ""
        if relation == "likes":
            return f"I like {value}" if language == "en" else f"lubię {value}"
        if relation == "name":
            return f"my name is {value}" if language == "en" else f"mam na imię {value}"
        if relation == "owned_by":
            owner = "me" if value == "user" and language == "en" else value
            owner = "mnie" if value == "user" and language != "en" else owner
            return f"{subject} belongs to {owner}" if language == "en" else f"{subject} należy do {owner}"
        connector = "is" if language == "en" else "jest"
        if language == "pl" and subject.endswith("e"):
            connector = "są"
        return f"{subject} {connector} {value}"

    @staticmethod
    def _build_fact_id(
        *,
        subject_text: str,
        relation: str,
        value_text: str,
        language: str,
    ) -> str:
        digest = hashlib.sha1(
            f"{language}|{subject_text}|{relation}|{value_text}".encode("utf-8")
        ).hexdigest()[:16]
        return f"fact_{digest}"

    def _detect_fact_query(
        self,
        normalized_query: str,
        query_tokens: list[str],
    ) -> dict[str, Any] | None:
        if self._looks_like_location_query(normalized_query):
            return {"relation": "location", "subject_tokens": query_tokens, "value_tokens": []}

        if self._looks_like_name_query(normalized_query):
            return {"relation": "name", "subject_tokens": ["user"], "value_tokens": []}

        if self._looks_like_preference_query(normalized_query):
            return {"relation": "likes", "subject_tokens": ["user"], "value_tokens": []}

        ownership_subject = self._extract_ownership_query_subject(normalized_query)
        if ownership_subject:
            return {
                "relation": "owned_by",
                "subject_tokens": self._tokenize(ownership_subject),
                "value_tokens": [],
            }

        about_subject = self._extract_about_query_subject(normalized_query)
        if about_subject:
            return {
                "relation": "",
                "subject_tokens": self._tokenize(about_subject),
                "value_tokens": [],
            }

        return None

    @staticmethod
    def _looks_like_people_list_query(normalized_query: str) -> bool:
        return normalized_query in {
            "kogo znasz",
            "jakie osoby znasz",
            "pokaż kogo znasz",
            "pokaz kogo znasz",
            "pokaż osoby które znasz",
            "pokaz osoby ktore znasz",
            "who do you know",
            "show people you know",
            "show known people",
            "what people do you know",
        }

    @staticmethod
    def _looks_like_location_query(normalized_query: str) -> bool:
        return bool(
            re.search(r"\bwhere\b", normalized_query)
            or re.search(r"\bgdzie\b", normalized_query)
            or re.search(r"\b(?:lezy|sa|jest)\b", normalized_query)
        )

    @staticmethod
    def _looks_like_name_query(normalized_query: str) -> bool:
        return normalized_query in {
            "jak mam na imie",
            "jak sie nazywam",
            "what is my name",
            "what do you call me",
        }

    @staticmethod
    def _looks_like_preference_query(normalized_query: str) -> bool:
        return normalized_query in {
            "co lubie",
            "co ja lubie",
            "co lubie robic",
            "what do i like",
            "what do i like doing",
        }

    def _extract_ownership_query_subject(self, normalized_query: str) -> str:
        patterns = (
            r"^czyj to (?P<subject>.+)$",
            r"^do kogo nalezy (?P<subject>.+)$",
            r"^whose (?P<subject>.+?) is this$",
            r"^who owns (?P<subject>.+)$",
        )
        match = self._match_first(patterns, normalized_query)
        if match is None:
            return ""
        return self._normalize_fact_subject(match.group("subject"))

    def _extract_about_query_subject(self, normalized_query: str) -> str:
        patterns = (
            r"^co wiesz o (?P<subject>.+)$",
            r"^what do you know about (?P<subject>.+)$",
        )
        match = self._match_first(patterns, normalized_query)
        if match is None:
            return ""
        subject = self._normalize_fact_subject(match.group("subject"))
        if subject in {"mnie", "sobie", "me", "myself"}:
            return "user"
        return subject

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
        best_record_token_count = 0

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

            # Exact match always wins immediately.
            if normalized_query == normalized_text:
                return self._to_match(
                    record,
                    score=1.0,
                    exact=True,
                    normalized_query=normalized_query,
                )

            # Score every candidate. Don't return the first containment hit —
            # otherwise a stale truncated record like "my phone is..." beats
            # a complete one like "my phone is on the desk." just because it
            # was saved first.
            if normalized_query in normalized_text:
                length_bonus = min(len(record_tokens) * 0.005, 0.03)
                combined_score = 0.94 + length_bonus
                if (
                    combined_score > best_score
                    or (
                        combined_score == best_score
                        and len(record_tokens) > best_record_token_count
                    )
                ):
                    best_score = combined_score
                    best_record_token_count = len(record_tokens)
                    best_match = self._to_match(
                        record,
                        score=combined_score,
                        exact=False,
                        normalized_query=normalized_query,
                    )
                continue

            overlap_score = self._token_overlap_score(query_tokens, record_tokens)
            similarity_score = SequenceMatcher(None, normalized_query, normalized_text).ratio()
            combined_score = max(overlap_score, similarity_score * 0.72)

            if (
                combined_score > best_score
                or (
                    combined_score == best_score
                    and len(record_tokens) > best_record_token_count
                )
            ):
                best_score = combined_score
                best_record_token_count = len(record_tokens)
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

        # Normalize by the smaller side (typically the query). This way a
        # complete record like "telefon jest na biurku" is not penalized
        # for being longer than the query "telefon" — it still scores 1.0
        # for full coverage of the query tokens.
        return float(len(common) / max(min(len(set(left_tokens)), len(set(right_tokens))), 1))

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

    def _repair_polish_memory_dictation(self, text: str) -> str:
        compact = self._compact_original_text(text)
        normalized = self._clean_text(compact)
        if not normalized:
            return compact

        repaired = normalized
        replacements = (
            (r"\bklu+l?czesa\b", "klucze sa"),
            (r"\bklulczesa\b", "klucze sa"),
            (r"\bkluucze\b", "klucze"),
            (r"\bkluczesa\b", "klucze sa"),
            (r"\bklucze sa\b", "klucze są"),
        )
        for pattern, replacement in replacements:
            repaired = re.sub(pattern, replacement, repaired)

        if repaired == normalized:
            return compact

        return self._compact_original_text(repaired)

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
