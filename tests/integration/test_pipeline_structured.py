"""
Integrations-Tests: Pipeline mit strukturiertem Output (JSON).

Testziele:
  - Gültiger JSON-Output → Strukturprüfung bestanden → semantische Prüfung
  - Ungültiger JSON-Output → Strukturfehler → sofortiges REFINEMENT
    (kein semantischer Check nötig)
  - Strukturcheck deaktiviert (F18) → direkt zur Semantik
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mdal.config import ChecksConfig, NotifierConfig
from mdal.fingerprint.models import (
    EmbeddingProfile, Fingerprint, GoldenSamples, StyleRules,
)
from mdal.interfaces.scoring import ScoringDecision
from mdal.notifier import AdminNotifier
from mdal.plugins.registry import PluginRegistry
from mdal.retry import RetryController
from mdal.session import SessionContext
from mdal.status import QueueStatusReporter
from mdal.transformer import RuleBasedToneTransformer
from mdal.verification.engine import VerificationEngine
from mdal.verification.semantic.layer1 import Layer1RuleChecker
from mdal.verification.semantic.layer2 import Layer2EmbeddingChecker
from mdal.verification.semantic.layer3 import Layer3LLMJudge
from mdal.verification.semantic.scorer import ScoringEngine
from mdal.verification.structure import StructureChecker


@pytest.fixture
def fingerprint() -> Fingerprint:
    return Fingerprint(
        version=1, language="de",
        layer1=StyleRules(formality_level=3),
        layer2=EmbeddingProfile(
            centroid=[1.0, 0.0],
            model_name="test",
            sample_count=1,
            dimensions=2,
        ),
        layer3=GoldenSamples(samples=[]),
    )


def make_verification_engine(
    embed_mock: MagicMock,
    llm_mock:   MagicMock,
    semantic:   bool = True,
    structure:  bool = True,
) -> VerificationEngine:
    """Baut eine echte VerificationEngine mit leerer Plugin-Registry."""
    registry = PluginRegistry()   # leer — kein Plugin-Pfad nötig für JSON-Basis
    layer1   = Layer1RuleChecker()
    layer2   = Layer2EmbeddingChecker(embedding_adapter=embed_mock)
    layer3   = Layer3LLMJudge(llm_adapter=llm_mock)
    scorer   = ScoringEngine()
    checks   = ChecksConfig(semantic=semantic, structure=structure)

    return VerificationEngine(
        checks=checks, registry=registry,
        layer1=layer1, layer2=layer2, layer3=layer3, scorer=scorer,
    )


class TestValidJsonPassesStructureCheck:
    def test_valid_json_proceeds_to_semantic(self, fingerprint):
        """
        Gültiger JSON-String → Strukturprüfung OK
        (kein Plugin → elements-Prüfung entfällt, XSD entfällt)
        → semantische Prüfung läuft durch.
        """
        valid_json = '{"result": "ok", "value": 42}'

        embed_mock = MagicMock()
        embed_mock.embed.return_value = [1.0, 0.0]  # identisch → HIGH
        llm_mock   = MagicMock()

        engine = make_verification_engine(embed_mock, llm_mock)
        ctx    = SessionContext(language="de", fingerprint_version=1)

        result = engine.verify(valid_json, fingerprint, ctx)

        # Struktur hat bestanden → semantic wurde geprüft
        assert result.structure_result is not None
        assert result.structure_result.passed is True
        assert result.semantic_s1 is not None
        assert result.semantic_s2 is not None


class TestMalformedJsonTreatedAsProse:
    def test_malformed_json_detected_as_prose(self, fingerprint):
        """
        Malformed JSON (beginnt mit '{' aber parse-Fehler) →
        detect_format fällt auf PROSE zurück →
        kein Strukturcheck → Semantik läuft durch.

        Hintergrund: Der Format-Detektor versucht json.loads(); schlägt es fehl,
        ist kein JSON erkennbar und der Text gilt als Prosa. Die Struktur-
        prüfung betrifft nur erfolgreich erkanntes JSON/XML.
        """
        invalid_json = '{"result": "missing closing brace"'

        embed_mock = MagicMock()
        embed_mock.embed.return_value = [1.0, 0.0]
        llm_mock   = MagicMock()

        engine = make_verification_engine(embed_mock, llm_mock)
        ctx    = SessionContext(language="de", fingerprint_version=1)

        result = engine.verify(invalid_json, fingerprint, ctx)

        # Als Prosa erkannt → kein Strukturcheck
        assert result.structure_result is None
        assert result.output_format == "prose"
        # Semantik lief durch
        assert result.semantic_s1 is not None

    def test_truly_non_json_text_is_prose(self, fingerprint):
        """Freitext ohne JSON/XML-Merkmale → immer PROSE."""
        embed_mock = MagicMock()
        embed_mock.embed.return_value = [1.0, 0.0]
        llm_mock   = MagicMock()

        engine = make_verification_engine(embed_mock, llm_mock)
        ctx    = SessionContext(language="de", fingerprint_version=1)

        result = engine.verify("Das ist einfacher Text.", fingerprint, ctx)

        assert result.structure_result is None
        assert result.output_format == "prose"


class TestStructureCheckDisabled:
    def test_structure_disabled_skips_json_check(self, fingerprint):
        """
        F18: Strukturprüfung abgeschaltet → kein StructureCheckResult.
        Semantik wird trotzdem geprüft.
        """
        invalid_json = "not json at all"

        embed_mock = MagicMock()
        embed_mock.embed.return_value = [1.0, 0.0]
        llm_mock   = MagicMock()

        engine = make_verification_engine(
            embed_mock, llm_mock,
            semantic=True, structure=False,
        )
        ctx = SessionContext(language="de", fingerprint_version=1)

        result = engine.verify(invalid_json, fingerprint, ctx)

        # Kein Strukturcheck → structure_result ist None
        assert result.structure_result is None
        # Semantik lief durch
        assert result.semantic_s1 is not None


class TestProseSkipsStructureCheck:
    def test_prose_output_has_no_structure_result(self, fingerprint):
        """
        Prosa-Output → detect_format gibt PROSE zurück → keine Strukturprüfung,
        auch wenn structure=True konfiguriert.
        """
        prose = "Die Analyse zeigt ein klares Ergebnis. Die Daten sind valide."

        embed_mock = MagicMock()
        embed_mock.embed.return_value = [1.0, 0.0]
        llm_mock   = MagicMock()

        engine = make_verification_engine(embed_mock, llm_mock)
        ctx    = SessionContext(language="de", fingerprint_version=1)

        result = engine.verify(prose, fingerprint, ctx)

        assert result.structure_result is None
        assert result.output_format == "prose"
