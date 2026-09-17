import pytest
from app.browser.policy import UrlPolicy, UrlValidationError


def test_valid_http_url_accepted() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    assert policy.is_allowed("http://example.com/path")
    assert policy.validate_url("http://example.com/path") == "http://example.com/path"


def test_valid_https_url_accepted() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    assert policy.is_allowed("https://example.com/secure?q=1")


def test_https_url_with_query_and_fragment() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    url = "https://example.com/page?a=1#frag"
    assert policy.is_allowed(url) is True
    normalized = policy.validate_url(url)
    assert normalized.startswith("https://example.com/page?a=1")


def test_javascript_url_rejected() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    with pytest.raises(UrlValidationError, match="scheme"):
        policy.validate_url("javascript:alert(1)")
    assert policy.is_allowed("javascript:alert(1)") is False


def test_file_url_rejected() -> None:
    policy = UrlPolicy()
    with pytest.raises(UrlValidationError, match="scheme"):
        policy.validate_url("file:///etc/passwd")
    assert policy.is_allowed("file:///C:/Windows/system.ini") is False


def test_data_url_rejected() -> None:
    policy = UrlPolicy()
    assert policy.is_allowed("data:text/html,<script>x</script>") is False
    with pytest.raises(UrlValidationError, match="scheme"):
        policy.validate_url("data:text/html,hello")


def test_unsupported_scheme_rejected() -> None:
    policy = UrlPolicy()
    for url in ("ftp://example.com/x", "mailto:a@b.com", "chrome://settings", "about:blank"):
        assert policy.is_allowed(url) is False
        with pytest.raises(UrlValidationError, match="scheme"):
            policy.validate_url(url)


def test_empty_url_rejected() -> None:
    policy = UrlPolicy()
    with pytest.raises(UrlValidationError, match="URL must be provided"):
        policy.validate_url("   ")
    with pytest.raises(UrlValidationError, match="URL must be provided"):
        policy.validate_url("")


def test_url_without_scheme_rejected() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    assert policy.is_allowed("example.com/path") is False


def test_url_without_host_rejected() -> None:
    policy = UrlPolicy()
    with pytest.raises(UrlValidationError, match="host"):
        policy.validate_url("http:///path/to/nowhere")


def test_credentials_in_url_rejected() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    with pytest.raises(UrlValidationError, match="credentials"):
        policy.validate_url("https://user:pass@example.com/")
    assert policy.is_allowed("http://user:pass@example.com/") is False


def test_default_policy_rejects_remote_domains() -> None:
    policy = UrlPolicy()
    assert policy.is_allowed("https://example.com") is False
    assert policy.is_allowed("http://google.com") is False


def test_default_policy_allows_localhost() -> None:
    policy = UrlPolicy()
    assert policy.is_allowed("http://localhost/") is True
    assert policy.is_allowed("https://localhost:8443/") is True
    assert policy.is_allowed("http://127.0.0.1:8000/") is True
    assert policy.is_allowed("http://[::1]:8080/") is True


def test_allow_localhost_disabled() -> None:
    policy = UrlPolicy(allow_localhost=False)
    assert policy.is_allowed("http://localhost/") is False
    assert policy.is_allowed("http://127.0.0.1/") is False


def test_allow_domain_exact_match() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    assert policy.is_allowed("https://example.com/") is True
    assert policy.is_allowed("https://www.example.com/") is True
    assert policy.is_allowed("https://api.example.com/v1") is True


def test_allow_domain_does_not_match_decoy() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    assert policy.is_allowed("https://example.com.evil.org/") is False
    assert policy.is_allowed("https://notexample.com/") is False


def test_deny_domain_wins_over_allow() -> None:
    policy = UrlPolicy(
        allow_domains=("example.com", "evil.com"),
        deny_domains=("evil.com",),
    )
    assert policy.is_allowed("https://example.com/") is True
    assert policy.is_allowed("https://evil.com/") is False
    assert policy.is_allowed("https://sub.evil.com/") is False


def test_deny_subdomain_matching() -> None:
    policy = UrlPolicy(
        allow_domains=("example.com",),
        deny_domains=("payments.example.com",),
    )
    assert policy.is_allowed("https://example.com/") is True
    assert policy.is_allowed("https://blog.example.com/") is True
    assert policy.is_allowed("https://payments.example.com/buy") is False


def test_normalization_lowercases_scheme_and_host() -> None:
    policy = UrlPolicy(allow_domains=("example.com",))
    normalized = policy.validate_url("HTTP://Example.COM/Path")
    assert normalized == "http://example.com/Path"


def test_policy_exposes_configuration() -> None:
    policy = UrlPolicy(
        allowed_schemes=("https",), allow_domains=("a.com",), deny_domains=("b.com",)
    )
    assert policy.allowed_schemes == frozenset({"https"})
    assert "a.com" in policy.allow_domains
    assert "b.com" in policy.deny_domains


def test_loopback_inside_allow_list_rules() -> None:
    policy = UrlPolicy(
        allow_domains=("10.0.0.0",),
        deny_domains=("localhost",),
        allow_localhost=True,
    )
    assert policy.is_allowed("http://localhost/") is False
    assert policy.is_allowed("http://127.0.0.1/") is False
    assert policy.is_allowed("http://10.0.0.0/") is True
