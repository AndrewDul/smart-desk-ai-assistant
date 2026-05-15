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

    @staticmethod
    def _clean_tokens(tokens: Iterable[Any]) -> list[str]:
        clean: list[str] = []
        for token in tokens:
            value = str(token or "").strip().lower()
            if value and value not in clean:
                clean.append(value)
        return clean

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
