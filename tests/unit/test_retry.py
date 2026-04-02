"""Unit-Tests für RetryController."""

from unittest.mock import MagicMock, call

import pytest

from mdal.interfaces.scoring import CheckResult, ScoreLevel, ScoringDecision
from mdal.retry import RetryController, RetryLimitError
from mdal.session import SessionContext
from mdal.verification.engine import VerificationResult


def make_context() -> SessionContext:
    return SessionContext(language="de", fingerprint_version=1)


def make_result(decision: ScoringDecision) -> VerificationResult:
    """Minimales VerificationResult für den angegebenen ScoringDecision."""
    return VerificationResult(
        decision         = decision,
        structure_result = None,
        semantic_s1      = CheckResult(level=ScoreLevel.HIGH),
        semantic_s2      = CheckResult(level=ScoreLevel.HIGH),
        semantic_s3      = None,
        output_format    = "prose",
    )


def make_notifier() -> MagicMock:
    return MagicMock()


class TestRetryControllerOutput:
    """OUTPUT-Entscheidung → sofortige Rückgabe ohne Transform."""

    def test_output_on_first_attempt(self):
        notifier    = make_notifier()
        controller  = RetryController(max_retries=3, notifier=notifier)
        initial     = MagicMock(return_value="gute Antwort")
        refine      = MagicMock()
        verify      = MagicMock(return_value=make_result(ScoringDecision.OUTPUT))
        transform   = MagicMock()

        result = controller.run(
            context      = make_context(),
            initial_call = initial,
            refine_call  = refine,
            verify       = verify,
            transform    = transform,
        )

        assert result == "gute Antwort"
        initial.assert_called_once()
        refine.assert_not_called()
        transform.assert_not_called()
        notifier.notify_escalation.assert_not_called()

    def test_output_after_refinement(self):
        notifier   = make_notifier()
        controller = RetryController(max_retries=3, notifier=notifier)
        initial    = MagicMock(return_value="schlechte Antwort")
        refine     = MagicMock(return_value="gute Antwort")
        decisions  = [
            make_result(ScoringDecision.REFINEMENT),
            make_result(ScoringDecision.OUTPUT),
        ]
        verify     = MagicMock(side_effect=decisions)
        transform  = MagicMock()

        result = controller.run(
            context      = make_context(),
            initial_call = initial,
            refine_call  = refine,
            verify       = verify,
            transform    = transform,
        )

        assert result == "gute Antwort"
        assert initial.call_count == 1
        assert refine.call_count == 1
        assert verify.call_count == 2


class TestRetryControllerTransform:
    """TRANSFORM-Entscheidung → Transformer anwenden."""

    def test_transform_on_first_attempt(self):
        notifier   = make_notifier()
        controller = RetryController(max_retries=3, notifier=notifier)
        initial    = MagicMock(return_value="mittelmäßige Antwort")
        verify     = MagicMock(return_value=make_result(ScoringDecision.TRANSFORM))
        transform  = MagicMock(return_value="angepasste Antwort")

        result = controller.run(
            context      = make_context(),
            initial_call = initial,
            refine_call  = MagicMock(),
            verify       = verify,
            transform    = transform,
        )

        assert result == "angepasste Antwort"
        transform.assert_called_once_with("mittelmäßige Antwort")

    def test_transform_after_refinement(self):
        notifier   = make_notifier()
        controller = RetryController(max_retries=3, notifier=notifier)
        initial    = MagicMock(return_value="schlechte Antwort")
        refine     = MagicMock(return_value="mittelmäßige Antwort")
        decisions  = [
            make_result(ScoringDecision.REFINEMENT),
            make_result(ScoringDecision.TRANSFORM),
        ]
        verify    = MagicMock(side_effect=decisions)
        transform = MagicMock(return_value="angepasste Antwort")

        result = controller.run(
            context      = make_context(),
            initial_call = initial,
            refine_call  = refine,
            verify       = verify,
            transform    = transform,
        )

        assert result == "angepasste Antwort"
        transform.assert_called_once_with("mittelmäßige Antwort")

    def test_transform_does_not_count_as_llm_call(self):
        """Transformer darf max_retries nicht beeinflussen (F5)."""
        notifier   = make_notifier()
        controller = RetryController(max_retries=1, notifier=notifier)
        initial    = MagicMock(return_value="ok")
        verify     = MagicMock(return_value=make_result(ScoringDecision.TRANSFORM))
        transform  = MagicMock(return_value="transformiert")

        result = controller.run(
            context      = make_context(),
            initial_call = initial,
            refine_call  = MagicMock(),
            verify       = verify,
            transform    = transform,
        )

        assert result == "transformiert"
        notifier.notify_escalation.assert_not_called()


