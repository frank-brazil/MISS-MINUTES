import asyncio

import pytest
from app.distributed.auth import (
    AUTH_HEADER,
    build_auth_dependency,
    request_headers,
)
from app.distributed.config import DistributedConfig
from fastapi import HTTPException


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


def _run(coro):
    return asyncio.run(coro)


def test_request_headers_empty_when_no_token():
    config = DistributedConfig()
    assert request_headers(config) == {}


def test_request_headers_include_token_when_configured():
    config = DistributedConfig(auth_token="abc123")
    headers = request_headers(config)
    assert headers == {AUTH_HEADER: "abc123"}


def test_auth_dependency_disabled_when_no_token():
    guard = build_auth_dependency(DistributedConfig())
    # No exception even without a header.
    _run(guard(_FakeRequest()))


def test_auth_dependency_requires_matching_token():
    guard = build_auth_dependency(DistributedConfig(auth_token="secret"))

    with pytest.raises(HTTPException) as missing:
        _run(guard(_FakeRequest()))
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as wrong:
        _run(guard(_FakeRequest({AUTH_HEADER: "nope"})))
    assert wrong.value.status_code == 401

    # Correct token passes.
    _run(guard(_FakeRequest({AUTH_HEADER: "secret"})))


def test_token_never_leaks_into_headers_representation():
    config = DistributedConfig(auth_token="topsecret")
    headers = request_headers(config)
    # The token is present for the outgoing request, but never as a field
    # name or in an unrelated header.
    assert list(headers) == [AUTH_HEADER]
    assert "topsecret" not in AUTH_HEADER
