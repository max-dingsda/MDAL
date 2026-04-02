"""
Tone Transformer Protocol — Nahtstelle für spätere Rust-Extraktion.

Der Transformer passt ausschließlich Tonalität an (F10).
Struktur, Reihenfolge, Hierarchie und Vollständigkeit bleiben unverändert.
Kein LLM-Aufruf — zählt daher nicht als Retry (F5).

→ Rust-Kern (Zielarchitektur)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from mdal.fingerprint.models import Fingerprint


@runtime_checkable
class ToneTransformerProtocol(Protocol):
    """
    Transformiert den Ton eines Textes anhand des Fingerprints.

    Invarianten (F10):
    - Reihenfolge von Aussagen bleibt erhalten
    - Hierarchie und Aufzählungsstruktur bleibt erhalten
    - Vollständigkeit: kein Inhalt wird hinzugefügt oder entfernt
    - Nur Tonalität, Formalitätsniveau und Formulierungsstil werden angepasst
    """

    def transform(self, text: str, fingerprint: Fingerprint) -> str:
        ...
