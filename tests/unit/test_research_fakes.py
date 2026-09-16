import asyncio

import pytest

from app.research.base import (
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
    SearchResult,
    Source,
)
from app.research.fakes import FakeResearchProvider


def result(title: str, score: float | None = None) -> SearchResult:
    return SearchResult(
        source=Source(title=title, url=f"https://example.com/{title}"),
        score=score,
    )


FIXTURES = {
    "latest AI news": [result("AI news A", 0.9), result("AI news B", 0.7)],
    "weather in delhi": [result("weather report", 0.6)],
}


def test_fake_research_provider_satisfies_interface() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    assert isinstance(provider, ResearchProvider)
    assert provider.name == "fake-research-provider"
    assert provider.description


def test_fake_research_provider_returns_fixture_results() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(
        provider.research(SearchRequest(query="latest AI news"))
    )
    assert response.success is True
    assert response.result_count == 2
    assert response.error is None
    assert response.query == "latest AI news"
    assert [item.title for item in response.results] == [
        "AI news A",
        "AI news B",
    ]


def test_fake_research_provider_unknown_query_returns_no_results() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(
        provider.research(SearchRequest(query="no such query"))
    )
    assert response.success is True
    assert response.results == []
    assert response.result_count == 0
    assert response.error is None


def test_fake_research_provider_default_results_for_unmatched_query() -> None:
    provider = FakeResearchProvider(
        fixtures=FIXTURES,
        default_results=[result("fallback result", 0.5)],
    )
    response = asyncio.run(
        provider.research(SearchRequest(query="unknown topic"))
    )
    assert response.success is True
    assert response.result_count == 1
    assert response.results[0].title == "fallback result"


def test_fake_research_provider_truncates_to_max_results() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(
        provider.research(
            SearchRequest(query="latest AI news", max_results=1)
        )
    )
    assert response.success is True
    assert response.result_count == 1
    assert response.results[0].title == "AI news A"


def test_fake_research_provider_orders_and_ranks_results() -> None:
    provider = FakeResearchProvider(
        fixtures={
            "mixed": [
                result("low", 0.4),
                result("top", 0.9),
                result("mid", 0.7),
            ]
        }
    )
    response = asyncio.run(
        provider.research(SearchRequest(query="mixed"))
    )
    assert [item.title for item in response.results] == ["top", "mid", "low"]
    assert [item.rank for item in response.results] == [1, 2, 3]


def test_fake_research_provider_preserves_order_when_sort_disabled() -> None:
    provider = FakeResearchProvider(
        fixtures={
            "preordered": [
                result("first", 0.1),
                result("second", 0.9),
            ]
        },
        sort_by_score=False,
    )
    response = asyncio.run(
        provider.research(SearchRequest(query="preordered"))
    )
    assert [item.title for item in response.results] == ["first", "second"]
    assert [item.rank for item in response.results] == [1, 2]


def test_fake_research_provider_can_fail_on_demand() -> None:
    provider = FakeResearchProvider(fail=True)
    response = asyncio.run(
        provider.research(SearchRequest(query="latest AI news"))
    )
    assert isinstance(response, ResearchResponse)
    assert response.success is False
    assert response.error == "simulated research failure"
    assert response.results == []


def test_fake_research_provider_can_raise_configured_error() -> None:
    provider = FakeResearchProvider(raise_error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(provider.research(SearchRequest(query="latest AI news")))


def test_fake_research_provider_records_requests() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    asyncio.run(provider.research(SearchRequest(query="weather in delhi")))
    asyncio.run(provider.research(SearchRequest(query="latest AI news")))
    assert len(provider.requests) == 2
    assert provider.requests[0].query == "weather in delhi"
    assert provider.requests[1].query == "latest AI news"


def test_fake_research_provider_preserves_source_metadata() -> None:
    evidence = Source(
        title="weather report",
        url="https://example.com/weather-report",
        snippet="clear skies",
        domain="example.com",
    )
    provider = FakeResearchProvider(
        fixtures={"weather": [SearchResult(source=evidence, score=0.6)]}
    )
    response = asyncio.run(provider.research(SearchRequest(query="weather")))
    assert response.results[0].source.domain == "example.com"
    assert response.results[0].source.snippet == "clear skies"
