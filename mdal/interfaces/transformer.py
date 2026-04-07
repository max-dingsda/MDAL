"""
Tone transformer protocol — interface for future Rust extraction.

The transformer adjusts tonality only (F10).
Structure, order, hierarchy, and completeness remain unchanged.
No LLM call — therefore does not count as a retry (F5).

→ Rust core (target architecture)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mdal.fingerprint.models import Fingerprint


@runtime_checkable
class ToneTransformerProtocol(Protocol):
    """
    Transforms the tone of a text according to the fingerprint.

    Invariants (F10):
    - Order of statements is preserved
    - Hierarchy and list structure is preserved
    - Completeness: no content is added or removed
    - Only tonality, formality level, and phrasing style are adjusted
    """

    def transform(self, text: str, fingerprint: Fingerprint, domain: str = "DEFAULT") -> str:
        ...
