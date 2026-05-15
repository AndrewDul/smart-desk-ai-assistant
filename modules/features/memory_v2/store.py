from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.shared.persistence.paths import DATA_DIR


@dataclass(frozen=True, slots=True)
class SQLiteMemoryPaths:
    root: Path
    database: Path
    assets: Path
    faces: Path
    objects: Path
    audio: Path
    video: Path


def default_memory_paths() -> SQLiteMemoryPaths:
    root = DATA_DIR / "nexa_memory"
    assets = root / "assets"
    return SQLiteMemoryPaths(
        root=root,
        database=root / "memory.sqlite3",
        assets=assets,
        faces=assets / "faces",
        objects=assets / "objects",
        audio=assets / "audio",
        video=assets / "video",
    )


class SQLiteMemoryStore:
    """Fast local SQLite index and future Memory v2 storage.

    This store is intentionally conservative in this sprint:
    - JSON memory records remain the compatibility source of truth.
    - SQLite mirrors searchable records for fast recall candidates.
    - Person/object/fact/asset tables are created now so future visual memory
      can extend the same database without another storage migration.
    """

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        root: str | Path | None = None,
    ) -> None:
        defaults = default_memory_paths()
        self.root = Path(root).expanduser() if root is not None else defaults.root
        self.path = Path(path).expanduser() if path is not None else self.root / "memory.sqlite3"
        self.assets_dir = self.root / "assets"
        self.faces_dir = self.assets_dir / "faces"
        self.objects_dir = self.assets_dir / "objects"
        self.audio_dir = self.assets_dir / "audio"
        self.video_dir = self.assets_dir / "video"

    def ensure_ready(self) -> None:
        self._ensure_directories()
        self._ensure_schema()

    def replace_all_records(self, records: Iterable[dict[str, Any]]) -> None:
        self.ensure_ready()
        normalized_records = [dict(record) for record in records if isinstance(record, dict)]
        with self._connect() as connection:
            connection.execute("DELETE FROM memory_tokens")
            connection.execute("DELETE FROM memory_records")
            for record in normalized_records:
                self._upsert_record(connection, record)

    def upsert_record(self, record: dict[str, Any]) -> None:
        self.ensure_ready()
        with self._connect() as connection:
            self._upsert_record(connection, record)

    def delete_record(self, record_id: str) -> None:
        clean_id = str(record_id or "").strip()
        if not clean_id:
            return

        self.ensure_ready()
        with self._connect() as connection:
            connection.execute("DELETE FROM memory_tokens WHERE record_id = ?", (clean_id,))
            connection.execute("DELETE FROM memory_records WHERE id = ?", (clean_id,))

    def clear_records(self) -> None:
        self.ensure_ready()
        with self._connect() as connection:
            connection.execute("DELETE FROM memory_tokens")
            connection.execute("DELETE FROM memory_records")
            connection.execute("DELETE FROM memory_facts")
            connection.execute("DELETE FROM memory_relationships")
            connection.execute("DELETE FROM memory_assets")
            connection.execute("DELETE FROM memory_entities")

    def replace_all_entities(self, entities: Iterable[dict[str, Any]]) -> None:
        self.ensure_ready()
        normalized_entities = [dict(entity) for entity in entities if isinstance(entity, dict)]
        with self._connect() as connection:
            connection.execute("DELETE FROM memory_relationships")
            connection.execute("DELETE FROM memory_assets")
            connection.execute("DELETE FROM memory_entities")
            for entity in normalized_entities:
                self._upsert_entity(connection, entity)

    def upsert_entity(self, entity: dict[str, Any]) -> None:
        self.ensure_ready()
        with self._connect() as connection:
            self._upsert_entity(connection, entity)

    def list_entities(
        self,
        *,
        entity_type: str | None = None,
        language: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        params: list[Any] = []
        where_parts: list[str] = []
        if entity_type:
            where_parts.append("entity_type = ?")
            params.append(str(entity_type))
        if language:
            where_parts.append("language = ?")
            params.append(str(language))

        where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        sql = f"""
            SELECT id, entity_type, display_name, aliases_json, language,
                   metadata_json, created_at_iso, updated_at_iso
            FROM memory_entities
            {where_sql}
            ORDER BY updated_at_iso DESC, display_name ASC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def find_entities(
        self,
        *,
        entity_type: str | None = None,
        query_tokens: Iterable[str] | None = None,
        language: str | None = None,
        limit: int = 16,
    ) -> list[dict[str, Any]]:
        clean_query_tokens = self._clean_tokens(query_tokens or [])
        if not entity_type and not clean_query_tokens:
            return []

        self.ensure_ready()
        params: list[Any] = []
        where_parts: list[str] = []
        if entity_type:
            where_parts.append("entity_type = ?")
            params.append(str(entity_type))
        if language:
            where_parts.append("language = ?")
            params.append(str(language))

        token_conditions: list[str] = []
        for token in clean_query_tokens:
            token_conditions.append("LOWER(display_name) = ?")
            params.append(token)
            token_conditions.append("LOWER(display_name) LIKE ?")
            params.append(token + "%")
            token_conditions.append("LOWER(aliases_json) LIKE ?")
            params.append("%" + token + "%")
        if token_conditions:
            where_parts.append("(" + " OR ".join(token_conditions) + ")")

        where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        params.append(max(1, int(limit)))
        sql = f"""
            SELECT id, entity_type, display_name, aliases_json, language,
                   metadata_json, created_at_iso, updated_at_iso
            FROM memory_entities
            {where_sql}
            ORDER BY updated_at_iso DESC, display_name ASC
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def replace_all_facts(self, facts: Iterable[dict[str, Any]]) -> None:
        self.ensure_ready()
        normalized_facts = [dict(fact) for fact in facts if isinstance(fact, dict)]
        with self._connect() as connection:
            connection.execute("DELETE FROM memory_facts")
            for fact in normalized_facts:
                self._upsert_fact(connection, fact)

    def upsert_fact(self, fact: dict[str, Any]) -> None:
        self.ensure_ready()
        with self._connect() as connection:
            self._upsert_fact(connection, fact)

    def find_location_facts(
        self,
        *,
        subject_tokens: Iterable[str],
        language: str | None = None,
        limit: int = 16,
    ) -> list[dict[str, Any]]:
        return self.find_facts(
            relation="location",
            subject_tokens=subject_tokens,
            language=language,
            limit=limit,
        )

    def find_facts(
        self,
        *,
        relation: str | None = None,
        subject_tokens: Iterable[str] | None = None,
        value_tokens: Iterable[str] | None = None,
        language: str | None = None,
        limit: int = 16,
    ) -> list[dict[str, Any]]:
        clean_subject_tokens = self._clean_tokens(subject_tokens or [])
        clean_value_tokens = self._clean_tokens(value_tokens or [])
        if not relation and not clean_subject_tokens and not clean_value_tokens:
            return []

        self.ensure_ready()
        params: list[Any] = []
        where_parts: list[str] = []

        clean_relation = str(relation or "").strip()
        if clean_relation:
            where_parts.append("f.relation = ?")
            params.append(clean_relation)

        subject_conditions = self._build_text_match_conditions(
            column="f.subject_text",
            tokens=clean_subject_tokens,
            params=params,
        )
        if subject_conditions:
            where_parts.append(f"({subject_conditions})")

        value_conditions = self._build_text_match_conditions(
            column="f.value_text",
            tokens=clean_value_tokens,
            params=params,
        )
        if value_conditions:
            where_parts.append(f"({value_conditions})")

        if language:
            where_parts.append("f.language = ?")
            params.append(str(language))

        params.append(max(1, int(limit)))
        where_sql = " AND ".join(where_parts) if where_parts else "1 = 1"

        sql = f"""
            SELECT f.id,
                   f.subject_entity_id,
                   f.subject_text,
                   f.relation,
                   f.value_text,
                   f.language,
                   f.source_record_id,
                   f.confidence,
                   f.metadata_json,
                   f.created_at_iso,
                   f.updated_at_iso,
                   r.original_text AS source_original_text,
                   r.normalized_text AS source_normalized_text
            FROM memory_facts f
            LEFT JOIN memory_records r ON r.id = f.source_record_id
            WHERE {where_sql}
            ORDER BY f.updated_at_iso DESC, f.confidence DESC
            LIMIT ?
        """

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_fact(row) for row in rows]

    @staticmethod
    def _build_text_match_conditions(
        *,
        column: str,
        tokens: list[str],
        params: list[Any],
    ) -> str:
        conditions: list[str] = []
        for token in tokens:
            conditions.append(f"{column} = ?")
            params.append(token)
            if len(token) >= 3:
                conditions.append(f"{column} LIKE ?")
                params.append(token + "%")
                conditions.append(f"{column} LIKE ?")
                params.append("% " + token)
                conditions.append(f"{column} LIKE ?")
                params.append("% " + token + " %")
        return " OR ".join(conditions)

    def list_records(self, *, language: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        self.ensure_ready()
        params: list[Any] = []
        where = ""
        if language:
            where = "WHERE language = ?"
            params.append(str(language))

        sql = f"""
            SELECT id, language, original_text, normalized_text, tokens_json,
                   source, confidence, metadata_json, created_at_iso
            FROM memory_records
            {where}
            ORDER BY created_at_iso DESC, id DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(1, int(limit)))

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def find_candidate_records(
        self,
        *,
        tokens: Iterable[str],
        language: str | None = None,
        limit: int = 64,
    ) -> list[dict[str, Any]]:
        clean_tokens = self._clean_tokens(tokens)
        if not clean_tokens:
            return []

        self.ensure_ready()
        placeholders = ",".join("?" for _ in clean_tokens)
        params: list[Any] = list(clean_tokens)
        language_filter = ""
        if language:
            language_filter = "AND r.language = ?"
            params.append(str(language))
        params.append(max(1, int(limit)))

        sql = f"""
            SELECT r.id,
                   r.language,
                   r.original_text,
                   r.normalized_text,
                   r.tokens_json,
                   r.source,
                   r.confidence,
                   r.metadata_json,
                   r.created_at_iso,
                   COUNT(DISTINCT t.token) AS token_hits
            FROM memory_tokens t
            JOIN memory_records r ON r.id = t.record_id
            WHERE t.token IN ({placeholders})
              {language_filter}
            GROUP BY r.id
            ORDER BY token_hits DESC, r.created_at_iso DESC
            LIMIT ?
        """

        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def record_count(self) -> int:
        self.ensure_ready()
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM memory_records").fetchone()
        return int(row["count"] if row is not None else 0)

    def entity_count(self) -> int:
        self.ensure_ready()
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM memory_entities").fetchone()
        return int(row["count"] if row is not None else 0)

    def fact_count(self) -> int:
        self.ensure_ready()
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM memory_facts").fetchone()
        return int(row["count"] if row is not None else 0)

    def _ensure_directories(self) -> None:
        for directory in (
            self.root,
            self.assets_dir,
            self.faces_dir,
            self.objects_dir,
            self.audio_dir,
            self.video_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    language TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    tokens_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL,
                    updated_at_iso TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_tokens (
                    token TEXT NOT NULL,
                    language TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    PRIMARY KEY (token, language, record_id),
                    FOREIGN KEY (record_id) REFERENCES memory_records(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    language TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL,
                    updated_at_iso TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_facts (
                    id TEXT PRIMARY KEY,
                    subject_entity_id TEXT,
                    subject_text TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    value_text TEXT NOT NULL,
                    language TEXT NOT NULL,
                    source_record_id TEXT,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL,
                    updated_at_iso TEXT NOT NULL,
                    FOREIGN KEY (subject_entity_id) REFERENCES memory_entities(id) ON DELETE SET NULL,
                    FOREIGN KEY (source_record_id) REFERENCES memory_records(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS memory_relationships (
                    id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL,
                    updated_at_iso TEXT NOT NULL,
                    FOREIGN KEY (source_entity_id) REFERENCES memory_entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_entity_id) REFERENCES memory_entities(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_assets (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT,
                    asset_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at_iso TEXT NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES memory_entities(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_tokens_lookup
                    ON memory_tokens(language, token);
                CREATE INDEX IF NOT EXISTS idx_memory_records_language
                    ON memory_records(language, created_at_iso);
                CREATE INDEX IF NOT EXISTS idx_memory_entities_type_name
                    ON memory_entities(entity_type, display_name);
                CREATE INDEX IF NOT EXISTS idx_memory_facts_subject_relation
                    ON memory_facts(subject_text, relation);
                CREATE INDEX IF NOT EXISTS idx_memory_assets_entity
                    ON memory_assets(entity_id, asset_type);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _upsert_record(self, connection: sqlite3.Connection, record: dict[str, Any]) -> None:
        record_id = str(record.get("id", "") or "").strip()
        original_text = str(record.get("original_text", "") or "").strip()
        normalized_text = str(record.get("normalized_text", "") or "").strip()
        language = str(record.get("language", "unknown") or "unknown").strip() or "unknown"
        tokens = self._clean_tokens(record.get("tokens", []) or [])
        if not record_id or not original_text or not normalized_text or not tokens:
            return

        now = self._now_iso()
        created_at_iso = str(record.get("created_at_iso", "") or now)
        connection.execute(
            """
            INSERT INTO memory_records (
                id, language, original_text, normalized_text, tokens_json,
                source, confidence, metadata_json, created_at_iso, updated_at_iso
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                language = excluded.language,
                original_text = excluded.original_text,
                normalized_text = excluded.normalized_text,
                tokens_json = excluded.tokens_json,
                source = excluded.source,
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json,
                updated_at_iso = excluded.updated_at_iso
            """,
            (
                record_id,
                language,
                original_text,
                normalized_text,
                json.dumps(tokens, ensure_ascii=False),
                str(record.get("source", "unknown") or "unknown"),
                float(record.get("confidence", 1.0) or 0.0),
                json.dumps(dict(record.get("metadata", {}) or {}), ensure_ascii=False),
                created_at_iso,
                now,
            ),
        )
        connection.execute("DELETE FROM memory_tokens WHERE record_id = ?", (record_id,))
        connection.executemany(
            """
            INSERT OR IGNORE INTO memory_tokens (token, language, record_id)
            VALUES (?, ?, ?)
            """,
            [(token, language, record_id) for token in tokens],
        )

    def _upsert_entity(self, connection: sqlite3.Connection, entity: dict[str, Any]) -> None:
        entity_id = str(entity.get("id", "") or "").strip()
        entity_type = str(entity.get("entity_type", "") or "").strip()
        display_name = str(entity.get("display_name", "") or "").strip()
        language = str(entity.get("language", "unknown") or "unknown").strip() or "unknown"
        aliases = self._clean_tokens(entity.get("aliases", []) or [])
        if not entity_id or not entity_type or not display_name:
            return

        now = self._now_iso()
        created_at_iso = str(entity.get("created_at_iso", "") or now)
        connection.execute(
            """
            INSERT INTO memory_entities (
                id, entity_type, display_name, aliases_json, language,
                metadata_json, created_at_iso, updated_at_iso
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                entity_type = excluded.entity_type,
                display_name = excluded.display_name,
                aliases_json = excluded.aliases_json,
                language = excluded.language,
                metadata_json = excluded.metadata_json,
                updated_at_iso = excluded.updated_at_iso
            """,
            (
                entity_id,
                entity_type,
                display_name,
                json.dumps(aliases, ensure_ascii=False),
                language,
                json.dumps(dict(entity.get("metadata", {}) or {}), ensure_ascii=False),
                created_at_iso,
                now,
            ),
        )

    def _upsert_fact(self, connection: sqlite3.Connection, fact: dict[str, Any]) -> None:
        fact_id = str(fact.get("id", "") or "").strip()
        subject_text = str(fact.get("subject_text", "") or "").strip()
        relation = str(fact.get("relation", "") or "").strip()
        value_text = str(fact.get("value_text", "") or "").strip()
        language = str(fact.get("language", "unknown") or "unknown").strip() or "unknown"
        if not fact_id or not subject_text or not relation or not value_text:
            return

        now = self._now_iso()
        created_at_iso = str(fact.get("created_at_iso", "") or now)
        connection.execute(
            """
            INSERT INTO memory_facts (
                id, subject_entity_id, subject_text, relation, value_text,
                language, source_record_id, confidence, metadata_json,
                created_at_iso, updated_at_iso
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                subject_entity_id = excluded.subject_entity_id,
                subject_text = excluded.subject_text,
                relation = excluded.relation,
                value_text = excluded.value_text,
                language = excluded.language,
                source_record_id = excluded.source_record_id,
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json,
                updated_at_iso = excluded.updated_at_iso
            """,
            (
                fact_id,
                fact.get("subject_entity_id"),
                subject_text,
                relation,
                value_text,
                language,
                fact.get("source_record_id"),
                float(fact.get("confidence", 1.0) or 0.0),
                json.dumps(dict(fact.get("metadata", {}) or {}), ensure_ascii=False),
                created_at_iso,
                now,
            ),
        )

    @staticmethod
    def _clean_tokens(tokens: Iterable[Any]) -> list[str]:
        clean: list[str] = []
        for token in tokens:
            value = str(token or "").strip().lower()
            if value and value not in clean:
                clean.append(value)
        return clean

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> dict[str, Any]:
        metadata: dict[str, Any]
        try:
            metadata = dict(json.loads(row["metadata_json"] or "{}"))
        except (TypeError, ValueError):
            metadata = {}

        try:
            aliases = list(json.loads(row["aliases_json"] or "[]"))
        except (TypeError, ValueError):
            aliases = []

        return {
            "id": str(row["id"]),
            "entity_type": str(row["entity_type"]),
            "display_name": str(row["display_name"]),
            "aliases": [str(alias) for alias in aliases if str(alias).strip()],
            "language": str(row["language"]),
            "metadata": metadata,
            "created_at_iso": str(row["created_at_iso"]),
            "updated_at_iso": str(row["updated_at_iso"]),
        }

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> dict[str, Any]:
        metadata: dict[str, Any]
        try:
            metadata = dict(json.loads(row["metadata_json"] or "{}"))
        except (TypeError, ValueError):
            metadata = {}

        return {
            "id": str(row["id"]),
            "subject_entity_id": row["subject_entity_id"],
            "subject_text": str(row["subject_text"]),
            "relation": str(row["relation"]),
            "value_text": str(row["value_text"]),
            "language": str(row["language"]),
            "source_record_id": row["source_record_id"],
            "confidence": float(row["confidence"]),
            "metadata": metadata,
            "created_at_iso": str(row["created_at_iso"]),
            "updated_at_iso": str(row["updated_at_iso"]),
            "source_original_text": str(row["source_original_text"] or ""),
            "source_normalized_text": str(row["source_normalized_text"] or ""),
        }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        metadata: dict[str, Any]
        try:
            metadata = dict(json.loads(row["metadata_json"] or "{}"))
        except (TypeError, ValueError):
            metadata = {}

        try:
            tokens = list(json.loads(row["tokens_json"] or "[]"))
        except (TypeError, ValueError):
            tokens = []

        return {
            "id": str(row["id"]),
            "language": str(row["language"]),
            "original_text": str(row["original_text"]),
            "normalized_text": str(row["normalized_text"]),
            "tokens": [str(token) for token in tokens if str(token).strip()],
            "source": str(row["source"]),
            "created_at_iso": str(row["created_at_iso"]),
            "confidence": float(row["confidence"]),
            "metadata": metadata,
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = ["SQLiteMemoryStore", "SQLiteMemoryPaths", "default_memory_paths"]
