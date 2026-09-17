"""HTTP-backed search provider behind the research abstraction.

This is a generic JSON REST search client speaking a documented contract: it
POSTs ``{"query": ..., "max_results": ...}`` to a configurable endpoint and
expects ``{"results": [...]}`` back. It is not coupled to any single search
engine; a compatible search endpoint (for example a project-owned search proxy)
can be pointed at it through environment variables.

The provider never fabricates sources: only items returned by the configured
endpoint are surfaced as evidence. Credentials come from the environment and
are never serialized into logs.
"""

import os
from typing import Any

from app.research.base import (
    ABSOLUTE_MAX_RESULTS,
    ResearchProvider,
    ResearchResponse,
    SearchRequest,
    SearchResult,
    Source,
    assign_ranks,
)

SEARCH_URL_ENV = "MISSMINUTES_SEARCH_URL"
SEARCH_API_KEY_ENV = "MISSMINUTES_SEARCH_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 10.0


class HttpSearchProvider(ResearchProvider):
    """Searches a JSON REST endpoint configured via environment variables.

    Configuration (constructor values take precedence over environment):
      - ``base_url`` / :envvar:`MISSMINUTES_SEARCH_URL`
      - ``api_key`` / :envvar:`MISSMINUTES_SEARCH_API_KEY`

    ``http_client`` may be injected for tests; it must expose ``async post``
    accepting ``url``, ``headers``, ``json`` and ``timeout`` and return an
    object with ``raise_for_status`` and ``json``.
    """

    name = "http-search"
    description = "Generic JSON REST search client behind the research abstraction."
    response_contract = "missminutes-search-v1"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        max_results: int = ABSOLUTE_MAX_RESULTS,
        http_client: Any | None = None,
    ) -> None:
        super().__init__()
        self._base_url = (base_url or os.getenv(SEARCH_URL_ENV) or "").strip() or None
        self._api_key = (api_key or os.getenv(SEARCH_API_KEY_ENV) or "").strip() or None
        self._timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS
        if not isinstance(self._timeout, (int, float)) or self._timeout <= 0:
            raise ValueError("timeout must be a positive number of seconds")
        self._max_results = max(1, min(int(max_results), ABSOLUTE_MAX_RESULTS))
        self._client = http_client

    @property
    def base_url(self) -> str | None:
        return self._base_url

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def max_results(self) -> int:
        return self._max_results

    def _payload(self, request: SearchRequest) -> dict[str, Any]:
        return {
            "query": request.query,
            "max_results": min(request.max_results, self._max_results),
        }

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        if self._client is not None:
            return await self._client.post(
                url, headers=headers, json=payload, timeout=self._timeout
            )
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, headers=headers, json=payload, timeout=self._timeout)

    def _parse_results(self, query: str, payload: dict[str, Any]) -> ResearchResponse:
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise ValueError("search endpoint returned no results list")

        results: list[SearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                self._logger.warning("Skipping malformed search result item")
                continue
            try:
                source = Source.model_validate(
                    {
                        key: item[key]
                        for key in (
                            "title",
                            "url",
                            "reference",
                            "snippet",
                            "summary",
                            "domain",
                            "published_at",
                        )
                        if key in item
                    }
                )
            except Exception as exc:  # noqa: BLE001 - keep evidence structured
                self._logger.warning(
                    "Skipping malformed search result: error=%s",
                    type(exc).__name__,
                )
                continue
            raw_score = item.get("score")
            score = (
                raw_score
                if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool)
                else None
            )
            results.append(SearchResult(source=source, score=score))

        results = results[: self._max_results]
        results = assign_ranks(results)
        self._logger.info(
            "Http search provider returned evidence: query=%s result_count=%d success=%s",
            query,
            len(results),
            True,
        )
        return ResearchResponse.ok(query=query, results=results)

    async def research(self, request: SearchRequest) -> ResearchResponse:
        if self._base_url is None:
            self._logger.error("Http search provider is not configured")
            return ResearchResponse.fail(
                query=request.query,
                error="search provider is not configured: MISSMINUTES_SEARCH_URL is missing",
            )
        self._logger.info(
            "Http search provider searching: query=%s max_results=%d",
            request.query,
            min(request.max_results, self._max_results),
        )
        try:
            response = await self._post(self._base_url, self._headers(), self._payload(request))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("search endpoint returned a non-object payload")
            return self._parse_results(request.query, payload)
        except Exception as exc:  # noqa: BLE001 - network/timeout/parse failures
            self._logger.warning(
                "Http search provider call failed: error=%s",
                type(exc).__name__,
            )
            return ResearchResponse.fail(query=request.query, error="search provider call failed")
