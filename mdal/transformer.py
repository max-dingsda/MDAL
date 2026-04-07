"""
Tone transformer (F10).

Adjusts tone and phrasing style only.
No LLM call for RuleBasedToneTransformer — does NOT count as a retry (F5).

Invariants (F10):
  - order of statements is preserved
  - hierarchy and list structure is preserved
  - completeness: no content is added or removed
  - word level only: remove / replace informal filler words

Implements ToneTransformerProtocol → Rust core (target architecture).
"""

from __future__ import annotations

import re
import difflib
import logging

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.llm import LLMAdapterProtocol

logger = logging.getLogger(__name__)

_TRANSFORM_PROMPT = """\
Your task is to adapt a text. The following STRICT priority applies (most important first):

1. LANGUAGE QUALITY: Grammar must be flawless, fluent, and natural. Do NOT invent new words or unnatural compound words (neologisms). Foreign technical terms (e.g. from IT) are permitted.
2. FACTUAL ACCURACY: All facts, numbers, entities, and logical connections from the original text MUST be preserved exactly. Add nothing, omit nothing. Preserve lists and their order exactly.
3. STYLE ADAPTATION: Adapt the text to the style requirements below, BUT ONLY if it does not violate priorities 1 and 2.

DETECTED TEXT DOMAIN: {domain}
(IMPORTANT: If the domain is TECHNICAL or CREATIVE, do NOT use out-of-place business terms like "service provider" or "contract negotiation" in your adaptations!)

Requirements (for priority 3):
- Formality level: {formality} (1=very informal, 5=very formal/academic)
- Preferred vocabulary: {preferred} (IMPORTANT: Only use these words if they fit the content! Do not force them into unrelated topics!)
- Avoided vocabulary: {avoided}

- Respond EXCLUSIVELY with the transformed text, without introduction or explanation.

Original text:
{text}
"""

_VALIDATION_PROMPT = """\
Compare Text A (original) and Text B (transformed).

Text A (Original):
{original}

Text B (Transformed):
{transformed}

Check STRICTLY:
1. Does Text B still contain all facts, numbers, proper names, places, and times from Text A?
2. Is the language in Text B natural and does it contain NO invented words (neologisms) or completely out-of-place vocabulary (context leak)?
Respond EXCLUSIVELY with "TRUE" (if facts are present AND grammar is perfect) or "FALSE" (if anything is missing, invented, or unnatural). No explanations.
"""

_CORRECTION_PROMPT = """\
Your last transformation was faulty (facts changed, unnatural grammar/neologisms, or out-of-place vocabulary). Here is the original text again:
{text}

Requirements: formality level {formality}, preferred: {preferred}, avoided: {avoided}.

Transform the text stylistically, but preserve EVERY FACT and EVERY NUMBER 100%. Add nothing!
Respond EXCLUSIVELY with the corrected text, without introduction or explanation.
"""

class LLMToneTransformer:
    """
    LLM-based tone transformer (F10).

    Adjusts tone and phrasing style using an LLM.
    Avoids grammatical artifacts that arise with rule-based regex replacement
    in heavily inflected languages (such as German).
    """

    def __init__(self, llm_adapter: LLMAdapterProtocol) -> None:
        self._llm = llm_adapter

    def transform(self, text: str, fingerprint: Fingerprint, domain: str = "DEFAULT") -> str:
        rules = fingerprint.layer1

        preferred = ", ".join(rules.preferred_vocabulary) if rules.preferred_vocabulary else "No specific requirements"
        avoided = ", ".join(rules.avoided_vocabulary) if rules.avoided_vocabulary else "No specific requirements"

        current_prompt = _TRANSFORM_PROMPT.format(
            domain=domain,
            formality=rules.formality_level,
            preferred=preferred,
            avoided=avoided,
            text=text
        )

        max_attempts = 2

        for attempt in range(max_attempts):
            try:
                # 1. Perform transformation
                result = self._llm.complete([{"role": "user", "content": current_prompt}]).strip()

                # F10: Confidence scoring (protection against over-optimization).
                # If more than 30% of the text was changed, the "demure" rule applies.
                ratio = difflib.SequenceMatcher(None, text.split(), result.split()).ratio()
                if ratio < 0.70:
                    logger.warning("Transformer confidence score too low (ratio: %.2f). Transformation discarded (demure mode).", ratio)
                    return text

                # 2. Perform entity check (validation)
                val_prompt = _VALIDATION_PROMPT.format(original=text, transformed=result)
                val_response = self._llm.complete([{"role": "user", "content": val_prompt}]).strip().upper()

                if "TRUE" in val_response and "FALSE" not in val_response:
                    return result  # Facts preserved → success

                logger.warning("Transformer entity check failed (attempt %d/%d).", attempt + 1, max_attempts)

                # 3. Load stricter correction prompt for the next attempt
                current_prompt = _CORRECTION_PROMPT.format(
                    formality=rules.formality_level,
                    preferred=preferred,
                    avoided=avoided,
                    text=text
                )

            except Exception as exc:
                logger.error("LLMToneTransformer failed: %s. Returning original text.", exc)
                return text

        logger.error("Transformer could not ensure factual accuracy. Falling back to original text.")
        return text

