"""
Semantic Layer 2 — embedding comparison (SemanticCheckerProtocol).

Computes the embedding vector of the current output and compares it
with the centroid vector from the fingerprint via cosine similarity.

Thresholds (configurable, defaults here as starting point for calibration):
  similarity >= THRESHOLD_HIGH  → HIGH
  similarity >= THRESHOLD_LOW   → MEDIUM
  similarity <  THRESHOLD_LOW   → LOW

These thresholds are one of the four open PoC questions — observe and adjust.

→ Rust core (target architecture): cosine similarity on float vectors,
  computationally intensive for large embedding dimensions.
"""

from __future__ import annotations

import math

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext

# Thresholds for score classification
# Phase 6 calibration (2026-04-04, pilot fingerprint 30 conversations):
#   - 0.85 was too high: style-conforming ChatGPT text only reached 0.8416 → never OUTPUT
#   - 0.82 empirically appropriate: good style → HIGH, minor deviations → MEDIUM
#   - 0.65 fits: informal texts land in MEDIUM (→ TRANSFORM), not LOW (→ REFINEMENT)
# Re-check after full run (454 conversations) and adjust if needed.
THRESHOLD_HIGH: float = 0.80  # was 0.85→0.82→0.80, calibrated 2026-04-04 against v2 fingerprint (454 conversations)
THRESHOLD_LOW:  float = 0.65


class Layer2EmbeddingChecker:
    """
    Implements SemanticCheckerProtocol via embedding similarity comparison.

    Requires an embedding adapter (dedicated embedding model, e.g. nomic-embed-text).
    Must use the same model as the trainer — otherwise vectors are not comparable.
    """

    def __init__(
        self,
        embedding_adapter: LLMAdapterProtocol,
        threshold_high: float = THRESHOLD_HIGH,
        threshold_low:  float = THRESHOLD_LOW,
    ) -> None:
        self._embed      = embedding_adapter
        self._thresh_high = threshold_high
        self._thresh_low  = threshold_low

    def check(
        self,
        output: str,
        fingerprint: Fingerprint,
        context: SessionContext,
    ) -> CheckResult:
        output_embedding  = self._embed.embed(output)
        target_embedding  = fingerprint.layer2.centroid
        similarity        = cosine_similarity(output_embedding, target_embedding)
        level             = self._score(similarity)

        return CheckResult(
            level=level,
            details=f"Cosine similarity: {similarity:.4f} "
                    f"(high≥{self._thresh_high}, low<{self._thresh_low})",
            raw_score=similarity,
        )

    def _score(self, similarity: float) -> ScoreLevel:
        if similarity >= self._thresh_high:
            return ScoreLevel.HIGH
        if similarity >= self._thresh_low:
            return ScoreLevel.MEDIUM
        return ScoreLevel.LOW


# ---------------------------------------------------------------------------
# Cosine similarity
# → Rust core: this compute kernel is the primary candidate for PyO3 extraction
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Computes the cosine similarity between two vectors.

    Returns 0.0 if either vector has zero length.
    Raises ValueError for vectors of different dimensions.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Vectors have different dimensions: {len(a)} vs {len(b)}"
        )

    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)
