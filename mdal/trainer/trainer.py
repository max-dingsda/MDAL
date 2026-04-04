"""
Trainer-Komponente (F17) — Offline-Ableitung des Fingerprints aus Chat-Verläufen.

Kein Bestandteil der Laufzeit-Pipeline — wird bei Ersteinrichtung und bei
bewusster Weiterentwicklung des Fingerprints (F7) eingesetzt.

Ablauf:
  1. Chat-Verläufe einlesen
  2. Assistent-Antworten extrahieren
  3. Layer 1: LLM extrahiert Stilregeln aus den Antworten
  4. Layer 2: Embedding-Centroid aus allen Assistent-Antworten berechnen
  5. Layer 3: LLM selektiert repräsentative Golden Samples
  6. Fingerprint bauen und im Store speichern
  7. Rohdaten werden nicht gespeichert (NF3)

Das LLM für die Analyse muss nicht identisch mit dem Produktiv-LLM sein.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mdal.llm.adapter import LLMResponseError

from mdal.fingerprint.models import (
    Conversation,
    EmbeddingProfile,
    Fingerprint,
    GoldenSample,
    GoldenSamples,
    StyleRule,
    StyleRules,
)
from mdal.fingerprint.store import FingerprintStore
from mdal.interfaces.llm import LLMAdapterProtocol

logger = logging.getLogger(__name__)

# Anzahl Golden Samples die der Trainer selektiert
DEFAULT_GOLDEN_SAMPLE_COUNT = 5


class TrainerError(Exception):
    """Wird geworfen wenn der Trainer-Lauf fehlschlägt."""


class Trainer:
    """
    Offline-Trainer: destilliert aus Chat-Verläufen einen Fingerprint.

    Benötigt:
      - llm_adapter:       für Stilregel-Extraktion und Sample-Selektion
      - embedding_adapter: für Layer-2-Embeddings (kann derselbe Endpunkt sein)
      - store:             Ziel für den fertigen Fingerprint
    """

    def __init__(
        self,
        llm_adapter:       LLMAdapterProtocol,
        embedding_adapter: LLMAdapterProtocol,
        store:             FingerprintStore,
        golden_sample_count: int = DEFAULT_GOLDEN_SAMPLE_COUNT,
    ) -> None:
        self._llm       = llm_adapter
        self._embed     = embedding_adapter
        self._store     = store
        self._n_samples = golden_sample_count

    # ------------------------------------------------------------------
    # Haupt-Einstiegspunkt
    # ------------------------------------------------------------------

    def run(self, conversations: list[Conversation], language: str) -> int:
        """
        Führt einen vollständigen Trainer-Lauf durch.

        Gibt die vergebene Fingerprint-Versionsnummer zurück.
        Rohdaten (Konversationen) liegen nach dem Aufruf nur noch
        in der Verantwortung des Aufrufers — das System speichert sie nicht.
        """
        if not conversations:
            raise TrainerError("Mindestens eine Konversation erforderlich.")

        responses = self._collect_responses(conversations)
        if not responses:
            raise TrainerError(
                "Keine Assistent-Antworten in den Konversationen gefunden."
            )

        logger.info(
            "Trainer: %d Konversationen, %d Assistent-Antworten, Sprache=%s",
            len(conversations), len(responses), language,
        )

        logger.info("Trainer: Extrahiere Stilregeln (Layer 1) …")
        layer1 = self._extract_style_rules(responses, language)

        logger.info("Trainer: Berechne Embedding-Profil (Layer 2) …")
        layer2 = self._compute_embedding_profile(responses)

        logger.info("Trainer: Selektiere Golden Samples (Layer 3) …")
        layer3 = self._select_golden_samples(conversations, language)

        fingerprint = Fingerprint(
            version=0,      # wird vom Store vergeben
            language=language,
            layer1=layer1,
            layer2=layer2,
            layer3=layer3,
        )

        version = self._store.save(fingerprint)
        logger.info("Trainer: Fingerprint v%d gespeichert.", version)
        return version

    # ------------------------------------------------------------------
    # Layer 1 — Stilregel-Extraktion via LLM
    # ------------------------------------------------------------------

    def _extract_style_rules(
        self, responses: list[str], language: str
    ) -> StyleRules:
        """
        Extrahiert Stilregeln via LLM mit bis zu drei Versuchen (CR-Finding #4):

        1. JSON-Mode des LLM aktivieren (sofern vom Endpunkt unterstützt) — liefert
           direkt valides JSON ohne Markdown oder Erklärtext.
        2. Standard-Completion ohne JSON-Mode — funktioniert mit allen Endpunkten.
        3. Korrektur-Prompt im selben Message-Thread — explizite Aufforderung zur
           Reparatur der vorigen Antwort.

        Erst nach Scheitern aller drei Versuche wird TrainerError geworfen.
        """
        sample_text = self._build_response_sample(responses, max_chars=6000)
        prompt = _STYLE_EXTRACTION_PROMPT.format(
            language=language,
            responses=sample_text,
        )
        messages = [{"role": "user", "content": prompt}]

        # Versuch 1: JSON-Mode (nicht alle Endpunkte unterstützen das)
        try:
            raw = self._llm.complete(
                messages,
                response_format={"type": "json_object"},
            )
            return _parse_style_rules(raw)
        except (LLMResponseError, json.JSONDecodeError, ValueError, KeyError):
            logger.debug(
                "Layer-1: JSON-Mode nicht unterstützt oder Parsing fehlgeschlagen,"
                " verwende Standard-Completion."
            )

        # Versuch 2: Standard-Completion
        raw = self._llm.complete(messages)
        try:
            return _parse_style_rules(raw)
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning(
                "Layer-1: Standard-Completion nicht parsebar, sende Korrektur-Prompt."
            )

        # Versuch 3: Korrektur-Prompt
        correction_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": _JSON_CORRECTION_PROMPT},
        ]
        raw = self._llm.complete(correction_messages)
        try:
            return _parse_style_rules(raw)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            raise TrainerError(
                f"Layer-1-Extraktion nach 3 Versuchen fehlgeschlagen. "
                f"Letzte LLM-Antwort war:\n{raw[:500]}"
            ) from exc

    # ------------------------------------------------------------------
    # Layer 2 — Embedding-Profil
    # ------------------------------------------------------------------

    def _compute_embedding_profile(self, responses: list[str]) -> EmbeddingProfile:
        embeddings = [self._embed.embed(r) for r in responses]

        if not embeddings:
            raise TrainerError("Keine Embeddings berechnet.")

        dimensions = len(embeddings[0])
        centroid = [
            sum(vec[i] for vec in embeddings) / len(embeddings)
            for i in range(dimensions)
        ]

        return EmbeddingProfile(
            centroid=centroid,
            model_name="unknown",   # wird vom Aufrufer überschrieben wenn bekannt
            sample_count=len(embeddings),
            dimensions=dimensions,
        )

    # ------------------------------------------------------------------
    # Layer 3 — Golden Sample Selektion
    # ------------------------------------------------------------------

    def _select_golden_samples(
        self, conversations: list[Conversation], language: str
    ) -> GoldenSamples:
        all_pairs = [
            pair
            for conv in conversations
            for pair in conv.as_turn_pairs()
        ]

        if not all_pairs:
            return GoldenSamples(samples=[])

        # Kandidaten für den LLM aufbereiten (begrenzt auf max. 20 Paare)
        candidates = all_pairs[: min(len(all_pairs), 20)]
        candidates_text = "\n\n".join(
            f"[{i+1}] User: {p[0][:300]}\nAssistent: {p[1][:500]}"
            for i, p in enumerate(candidates)
        )

        prompt = _SAMPLE_SELECTION_PROMPT.format(
            language=language,
            n=min(self._n_samples, len(candidates)),
            candidates=candidates_text,
        )

        raw = self._llm.complete([{"role": "user", "content": prompt}])

        try:
            data = _extract_json(raw)
            selected_indices: list[int] = [
                int(i) - 1 for i in data.get("selected", [])
            ]
            samples = [
                GoldenSample(prompt=candidates[i][0], response=candidates[i][1])
                for i in selected_indices
                if 0 <= i < len(candidates)
            ]
            # Fallback: wenn LLM-Selektion fehlschlägt, erste N nehmen
            if not samples:
                samples = [
                    GoldenSample(prompt=p[0], response=p[1])
                    for p in candidates[: self._n_samples]
                ]
            return GoldenSamples(samples=samples)
        except Exception as exc:
            logger.warning(
                "Golden-Sample-Selektion via LLM fehlgeschlagen (%s), "
                "verwende erste %d Samples.",
                exc, self._n_samples,
            )
            return GoldenSamples(
                samples=[
                    GoldenSample(prompt=p[0], response=p[1])
                    for p in candidates[: self._n_samples]
                ]
            )

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_responses(conversations: list[Conversation]) -> list[str]:
        return [r for conv in conversations for r in conv.assistant_responses()]

    @staticmethod
    def _build_response_sample(responses: list[str], max_chars: int) -> str:
        """
        Baut einen Textblock aus Assistent-Antworten auf.
        Begrenzt auf max_chars um das LLM-Kontextfenster nicht zu überlasten.
        """
        parts: list[str] = []
        total = 0
        for i, r in enumerate(responses):
            entry = f"[{i+1}] {r}"
            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _parse_style_rules(raw: str) -> StyleRules:
    """
    Parst die LLM-Antwort der Layer-1-Extraktion zu einem StyleRules-Objekt.
    Wirft json.JSONDecodeError / ValueError / KeyError bei ungültigem Format.
    """
    data = _extract_json(raw)
    return StyleRules(
        formality_level=int(data.get("formality_level", 3)),
        avg_sentence_length_max=data.get("avg_sentence_length_max"),
        preferred_vocabulary=data.get("preferred_vocabulary", []),
        avoided_vocabulary=data.get("avoided_vocabulary", []),
        custom_rules=[
            StyleRule(**r) for r in data.get("custom_rules", [])
        ],
    )


def _extract_json(text: str) -> dict:
    """
    Extrahiert das erste JSON-Objekt aus einem LLM-Antwort-Text.
    LLMs umhüllen JSON oft mit Markdown-Fences oder Erklärtexten.
    """
    text = text.strip()

    # Markdown-Fence entfernen
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    # Ersten { ... } Block finden
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    return json.loads(text)


# ---------------------------------------------------------------------------
# LLM-Prompts
# ---------------------------------------------------------------------------

_STYLE_EXTRACTION_PROMPT = """\
Analysiere die folgenden Assistent-Antworten und extrahiere präzise Stilregeln.

Sprache der Antworten: {language}

Antworte ausschließlich mit einem JSON-Objekt — kein Erklärtext, keine Markdown-Fences.
Format:
{{
  "formality_level": <1-5>,
  "avg_sentence_length_max": <integer oder null>,
  "preferred_vocabulary": ["Begriff1", "Begriff2"],
  "avoided_vocabulary": ["Begriff1"],
  "custom_rules": [
    {{"name": "regelname", "description": "Beschreibung der Regel"}}
  ]
}}

Skala Formalität: 1 = sehr informell/umgangssprachlich, 5 = sehr formal/akademisch.
preferred_vocabulary: Charakteristische Begriffe oder Phrasen die häufig vorkommen.
avoided_vocabulary: Ausdrücke die konsistent vermieden werden.
custom_rules: Weitere stilistische Beobachtungen (Satzbau, Struktur, Eigenheiten).

Assistent-Antworten:
{responses}
"""

_JSON_CORRECTION_PROMPT = """\
Deine vorige Antwort war kein valides JSON-Objekt. Bitte antworte diesmal
ausschließlich mit dem JSON-Objekt — ohne Erklärtext, ohne Markdown-Fences.
Verwende exakt das Schema aus der ursprünglichen Aufgabe.
"""

_SAMPLE_SELECTION_PROMPT = """\
Die folgenden Interaktionen stammen aus Chat-Verläufen in der Sprache: {language}

Wähle die {n} Interaktionen aus, die den Stil des Assistenten am besten repräsentieren.
Kriterien: Typischkeit des Stils, Qualität, Vielfalt der Themen.

Antworte ausschließlich mit einem JSON-Objekt — kein Erklärtext.
Format:
{{
  "selected": [<Nummer>, <Nummer>, ...]
}}

Interaktionen:
{candidates}
"""


# ---------------------------------------------------------------------------
# Datei-Loader
# ---------------------------------------------------------------------------

def load_conversations_from_file(path: str | Path, language: str = "de") -> list[Conversation]:
    """
    Lädt Konversationen aus einer JSON-Datei.

    Unterstützte Formate:
      - Liste von Konversationen: [[{"role": ..., "content": ...}, ...], ...]
      - Einzelne Konversation:    [{"role": ..., "content": ...}, ...]
    """
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    if not raw:
        return []

    # Einzelne Konversation (Liste von Turns)
    if isinstance(raw[0], dict) and "role" in raw[0]:
        return [Conversation.from_openai_format(raw, language=language)]

    # Liste von Konversationen
    return [
        Conversation.from_openai_format(conv, language=language)
        for conv in raw
        if conv
    ]


# ---------------------------------------------------------------------------
# CLI-Einstiegspunkt
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import sys

    from mdal.config import load_config
    from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config

    parser = argparse.ArgumentParser(
        description="MDAL Trainer — Fingerprint aus Chat-Verläufen destillieren"
    )
    parser.add_argument("--config",   required=True, help="Pfad zur mdal.yaml")
    parser.add_argument("--input",    required=True, nargs="+", help="Konversations-JSON-Dateien")
    parser.add_argument("--language", default="de",  help="Sprache der Konversationen (default: de)")
    args = parser.parse_args()

    config = load_config(args.config)
    llm    = llm_adapter_from_config(config.llm)
    embed  = embedding_adapter_from_config(config.embedding)
    store  = FingerprintStore(config.fingerprint_path)

    conversations: list[Conversation] = []
    for path in args.input:
        conversations.extend(load_conversations_from_file(path, language=args.language))

    if not conversations:
        print("Fehler: Keine Konversationen geladen.", file=sys.stderr)
        sys.exit(1)

    trainer = Trainer(llm_adapter=llm, embedding_adapter=embed, store=store)
    version = trainer.run(conversations=conversations, language=args.language)
    print(f"Fingerprint v{version} für Sprache '{args.language}' gespeichert.")


if __name__ == "__main__":
    main()
