"""Tests for evaluation metrics and computation functions."""

import pytest
from app.evaluation.metrics import (
    METRICS,
    compute_accuracy,
    compute_cer,
    compute_pass_rate,
    compute_wer,
    safe_divide,
)
from app.evaluation.models import EvaluationCategory


class TestComputeWer:
    def test_identical_strings(self):
        assert compute_wer("hello world", "hello world") == 0.0

    def test_one_substitution(self):
        assert compute_wer("hello world", "hello there") == pytest.approx(0.5)

    def test_one_insertion(self):
        assert compute_wer("hello", "hello world") == pytest.approx(1.0)

    def test_one_deletion(self):
        assert compute_wer("hello world", "hello") == pytest.approx(0.5)

    def test_empty_both(self):
        assert compute_wer("", "") == 0.0

    def test_empty_reference(self):
        assert compute_wer("", "hello") == 1.0

    def test_empty_hypothesis(self):
        assert compute_wer("hello", "") == 1.0

    def test_single_word_correct(self):
        assert compute_wer("hello", "hello") == 0.0

    def test_single_word_wrong(self):
        assert compute_wer("hello", "world") == 1.0


class TestComputeCer:
    def test_identical_strings(self):
        assert compute_cer("abc", "abc") == 0.0

    def test_one_substitution(self):
        assert compute_cer("abc", "axc") == pytest.approx(1 / 3)

    def test_empty_both(self):
        assert compute_cer("", "") == 0.0

    def test_empty_reference(self):
        assert compute_cer("", "abc") == 1.0

    def test_empty_hypothesis(self):
        assert compute_cer("abc", "") == 1.0

    def test_single_char_correct(self):
        assert compute_cer("a", "a") == 0.0

    def test_single_char_wrong(self):
        assert compute_cer("a", "b") == 1.0


class TestComputeAccuracy:
    def test_all_correct(self):
        assert compute_accuracy(10, 10) == 1.0

    def test_none_correct(self):
        assert compute_accuracy(0, 10) == 0.0

    def test_half(self):
        assert compute_accuracy(5, 10) == 0.5

    def test_zero_total_raises(self):
        with pytest.raises(ValueError, match="total must be positive"):
            compute_accuracy(0, 0)

    def test_negative_total_raises(self):
        with pytest.raises(ValueError, match="total must be positive"):
            compute_accuracy(0, -1)

    def test_negative_correct_raises(self):
        with pytest.raises(ValueError, match="correct must be non-negative"):
            compute_accuracy(-1, 10)


class TestComputePassRate:
    def test_all_pass(self):
        assert compute_pass_rate(5, 5) == 1.0

    def test_none_pass(self):
        assert compute_pass_rate(0, 5) == 0.0

    def test_zero_total_raises(self):
        with pytest.raises(ValueError, match="total must be positive"):
            compute_pass_rate(0, 0)


class TestSafeDivide:
    def test_normal(self):
        assert safe_divide(10, 2) == 5.0

    def test_zero_numerator(self):
        assert safe_divide(0, 5) == 0.0

    def test_zero_denominator_raises(self):
        with pytest.raises(ValueError, match="denominator must not be zero"):
            safe_divide(10, 0)


class TestMetricDefinitions:
    def test_metrics_count(self):
        assert len(METRICS) > 0

    def test_all_have_names(self):
        for metric in METRICS:
            assert metric.name
            assert metric.name.strip()

    def test_all_have_definitions(self):
        for metric in METRICS:
            assert metric.definition
            assert metric.definition.strip()

    def test_all_have_categories(self):
        for metric in METRICS:
            assert isinstance(metric.category, EvaluationCategory)

    def test_unique_names(self):
        names = [m.name for m in METRICS]
        assert len(names) == len(set(names))

    def test_stt_metrics_exist(self):
        stt_metrics = [m for m in METRICS if m.category == EvaluationCategory.STT]
        assert len(stt_metrics) >= 2
        names = {m.name for m in stt_metrics}
        assert "stt_word_error_rate" in names
        assert "stt_character_error_rate" in names

    def test_voice_metrics_exist(self):
        voice_metrics = [m for m in METRICS if m.category == EvaluationCategory.VOICE]
        assert len(voice_metrics) >= 4

    def test_security_metrics_exist(self):
        sec_metrics = [m for m in METRICS if m.category == EvaluationCategory.SECURITY]
        assert len(sec_metrics) >= 7

    def test_reliability_metrics_exist(self):
        rel_metrics = [m for m in METRICS if m.category == EvaluationCategory.RELIABILITY]
        assert len(rel_metrics) >= 6

    def test_avatar_metrics_exist(self):
        avatar_metrics = [m for m in METRICS if m.category == EvaluationCategory.AVATAR]
        assert len(avatar_metrics) >= 2

    def test_memory_metrics_exist(self):
        mem_metrics = [m for m in METRICS if m.category == EvaluationCategory.MEMORY]
        assert len(mem_metrics) >= 3

    def test_e2e_metrics_exist(self):
        e2e_metrics = [m for m in METRICS if m.category == EvaluationCategory.END_TO_END]
        assert len(e2e_metrics) >= 2

    def test_distributed_metrics_exist(self):
        dist_metrics = [m for m in METRICS if m.category == EvaluationCategory.DISTRIBUTED]
        assert len(dist_metrics) >= 4

    def test_verification_metrics_exist(self):
        ver_metrics = [m for m in METRICS if m.category == EvaluationCategory.VERIFICATION]
        assert len(ver_metrics) >= 3
