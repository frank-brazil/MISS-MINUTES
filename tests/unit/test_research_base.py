import asyncio

import pytest

from app.research.base import (
    ABSOLUTE_MAX_RESULTS,
    DEFAULT_MAX_RESULTS,
    ResearchError,
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
    SearchResult,
    Source,
    assign_ranks,
    is_http_url,
    order_results,
)


def source(title: str = "Example title") -> Source:
    return Source(title=title, url="https://example.com/page")


def test_search_request_defaults() -> None:
    request = SearchRequest(query="latest AI news")
    assert request.query == "latest AI news"
    assert request.max_results == DEFAULT_MAX_RESULTS


def test_search_request_custom_max_results() -> None:
    request = SearchRequest(query="weather", max_results=8)
    assert request.max_results == 8


def test_search_request_accepts_maximum_limit() -> None:
    request = SearchRequest(query="research", max_results=ABSOLUTE_MAX_RESULTS)
    assert request.max_results == ABSOLUTE_MAX_RESULTS


def test_search_request_strips_query() -> None:
    request = SearchRequest(query="  weather  ")
    assert request.query == "weather"


def test_search_request_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query"):
        SearchRequest(query="")


def test_search_request_rejects_blank_query() -> None:
    with pytest.raises(ValueError, match="query"):
        SearchRequest(query="   ")


def test_search_request_rejects_zero_max_results() -> None:
    with pytest.raises(ValueError, match="max_results"):
        SearchRequest(query="weather", max_results=0)


def test_search_request_rejects_negative_max_results() -> None:
    with pytest.raises(ValueError, match="max_results"):
        SearchRequest(query="weather", max_results=-3)


def test_search_request_rejects_unbounded_max_results() -> None:
    with pytest.raises(ValueError, match="max_results"):
        SearchRequest(query="weather", max_results=ABSOLUTE_MAX_RESULTS + 1)


def test_source_valid_with_url() -> None:
    item = Source(title="T", url="https://example.com/a")
    assert item.title == "T"
    assert item.url == "https://example.com/a"
    assert item.reference is None
    assert item.retrieved_at is not None


def test_source_valid_with_reference_only() -> None:
    item = Source(title="Paper", reference="https://arxiv.org/abs/2301.10000")
    assert item.url is None
    assert item.reference == "https://arxiv.org/abs/2301.10000"


def test_source_valid_with_reference_doi() -> None:
    item = Source(title="Paper", reference="doi:10.1000/xyz123")
    assert item.reference == "doi:10.1000/xyz123"


def test_source_requires_url_or_reference() -> None:
    with pytest.raises(ValueError, match="url or a reference"):
        Source(title="T")


def test_source_rejects_blank_title() -> None:
    with pytest.raises(ValueError, match="title"):
        Source(title="  ", url="https://example.com/a")


def test_source_rejects_invalid_url() -> None:
    with pytest.raises(ValueError, match="url"):
        Source(title="T", url="ftp://example.com/a")


def test_source_rejects_non_url_value() -> None:
    with pytest.raises(ValueError, match="url"):
        Source(title="T", url="not a url")


def test_source_accepts_http_url() -> None:
    item = Source(title="T", url="http://example.com/a")
    assert item.url == "http://example.com/a"


def test_source_optional_evidence_fields() -> None:
    item = Source(
        title="T",
        url="https://example.com/a",
        snippet="a snippet",
        summary="a summary",
        domain="example.com",
        metadata={"retrieved_by": "test"},
    )
    assert item.snippet == "a snippet"
    assert item.summary == "a summary"
    assert item.domain == "example.com"
    assert item.metadata["retrieved_by"] == "test"


def test_search_result_exposes_source_and_ordering() -> None:
    item = SearchResult(source=source(), rank=2, score=0.9)
    assert item.rank == 2
    assert item.score == 0.9
    assert item.title == "Example title"
    assert item.url == "https://example.com/page"


def test_search_result_rejects_invalid_score() -> None:
    with pytest.raises(ValueError, match="score"):
        SearchResult(source=source(), score=1.5)


def test_search_result_rejects_non_positive_rank() -> None:
    with pytest.raises(ValueError, match="rank"):
        SearchResult(source=source(), rank=0)


def test_research_response_ok_factory() -> None:
    response = ResearchResponse.ok(
        query="weather", results=[SearchResult(source=source())]
    )
    assert response.success is True
    assert response.query == "weather"
    assert response.result_count == 1
    assert response.error is None


def test_research_response_fail_factory() -> None:
    response = ResearchResponse.fail(query="weather", error="boom")
    assert response.success is False
    assert response.error == "boom"
    assert response.results == []
    assert response.result_count == 0


def test_research_response_supports_no_results() -> None:
    response = ResearchResponse.ok(query="rare query", results=[])
    assert response.success is True
    assert response.results == []
    assert response.error is None


def test_order_results_sorts_by_descending_score() -> None:
    low = SearchResult(source=source("low"), score=0.4)
    high = SearchResult(source=source("high"), score=0.9)
    mid = SearchResult(source=source("mid"), score=0.7)
    ordered = order_results([low, mid, high])
    assert [result.title for result in ordered] == ["high", "mid", "low"]


def test_order_results_places_missing_scores_last() -> None:
    scored = SearchResult(source=source("scored"), score=0.8)
    unscored = SearchResult(source=source("unscored"))
    ordered = order_results([unscored, scored])
    assert [result.title for result in ordered] == ["scored", "unscored"]


def test_assign_ranks_fills_one_based_ranks() -> None:
    unordered = [
        SearchResult(source=source("a")),
        SearchResult(source=source("b")),
        SearchResult(source=source("c")),
    ]
    ranked = assign_ranks(unordered)
    assert [result.rank for result in ranked] == [1, 2, 3]
    assert ranked[0].source.title == "a"
    assert unordered[0].rank is None


def test_is_http_url() -> None:
    assert is_http_url("https://example.com/a") is True
    assert is_http_url("http://example.com") is True
    assert is_http_url("ftp://example.com") is False
    assert is_http_url("example.com") is False


class SampleResearchProvider(ResearchProvider):
    name = "sample-research"
    description = "A sample research provider for tests."

    def __init__(self, response: ResearchResponse) -> None:
        super().__init__()
        self._response = response

    async def research(self, request: SearchRequest) -> ResearchResponse:
        return self._response


def test_research_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        ResearchProvider()


def test_research_provider_requires_metadata() -> None:
    with pytest.raises(TypeError, match="name"):

        class MissingMetadata(ResearchProvider):
            async def research(
                self, request: SearchRequest
            ) -> ResearchResponse:
                return ResearchResponse.ok(query="q", results=[])


def test_concrete_research_provider_satisfies_interface() -> None:
    provider = SampleResearchProvider(
        response=ResearchResponse.ok(
            query="weather", results=[SearchResult(source=source())]
        )
    )
    assert isinstance(provider, ResearchProvider)
    response = asyncio.run(provider.research(SearchRequest(query="weather")))
    assert response.success is True
    assert response.result_count == 1


def test_evidence_preserves_source_metadata_for_citation() -> None:
    evidence = Source(
        title="Example",
        url="https://example.com/page",
        snippet="snippet",
        domain="example.com",
    )
    response = ResearchResponse.ok(
        query="q", results=[SearchResult(source=evidence, rank=1, score=0.9)]
    )
    result = response.results[0]
    assert result.source.domain == "example.com"
    assert result.source.url == "https://example.com/page"
    assert result.source.snippet == "snippet"


def test_research_error_is_exception() -> None:
    error = ResearchError("boom")
    assert isinstance(error, Exception)
    assert str(error) == "boom"