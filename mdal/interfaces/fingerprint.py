"""
Fingerprint-Matcher Protocol — Nahtstelle für spätere Rust-Extraktion.

Der mathematische Kern des Embedding-Vergleichs (Schicht 2) ist
rechenintensiv und ein klarer Kandidat für den Rust-Kern.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class FingerprintMatcherProtocol(Protocol):
    """
    Berechnet die Ähnlichkeit zwischen dem Embedding eines aktuellen
    Outputs und dem Ziel-Embedding aus dem Fingerprint.

    Gibt einen Wert zwischen 0.0 (keine Ähnlichkeit) und 1.0 (identisch) zurück.
    Die Schwellwerte für low/medium/high werden extern konfiguriert.

    → Rust-Kern (Zielarchitektur): Cosine-Similarity auf float-Vektoren
    """

    def similarity(
        self,
        output_embedding: list[float],
        target_embedding: list[float],
    ) -> float:
        ...