class TestRetryControllerRefinement:
    """REFINEMENT exhausted → RetryLimitError + Notifier."""

    def test_limit_exhausted_raises(self):
        notifier   = make_notifier()
        controller = RetryController(max_retries=2, notifier=notifier)
        initial    = MagicMock(return_value="Antwort 1")
        refine     = MagicMock(return_value="Antwort 2")
        verify     = MagicMock(return_value=make_result(ScoringDecision.REFINEMENT))

        with pytest.raises(RetryLimitError) as exc_info:
            controller.run(
                context      = make_context(),
                initial_call = initial,
                refine_call  = refine,
                verify       = verify,
                transform    = MagicMock(),
            )

        assert exc_info.value.attempts == 2

    def test_notifier_called_on_exhaustion(self):
        notifier   = make_notifier()
        controller = RetryController(max_retries=2, notifier=notifier)
        ctx        = make_context()

        with pytest.raises(RetryLimitError):
            controller.run(
                context      = ctx,
                initial_call = MagicMock(return_value="x"),
                refine_call  = MagicMock(return_value="y"),
                verify       = MagicMock(return_value=make_result(ScoringDecision.REFINEMENT)),
                transform    = MagicMock(),
            )

        notifier.notify_escalation.assert_called_once()
        call_kwargs = notifier.notify_escalation.call_args[1]
        assert call_kwargs["session_id"] == ctx.session_id
        assert call_kwargs["retry_count"] == 2

    def test_max_retries_1_raises_immediately(self):
        notifier   = make_notifier()
        controller = RetryController(max_retries=1, notifier=notifier)

        with pytest.raises(RetryLimitError) as exc_info:
            controller.run(
                context      = make_context(),
                initial_call = MagicMock(return_value="schlecht"),
                refine_call  = MagicMock(),
                verify       = MagicMock(return_value=make_result(ScoringDecision.REFINEMENT)),
                transform    = MagicMock(),
            )

        assert exc_info.value.attempts == 1

    def test_refine_called_with_error_summary(self):
        """refine_call bekommt den error_summary aus dem VerificationResult."""
        notifier   = make_notifier()
        controller = RetryController(max_retries=3, notifier=notifier)

        bad_result  = make_result(ScoringDecision.REFINEMENT)
        good_result = make_result(ScoringDecision.OUTPUT)
        # Füge einen Fehler ein damit error_summary nicht leer ist
        bad_result.semantic_s1 = CheckResult(
            level=ScoreLevel.LOW, details="Stilregel verletzt"
        )

        refine = MagicMock(return_value="besser")
        verify = MagicMock(side_effect=[bad_result, good_result])

        controller.run(
            context      = make_context(),
            initial_call = MagicMock(return_value="schlecht"),
            refine_call  = refine,
            verify       = verify,
            transform    = MagicMock(),
        )

        # refine_call muss mit (prev_output, error_summary) aufgerufen worden sein
        refine.assert_called_once()
        args = refine.call_args[0]
        assert args[0] == "schlecht"
        assert "Stilregel verletzt" in args[1]

    def test_exact_retry_count_with_three_attempts(self):
        """Drei Versuche: initial + 2 Refinements → Limit bei max_retries=3."""
        notifier   = make_notifier()
        controller = RetryController(max_retries=3, notifier=notifier)
        initial    = MagicMock(return_value="v1")
        refine     = MagicMock(side_effect=["v2", "v3"])
        verify     = MagicMock(return_value=make_result(ScoringDecision.REFINEMENT))

        with pytest.raises(RetryLimitError) as exc_info:
            controller.run(
                context      = make_context(),
                initial_call = initial,
                refine_call  = refine,
                verify       = verify,
                transform    = MagicMock(),
            )

        assert exc_info.value.attempts == 3
        assert initial.call_count == 1
        assert refine.call_count == 2     # 2 Refinements nach initial


class TestRetryControllerInit:
    def test_max_retries_zero_raises(self):
        with pytest.raises(ValueError):
            RetryController(max_retries=0, notifier=make_notifier())

    def test_max_retries_negative_raises(self):
        with pytest.raises(ValueError):
            RetryController(max_retries=-1, notifier=make_notifier())
