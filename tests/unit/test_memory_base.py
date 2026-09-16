import asyncio
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.memory.base import Memory, MemoryQueryResult, MemoryRecord


class InMemoryMemory(Memory):
    name = "in-memory"
    description = "A simple in-memory store for testing."

    def __init__(self) -> None:
        self._store: dict[UUID, MemoryRecord] = {}

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        self._store[record.memory_id] = record
        return record

    async def retrieve(
        self, query: str, *, limit: int = 10
    ) -> MemoryQueryResult:
        results = [
            record
            for record in self._store.values()
            if query.lower() in record.content.lower()
        ]
        return MemoryQueryResult.ok(results[:limit])

    async def delete(self, memory_id: UUID) -> bool:
        return self._store.pop(memory_id, None) is not None


class FailingMemory(Memory):
    name = "failing"
    description = "Always fails."

    async def store(self, record: MemoryRecord) -> MemoryRecord:
        raise RuntimeError("store failed")

    async def retrieve(
        self, query: str, *, limit: int = 10
    ) -> MemoryQueryResult:
        return MemoryQueryResult.fail(error="retrieve failed")

    async def delete(self, memory_id: UUID) -> bool:
        return False


def test_memory_is_abstract() -> None:
    with pytest.raises(TypeError):
        Memory()


def test_required_memory_metadata() -> None:
    assert InMemoryMemory.name == "in-memory"
    assert InMemoryMemory.description == "A simple in-memory store for testing."


def test_missing_metadata_rejected() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingName(Memory):
            description = "missing name"

            async def store(self, record: MemoryRecord) -> MemoryRecord:
                return record

            async def retrieve(
                self, query: str, *, limit: int = 10
            ) -> MemoryQueryResult:
                return MemoryQueryResult.ok([])

            async def delete(self, memory_id: UUID) -> bool:
                return False


def test_valid_memory_record_creation() -> None:
    record = MemoryRecord(content="test content")
    assert record.content == "test content"
    assert isinstance(record, MemoryRecord)


def test_automatic_memory_id() -> None:
    first = MemoryRecord(content="first")
    second = MemoryRecord(content="second")
    assert isinstance(first.memory_id, UUID)
    assert first.memory_id != second.memory_id


def test_automatic_timestamps() -> None:
    record = MemoryRecord(content="timestamped")
    assert record.created_at is not None
    assert record.updated_at is not None
    assert record.created_at.tzinfo is not None
    assert record.updated_at.tzinfo is not None


def test_metadata_defaults_to_empty_dict() -> None:
    record = MemoryRecord(content="with default metadata")
    assert record.metadata == {}


def test_metadata_accepts_arbitrary_values() -> None:
    record = MemoryRecord(
        content="tagged",
        metadata={"category": "note", "priority": 3},
    )
    assert record.metadata["category"] == "note"
    assert record.metadata["priority"] == 3


def test_empty_content_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(content="")


def test_whitespace_only_content_rejected() -> None:
    with pytest.raises(ValidationError):
        MemoryRecord(content="   ")


def test_sample_concrete_memory_satisfies_interface() -> None:
    memory = InMemoryMemory()
    assert isinstance(memory, Memory)


def test_storing_a_memory() -> None:
    memory = InMemoryMemory()
    record = MemoryRecord(content="remember this")
    result = asyncio.run(memory.store(record))
    assert result.content == "remember this"


def test_retrieving_memories() -> None:
    memory = InMemoryMemory()
    asyncio.run(memory.store(MemoryRecord(content="alpha note")))
    asyncio.run(memory.store(MemoryRecord(content="beta log")))
    asyncio.run(memory.store(MemoryRecord(content="alpha extra")))
    result = asyncio.run(memory.retrieve("alpha"))
    assert result.success is True
    assert result.count == 2
    assert all("alpha" in r.content for r in result.results)


def test_retrieving_with_limit() -> None:
    memory = InMemoryMemory()
    asyncio.run(memory.store(MemoryRecord(content="x note")))
    asyncio.run(memory.store(MemoryRecord(content="x log")))
    asyncio.run(memory.store(MemoryRecord(content="x extra")))
    result = asyncio.run(memory.retrieve("x", limit=2))
    assert result.count == 2


def test_deleting_a_memory() -> None:
    memory = InMemoryMemory()
    record = MemoryRecord(content="delete me")
    asyncio.run(memory.store(record))
    deleted = asyncio.run(memory.delete(record.memory_id))
    assert deleted is True
    result = asyncio.run(memory.retrieve("delete me"))
    assert result.count == 0


def test_deleting_nonexistent_memory_returns_false() -> None:
    memory = InMemoryMemory()
    deleted = asyncio.run(memory.delete(uuid4()))
    assert deleted is False


def test_failing_memory_returns_error() -> None:
    memory = FailingMemory()
    result = asyncio.run(memory.retrieve("anything"))
    assert result.success is False
    assert result.error is not None
    assert result.count == 0
    assert result.results == []