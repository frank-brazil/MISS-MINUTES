"""Research abstraction for time-sensitive information.

The research layer is provider-independent: it describes structured evidence
gathered from search providers and never decides the final answer. A future AI
synthesis stage consumes this evidence to produce source-aware answers.

Important boundary: retrieving a source does not make it authoritative. This
layer only returns what a provider returned; it does not fabricate sources and
does not rank claims by authority.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, ClassVar, Sequence

from pydantic import BaseModel, Field, field_validator, model_validator


def _utc_now() -> datetime:
    return datetime.now(UTC)


DEFAULT_MAX_RESULTS = 5
"""Result limit applied when a caller does not request a specific count."""

ABSOLUTE_MAX_RESULTS = 20
"""Hard ceiling enforced by requests and providers to prevent unbounded results."""


def is_http_url(value: str) -> bool:
    """Return True when ``value`` is a well-formed http(s) URL."""
    from urllib.parse import urlsplit

    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


class SearchRequest(BaseModel):
    """A single research/search request.

    ``max_results`` is bounded by ``ABSOLUTE_MAX_RESULTS`` so a caller cannot
    request an unbounded result set.
    """

    query: str = Field(min_length=1)
    max_results: int = Field(default=DEFAULT_MAX_RESULTS, ge=1)

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped

    @field_validator("max_results")
    @classmethod
    def _max_results_bounded(cls, value: int) -> int:
        if value > ABSOLUTE_MAX_RESULTS:
            raise ValueError(
                f"max_results must not exceed {ABSOLUTE_MAX_RESULTS}"
            )
        return value


class Source(BaseModel):
    """Structured evidence about where information came from.

    A source must identify itself through at least one of ``url`` or
    ``reference``. All metadata is preserved so future AI responses can cite
    where information came from.
    """

    title: str = Field(min_length=1)
    url: str | None = None
    reference: str | None = None
    snippet: str | None = None
    summary: str | None = None
    domain: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "reference", "snippet", "summary", "domain")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not is_http_url(stripped):
            raise ValueError("url must be an http(s) reference")
        return stripped

    @model_validator(mode="after")
    def _requires_reference(self) -> "Source":
        if not self.url and not self.reference:
            raise ValueError("a source must have a url or a reference")
        return self


class SearchResult(BaseModel):
    """A single search hit: evidence plus result-ordering metadata.

    The cited evidence lives in ``source``; ``rank`` and ``score`` describe
    ordering within a response, not factual authority.
    """

    source: Source
    rank: int | None = None
    score: float | None = None

    @field_validator("rank")
    @classmethod
    def _rank_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("rank must be a positive number")
        return value

    @field_validator("score")
    @classmethod
    def _score_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("score must be between 0 and 1")
        return value

    @property
    def title(self) -> str:
        return self.source.title

    @property
    def url(self) -> str | None:
        return self.source.url

    @property
    def snippet(self) -> str | None:
        return self.source.snippet


class ResearchResponse(BaseModel):
    """Typed outcome of a research request.

    On success ``results`` holds ordered evidence and ``error`` is None. On
    failure ``success`` is False and ``error`` describes the problem. A
    successful request may legitimately return zero results.
    """

    success: bool
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    error: str | None = None

    @property
    def result_count(self) -> int:
        return len(self.results)

    @classmethod
    def ok(
        cls, query: str, results: Sequence[SearchResult]
    ) -> "ResearchResponse":
        return cls(success=True, query=query, results=list(results))

    @classmethod
    def fail(cls, query: str, error: str) -> "ResearchResponse":
        return cls(success=False, query=query, results=[], error=error)


def order_results(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Order results deterministically by descending score.

    Results without a score sort last. This is ordering metadata only; it does
    not rank sources by authority.
    """
    return sorted(
        results,
        key=lambda result: (
            result.score is None,
            -(result.score or 0.0),
        ),
    )


def assign_ranks(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Return copies of ``results`` with 1-based ranks filled in order."""
    ranked: list[SearchResult] = []
    for index, result in enumerate(results, start=1):
        if result.rank is None:
            result = result.model_copy(update={"rank": index})
        ranked.append(result)
    return ranked


class ResearchError(Exception):
    """Base exception for research subsystem failures.

    Provider failures are normally reported through ``ResearchResponse.fail``;
    this type is reserved for programming-level problems so callers can catch
    provider exceptions without knowing provider internals.
    """


class ResearchProvider(ABC):
    """Provider-independent search/research interface.

    Concrete providers receive a ``SearchRequest`` and return a
    ``ResearchResponse`` with structured sources as evidence. Providers:

    - must not fabricate sources or claims,
    - must leave final-answer synthesis to a higher layer,
    - should only return what the underlying engine returned,
    - may report failures through ``ResearchResponse.fail`` instead of raising.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        missing = [
            attribute
            for attribute in ("name", "description")
            if not hasattr(cls, attribute)
        ]
        if missing:
            raise TypeError(
                f"{cls.__name__} must define required attribute(s): {', '.join(missing)}"
            )

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    @abstractmethod
    async def research(self, request: SearchRequest) -> ResearchResponse:
        raise NotImplementedError
