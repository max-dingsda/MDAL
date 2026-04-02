"""Unit-Tests für mdal.session — SessionContext (F14, NF3)."""

import pytest

from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext


def make_result(level: ScoreLevel = ScoreLevel.HIGH) -> CheckResult:
    return CheckResult(level=level, details="test")


class TestSessionContext:
    def test_session_id_is_unique(self):
        s1 = SessionContext(language="de", fingerprint_version=1)
        s2 = SessionContext(language="de", fingerprint_version=1)
        assert s1.session_id != s2.session_id

    def test_initial_turn_count_is_zero(self):
        s = SessionContext(language="de", fingerprint_version=1)
        assert s.turn_count == 0

    def test_initial_check_history_is_empty(self):
        s = SessionContext(language="de", fingerprint_version=1)
        assert s.check_history() == []

    def test_has_prior_checks_false_initially(self):
        s = SessionContext(language="de", fingerprint_version=1)
        assert s.has_prior_checks() is False

    def test_record_check_increments_turn_count(self):
        s = SessionContext(language="de", fingerprint_version=1)
        s.record_check(make_result())
        s.record_check(make_result())
        assert s.turn_count == 2

    def test_record_check_appends_to_history(self):
        s = SessionContext(language="de", fingerprint_version=1)
        r1 = make_result(ScoreLevel.HIGH)
        r2 = make_result(ScoreLevel.LOW)
        s.record_check(r1)
        s.record_check(r2)
        history = s.check_history()
        assert len(history) == 2
        assert history[0].level == ScoreLevel.HIGH
        assert history[1].level == ScoreLevel.LOW

    def test_has_prior_checks_true_after_record(self):
        s = SessionContext(language="de", fingerprint_version=1)
        s.record_check(make_result())
        assert s.has_prior_checks() is True

    def test_last_check_returns_most_recent(self):
        s = SessionContext(language="de", fingerprint_version=1)
        s.record_check(make_result(ScoreLevel.HIGH))
        s.record_check(make_result(ScoreLevel.LOW))
        assert s.last_check().level == ScoreLevel.LOW

    def test_last_check_returns_none_when_empty(self):
        s = SessionContext(language="de", fingerprint_version=1)
        assert s.last_check() is None

    def test_check_history_returns_copy(self):
        """Externe Mutation der History darf den internen Zustand nicht verändern."""
        s = SessionContext(language="de", fingerprint_version=1)
        s.record_check(make_result())
        history = s.check_history()
        history.clear()
        assert len(s.check_history()) == 1

    def test_no_persistence_between_instances(self):
        """Zwei SessionContext-Instanzen teilen keinen Zustand."""
        s1 = SessionContext(language="de", fingerprint_version=1)
        s2 = SessionContext(language="de", fingerprint_version=1)
        s1.record_check(make_result())
        assert s2.turn_count == 0
        assert s2.check_history() == []
