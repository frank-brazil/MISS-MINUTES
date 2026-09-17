import asyncio

from app.research.base import (
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
    SearchResult,
    Source,
)
from app.research.fakes import FakeResearchProvider


def source(title: str, url: str) -> Source:
    return Source(title=title, url=url, domain="example.com")


FIXTURES = {
    "current AI news": [
        SearchResult(
            source=source(
                "Example: foundation models roundup",
                "https://example.com/news/foundation-models",
            ),
            score=0.9,
        ),
        SearchResult(
            source=source(
                "Example: local inference benchmark update",
                "https://example.com/news/local-inference",
            ),
            score=0.7,
        ),
        SearchResult(
            source=source(
                "Example: voice agents survey",
                "https://example.com/news/voice-agents",
            ),
            score=0.5,
        ),
    ],
    "latest research papers": [
        SearchResult(
            source=Source(
                title="Example: multilingual speech evaluation",
                reference="doi:10.0000/example001",
                snippet="A fictional summary for deterministic tests.",
            ),
            score=0.8,
        ),
    ],
}


def test_research_pipeline_returns_structured_evidence() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(provider.research(SearchRequest(query="current AI news", max_results=2)))
    assert response.success is True
    assert response.query == "current AI news"
    assert response.error is None
    assert response.result_count == 2
    for result in response.results:
        assert isinstance(result.source, Source)
        assert result.source.url is not None
        assert result.source.domain == "example.com"
    assert [result.rank for result in response.results] == [1, 2]
    assert response.results[0].score >= response.results[1].score


def test_research_pipeline_preserves_citation_metadata() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(provider.research(SearchRequest(query="latest research papers")))
    result = response.results[0]
    assert result.source.reference == "doi:10.0000/example001"
    assert result.source.snippet is not None
    evidence = result.source
    assert evidence.title and (evidence.url or evidence.reference)


def test_research_pipeline_no_results_is_successful() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(provider.research(SearchRequest(query="nothing in the index")))
    assert response.success is True
    assert response.result_count == 0
    assert response.results == []
    assert response.error is None


def test_research_pipeline_controlled_provider_failure() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES, fail=True)
    response = asyncio.run(provider.research(SearchRequest(query="current AI news")))
    assert response.success is False
    assert response.error == "simulated research failure"
    assert response.result_count == 0
    assert response.query == "current AI news"


async def _consume(provider: ResearchProvider) -> ResearchResponse:
    return await provider.research(SearchRequest(query="current AI news"))


def test_research_providers_are_interchangeable() -> None:
    fake = FakeResearchProvider(fixtures=FIXTURES)

    class EchoProvider(ResearchProvider):
        name = "echo-research"
        description = "Returns a single fixed evidence source."

        async def research(self, request: SearchRequest) -> ResearchResponse:
            return ResearchResponse.ok(
                query=request.query,
                results=[
                    SearchResult(
                        source=Source(
                            title="Echoed evidence",
                            url="https://example.com/echoed",
                        )
                    )
                ],
            )

    for provider in (fake, EchoProvider()):
        response = asyncio.run(_consume(provider))
        assert response.success is True
        assert response.query == "current AI news"


def test_research_pipeline_evidence_feeds_future_synthesis() -> None:
    provider = FakeResearchProvider(fixtures=FIXTURES)
    response = asyncio.run(provider.research(SearchRequest(query="current AI news")))
    synthesis_input = [
        {
            "title": result.source.title,
            "url": result.source.url,
            "reference": result.source.reference,
            "snippet": result.source.snippet,
        }
        for result in response.results
    ]
    assert all(item["title"] for item in synthesis_input)
    assert any(item["url"] for item in synthesis_input)
