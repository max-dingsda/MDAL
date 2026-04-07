"""
Semantic Layer 3 — LLM-as-Judge (SemanticCheckerProtocol).

Highest precision, highest cost.
Only called for edge cases when S1 and S2 produce no unambiguous finding
(ScoringDecision.TIEBREAK).

The judge receives the golden samples from the fingerprint as context and
decides whether the output under review matches them stylistically.
Answer is binary: "matches" → HIGH, "does not match" → LOW.

Counts as an LLM call in terms of retry logic (F5).
Stays in Python — direct LLM call, not a Rust candidate.
"""

from __future__ import annotations

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.interfaces.scoring import CheckResult, ScoreLevel
from mdal.session import SessionContext

_JUDGE_PROMPT = """\
You are a style assessor. Your task is to judge whether a text \
matches a set of reference examples stylistically.

Reference examples (representing the desired style):
{samples}

Text to assess:
{output}

Criteria: tonality, formality level, phrasing style, linguistic behavior.
The content and topic of the text are irrelevant — only style matters.

Justify your verdict in 1-2 sentences. Then write as the last line \
exclusively one of the following:
  MATCHES
  DOES NOT MATCH
"""


class Layer3LLMJudge:
    """
    Implements SemanticCheckerProtocol via LLM-as-Judge.

    Requires a fingerprint with at least one golden sample.
    If no golden samples are present: MEDIUM as a conservative result.
    """

    def __init__(self, llm_adapter: LLMAdapterProtocol) -> None:
        self._llm = llm_adapter

    def check(
        self,
        output: str,
        fingerprint: Fingerprint,
        context: SessionContext,
    ) -> CheckResult:
        samples = fingerprint.layer3.samples

        if not samples:
            return CheckResult(
                level=ScoreLevel.MEDIUM,
                details="No golden samples configured — conservative MEDIUM.",
            )

        samples_text = "\n\n".join(
            f"[Example {i+1}]\nUser: {s.prompt}\nAssistant: {s.response}"
            for i, s in enumerate(samples[:5])   # max. 5 samples in prompt
        )

        prompt = _JUDGE_PROMPT.format(
            samples=samples_text,
            output=output,
        )

        raw = self._llm.complete([{"role": "user", "content": prompt}])
        passed = _parse_judgment(raw)

        # Extract reasoning from CoT response (all lines except the verdict)
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        reasoning = " ".join(lines[:-1]) if len(lines) > 1 else ""

        return CheckResult(
            level=ScoreLevel.HIGH if passed else ScoreLevel.LOW,
            details=f"LLM-Judge: {'MATCHES' if passed else 'DOES NOT MATCH'}"
                    + (f" — {reasoning[:120]}" if reasoning else ""),
        )


def _parse_judgment(response: str) -> bool:
    """
    Parses the LLM-Judge response in CoT format (CR-Finding #5).

    The verdict appears at the end of the response (last non-empty line).
    Robust against whitespace and case variations.
    Fallback: conservatively treat as non-matching if unclear.
    """
    lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
    if not lines:
        return False

    last = lines[-1].upper()
    if last == "DOES NOT MATCH" or last.startswith("DOES NOT MATCH"):
        return False
    if last == "MATCHES" or last.startswith("MATCHES"):
        return True

    # Fallback: search entire text for "DOES NOT MATCH" / "MATCHES"
    text = response.upper()
    if "DOES NOT MATCH" in text:
        return False
    if "MATCHES" in text:
        return True

    return False
