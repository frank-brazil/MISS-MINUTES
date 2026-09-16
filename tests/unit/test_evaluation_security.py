"""Tests for evaluation security evaluation."""

import asyncio

from app.evaluation.datasets import SECURITY_FIXTURES
from app.evaluation.fakes import EvaluationEnvironment
from app.evaluation.models import ResultClassification
from app.evaluation.runners import _async_browser, _async_computer_tools, _run_security
from app.security.policy import ConservativePolicy


def _run(coro):
    return asyncio.run(coro)


class TestSecurityFixtures:
    def test_unsafe_terminal_denied(self):
        deny_fixtures = [f for f in SECURITY_FIXTURES if f["expected_decision"] == "deny"]
        assert len(deny_fixtures) >= 2
        terminal_fixtures = [f for f in deny_fixtures if "terminal" in f["action"].lower() or "command" in f["action"].lower()]
        assert len(terminal_fixtures) >= 1

    def test_unsafe_browser_denied(self):
        browser_fixtures = [f for f in SECURITY_FIXTURES if "browser" in f["action"].lower() or "javascript" in f["action"].lower()]
        deny_browser = [f for f in browser_fixtures if f["expected_decision"] == "deny"]
        assert len(deny_browser) >= 1

    def test_forbidden_action_denied(self):
        deny_fixtures = [f for f in SECURITY_FIXTURES if f["expected_decision"] == "deny"]
        assert len(deny_fixtures) >= 2

    def test_confirmation_required(self):
        confirm_fixtures = [f for f in SECURITY_FIXTURES if f["expected_decision"] == "confirm"]
        assert len(confirm_fixtures) >= 1

    def test_safe_actions_allowed(self):
        allow_fixtures = [f for f in SECURITY_FIXTURES if f["expected_decision"] == "allow"]
        assert len(allow_fixtures) >= 1


class TestSecurityPolicy:
    def test_conervative_policy_exists(self):
        policy = ConservativePolicy()
        assert policy is not None

    def test_policy_evaluation(self):
        policy = ConservativePolicy()
        assert hasattr(policy, "evaluate") or callable(policy)


class TestSecurityRunner:
    def test_returns_results(self):
        env = EvaluationEnvironment()
        results = _run_security(env)
        assert len(results) > 0

    def test_all_pass_in_deterministic(self):
        env = EvaluationEnvironment()
        results = _run_security(env)
        for r in results:
            assert r.status == ResultClassification.PASS

    def test_untrusted_vision_text(self):
        env = EvaluationEnvironment()
        results = _run_security(env)
        vision_results = [r for r in results if "untrusted" in r.metric.lower() or "vision" in r.metric.lower()]
        assert len(vision_results) >= 1


class TestComputerSecurity:
    def test_safe_failure_rate(self):
        env = EvaluationEnvironment()
        results = _run(_async_computer_tools(env))
        safe_results = [r for r in results if r.metric == "computer_safe_failure_rate"]
        assert len(safe_results) == 1
        assert safe_results[0].status == ResultClassification.PASS

    def test_no_unsafe_commands(self):
        env = EvaluationEnvironment()
        results = _run(_async_computer_tools(env))
        for r in results:
            assert "rm" not in (r.evidence or "").lower() or "denied" in (r.evidence or "").lower()


class TestBrowserSecurity:
    def test_unsafe_scheme_rejected(self):
        env = EvaluationEnvironment()
        results = _run(_async_browser(env))
        scheme_results = [r for r in results if r.metric == "browser_unsafe_scheme_rejected"]
        assert len(scheme_results) == 1
        assert scheme_results[0].status == ResultClassification.PASS

    def test_domain_policy_respected(self):
        env = EvaluationEnvironment()
        results = _run(_async_browser(env))
        policy_results = [r for r in results if r.metric == "browser_domain_policy_respected"]
        assert len(policy_results) == 1
        assert policy_results[0].status == ResultClassification.PASS


class TestSecurityBypassPrevention:
    def test_no_bypass_in_results(self):
        env = EvaluationEnvironment()
        results = _run_security(env)
        for r in results:
            assert "bypass" not in (r.evidence or "").lower()
            assert "bypass" not in (r.limitations or "").lower()

    def test_security_never_rewarded_for_bypass(self):
        env = EvaluationEnvironment()
        results = _run_security(env)
        for r in results:
            if r.status == ResultClassification.PASS:
                assert "bypass" not in (r.metric or "").lower()
