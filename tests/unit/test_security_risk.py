from app.security.models import PermissionCategory, RiskLevel
from app.security.risk import RiskAssessor, risk_rank


def test_category_defaults() -> None:
    assessor = RiskAssessor()
    assert assessor.assess(category=PermissionCategory.READ) is RiskLevel.LOW
    assert assessor.assess(category=PermissionCategory.WRITE) is RiskLevel.MEDIUM
    assert assessor.assess(category=PermissionCategory.EXECUTE) is RiskLevel.MEDIUM
    assert assessor.assess(category=PermissionCategory.BROWSER) is RiskLevel.MEDIUM
    assert assessor.assess(category=PermissionCategory.NETWORK) is RiskLevel.MEDIUM
    assert assessor.assess(category=PermissionCategory.SYSTEM) is RiskLevel.HIGH
    assert (
        assessor.assess(category=PermissionCategory.SENSITIVE)
        is RiskLevel.CRITICAL
    )
    assert (
        assessor.assess(category=PermissionCategory.DISTRIBUTED)
        is RiskLevel.MEDIUM
    )


def test_unknown_category_is_unknown_risk() -> None:
    from enum import StrEnum

    class UnknownCategory(StrEnum):
        WEIRD = "weird"

    assert RiskAssessor().assess(category=UnknownCategory.WEIRD) is (
        RiskLevel.UNKNOWN
    )


def test_destructive_keyword_escalates() -> None:
    assessor = RiskAssessor()
    assert (
        assessor.assess(
            category=PermissionCategory.WRITE, action="delete all files"
        )
        is RiskLevel.HIGH
    )
    assert (
        assessor.assess(
            category=PermissionCategory.WRITE, action="drop table users"
        )
        is RiskLevel.HIGH
    )


def test_high_keyword_escalates_medium_to_high() -> None:
    assessor = RiskAssessor()
    assert (
        assessor.assess(
            category=PermissionCategory.EXECUTE, action="run admin command"
        )
        is RiskLevel.HIGH
    )


def test_shell_meta_escalates() -> None:
    assessor = RiskAssessor()
    assert (
        assessor.assess(
            category=PermissionCategory.EXECUTE, action="run with $HOME"
        )
        is RiskLevel.HIGH
    )


def test_benign_action_stays_at_base() -> None:
    assessor = RiskAssessor()
    assert (
        assessor.assess(
            category=PermissionCategory.READ, action="read config file"
        )
        is RiskLevel.LOW
    )


def test_category_overrides() -> None:
    assessor = RiskAssessor(
        category_overrides={
            PermissionCategory.NETWORK: RiskLevel.HIGH
        }
    )
    assert assessor.assess(category=PermissionCategory.NETWORK) is RiskLevel.HIGH
    assert assessor.category_overrides == {
        PermissionCategory.NETWORK: RiskLevel.HIGH
    }


def test_risk_rank_order() -> None:
    assert risk_rank(RiskLevel.LOW) < risk_rank(RiskLevel.MEDIUM)
    assert risk_rank(RiskLevel.MEDIUM) < risk_rank(RiskLevel.HIGH)
    assert risk_rank(RiskLevel.HIGH) < risk_rank(RiskLevel.CRITICAL)
    assert risk_rank(RiskLevel.CRITICAL) < risk_rank(RiskLevel.UNKNOWN)