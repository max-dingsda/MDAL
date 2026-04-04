"""
Semantic Layer 2 — Embedding-Vergleich (SemanticCheckerProtocol).

Berechnet den Embedding-Vektor des aktuellen Outputs und vergleicht ihn
mit dem Centroid-Vektor aus dem Fingerprint via Cosine-Similarity.

Schwellwerte (konfigurierbar, Defaults hier als Ausgangspunkt für Kalibrierung):
  similarity >= THRESHOLD_HIGH  → HIGH
  similarity >= THRESHOLD_LOW   → MEDIUM
  similarity <  THRESHOLD_LOW   → LOW

Diese Schwellwerte sind eine der vier offenen PoC-Fragen — beobachten und justieren.

→ Rust-Kern (Zielarchitektur): Cosine-Similarity auf float-Vektoren,
  rechenintensiv bei großen Embedding-Dimensionen.
"""

from __future__ import annotations

import math

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext

# Schwellwerte für die Score-Einstufung
# Phase 6 Kalibrierung (2026-04-04, Pilot-Fingerprint 30 Konversationen):
#   - 0.85 war zu hoch: stilkonformer ChatGPT-Text erreichte nur 0.8416 → nie OUTPUT
#   - 0.82 empirisch passend: guter Stil → HIGH, leichte Abweichungen → MEDIUM
#   - 0.65 passt: informelle Texte landen in MEDIUM (→ TRANSFORM), nicht LOW (→ REFINEMENT)
# Nach Full-Run (454 Konversationen) erneut prüfen und ggf. nachjustieren.
THRESHOLD_HIGH: float = 0.80  # was 0.85→0.82→0.80, kalibriert 2026-04-04 gegen v2-Fingerprint (454 Konversationen)
THRESHOLD_LOW:  float = 0.65


class Layer2EmbeddingChecker:
    """
    Implementiert SemanticCheckerProtocol via Embedding-Ähnlichkeitsvergleich.

    Benötigt einen Embedding-Adapter (dediziertes Embedding-Modell, z.B. nomic-embed-text).
    Muss dasselbe Modell wie der Trainer verwenden — sonst sind Vektoren nicht vergleichbar.
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
            details=f"Cosine-Similarity: {similarity:.4f} "
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
# Cosine-Similarity
# → Rust-Kern: dieser Rechenkernel ist der primäre Kandidat für PyO3-Extraktion
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Berechnet die Cosine-Similarity zwischen zwei Vektoren.

    Gibt 0.0 zurück wenn einer der Vektoren Nulllänge hat.
    Wirft ValueError bei unterschiedlichen Dimensionen.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Vektoren haben unterschiedliche Dimensionen: {len(a)} vs {len(b)}"
        )

    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)
