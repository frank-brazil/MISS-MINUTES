import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.memory.base import Memory, MemoryBackendError, MemoryQueryResult, MemoryRecord
from app.memory.sqlite_memory import DEFAULT_MEMORY_DB_ENV, SQLiteMemory


def make_memory(tmp_path: Path, name: str = "memory.db") -> SQLiteMemory:
    return SQLiteMemory(tmp_path / name)


@pytest.fixture
def memory(tmp_path: Path) -> SQLiteMemory:
    return make_memory(tmp_path)


def test_database_file_created(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "deep" / "memory.db"
    assert not db_path.exists()
    SQLiteMemory(db_path)
    assert db_path.exists()
    assert db_path.is_file()


def test_table_created(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    SQLiteMemory(db_path)
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type = 'table' AND name = 'memories'"
        ).fetchone()
    assert row is not None
    assert row[0] == "memories"


def test_initialization_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    SQLiteMemory(db_path)
    SQLiteMemory(db_path)
    SQLiteMemory(db_path)


def test_instances_satisfy_memory_interface(memory: SQLiteMemory) -> None:
    assert isinstance(memory, Memory)
    assert memory.name == "sqlite"
    assert memory.description


def test_store_a_memory(memory: SQLiteMemory) -> None:
    record = MemoryRecord(content="remember this")
    stored = asyncio.run(memory.store(record))
    assert isinstance(stored, MemoryRecord)
    assert stored.content == "remember this"
    assert stored.memory_id == record.memory_id


def test_retrieve_a_stored_memory(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="hello world")))
    result = asyncio.run(memory.retrieve("hello"))
    assert result.success is True
    assert result.count == 1
    assert result.error is None
    assert result.results[0].content == "hello world"


def test_retrieve_with_limit(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="alpha note")))
    asyncio.run(memory.store(MemoryRecord(content="alpha log")))
    asyncio.run(memory.store(MemoryRecord(content="alpha extra")))
    result = asyncio.run(memory.retrieve("alpha", limit=2))
    assert result.success is True
    assert result.count == 2
    assert len(result.results) == 2


def test_retrieve_with_limit_zero(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="alpha note")))
    result = asyncio.run(memory.retrieve("alpha", limit=0))
    assert result.success is True
    assert result.count == 0
    assert result.results == []


def test_retrieve_negative_limit_clamped(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="alpha note")))
    result = asyncio.run(memory.retrieve("alpha", limit=-5))
    assert result.success is True
    assert result.count == 0


def test_retrieve_matching_is_case_insensitive(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="Hello World")))
    result = asyncio.run(memory.retrieve("hello"))
    assert result.count == 1


def test_multiple_memory_records(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="alpha note")))
    asyncio.run(memory.store(MemoryRecord(content="beta log")))
    asyncio.run(memory.store(MemoryRecord(content="alpha extra")))
    result = asyncio.run(memory.retrieve("alpha"))
    assert result.success is True
    assert result.count == 2
    assert all("alpha" in r.content for r in result.results)


def test_delete_a_memory(memory: SQLiteMemory) -> None:
    record = MemoryRecord(content="delete me")
    asyncio.run(memory.store(record))
    deleted = asyncio.run(memory.delete(record.memory_id))
    assert deleted is True


def test_deleted_memory_no_longer_returned(memory: SQLiteMemory) -> None:
    record = MemoryRecord(content="delete me")
    asyncio.run(memory.store(record))
    asyncio.run(memory.delete(record.memory_id))
    result = asyncio.run(memory.retrieve("delete"))
    assert result.success is True
    assert result.count == 0
    assert result.results == []


def test_delete_nonexistent_memory_returns_false(memory: SQLiteMemory) -> None:
    deleted = asyncio.run(memory.delete(uuid4()))
    assert deleted is False


def test_retrieve_no_results(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="something")))
    result = asyncio.run(memory.retrieve("nothing-here"))
    assert result.success is True
    assert result.count == 0
    assert result.results == []
    assert result.error is None


def test_metadata_persistence(memory: SQLiteMemory) -> None:
    record = MemoryRecord(
        content="tagged note",
        metadata={"category": "study", "priority": 3, "tags": ["cn", "networks"]},
    )
    asyncio.run(memory.store(record))
    result = asyncio.run(memory.retrieve("tagged"))
    assert result.count == 1
    assert result.results[0].metadata == {
        "category": "study",
        "priority": 3,
        "tags": ["cn", "networks"],
    }


def test_empty_metadata_persistence(memory: SQLiteMemory) -> None:
    asyncio.run(memory.store(MemoryRecord(content="plain note")))
    result = asyncio.run(memory.retrieve("plain"))
    assert result.results[0].metadata == {}


