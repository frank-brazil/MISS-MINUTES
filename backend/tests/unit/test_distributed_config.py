import pytest
from app.distributed.config import (
    BIND_HOST,
    DISPATCH_TIMEOUT_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_TIMEOUT_SECONDS,
    MASTER_BIND_PORT,
    MAX_CONCURRENT_DISPATCH,
    MAX_RETRIES,
    WORKER_BIND_PORT,
    DistributedConfig,
)
from pydantic import ValidationError


def test_defaults_are_loopback_and_safe():
    config = DistributedConfig()
    assert config.master_bind_host == BIND_HOST == "127.0.0.1"
    assert config.worker_bind_host == BIND_HOST
    assert config.master_bind_port == MASTER_BIND_PORT
    assert config.worker_bind_port == WORKER_BIND_PORT
    assert config.heartbeat_interval_seconds == HEARTBEAT_INTERVAL_SECONDS
    assert config.heartbeat_timeout_seconds == HEARTBEAT_TIMEOUT_SECONDS
    assert config.max_retries == MAX_RETRIES
    assert config.max_concurrent_dispatch == MAX_CONCURRENT_DISPATCH
    assert config.dispatch_timeout_seconds == DISPATCH_TIMEOUT_SECONDS
    # No secret is ever hard-coded in source.
    assert config.auth_token is None


def test_port_and_duration_validation():
    with pytest.raises(ValidationError):
        DistributedConfig(master_bind_port=0)
    with pytest.raises(ValidationError):
        DistributedConfig(worker_bind_port=70000)
    with pytest.raises(ValidationError):
        DistributedConfig(heartbeat_interval_seconds=0)
    with pytest.raises(ValidationError):
        DistributedConfig(master_bind_host="  ")
    with pytest.raises(ValidationError):
        DistributedConfig(max_retries=-1)
    with pytest.raises(ValidationError):
        DistributedConfig(max_concurrent_dispatch=0)


def test_from_env_reads_overrides():
    env = {
        "MISSMINUTES_MASTER_HOST": "0.0.0.0",
        "MISSMINUTES_MASTER_PORT": "9999",
        "MISSMINUTES_WORKER_HOST": "10.0.0.5",
        "MISSMINUTES_WORKER_PORT": "8888",
        "MISSMINUTES_HEARTBEAT_INTERVAL": "5",
        "MISSMINUTES_HEARTBEAT_TIMEOUT": "10",
        "MISSMINUTES_MAX_RETRIES": "4",
        "MISSMINUTES_MAX_CONCURRENT_DISPATCH": "8",
        "MISSMINUTES_DISPATCH_TIMEOUT": "12",
        "MISSMINUTES_AUTH_TOKEN": "super-secret",
    }
    config = DistributedConfig.from_env(env)
    assert config.master_bind_host == "0.0.0.0"
    assert config.master_bind_port == 9999
    assert config.worker_bind_host == "10.0.0.5"
    assert config.worker_bind_port == 8888
    assert config.heartbeat_interval_seconds == 5.0
    assert config.heartbeat_timeout_seconds == 10.0
    assert config.max_retries == 4
    assert config.max_concurrent_dispatch == 8
    assert config.dispatch_timeout_seconds == 12.0
    assert config.auth_token == "super-secret"


def test_from_env_uses_defaults_when_empty():
    config = DistributedConfig.from_env({})
    assert config.master_bind_host == BIND_HOST
    assert config.auth_token is None


def test_config_is_assignable_with_validation():
    config = DistributedConfig()
    config.max_retries = 5
    assert config.max_retries == 5
    with pytest.raises(ValidationError):
        config.max_retries = -2
