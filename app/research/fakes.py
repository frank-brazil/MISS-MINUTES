"""Deterministic research provider for offline tests."""

import logging
from collections.abc import Mapping, Sequence

from app.research.base import (
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
    SearchResult,
    assign_ranks,
    order_results,
)


class FakeResearchProvider(ResearchProvider):
    """Deterministic research fake for offline tests.

    The fake never touches an external service. Exact queries map to configured
    fixture results; unmatched queries fall back to a configurable default set
    (empty by default, so unknown queries yield a successful no-results
    response). Results are truncated to ``request.max_results`` and ordered by
    descending score so responses are predictable. Failure behavior is
    configurable to exercise controlled error handling.
    """

    name = "fake-research-provider"
    description = "Deterministic research fake for offline tests."

    def __init__(
        self,
        *,
        fixtures: Mapping[str, Sequence[SearchResult]] | None = None,
        default_results: Sequence[SearchResult] | None = None,
        sort_by_score: bool = True,
        fail: bool = False,
        fail_message: str = "simulated research failure",
        raise_error: Exception | None = None,
    ) -> None:
        super().__init__()
        self._fixtures: dict[str, list[SearchResult]] = {
            key: list(value) for key, value in (fixtures or {}).items()
        }
        self._default_results = list(default_results or [])
        self._sort_by_score = sort_by_score
        self._fail = fail
        self._fail_message = fail_message
        self._raise_error = raise_error
        self._requests: list[SearchRequest] = []
        self._logger = logging.getLogger(__name__)

    @property
    def requests(self) -> tuple[SearchRequest, ...]:
        return tuple(self._requests)

    async def research(self, request: SearchRequest) -> ResearchResponse:
        self._requests.append(request)
        if self._raise_error is not None:
            self._logger.error(
                "Fake research provider raising: %s",
                type(self._raise_error).__name__,
            )
            raise self._raise_error
        if self._fail:
            self._logger.warning("Fake research provider configured to fail")
            return ResearchResponse.fail(
                query=request.query, error=self._fail_message
            )

        results = self._fixtures.get(request.query, self._default_results)
        results = list(results)[: request.max_results]
        if self._sort_by_score:
            results = order_results(results)
        results = assign_ranks(results)

        self._logger.info(
            "Fake research provider returned evidence: query=%s "
            "result_count=%d success=%s",
            request.query,
            len(results),
            True,
        )
        return ResearchResponse.ok(query=request.query, results=results)
