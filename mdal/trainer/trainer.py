"""
Trainer component (F17) — Offline derivation of the fingerprint from chat histories.

Not part of the runtime pipeline — used during initial setup and when
intentionally evolving the fingerprint (F7).

Process:
  1. Load chat histories
  2. Extract assistant responses
  3. Layer 1: LLM extracts style rules from the responses
  4. Layer 2: Compute embedding centroid from all assistant responses
  5. Layer 3: LLM selects representative golden samples
  6. Build fingerprint and save to store
  7. Raw data is not persisted (NF3)

The LLM used for analysis does not need to be identical to the production LLM.
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

# Number of golden samples selected by the trainer
DEFAULT_GOLDEN_SAMPLE_COUNT = 5


class TrainerError(Exception):
    """Raised when a trainer run fails."""


class Trainer:
    """
    Offline trainer: distills a fingerprint from chat histories.

    Requires:
      - llm_adapter:       for style rule extraction and sample selection
      - embedding_adapter: for Layer 2 embeddings (can be the same endpoint)
      - store:             target for the completed fingerprint
    """

    def __init__(
        self,
        llm_adapter:          LLMAdapterProtocol,
        embedding_adapter:    LLMAdapterProtocol,
        store:                FingerprintStore,
        golden_sample_count:  int = DEFAULT_GOLDEN_SAMPLE_COUNT,
        embedding_model_name: str = "unknown",
    ) -> None:
        self._llm             = llm_adapter
        self._embed           = embedding_adapter
        self._store           = store
        self._n_samples       = golden_sample_count
        self._embed_model     = embedding_model_name

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, conversations: list[Conversation], language: str) -> int:
        """
        Runs a complete trainer pass.

        Returns the assigned fingerprint version number.
        Raw data (conversations) remains solely the caller's responsibility
        after this call — the system does not store them.
        """
        if not conversations:
            raise TrainerError("At least one conversation is required.")

        responses = self._collect_responses(conversations)
        if not responses:
            raise TrainerError(
                "No assistant responses found in the conversations."
            )

        logger.info(
            "Trainer: %d conversations, %d assistant responses, language=%s",
            len(conversations), len(responses), language,
        )

        print(f"\n🚀 Starte Fingerprint-Destillation für Sprache '{language}'...", flush=True)
        print(f"📊 Analysiere {len(conversations)} Konversationen mit {len(responses)} Assistant-Antworten...\n", flush=True)

        logger.info("Trainer: Extracting style rules (Layer 1) …")
        print("⏳ [1/3] Extrahiere Stil-Regeln via LLM (Layer 1)...", flush=True)
        layer1 = self._extract_style_rules(responses, language)
        print("   ✅ Stil-Regeln erfolgreich extrahiert.\n", flush=True)

        logger.info("Trainer: Computing embedding profile (Layer 2) …")
        print("⏳ [2/3] Berechne Embedding-Profile (Layer 2)...", flush=True)
        layer2 = self._compute_embedding_profile(responses)
        print("   ✅ Embeddings berechnet und Centroid ermittelt.\n", flush=True)

        logger.info("Trainer: Selecting golden samples (Layer 3) …")
        print("⏳ [3/3] Wähle repräsentative Golden Samples via LLM (Layer 3)...", flush=True)
        layer3 = self._select_golden_samples(conversations, language)
        print(f"   ✅ {len(layer3.samples)} Golden Samples ausgewählt.\n", flush=True)

        fingerprint = Fingerprint(
            version=0,      # assigned by the store
            language=language,
            layer1=layer1,
            layer2=layer2,
            layer3=layer3,
        )

        version = self._store.save(fingerprint)
        logger.info("Trainer: Fingerprint v%d saved.", version)
        return version

    # ------------------------------------------------------------------
    # Layer 1 — Style rule extraction via LLM
    # ------------------------------------------------------------------

    def _extract_style_rules(
        self, responses: list[str], language: str
    ) -> StyleRules:
        """
        Extracts style rules via LLM with up to three attempts (CR-Finding #4):

        1. JSON mode on the LLM (if supported by the endpoint) — returns
           valid JSON directly without Markdown or explanatory text.
        2. Standard completion without JSON mode — works with all endpoints.
        3. Correction prompt in the same message thread — explicit request to
           repair the previous response.

        TrainerError is only raised after all three attempts fail.
        """
        sample_text = self._build_response_sample(responses, max_chars=6000)
        prompt = _STYLE_EXTRACTION_PROMPT.format(
            language=language,
            responses=sample_text,
        )
        messages = [{"role": "user", "content": prompt}]

        # Attempt 1: JSON mode (not supported by all endpoints)
        try:
            raw = self._llm.complete(
                messages,
                response_format={"type": "json_object"},
            )
            return _parse_style_rules(raw)
        except (LLMResponseError, json.JSONDecodeError, ValueError, KeyError):
            logger.debug(
                "Layer-1: JSON mode not supported or parsing failed,"
                " falling back to standard completion."
            )

        # Attempt 2: Standard completion
        raw = self._llm.complete(messages)
        try:
            return _parse_style_rules(raw)
        except (json.JSONDecodeError, ValueError, KeyError):
            logger.warning(
                "Layer-1: Standard completion not parseable, sending correction prompt."
            )

        # Attempt 3: Correction prompt
        # The previous LLM response is truncated — it can be very long and would
        # overflow the LLM context window together with the original prompt.
        correction_messages = messages + [
            {"role": "assistant", "content": raw[:800]},
            {"role": "user", "content": _JSON_CORRECTION_PROMPT},
        ]
        raw = self._llm.complete(correction_messages)
        try:
            return _parse_style_rules(raw)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            raise TrainerError(
                f"Layer-1 extraction failed after 3 attempts. "
                f"Last LLM response was:\n{raw[:500]}"
            ) from exc

    # ------------------------------------------------------------------
    # Layer 2 — Embedding profile
    # ------------------------------------------------------------------

    # Maximum character length per text before the embedding call.
    # nomic-embed-text (BERT tokenizer) has a 2048-token context window.
    # For German text ~2 chars/token → safe limit: 3000 characters.
    _EMBED_MAX_CHARS: int = 3000

    def _compute_embedding_profile(self, responses: list[str]) -> EmbeddingProfile:
        truncated = [r[:self._EMBED_MAX_CHARS] for r in responses]
        embeddings = [self._embed.embed(r) for r in truncated]

        if not embeddings:
            raise TrainerError("No embeddings computed.")

        dimensions = len(embeddings[0])
        centroid = [
            sum(vec[i] for vec in embeddings) / len(embeddings)
            for i in range(dimensions)
        ]

        return EmbeddingProfile(
            centroid=centroid,
            model_name=self._embed_model,
            sample_count=len(embeddings),
            dimensions=dimensions,
        )

    # ------------------------------------------------------------------
    # Layer 3 — Golden sample selection
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

        # Prepare candidates for the LLM (limited to max. 20 pairs)
        candidates = all_pairs[: min(len(all_pairs), 20)]
        candidates_text = "\n\n".join(
            f"[{i+1}] User: {p[0][:300]}\nAssistant: {p[1][:500]}"
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
            # Fallback: if LLM selection fails, take first N
            if not samples:
                samples = [
                    GoldenSample(prompt=p[0], response=p[1])
                    for p in candidates[: self._n_samples]
                ]
            return GoldenSamples(samples=samples)
        except Exception as exc:
            logger.warning(
                "Golden sample selection via LLM failed (%s), "
                "using first %d samples.",
                exc, self._n_samples,
            )
            return GoldenSamples(
                samples=[
                    GoldenSample(prompt=p[0], response=p[1])
                    for p in candidates[: self._n_samples]
                ]
            )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_responses(conversations: list[Conversation]) -> list[str]:
        return [r for conv in conversations for r in conv.assistant_responses()]

    @staticmethod
    def _build_response_sample(responses: list[str], max_chars: int) -> str:
        """
        Builds a text block from assistant responses.
        Limited to max_chars to avoid overloading the LLM context window.
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
# Helper functions
# ---------------------------------------------------------------------------

def _parse_style_rules(raw: str) -> StyleRules:
    """
    Parses the LLM response from Layer-1 extraction into a StyleRules object.
    Raises json.JSONDecodeError / ValueError / KeyError on invalid format.
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
    Extracts the first JSON object from an LLM response text.
    LLMs often wrap JSON in Markdown fences or explanatory text.
    """
    text = text.strip()

    # Strip Markdown fence
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    # Find first { ... } block
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    return json.loads(text)


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

_STYLE_EXTRACTION_PROMPT = """\
Analyze the following assistant responses and extract precise style rules.

Language of the responses: {language}

Respond exclusively with a JSON object — no explanatory text, no Markdown fences.
Format:
{{
  "formality_level": <1-5>,
  "avg_sentence_length_max": <integer or null>,
  "preferred_vocabulary": ["term1", "term2"],
  "avoided_vocabulary": ["term1"],
  "custom_rules": [
    {{"name": "rule_name", "description": "Description of the rule"}}
  ]
}}

Formality scale: 1 = very informal/colloquial, 5 = very formal/academic.
preferred_vocabulary: Characteristic terms or phrases that appear frequently.
avoided_vocabulary: Expressions that are consistently avoided.
custom_rules: Additional stylistic observations (sentence structure, formatting, idiosyncrasies).

Assistant responses:
{responses}
"""

_JSON_CORRECTION_PROMPT = """\
Your previous response was not a valid JSON object. Please respond this time
exclusively with the JSON object — no explanatory text, no Markdown fences.
Use exactly the schema from the original task.
"""

_SAMPLE_SELECTION_PROMPT = """\
The following interactions come from chat histories in the language: {language}

Select the {n} interactions that best represent the assistant's style.
Criteria: typicality of style, quality, diversity of topics.

Respond exclusively with a JSON object — no explanatory text.
Format:
{{
  "selected": [<number>, <number>, ...]
}}

Interactions:
{candidates}
"""


# ---------------------------------------------------------------------------
# File loader
# ---------------------------------------------------------------------------

def load_conversations_from_file(path: str | Path, language: str = "de") -> list[Conversation]:
    """
    Loads conversations from a JSON file.

    Supported formats:
      - List of conversations: [[{"role": ..., "content": ...}, ...], ...]
      - Single conversation:   [{"role": ..., "content": ...}, ...]
    """
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    if not raw:
        return []

    # Single conversation (list of turns)
    if isinstance(raw[0], dict) and "role" in raw[0]:
        return [Conversation.from_openai_format(raw, language=language)]

    # List of conversations
    return [
        Conversation.from_openai_format(conv, language=language)
        for conv in raw
        if conv
    ]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import sys

    from mdal.config import load_config
    from mdal.llm.adapter import embedding_adapter_from_config, llm_adapter_from_config

    parser = argparse.ArgumentParser(
        description="MDAL Trainer — distill fingerprint from chat histories"
    )
    parser.add_argument("--config",   required=True, help="Path to mdal.yaml")
    parser.add_argument("--input",    required=True, nargs="+", help="Conversation JSON files")
    parser.add_argument("--language", default="de",  help="Language of the conversations (default: de)")
    args = parser.parse_args()

    config = load_config(args.config)
    llm    = llm_adapter_from_config(config.llm)
    embed  = embedding_adapter_from_config(config.embedding)
    store  = FingerprintStore(config.fingerprint_path)

    conversations: list[Conversation] = []
    for path in args.input:
        conversations.extend(load_conversations_from_file(path, language=args.language))

    if not conversations:
        print("Error: No conversations loaded.", file=sys.stderr)
        sys.exit(1)

    trainer = Trainer(
        llm_adapter=llm,
        embedding_adapter=embed,
        store=store,
        embedding_model_name=config.embedding.model,
    )
    version = trainer.run(conversations=conversations, language=args.language)
    print(f"🎉 ERFOLG: Fingerprint v{version} für Sprache '{args.language}' wurde gespeichert!\n", flush=True)


if __name__ == "__main__":
    main()
