"""Unit tests for Semantic Layer 2 — embedding comparison."""

import math
from unittest.mock import MagicMock

import pytest

from mdal.fingerprint.models import (
    EmbeddingProfile, Fingerprint, GoldenSamples, StyleRules,
)
from mdal.interfaces.scoring import ScoreLevel
from mdal.session import SessionContext
from mdal.verification.semantic.layer2 import (
    THRESHOLD_HIGH, THRESHOLD_LOW, Layer2EmbeddingChecker, cosine_similarity,
)


def make_fingerprint(centroid: list[float]) -> Fingerprint:
    return Fingerprint(
        version=1, language="de",
        layer1=StyleRules(formality_level=3),
        layer2=EmbeddingProfile(
            centroid=centroid,
            model_name="nomic-embed-text",
            sample_count=5,
            dimensions=len(centroid),
        ),
        layer3=GoldenSamples(samples=[]),
    )


def make_context() -> SessionContext:
    return SessionContext(language="de", fingerprint_version=1)


# ---------------------------------------------------------------------------
# cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_give_1(self):
        v = [1.0, 0.5, 0.3]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_give_0(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_give_minus_1(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_gives_0(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.5]) == 0.0

    def test_dimension_mismatch_raises(self):
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0])

    def test_known_value(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 1.0]
        expected = 1.0 / (math.sqrt(2) * math.sqrt(2))
        assert cosine_similarity(a, b) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Layer2EmbeddingChecker
# ---------------------------------------------------------------------------

class TestLayer2EmbeddingChecker:
    def _make_checker(self, output_embedding: list[float]) -> tuple[Layer2EmbeddingChecker, MagicMock]:
        embed_mock = MagicMock()
        embed_mock.embed.return_value = output_embedding
        checker = Layer2EmbeddingChecker(embedding_adapter=embed_mock)
        return checker, embed_mock

    def test_identical_embedding_gives_high(self):
        v = [1.0, 0.5, 0.3]
        checker, _ = self._make_checker(v)
        result = checker.check("text", make_fingerprint(v), make_context())
        assert result.level == ScoreLevel.HIGH

    def test_orthogonal_embedding_gives_low(self):
        centroid = [1.0, 0.0, 0.0]
        output   = [0.0, 1.0, 0.0]
        checker, _ = self._make_checker(output)
        result = checker.check("text", make_fingerprint(centroid), make_context())
        assert result.level == ScoreLevel.LOW

    def test_medium_similarity_gives_medium(self):
        # Cosine similarity between these vectors lies between threshold_low and high
        centroid = [1.0, 0.0]
        # 45° → similarity = cos(45°) ≈ 0.707
        import math
        output = [math.cos(math.radians(45)), math.sin(math.radians(45))]
        checker = Layer2EmbeddingChecker(
            embedding_adapter=MagicMock(embed=MagicMock(return_value=output)),
            threshold_high=0.85,
            threshold_low=0.65,
        )
        result = checker.check("text", make_fingerprint(centroid), make_context())
        assert result.level == ScoreLevel.MEDIUM

    def test_result_contains_raw_score(self):
        v = [1.0, 0.0]
        checker, _ = self._make_checker(v)
        result = checker.check("text", make_fingerprint(v), make_context())
        assert result.raw_score is not None
        assert 0.0 <= result.raw_score <= 1.0

    def test_result_contains_similarity_in_details(self):
        v = [1.0, 0.0]
        checker, _ = self._make_checker(v)
        result = checker.check("text", make_fingerprint(v), make_context())
        assert "similarity" in result.details.lower() or "cosine" in result.details.lower()

    def test_calls_embed_with_output_text(self):
        v = [1.0, 0.0]
        checker, embed_mock = self._make_checker(v)
        checker.check("my output text", make_fingerprint(v), make_context())
        embed_mock.embed.assert_called_once_with("my output text")

    def test_custom_thresholds_respected(self):
        # With very high threshold_high → MEDIUM instead of HIGH
        v = [1.0, 0.0]
        embed_mock = MagicMock(embed=MagicMock(return_value=v))
        checker = Layer2EmbeddingChecker(
            embedding_adapter=embed_mock,
            threshold_high=1.1,   # unerreichbar
            threshold_low=0.5,
        )
        result = checker.check("text", make_fingerprint(v), make_context())
        assert result.level == ScoreLevel.MEDIUM
