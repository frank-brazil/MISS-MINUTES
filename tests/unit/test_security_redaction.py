from app.security.redaction import (
    REDACTED,
    is_redacted,
    redact,
    redact_mapping,
    redact_string,
    redact_value,
)


def test_redact_bearer_token() -> None:
    value = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def"
    redacted = redact_string(value)
    assert REDACTED in redacted
    assert "eyJhbGci" not in redacted
    assert redacted.startswith("Bearer ")


def test_redact_basic_auth() -> None:
    value = "Basic dXNlcjpwYXNzMTIzNDU2Nzg5MDEyMzQ1Njc4"
    redacted = redact_string(value)
    assert REDACTED in redacted
    assert "dXNlcjpwYXNz" not in redacted


def test_redact_password_kv() -> None:
    value = "password=hunter2 is not safe"
    redacted = redact_string(value)
    assert "hunter2" not in redacted
    assert "password=" in redacted
    assert REDACTED in redacted


def test_redact_api_key_in_dict() -> None:
    original = {"api_key": "sk_live_abc123xyz", "name": "test"}
    result = redact_mapping(original)
    assert result["api_key"] == REDACTED
    assert result["name"] == "test"


def test_redact_nested_dict() -> None:
    original = {
        "config": {"secret": "top-secret", "port": 8080},
        "token": "bearer-abc",
    }
    result = redact_value(original)
    assert result["config"]["secret"] == REDACTED
    assert result["config"]["port"] == 8080
    assert result["token"] == REDACTED


def test_redact_list_of_values() -> None:
    original = ["normal text", "Bearer secret123456789012", {"password": "pw"}]
    result = redact_value(original)
    assert result[0] == "normal text"
    assert REDACTED in result[1]
    assert result[2]["password"] == REDACTED


def test_benign_text_unchanged() -> None:
    original = "File search for *.py in src/"
    assert redact_string(original) == original


def test_empty_string() -> None:
    assert redact_string("") == ""


def test_redact_alias() -> None:
    assert redact("Bearer token123456789012345") == redact_value(
        "Bearer token123456789012345"
    )


def test_is_redacted_detects_marker() -> None:
    assert is_redacted(REDACTED)
    assert is_redacted({"secret": REDACTED})
    assert is_redacted([REDACTED, "ok"])
    assert not is_redacted("clean")


def test_various_secret_keys() -> None:
    for key in (
        "API_KEY",
        "authorization",
        "AUTH_TOKEN",
        "client_secret",
        "credentials",
    ):
        result = redact_mapping({key: "secret-value"})
        assert result[key] == REDACTED, f"Failed for key {key}"


def test_non_secret_keys_preserved() -> None:
    original = {"task_type": "analysis", "worker_name": "w1"}
    assert redact_mapping(original) == original


def test_numeric_value_in_secret_key() -> None:
    result = redact_mapping({"token": 12345})
    assert result["token"] == REDACTED