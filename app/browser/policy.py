"""URL validation and domain policy for safe browsing.

Navigation is only permitted for URLs that pass :class:`UrlPolicy`.  The
default policy is conservative:

- http / https schemes only;
- ``javascript:``, ``data:``, ``file:`` and any custom scheme are rejected;
- URLs embedding credentials are rejected;
- with no allow-list configured, only loopback/localhost hosts are permitted
  (so local development and testing work out of the box).

Domain allow/deny lists are supported; deny always wins and both match on
exact host or trailing sub-domain (``example.com`` matches ``api.example.com``).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit


class UrlValidationError(ValueError):
    """Raised when a URL violates the browsing policy."""


def _host_matches(host: str, rule: str) -> bool:
    host = host.rstrip(".").lower()
    rule = rule.rstrip(".").lower()
    if host == rule:
        return True
    return host.endswith("." + rule)


def _is_loopback(host: str) -> bool:
    host = host.rstrip(".").lower()
    if host in ("localhost", "::1", "0:0:0:0:0:0:0:1"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class UrlPolicy:
    """Validates and normalizes URLs against a configurable policy."""

    def __init__(
        self,
        *,
        allowed_schemes: tuple[str, ...] = ("http", "https"),
        allow_domains: tuple[str, ...] = (),
        deny_domains: tuple[str, ...] = (),
        allow_localhost: bool = True,
    ) -> None:
        self._schemes = frozenset(
            scheme.lower() for scheme in allowed_schemes
        ) or frozenset({"http", "https"})
        self._allow = frozenset(
            domain.rstrip(".").lower() for domain in allow_domains
        )
        self._deny = frozenset(
            domain.rstrip(".").lower() for domain in deny_domains
        )
        self._allow_localhost = allow_localhost

    @property
    def allowed_schemes(self) -> frozenset[str]:
        return self._schemes

    @property
    def allow_domains(self) -> frozenset[str]:
        return self._allow

    @property
    def deny_domains(self) -> frozenset[str]:
        return self._deny

    @property
    def allow_localhost(self) -> bool:
        return self._allow_localhost

    def validate_url(self, url: str) -> str:
        """Validate ``url`` and return its normalized form.

        Raises
        ------
        UrlValidationError
            If the URL uses a disallowed scheme, embeds credentials, lacks a
            host, or targets a domain blocked by policy.
        """
        normalized = url.strip()
        if not normalized:
            raise UrlValidationError("URL must be provided")

        try:
            parts = urlsplit(normalized)
        except ValueError as exc:
            raise UrlValidationError(f"Malformed URL: {exc}") from exc

        scheme = parts.scheme.lower()
        if scheme not in self._schemes:
            raise UrlValidationError(
                f"URL scheme '{scheme}' is not allowed (http/https only)"
            )

        if parts.username or parts.password:
            raise UrlValidationError(
                "URLs with embedded credentials are not allowed"
            )

        host = (parts.hostname or "").rstrip(".").lower()
        if not host:
            raise UrlValidationError("URL must include a host")

        if not self._host_allowed(host):
            raise UrlValidationError(
                f"domain '{host}' is not allowed by policy"
            )

        netloc = parts.netloc.lower()
        return urlunsplit((scheme, netloc, parts.path or "/", parts.query, parts.fragment))

    def is_allowed(self, url: str) -> bool:
        """Return True when ``url`` would be accepted by this policy."""
        try:
            self.validate_url(url)
            return True
        except UrlValidationError:
            return False

    def _host_allowed(self, host: str) -> bool:
        for rule in self._deny:
            if _host_matches(host, rule):
                return False
        for rule in self._allow:
            if _host_matches(host, rule):
                return True
        if self._allow:
            return False
        if self._allow_localhost and _is_loopback(host):
            return True
        return False