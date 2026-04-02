"""Unit-Tests für mdal.fingerprint.store — FingerprintStore (F7)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mdal.fingerprint.models import (
    EmbeddingProfile,
    Fingerprint,
    GoldenSamples,
    StyleRules,
)
from mdal.fingerprint.store import FingerprintNotFoundError, FingerprintStore


# ---------------------------------------------------------------------------
# Fixture: minimaler gültiger Fingerprint
# ---------------------------------------------------------------------------

def make_fingerprint(language: str = "de", version: int = 0) -> Fingerprint:
    return Fingerprint(
        version=version,
        language=language,
        layer1=StyleRules(formality_level=3),
        layer2=EmbeddingProfile(
            centroid=[0.1, 0.2, 0.3],
            model_name="nomic-embed-text",
            sample_count=5,
            dimensions=3,
        ),
        layer3=GoldenSamples(samples=[]),
    )


def store(tmp_path: Path) -> FingerprintStore:
    return FingerprintStore(tmp_path / "fingerprints")


# ---------------------------------------------------------------------------
# Speichern
# ---------------------------------------------------------------------------

class TestSave:
    def test_returns_version_1_for_first_save(self, tmp_path):
        v = store(tmp_path).save(make_fingerprint())
        assert v == 1

    def test_returns_incrementing_versions(self, tmp_path):
        s = store(tmp_path)
        assert s.save(make_fingerprint()) == 1
        assert s.save(make_fingerprint()) == 2
        assert s.save(make_fingerprint()) == 3

    def test_creates_version_file(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        assert (tmp_path / "fingerprints" / "de" / "v1.json").exists()

    def test_creates_pointer_file(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        assert (tmp_path / "fingerprints" / "de" / "current").exists()

    def test_pointer_points_to_latest_version(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        assert s.current_version("de") == 2

    def test_saves_correct_language_subdirectory(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("en"))
        assert (tmp_path / "fingerprints" / "en" / "v1.json").exists()

    def test_different_languages_are_independent(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("en"))
        assert s.current_version("de") == 2
        assert s.current_version("en") == 1

    def test_version_in_saved_fingerprint_matches_assigned_version(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        fp = s.load_current("de")
        assert fp.version == 1


# ---------------------------------------------------------------------------
# Laden
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_current_returns_latest(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        fp2 = make_fingerprint("de")
        fp2 = fp2.model_copy(update={"layer1": StyleRules(formality_level=5)})
        s.save(fp2)
        loaded = s.load_current("de")
        assert loaded.layer1.formality_level == 5

    def test_load_version_returns_specific_version(self, tmp_path):
        s = store(tmp_path)
        fp1 = make_fingerprint("de")
        fp1 = fp1.model_copy(update={"layer1": StyleRules(formality_level=2)})
        fp2 = make_fingerprint("de")
        fp2 = fp2.model_copy(update={"layer1": StyleRules(formality_level=4)})
        s.save(fp1)
        s.save(fp2)
        loaded = s.load_version("de", 1)
        assert loaded.layer1.formality_level == 2

    def test_load_current_raises_when_no_fingerprint(self, tmp_path):
        with pytest.raises(FingerprintNotFoundError):
            store(tmp_path).load_current("de")

    def test_load_version_raises_when_version_missing(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        with pytest.raises(FingerprintNotFoundError):
            s.load_version("de", 99)

    def test_roundtrip_preserves_all_layers(self, tmp_path):
        s = store(tmp_path)
        fp = Fingerprint(
            version=0,
            language="de",
            layer1=StyleRules(
                formality_level=4,
                preferred_vocabulary=["präzise", "strukturiert"],
                avoided_vocabulary=["halt", "irgendwie"],
            ),
            layer2=EmbeddingProfile(
                centroid=[0.1, 0.9, 0.5],
                model_name="nomic-embed-text",
                sample_count=10,
                dimensions=3,
            ),
            layer3=GoldenSamples(samples=[]),
        )
        s.save(fp)
        loaded = s.load_current("de")
        assert loaded.layer1.preferred_vocabulary == ["präzise", "strukturiert"]
        assert loaded.layer2.centroid == [0.1, 0.9, 0.5]
        assert loaded.layer2.model_name == "nomic-embed-text"


# ---------------------------------------------------------------------------
# Rollback (F7)
# ---------------------------------------------------------------------------

class TestRollback:
    def test_rollback_changes_current_pointer(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        s.rollback("de", 1)
        assert s.current_version("de") == 1

    def test_rollback_load_current_returns_rolled_back_version(self, tmp_path):
        s = store(tmp_path)
        fp1 = make_fingerprint("de")
        fp1 = fp1.model_copy(update={"layer1": StyleRules(formality_level=1)})
        fp2 = make_fingerprint("de")
        fp2 = fp2.model_copy(update={"layer1": StyleRules(formality_level=5)})
        s.save(fp1)
        s.save(fp2)
        s.rollback("de", 1)
        assert s.load_current("de").layer1.formality_level == 1

    def test_rollback_to_nonexistent_version_raises(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        with pytest.raises(FingerprintNotFoundError):
            s.rollback("de", 99)

    def test_rollback_does_not_delete_newer_versions(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        s.rollback("de", 1)
        assert s.load_version("de", 2) is not None


# ---------------------------------------------------------------------------
# list_versions / has_fingerprint
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_list_versions_empty_for_unknown_language(self, tmp_path):
        assert store(tmp_path).list_versions("de") == []

    def test_list_versions_returns_sorted_list(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        s.save(make_fingerprint("de"))
        assert s.list_versions("de") == [1, 2, 3]

    def test_has_fingerprint_false_when_empty(self, tmp_path):
        assert store(tmp_path).has_fingerprint("de") is False

    def test_has_fingerprint_true_after_save(self, tmp_path):
        s = store(tmp_path)
        s.save(make_fingerprint("de"))
        assert s.has_fingerprint("de") is True

    def test_current_version_none_when_empty(self, tmp_path):
        assert store(tmp_path).current_version("de") is None
