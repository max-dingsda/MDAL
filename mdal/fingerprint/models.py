"""
Fingerprint data model — three layers from fast/cheap to slow/precise.

Layer 1 — Style rules:      hard, measurable properties (deterministic, fast)
Layer 2 — Embedding profile: mathematical representation of the target style
Layer 3 — Golden samples:   reference interactions for LLM-as-Judge

The fingerprint is maintained per language (F8) and is versioned (F7).
→ Rust core (target architecture): layers 1 + 2 migrate to the Rust core.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Layer 1 — Style rules
# ---------------------------------------------------------------------------

class StyleRule(BaseModel):
    """A single descriptive style rule — supplements the measurable properties."""
    name:        str
    description: str


class StyleRules(BaseModel):
    """
    Layer 1 of the fingerprint.

    Contains measurable properties (formality, sentence length, vocabulary)
    as well as free-text rules extracted from the LLM by the trainer.
    This layer is the pre-filter — fast and deterministic.

    → Rust core: rule matching runs as compiled code.
    """
    # 1 = very informal, 5 = very formal
    formality_level:         int            = Field(default=3, ge=1, le=5)
    avg_sentence_length_max: int | None     = None    # words per sentence
    preferred_vocabulary:    list[str]      = Field(default_factory=list)
    avoided_vocabulary:      list[str]      = Field(default_factory=list)
    custom_rules:            list[StyleRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer 2 — Embedding profile
# ---------------------------------------------------------------------------

class EmbeddingProfile(BaseModel):
    """
    Layer 2 of the fingerprint.

    The centroid vector is the average of all reference embeddings
    from the trainer. It represents the "center of mass" of the target style
    in the embedding space.

    → Rust core: cosine similarity calculation on float vectors.
    """
    centroid:     list[float]
    model_name:   str            # embedding model that produced the vector
    sample_count: int            # number of samples that contributed to the centroid
    dimensions:   int            # vector dimension — for later consistency checks


# ---------------------------------------------------------------------------
# Layer 3 — Golden samples
# ---------------------------------------------------------------------------

class GoldenSample(BaseModel):
    """
    A single reference interaction pair for Layer 3 (LLM-as-Judge).

    The judge receives these samples as context and decides whether
    the output under review matches them stylistically.
    """
    prompt:   str
    response: str


class GoldenSamples(BaseModel):
    """
    Layer 3 of the fingerprint.

    Maximum precision, highest cost — used only for edge cases (TIEBREAK).
    Samples are selected by the trainer from real chat logs.
    """
    samples: list[GoldenSample] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Fingerprint (complete)
# ---------------------------------------------------------------------------

class Fingerprint(BaseModel):
    """
    Complete character fingerprint.

    Versioned (F7), language-sensitive (F8), distilled from real data (F17).
    Raw data (chat logs) are discarded after the trainer run (NF3) —
    only this distilled fingerprint is persisted.
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
# Conversation format for the trainer
# ---------------------------------------------------------------------------

class ConversationTurn(BaseModel):
    """A single turn in a multi-turn conversation."""
    role:    str    # "user" | "assistant" | "system"
    content: str


class Conversation(BaseModel):
    """
    A complete chat log as trainer input.

    The format is deliberately OpenAI-compatible — simplifies importing
    from existing chat export formats.
    """
    turns:    list[ConversationTurn]
    language: str = "de"

    def assistant_responses(self) -> list[str]:
        """Returns all assistant responses — basis for Layer 2."""
        return [t.content for t in self.turns if t.role == "assistant"]

    def as_turn_pairs(self) -> list[tuple[str, str]]:
        """
        Returns (user prompt, assistant response) pairs.
        Basis for golden sample selection (Layer 3).
        """
        pairs: list[tuple[str, str]] = []
        for i, turn in enumerate(self.turns):
            if turn.role == "assistant" and i > 0 and self.turns[i - 1].role == "user":
                pairs.append((self.turns[i - 1].content, turn.content))
        return pairs

    @classmethod
    def from_openai_format(cls, data: list[dict[str, str]], language: str = "de") -> Conversation:
        """Loads from OpenAI-compatible format: [{"role": ..., "content": ...}]."""
        return cls(
            turns=[ConversationTurn(**t) for t in data],
            language=language,
        )
