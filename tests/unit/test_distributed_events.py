from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.distributed.events import (
    DistributedEvent,
    DistributedEventType,
)


def test_event_types_cover_the_lifecycle():
    expected = {
        "WORKER_REGISTERED",
        "HEARTBEAT_RECEIVED",
        "TASK_QUEUED",
        "TASK_ASSIGNED",
        "TASK_STARTED",
        "TASK_COMPLETED",
        "TASK_FAILED",
        "TASK_RETRIED",
        "TASK_REQUEUED",
        "TASK_REROUTED",
        "TASK_CANCELLED",
        "WORKER_STALE",
        "WORKER_REMOVED",
    }
    assert {member.name for member in DistributedEventType} == expected


def test_event_defaults():
    event = DistributedEvent(
        event_type=DistributedEventType.TASK_QUEUED,
        message="queued",
    )
    assert event.event_id is not None
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo is not None
    assert event.success is None
    assert event.worker_id is None
    assert event.task_id is None
    assert event.attempt is None


def test_event_carries_safe_metadata_only():
    worker_id = uuid4()
    task_id = uuid4()
    event = DistributedEvent(
        event_type=DistributedEventType.TASK_COMPLETED,
        message="done",
        success=True,
        worker_id=worker_id,
        task_id=task_id,
        attempt=2,
    )
    assert event.worker_id == worker_id
    assert event.task_id == task_id
    assert event.attempt == 2


def test_event_rejects_blank_message():
    with pytest.raises(ValidationError):
        DistributedEvent(
            event_type=DistributedEventType.TASK_QUEUED,
            message="   ",
        )


def test_event_has_no_payload_leak_field():
    assert "payload" not in DistributedEvent.model_fields
    assert "auth_token" not in DistributedEvent.model_fields


def test_event_timestamp_is_utc():
    event = DistributedEvent(
        event_type=DistributedEventType.HEARTBEAT_RECEIVED,
        message="beat",
    )
    assert event.timestamp <= datetime.now(UTC)