# ---------------------------------------------------------------------------
# Known informal filler words → replacement (empty string = remove word)
# ---------------------------------------------------------------------------
# Only unambiguous filler usages — words with central semantic meaning
# are NOT automatically replaced.
_INFORMAL_SUBSTITUTIONS: dict[str, str] = {
    # Unambiguous fillers without independent meaning → remove
    "halt":       "",          # "Das ist halt so." → "Das ist so."
    "irgendwie":  "",          # "Das funktioniert irgendwie nicht." → "Das funktioniert nicht."
    "eigentlich": "",          # "Das sollte eigentlich klappen." → "Das sollte klappen."
    "lol":        "",
    "haha":       "",
    "hey":        "",          # As a greeting at the start of a sentence — filler only
    # Colloquial → standard
    "quasi":      "im Wesentlichen",
    "sozusagen":  "gewissermaßen",
    "okay":       "in Ordnung",
    "ok":         "in Ordnung",
    "super":      "sehr gut",
    "toll":       "gut",
    "mega":       "sehr",
    "echt":       "tatsächlich",
    "krass":      "deutlich",
    "cool":       "gut",
    "nice":       "gut",
    "jo":         "ja",
    "nö":         "nein",
    "grad":       "gerade",
}

# Formality level from which informal filler words are automatically removed
_FORMALITY_SUBSTITUTION_THRESHOLD = 3


class RuleBasedToneTransformer:
    """
    Adjusts the tone of a text using rule-based processing against the fingerprint.

    Step 1: Remove avoided vocabulary from the fingerprint.
    Step 2: Remove general informal filler words (at formality ≥ 3).
    Step 3: Normalize whitespace artifacts.

    Implements ToneTransformerProtocol.
    """

    def transform(self, text: str, fingerprint: Fingerprint, domain: str = "DEFAULT") -> str:
        """
        Transforms the tone of the text according to the fingerprint.

        Always returns a string — even if no changes are needed.
        Never alters structure, order, or completeness.
        """
        rules  = fingerprint.layer1
        result = text

        # Step 1: Remove avoided vocabulary from the fingerprint
        for word in rules.avoided_vocabulary:
            result = _replace_word(result, word, "")

        # Step 2: General informal filler words (at formality ≥ threshold)
        if rules.formality_level >= _FORMALITY_SUBSTITUTION_THRESHOLD:
            for informal, replacement in _INFORMAL_SUBSTITUTIONS.items():
                result = _replace_word(result, informal, replacement)

        # Step 3: Normalize whitespace (artifacts from word removals)
        result = _normalize_whitespace(result)

        return result


# ---------------------------------------------------------------------------
# Helper functions (public for tests)
# ---------------------------------------------------------------------------

def _replace_word(text: str, word: str, replacement: str) -> str:
    """
    Replaces a word (word-boundary-sensitive, case-insensitive).

    Word boundaries ensure that "ok" is not matched inside "okay" or "Token".
    """
    pattern = r"\b" + re.escape(word) + r"\b"
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)


def _normalize_whitespace(text: str) -> str:
    """
    Cleans up whitespace artifacts after word removals.

      - Multiple spaces → single space
      - Space before punctuation → no space
      - Leading/trailing whitespace removed
    """
    result = re.sub(r" {2,}", " ", text)
    result = re.sub(r" ([,.:;!?])", r"\1", result)
    return result.strip()
