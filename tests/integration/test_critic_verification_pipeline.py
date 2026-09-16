import asyncio
import logging

from app.core.critic import (
    Critic,
    Critique,
    CritiqueRequest,
    FakeCritic,
    Severity,
)
from app.core.verification import (
    FakeVerifier,
    ObservedResult,
    VerificationExpectation,
    VerificationResult,
    VerificationStatus,
    Verifier,
)


async def _review(critic: Critic, requested: CritiqueRequest) -> Critique:
    return await critic.critique(requested)


async def _check(
    verifier: Verifier,
    exp: VerificationExpectation,
    obs: ObservedResult,
) -> VerificationResult:
    return await verifier.verify(exp, obs)


def test_critic_providers_are_interchangeable() -> None:
    fake = FakeCritic()

    class EchoCritic(Critic):
        name = "echo-critic"
        description = "Returns a single fixed deterministic critique point."

        async def critique(self, requested: CritiqueRequest) -> Critique:
            return Critique(
                target=requested.target,
                points=[
                    {
                        "aspect": "risk",
                        "description": (
                            "The echo critic flags an estimated risk that is "
                            "not guaranteed."
                        ),
                        "severity": Severity.MEDIUM,
                        "confidence": 0.5,
                    }
                ],
            )

    requested = CritiqueRequest(target="Proposed solution under review.")
    for critic in (fake, EchoCritic()):
        result = asyncio.run(_review(critic, requested))
        assert isinstance(result, Critique)
        assert result.target == requested.target
        assert len(result.risks) >= 1
        assert result.confidence is None or 0.0 <= result.confidence <= 1.0


def test_verifier_providers_are_interchangeable() -> None:
    fake = FakeVerifier()

    class EchoVerifier(Verifier):
        name = "echo-verifier"
        description = "Always echoes a deterministic verification result."

        async def verify(
            self,
            exp: VerificationExpectation,
            obs: ObservedResult,
        ) -> VerificationResult:
            return VerificationResult(
                expectation=exp,
                status=VerificationStatus.VERIFIED,
                expected_outcome=exp.description,
                observed_outcome=obs.description,
                confidence=0.9,
            )

    exp = VerificationExpectation(
        description="The expected outcome occurs.",
        conditions=["expected outcome"],
    )
    obs = ObservedResult(
        description="expected outcome observed",
        observations=["expected outcome occurred"],
    )
    for verifier in (fake, EchoVerifier()):
        result = asyncio.run(_check(verifier, exp, obs))
        assert isinstance(result, VerificationResult)
        assert result.success is True
        assert result.expected_outcome == exp.description


def test_critique_logs_do_not_leak_target_text(caplog) -> None:
    critic = FakeCritic()
    with caplog.at_level(logging.INFO, logger="app.core.critic"):
        asyncio.run(
            _review(
                critic,
                CritiqueRequest(
                    target="A private proposed solution to an internal issue."
                ),
            )
        )
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_id=" in messages
    assert "A private proposed solution to an internal issue." not in messages


def test_verifier_logs_do_not_leak_observation_text(caplog) -> None:
    verifier = FakeVerifier()
    with caplog.at_level(logging.INFO, logger="app.core.verification"):
        asyncio.run(
            _check(
                verifier,
                VerificationExpectation(
                    description="A sensitive expected outcome.",
                    conditions=["sensitive condition"],
                ),
                ObservedResult(
                    description="A sensitive private observation.",
                    observations=["something sensitive occurred"],
                ),
            )
        )
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "expectation_id=" in messages
    assert "A sensitive private observation." not in messages


def test_di_pipeline_verification_tracks_expected_outcome() -> None:
    verifier = FakeVerifier()
    exp = VerificationExpectation(
        description="The file appears in the project directory.",
        conditions=["project dir lists the file"],
    )
    obs = ObservedResult(
        description="Directory listing ran.",
        observations=["project dir lists the file"],
        action_succeeded=True,
    )
    result = asyncio.run(_check(verifier, exp, obs))
    assert result.is_verified is True
    assert result.expected_outcome == exp.description
    assert result.observed_outcome == obs.description


def test_di_pipeline_verification_surfaces_failed_observation() -> None:
    verifier = FakeVerifier()
    exp = VerificationExpectation(
        description="The service comes back online.",
        conditions=["service online"],
    )
    obs = ObservedResult(
        description="Service failed to start.",
        observations=["startup failed", "not service online"],
        action_succeeded=False,
    )
    result = asyncio.run(_check(verifier, exp, obs))
    assert result.is_failed is True
    assert not result.is_verified
    assert result.discrepancy is not None


def test_critic_and_verifier_modules_are_standalone() -> None:
    import sys

    for module_name in ("app.core.critic", "app.core.verification"):
        module = sys.modules[module_name]
        with open(module.__file__, encoding="utf-8") as handle:
            content = handle.read()
        assert "httpx" not in content
        assert "openai" not in content
        assert "fastapi" not in content
        assert "sqlite" not in content
