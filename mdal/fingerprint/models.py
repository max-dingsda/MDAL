"""
Fingerprint-Datenmodell — drei Schichten von schnell/günstig bis langsam/präzise.

Schicht 1 — Stilregeln:      harte, messbare Eigenschaften (deterministisch, schnell)
Schicht 2 — Embedding-Profil: mathematische Repräsentation des Zielstils
Schicht 3 — Golden Samples:  Referenz-Interaktionen für LLM-as-Judge

Der Fingerprint wird pro Sprache gepflegt (F8) und ist versioniert (F7).
→ Rust-Kern (Zielarchitektur): Schicht 1 + 2 wandern in den Rust-Kern.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schicht 1 — Stilregeln
# ---------------------------------------------------------------------------

class StyleRule(BaseModel):
    """Eine einzelne, beschreibende Stilregel — ergänzt die Messgrößen."""
    name:        str
    description: str


class StyleRules(BaseModel):
    """
    Schicht 1 des Fingerprints.

    Enthält messbare Eigenschaften (Formalität, Satzlänge, Vokabular)
    sowie freitextliche Regeln die der Trainer aus dem LLM extrahiert.
    Diese Schicht ist der Vorfilter — schnell und deterministisch.

    → Rust-Kern: Regelabgleich läuft als kompilierter Code.
    """
    # 1 = sehr informal, 5 = sehr formal
    formality_level:         int            = Field(default=3, ge=1, le=5)
    avg_sentence_length_max: int | None     = None    # Wörter pro Satz
    preferred_vocabulary:    list[str]      = Field(default_factory=list)
    avoided_vocabulary:      list[str]      = Field(default_factory=list)
    custom_rules:            list[StyleRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schicht 2 — Embedding-Profil
# ---------------------------------------------------------------------------

class EmbeddingProfile(BaseModel):
    """
    Schicht 2 des Fingerprints.

    Der Centroid-Vektor ist der Durchschnitt aller Referenz-Embeddings
    aus dem Trainer. Er repräsentiert den "Mittelpunkt" des Zielstils
    im Embedding-Raum.

    → Rust-Kern: Cosine-Similarity-Berechnung auf float-Vektoren.
    """
    centroid:     list[float]
    model_name:   str            # Embedding-Modell das den Vektor erzeugt hat
    sample_count: int            # Anzahl der Samples die in den Centroid geflossen sind
    dimensions:   int            # Vektordimension — für spätere Konsistenzprüfung


# ---------------------------------------------------------------------------
# Schicht 3 — Golden Samples
# ---------------------------------------------------------------------------

class GoldenSample(BaseModel):
    """
    Ein einzelnes Referenz-Interaktionspaar für Schicht 3 (LLM-as-Judge).

    Der Judge bekommt diese Samples als Kontext und entscheidet ob
    der zu prüfende Output stilistisch dazu passt.
    """
    prompt:   str
    response: str


class GoldenSamples(BaseModel):
    """
    Schicht 3 des Fingerprints.

    Maximale Präzision, höchste Kosten — nur für Grenzfälle (TIEBREAK).
    Die Samples werden vom Trainer aus echten Chat-Verläufen selektiert.
    """
    samples: list[GoldenSample] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Fingerprint (vollständig)
# ---------------------------------------------------------------------------

class Fingerprint(BaseModel):
    """
    Vollständiger Charakter-Fingerabdruck.

    Versioniert (F7), sprachsensitiv (F8), aus echten Daten destilliert (F17).
    Rohdaten (Chat-Verläufe) werden nach Trainer-Lauf verworfen (NF3) —
    persistiert wird ausschließlich dieser destillierte Fingerabdruck.
    """
    id:         str      = Field(default_factory=lambda: str(uuid4()))
    version:    int
    language:   str      # ISO 639-1: "de", "en", "fr", …
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    layer1: StyleRules
    layer2: EmbeddingProfile
    layer3: GoldenSamples

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, data: str) -> Fingerprint:
        return cls.model_validate_json(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fingerprint:
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Konversationsformat für den Trainer
# ---------------------------------------------------------------------------

class ConversationTurn(BaseModel):
    """Eine Gesprächsrunde — ein Zug in einem Multi-Turn-Gespräch."""
    role:    str    # "user" | "assistant" | "system"
    content: str


class Conversation(BaseModel):
    """
    Ein vollständiger Chat-Verlauf als Trainer-Input.

    Format ist bewusst OpenAI-kompatibel — erleichtert den Import
    aus bestehenden Chat-Export-Formaten.
    """
    turns:    list[ConversationTurn]
    language: str = "de"

    def assistant_responses(self) -> list[str]:
        """Gibt alle Assistent-Antworten zurück — Basis für Layer 2."""
        return [t.content for t in self.turns if t.role == "assistant"]

    def as_turn_pairs(self) -> list[tuple[str, str]]:
        """
        Gibt (User-Prompt, Assistent-Antwort)-Paare zurück.
        Basis für Golden Sample Selektion (Layer 3).
        """
        pairs: list[tuple[str, str]] = []
        for i, turn in enumerate(self.turns):
            if turn.role == "assistant" and i > 0 and self.turns[i - 1].role == "user":
                pairs.append((self.turns[i - 1].content, turn.content))
        return pairs

    @classmethod
    def from_openai_format(cls, data: list[dict[str, str]], language: str = "de") -> Conversation:
        """Lädt aus OpenAI-kompatiblem Format: [{"role": ..., "content": ...}]."""
        return cls(
            turns=[ConversationTurn(**t) for t in data],
            language=language,
        )
