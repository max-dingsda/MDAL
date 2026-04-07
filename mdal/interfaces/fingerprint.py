"""
Fingerprint matcher protocol — interface for future Rust extraction.

The mathematical core of the embedding comparison (Layer 2) is
computationally intensive and a clear candidate for the Rust core.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class FingerprintMatcherProtocol(Protocol):
    """
    Computes the similarity between the embedding of a current output
    and the target embedding from the fingerprint.

    Returns a value between 0.0 (no similarity) and 1.0 (identical).
    Thresholds for low/medium/high are configured externally.

    → Rust core (target architecture): cosine similarity on float vectors
    """

    def similarity(
        self,
        output_embedding: list[float],
        target_embedding: list[float],
    ) -> float:
        ...