def test_timestamp_persistence(memory: SQLiteMemory) -> None:
    created_at = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC)
    updated_at = datetime(2026, 2, 3, 4, 5, 6, 654321, tzinfo=UTC)
    record = MemoryRecord(
        content="timestamped",
        created_at=created_at,
        updated_at=updated_at,
    )
    asyncio.run(memory.store(record))
    result = asyncio.run(memory.retrieve("timestamped"))
    stored = result.results[0]
    assert stored.created_at == created_at
    assert stored.updated_at == updated_at
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None


def test_naive_timestamp_assumed_utc(memory: SQLiteMemory) -> None:
    naive = datetime(2026, 5, 6, 7, 8, 9)
    record = MemoryRecord(content="naive time", created_at=naive, updated_at=naive)
    asyncio.run(memory.store(record))
    result = asyncio.run(memory.retrieve("naive"))
    stored = result.results[0]
    assert stored.created_at.tzinfo is not None
    assert stored.created_at.astimezone(UTC) == naive.replace(tzinfo=UTC)


def test_uuid_persistence(memory: SQLiteMemory) -> None:
    memory_id = uuid4()
    record = MemoryRecord(memory_id=memory_id, content="uuid note")
    asyncio.run(memory.store(record))
    result = asyncio.run(memory.retrieve("uuid"))
    assert result.results[0].memory_id == memory_id
    assert isinstance(result.results[0].memory_id, UUID)


def test_empty_content_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(content="")
    with pytest.raises(ValidationError):
        MemoryRecord(content="   ")


def test_non_serializable_metadata_controlled_failure(
    memory: SQLiteMemory,
) -> None:
    record = MemoryRecord(
        content="bad metadata",
        metadata={"bad": {1, 2, 3}},
    )
    with pytest.raises(MemoryBackendError):
        asyncio.run(memory.store(record))


def test_init_failure_when_parent_is_a_file(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file")
    with pytest.raises((OSError, MemoryBackendError)):
        SQLiteMemory(blocker / "memory.db")


def test_init_failure_when_path_is_a_directory(tmp_path: Path) -> None:
    directory = tmp_path / "adir"
    directory.mkdir()
    with pytest.raises(MemoryBackendError):
        SQLiteMemory(directory)


def test_memory_memory_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file-based"):
        SQLiteMemory(":memory:")


def test_retrieve_failure_returns_controlled_failure(
    memory: SQLiteMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(query: str, limit: int) -> MemoryQueryResult:
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(memory, "_retrieve_sync", boom)
    result = asyncio.run(memory.retrieve("anything"))
    assert result.success is False
    assert result.count == 0
    assert result.results == []
    assert result.error is not None


def test_corrupt_database_retrieve_returns_controlled_failure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "memory.db"
    memory = SQLiteMemory(db_path)
    asyncio.run(memory.store(MemoryRecord(content="hello")))
    db_path.write_bytes(b"this is not a sqlite database")
    result = asyncio.run(memory.retrieve("hello"))
    assert result.success is False
    assert result.count == 0
    assert result.results == []
    assert result.error is not None


def test_store_failure_is_controlled(
    memory: SQLiteMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(record: MemoryRecord) -> MemoryRecord:
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(memory, "_store_sync", boom)
    with pytest.raises(MemoryBackendError):
        asyncio.run(memory.store(MemoryRecord(content="another")))


def test_delete_failure_returns_controlled_exception(
    memory: SQLiteMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(memory_id: UUID) -> bool:
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(memory, "_delete_sync", boom)
    with pytest.raises(MemoryBackendError):
        asyncio.run(memory.delete(uuid4()))


def test_isolation_between_separate_databases(tmp_path: Path) -> None:
    first = SQLiteMemory(tmp_path / "first.db")
    second = SQLiteMemory(tmp_path / "second.db")
    asyncio.run(
        first.store(MemoryRecord(content="secret of first database"))
    )
    second_result = asyncio.run(second.retrieve("secret"))
    assert second_result.count == 0
    first_result = asyncio.run(first.retrieve("secret"))
    assert first_result.count == 1


def test_reopening_database_persists_data(tmp_path: Path) -> None:
    db_path = tmp_path / "persistent.db"
    first = SQLiteMemory(db_path)
    asyncio.run(first.store(MemoryRecord(content="persisted note")))
    second = SQLiteMemory(db_path)
    result = asyncio.run(second.retrieve("persisted"))
    assert result.count == 1
    assert result.results[0].content == "persisted note"


def test_from_env_uses_configured_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "env.db"
    monkeypatch.setenv(DEFAULT_MEMORY_DB_ENV, str(db_path))
    memory = SQLiteMemory.from_env()
    asyncio.run(memory.store(MemoryRecord(content="env note")))
    result = asyncio.run(memory.retrieve("env"))
    assert result.count == 1


def test_from_env_falls_back_to_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(DEFAULT_MEMORY_DB_ENV, raising=False)
    default = tmp_path / "default.db"
    memory = SQLiteMemory.from_env(default=str(default))
    asyncio.run(memory.store(MemoryRecord(content="default note")))
    result = asyncio.run(memory.retrieve("default"))
    assert result.count == 1
