import asyncio
from typing import Any

import pytest
from app.research.base import ABSOLUTE_MAX_RESULTS, SearchRequest
from app.research.http_provider import (
    DEFAULT_TIMEOUT_SECONDS,
    HttpSearchProvider,
)


class FakeHttpResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._error = error
        self._json_called = False

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> dict[str, Any]:
        self._json_called = True
        return self._payload or {}


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse | None = None) -> None:
        self.response = response or FakeHttpResponse(payload={"results": []})
        self.calls: list[dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> FakeHttpResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


def build_provider(
    *,
    client: FakeHttpClient,
    base_url: str = "https://search.example.test/api",
    api_key: str | None = "test-key",
    **kwargs: Any,
) -> HttpSearchProvider:
    return HttpSearchProvider(base_url=base_url, api_key=api_key, http_client=client, **kwargs)


def test_http_provider_reads_configuration_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISSMINUTES_SEARCH_URL", "https://env.example.test")
    monkeypatch.setenv("MISSMINUTES_SEARCH_API_KEY", "env-secret-key")
    client = FakeHttpClient(
        response=FakeHttpResponse(
            payload={"results": [{"title": "T", "url": "https://example.com/a"}]}
        )
    )
    provider = HttpSearchProvider(http_client=client)
    response = asyncio.run(provider.research(SearchRequest(query="news")))
    assert response.success is True
    assert response.results[0].title == "T"


def test_http_provider_constructor_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISSMINUTES_SEARCH_URL", "https://wrong.example.test")
    client = FakeHttpClient()
    provider = build_provider(client=client, base_url="https://right.example.test")
    asyncio.run(provider.research(SearchRequest(query="news")))
    assert provider.base_url == "https://right.example.test"
    assert client.calls[0]["url"] == "https://right.example.test"


def test_http_provider_unconfigured_returns_controlled_failure() -> None:
    provider = HttpSearchProvider(base_url=None, http_client=FakeHttpClient())
    response = asyncio.run(provider.research(SearchRequest(query="news")))
    assert response.success is False
    assert response.error is not None
    assert response.results == []
    assert response.query == "news"


def test_http_provider_posts_search_contract() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(
            payload={"results": [{"title": "T", "url": "https://example.com/a"}]}
        )
    )
    provider = build_provider(client=client)
    asyncio.run(provider.research(SearchRequest(query="weather", max_results=3)))
    call = client.calls[0]
    assert call["json"] == {"query": "weather", "max_results": 3}
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["headers"]["Accept"] == "application/json"


def test_http_provider_passes_timeout_to_client() -> None:
    client = FakeHttpClient()
    provider = build_provider(client=client, timeout=3.5)
    asyncio.run(provider.research(SearchRequest(query="news")))
    assert client.calls[0]["timeout"] == 3.5


def test_http_provider_default_timeout() -> None:
    client = FakeHttpClient()
    provider = build_provider(client=client)
    asyncio.run(provider.research(SearchRequest(query="news")))
    assert client.calls[0]["timeout"] == DEFAULT_TIMEOUT_SECONDS


def test_http_provider_parses_structured_sources() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(
            payload={
                "results": [
                    {
                        "title": "Current AI news",
                        "url": "https://example.com/ai",
                        "snippet": "snippet text",
                        "domain": "example.com",
                        "score": 0.8,
                    }
                ]
            }
        )
    )
    provider = build_provider(client=client)
    response = asyncio.run(provider.research(SearchRequest(query="ai news")))
    assert response.success is True
    assert response.result_count == 1
    result = response.results[0]
    assert result.title == "Current AI news"
    assert result.url == "https://example.com/ai"
    assert result.source.domain == "example.com"
    assert result.source.snippet == "snippet text"
    assert result.score == 0.8
    assert result.rank == 1


def test_http_provider_clamps_max_results() -> None:
    client = FakeHttpClient()
    provider = build_provider(client=client, max_results=3)
    asyncio.run(provider.research(SearchRequest(query="news", max_results=10)))
    assert client.calls[0]["json"]["max_results"] == 3
    assert provider.max_results == 3


def test_http_provider_respects_hard_ceiling() -> None:
    client = FakeHttpClient()
    provider = build_provider(client=client, max_results=ABSOLUTE_MAX_RESULTS * 5)
    assert provider.max_results == ABSOLUTE_MAX_RESULTS


def test_http_provider_skips_malformed_results() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(
            payload={
                "results": [
                    {"title": "Good", "url": "https://example.com/good"},
                    {"title": "Bad"},
                    "not-a-dict",
                ]
            }
        )
    )
    provider = build_provider(client=client)
    response = asyncio.run(provider.research(SearchRequest(query="news")))
    assert response.success is True
    assert response.result_count == 1
    assert response.results[0].title == "Good"


def test_http_provider_network_failure_is_controlled() -> None:
    client = FakeHttpClient(response=FakeHttpResponse(error=RuntimeError("connection refused")))
    provider = build_provider(client=client)
    response = asyncio.run(provider.research(SearchRequest(query="news")))
    assert response.success is False
    assert response.error == "search provider call failed"
    assert response.results == []


def test_http_provider_non_dict_payload_is_controlled() -> None:
    client = FakeHttpClient(response=FakeHttpResponse(payload={"odd": True}))
    provider = build_provider(client=client)
    response = asyncio.run(provider.research(SearchRequest(query="news")))
    assert response.success is False
    assert response.results == []


def test_http_provider_does_not_fabricate_sources() -> None:
    client = FakeHttpClient(
        response=FakeHttpResponse(
            payload={"results": [{"title": "Only", "url": "https://example.com/o"}]}
        )
    )
    provider = build_provider(client=client)
    response = asyncio.run(provider.research(SearchRequest(query="news")))
    assert response.results[0].title == "Only"
    assert response.result_count == 1


def test_http_provider_without_api_key_sends_no_auth_header() -> None:
    client = FakeHttpClient()
    provider = build_provider(client=client, api_key=None)
    asyncio.run(provider.research(SearchRequest(query="news")))
    assert "Authorization" not in client.calls[0]["headers"]


def test_http_provider_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        HttpSearchProvider(base_url="https://example.test", timeout=0, http_client=FakeHttpClient())
    with pytest.raises(ValueError, match="timeout"):
        HttpSearchProvider(
            base_url="https://example.test", timeout=-1, http_client=FakeHttpClient()
        )
