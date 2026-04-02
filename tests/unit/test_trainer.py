"""Unit-Tests für mdal.trainer.trainer — Trainer (F17)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mdal.fingerprint.models import Conversation, GoldenSample
from mdal.fingerprint.store import FingerprintStore
from mdal.trainer.trainer import (
    Trainer,
    TrainerError,
    _extract_json,
    load_conversations_from_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STYLE_RULES_RESPONSE = json.dumps({
    "formality_level": 4,
    "avg_sentence_length_max": 20,
    "preferred_vocabulary": ["präzise", "strukturiert"],
    "avoided_vocabulary": ["halt"],
    "custom_rules": [{"name": "keine-emoticons", "description": "Keine Emoticons verwenden"}],
})

SAMPLE_SELECTION_RESPONSE = json.dumps({"selected": [1, 2]})

SAMPLE_CONVERSATIONS = [
    Conversation.from_openai_format([
        {"role": "user",      "content": "Was ist MDAL?"},
        {"role": "assistant", "content": "MDAL ist eine Middleware zur Output-Normalisierung."},
        {"role": "user",      "content": "Und wie funktioniert das?"},
        {"role": "assistant", "content": "Es prüft jeden LLM-Output gegen einen Fingerabdruck."},
    ], language="de"),
]


def make_trainer(tmp_path: Path, llm_responses: list[str]) -> tuple[Trainer, MagicMock, MagicMock]:
    llm = MagicMock()
    llm.complete.side_effect = llm_responses

    embed = MagicMock()
    embed.embed.return_value = [0.1, 0.2, 0.3]

    store = FingerprintStore(tmp_path / "fingerprints")
    trainer = Trainer(llm_adapter=llm, embedding_adapter=embed, store=store)
    return trainer, llm, embed


# ---------------------------------------------------------------------------
# Haupt-Trainer-Lauf
# ---------------------------------------------------------------------------

class TestTrainerRun:
    def test_returns_version_number(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        version = trainer.run(SAMPLE_CONVERSATIONS, language="de")
        assert version == 1

    def test_saves_fingerprint_to_store(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        assert store.has_fingerprint("de")

    def test_raises_on_empty_conversations(self, tmp_path):
        trainer, _, _ = make_trainer(tmp_path, [])
        with pytest.raises(TrainerError, match="Mindestens eine Konversation"):
            trainer.run([], language="de")

    def test_raises_on_conversations_with_no_assistant_turns(self, tmp_path):
        trainer, _, _ = make_trainer(tmp_path, [])
        conv = Conversation.from_openai_format([
            {"role": "user", "content": "Hi"},
            {"role": "user", "content": "Noch eine Frage"},
        ], language="de")
        with pytest.raises(TrainerError, match="Assistent-Antworten"):
            trainer.run([conv], language="de")

    def test_calls_llm_for_style_extraction(self, tmp_path):
        trainer, llm, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        assert llm.complete.call_count >= 1

    def test_calls_embedding_for_each_assistant_response(self, tmp_path):
        trainer, _, embed = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        # 2 Assistent-Antworten in SAMPLE_CONVERSATIONS
        assert embed.embed.call_count == 2


# ---------------------------------------------------------------------------
# Layer 1 — Stilregel-Extraktion
# ---------------------------------------------------------------------------

class TestLayer1Extraction:
    def test_formality_level_extracted(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert fp.layer1.formality_level == 4

    def test_preferred_vocabulary_extracted(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert "präzise" in fp.layer1.preferred_vocabulary

    def test_custom_rules_extracted(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert any(r.name == "keine-emoticons" for r in fp.layer1.custom_rules)

    def test_malformed_llm_response_raises_trainer_error(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            ["Das ist kein JSON", SAMPLE_SELECTION_RESPONSE],
        )
        with pytest.raises(TrainerError, match="Layer-1-Extraktion"):
            trainer.run(SAMPLE_CONVERSATIONS, language="de")


# ---------------------------------------------------------------------------
# Layer 2 — Embedding-Profil
# ---------------------------------------------------------------------------

class TestLayer2EmbeddingProfile:
    def test_centroid_computed(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert fp.layer2.centroid == [0.1, 0.2, 0.3]

    def test_sample_count_matches_responses(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert fp.layer2.sample_count == 2

    def test_centroid_is_average_of_embeddings(self, tmp_path):
        trainer, _, embed = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        embed.embed.side_effect = [[1.0, 0.0], [0.0, 1.0]]
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert fp.layer2.centroid == [0.5, 0.5]


# ---------------------------------------------------------------------------
# Layer 3 — Golden Samples
# ---------------------------------------------------------------------------

class TestLayer3GoldenSamples:
    def test_golden_samples_saved(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, SAMPLE_SELECTION_RESPONSE],
        )
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert len(fp.layer3.samples) > 0

    def test_fallback_used_when_selection_response_malformed(self, tmp_path):
        trainer, _, _ = make_trainer(
            tmp_path,
            [STYLE_RULES_RESPONSE, "kein JSON hier"],
        )
        # Sollte nicht werfen — Fallback zu ersten N Samples
        trainer.run(SAMPLE_CONVERSATIONS, language="de")
        store = FingerprintStore(tmp_path / "fingerprints")
        fp = store.load_current("de")
        assert isinstance(fp.layer3.samples, list)


# ---------------------------------------------------------------------------
# _extract_json Hilfsfunktion
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"key": "value"}') == {"key": "value"}

    def test_json_with_markdown_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert _extract_json(text) == {"key": "value"}

    def test_json_with_plain_fence(self):
        text = '```\n{"key": "value"}\n```'
        assert _extract_json(text) == {"key": "value"}

    def test_json_with_preamble_text(self):
        text = 'Hier ist das Ergebnis: {"key": "value"} Das war es.'
        assert _extract_json(text) == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _extract_json("kein json")


# ---------------------------------------------------------------------------
# load_conversations_from_file
# ---------------------------------------------------------------------------

class TestLoadConversations:
    def test_loads_single_conversation(self, tmp_path):
        data = [
            {"role": "user",      "content": "Hallo"},
            {"role": "assistant", "content": "Guten Tag"},
        ]
        p = tmp_path / "conv.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        convs = load_conversations_from_file(p, language="de")
        assert len(convs) == 1
        assert len(convs[0].turns) == 2

    def test_loads_multiple_conversations(self, tmp_path):
        data = [
            [{"role": "user", "content": "A"}, {"role": "assistant", "content": "B"}],
            [{"role": "user", "content": "C"}, {"role": "assistant", "content": "D"}],
        ]
        p = tmp_path / "convs.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        convs = load_conversations_from_file(p, language="de")
        assert len(convs) == 2

    def test_empty_file_returns_empty_list(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("[]", encoding="utf-8")
        assert load_conversations_from_file(p) == []

    def test_language_applied(self, tmp_path):
        data = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
        p = tmp_path / "conv.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        convs = load_conversations_from_file(p, language="en")
        assert convs[0].language == "en"
