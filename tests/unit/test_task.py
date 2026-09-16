import time
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.task import Task, TaskStatus


def test_valid_task_creation() -> None:
    task = Task(description="Run the test suite")
    assert task.description == "Run the test suite"
    assert task.status == TaskStatus.PENDING
    assert isinstance(task.task_id, UUID)


def test_automatic_task_id() -> None:
    first = Task(description="first")
    second = Task(description="second")
    assert first.task_id != second.task_id


def test_automatic_timestamps() -> None:
    task = Task(description="timestamps")
    assert isinstance(task.created_at, datetime)
    assert isinstance(task.updated_at, datetime)
    assert task.created_at.tzinfo is not None
    assert task.updated_at.tzinfo is not None


def test_valid_status_changes() -> None:
    task = Task(description="lifecycle")
    task.change_status(TaskStatus.RUNNING)
    assert task.status == TaskStatus.RUNNING
    task.change_status(TaskStatus.COMPLETED)
    assert task.status == TaskStatus.COMPLETED


def test_status_change_updates_updated_at() -> None:
    task = Task(description="updated at")
    original = task.updated_at
    time.sleep(0.01)
    task.change_status(TaskStatus.RUNNING)
    assert task.updated_at > original
    assert task.created_at < task.updated_at


def test_invalid_status_rejected_on_creation() -> None:
    with pytest.raises(ValidationError):
        Task(description="bad", status="invalid-status")


def test_invalid_status_rejected_on_change() -> None:
    task = Task(description="bad change")
    with pytest.raises(ValidationError):
        task.status = "invalid-status"
    assert task.status == TaskStatus.PENDING


def test_blank_description_rejected() -> None:
    with pytest.raises(ValidationError):
        Task(description="")


def test_whitespace_only_description_rejected() -> None:
    with pytest.raises(ValidationError):
        Task(description="   ")