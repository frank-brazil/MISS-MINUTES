import asyncio
import json
import logging
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.memory.base import (
    Memory,
    MemoryBackendError,
    MemoryQueryResult,
    MemoryRecord,
)

DEFAULT_MEMORY_DB_ENV = "MISSMINUTES_MEMORY_DB"
DEFAULT_MEMORY_DB_PATH = "data/missminutes_memory.db"

_TABLE_NAME = "memories"


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _connect(db_path: str) -> sqlite3.Connection:
    try:
        return sqlite3.connect(db_path, autocommit=True)
    except TypeError:
        return sqlite3.connect(db_path, isolation_level=None)


class SQLiteMemory(Memory):
    name = "sqlite"
    description = "SQLite-backed persistent memory storage for local use."

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self._logger = logging.getLogger(__name__)
        self._path = self._resolve_path(db_path)
        self._initialize()
        self._logger.info("Initialized SQLite memory database at %s", self._path)

    @classmethod
    def from_env(
        cls,
        *,
        env_var: str = DEFAULT_MEMORY_DB_ENV,
        default: str = DEFAULT_MEMORY_DB_PATH,
    ) -> "SQLiteMemory":
        path = os.getenv(env_var) or default
        return cls(path)

    @staticmethod
    def _resolve_path(db_path: str | os.PathLike[str]) -> str:
        raw = os.fspath(db_path)
        if raw == ":memory:":
            raise ValueError(
                "SQLiteMemory requires a file-based database path; "
                "':memory:' is not supported"
            )
        path = Path(raw).expanduser()
        parent = path.parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _initialize(self) -> None:
        try:
            with closing(_connect(self._path)) as connection:
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {_TABLE_NAME} ("
                    " memory_id TEXT PRIMARY KEY,"
                    " content TEXT NOT NULL,"
                    " created_at TEXT NOT NULL,"
                    " updated_at TEXT NOT NULL,"
                    " metadata TEXT NOT NULL DEFAULT '{}')"
                )
        except sqlite3.Error as exc:
            self._logger.error(
                "Failed to initialize SQLite memory database: %s",
                type(exc).__name__,
            )
            raise MemoryBackendError(
                f"failed to initialize memory database: {type(exc).__name__}"
            ) from exc

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        try:
            return await asyncio.to_thread(self._store_sync, record)
        except MemoryBackendError:
            raise
        except Exception as exc:
            self._logger.warning(
                "Memory store failed: %s", type(exc).__name__
            )
            raise MemoryBackendError("memory store failed") from exc

    async def retrieve(
        self, query: str, *, limit: int = 10
    ) -> MemoryQueryResult:
        effective_limit = max(0, limit)
        try:
            return await asyncio.to_thread(
                self._retrieve_sync, query, effective_limit
            )
        except Exception as exc:
            self._logger.warning(
                "Memory retrieval failed: %s", type(exc).__name__
            )
            return MemoryQueryResult.fail(error="memory retrieval failed")

    async def delete(self, memory_id: UUID) -> bool:
        try:
            return await asyncio.to_thread(self._delete_sync, memory_id)
        except MemoryBackendError:
            raise
        except Exception as exc:
            self._logger.warning(
                "Memory delete failed: %s", type(exc).__name__
            )
            raise MemoryBackendError("memory delete failed") from exc

    def _store_sync(self, record: MemoryRecord) -> MemoryRecord:
        try:
            metadata = json.dumps(record.metadata)
        except TypeError as exc:
            raise MemoryBackendError(
                "memory metadata is not JSON serializable"
            ) from exc
        created_at = _to_utc(record.created_at).isoformat()
        updated_at = _to_utc(record.updated_at).isoformat()
        try:
            with closing(_connect(self._path)) as connection:
                connection.execute(
                    f"INSERT OR REPLACE INTO {_TABLE_NAME}"
                    " (memory_id, content, created_at, updated_at, metadata)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        str(record.memory_id),
                        record.content,
                        created_at,
                        updated_at,
                        metadata,
                    ),
                )
                connection.commit()
        except sqlite3.Error as exc:
            self._logger.warning(
                "Memory store failed: %s", type(exc).__name__
            )
            raise MemoryBackendError("memory store failed") from exc
        return record

    def _retrieve_sync(self, query: str, limit: int) -> MemoryQueryResult:
        try:
            with closing(_connect(self._path)) as connection:
                rows = connection.execute(
                    f"SELECT memory_id, content, created_at, updated_at, metadata"
                    f" FROM {_TABLE_NAME}"
                    " WHERE instr(lower(content), lower(?)) > 0"
                    " ORDER BY created_at DESC, memory_id"
                    " LIMIT ?",
                    (query, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            self._logger.warning(
                "Memory retrieval failed: %s", type(exc).__name__
            )
            return MemoryQueryResult.fail(error="memory retrieval failed")
        records = [self._row_to_record(row) for row in rows]
        return MemoryQueryResult.ok(records)

    def _delete_sync(self, memory_id: UUID) -> bool:
        try:
            with closing(_connect(self._path)) as connection:
                cursor = connection.execute(
                    f"DELETE FROM {_TABLE_NAME} WHERE memory_id = ?",
                    (str(memory_id),),
                )
                connection.commit()
        except sqlite3.Error as exc:
            self._logger.warning(
                "Memory delete failed: %s", type(exc).__name__
            )
            raise MemoryBackendError("memory delete failed") from exc
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> MemoryRecord:
        memory_id = UUID(row[0])
        created_at = _to_utc(datetime.fromisoformat(row[2]))
        updated_at = _to_utc(datetime.fromisoformat(row[3]))
        metadata = json.loads(row[4])
        return MemoryRecord(
            memory_id=memory_id,
            content=row[1],
            created_at=created_at,
            updated_at=updated_at,
            metadata=metadata,
        )
