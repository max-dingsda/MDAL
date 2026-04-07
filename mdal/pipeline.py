"""
Pipeline orchestrator — connects all MDAL components (F1–F18).

Flow of a single request:
  1. STATUS: request is being processed
  2. Load fingerprint (current version for the language)
  3. Create SessionContext
  4. RetryController.run() with:
       - initial_call:  LLM call with the original messages
       - refine_call:   LLM call with refinement appendix
       - verify:        VerificationEngine (STATUS: checking)
       - transform:     LLMToneTransformer (STATUS: adjusting)
  5. STATUS: response is ready
  6. Return output

Error handling:
  - RetryLimitError: propagated upward (no output to client)
  - FingerprintStore errors: not caught (F11 — no silent fallback)
"""

from __future__ import annotations

import logging
import re

try:
    from langdetect import detect, LangDetectException
except ImportError:
    detect = None

from mdal.fingerprint.models import Fingerprint
from mdal.fingerprint.store import FingerprintStore
from mdal.interfaces.llm import LLMAdapterProtocol
from mdal.retry import RetryController, RetryLimitError
from mdal.session import SessionContext
from mdal.status import QueueStatusReporter, StatusMessage, StatusReporter
from mdal.transformer import LLMToneTransformer
from mdal.verification.engine import VerificationEngine, VerificationResult
from mdal.verification.detector import detect_format

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Refinement prompt
# ---------------------------------------------------------------------------

_REFINEMENT_USER_MESSAGE = """\
Your last response was faulty and was rejected by the system.

DETECTED ERRORS:
{error_summary}

YOUR REJECTED RESPONSE:
{prev_output}

TASK:
Please correct the errors listed above and regenerate the response. Under all circumstances keep the content structure, facts, order, and completeness of the response UNCHANGED.
"""


def _build_refinement_messages(
    original_messages: list[dict],
    prev_output:       str,
    error_summary:     str,
) -> list[dict]:
    """
    Appends an explicit correction note including the faulty output to the
    original messages.
    """
    return [
        *original_messages,
        {
            "role":    "user",
            "content": _REFINEMENT_USER_MESSAGE.format(
                error_summary=error_summary,
                prev_output=prev_output
            ),
        },
    ]

# ---------------------------------------------------------------------------
# Domain classification (Pillar B)
# ---------------------------------------------------------------------------

_DOMAIN_PROMPT = """\
Analyze the following user request and assign it to exactly one of these domains:
- TECHNICAL: Technical explanations, IT architecture, programming.
- BUSINESS: Formal business emails, board presentations, payment reminders.
- CREATIVE: Storytelling, prose, vivid descriptions, casual dialogues.
- SHORT_COPY: Very short requests, slogans, social media (fewer than 3 sentences expected).
- DEFAULT: Everything else, small talk, general questions.

Respond EXCLUSIVELY with exactly one of these 5 terms (TECHNICAL, BUSINESS, CREATIVE, SHORT_COPY, DEFAULT). No explanations!

User request:
{prompt}
"""

def _classify_domain(messages: list[dict], llm: LLMAdapterProtocol) -> str:
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    if not user_msgs:
        return "DEFAULT"
    prompt = _DOMAIN_PROMPT.format(prompt=user_msgs[-1][:1000])
    try:
        res = llm.complete([{"role": "user", "content": prompt}]).strip().upper()
        for d in ["TECHNICAL", "BUSINESS", "CREATIVE", "SHORT_COPY"]:
            if d in res:
                return d
        return "DEFAULT"
    except Exception:
        return "DEFAULT"

# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """
    Connects LLM, VerificationEngine, Transformer, and RetryController.

    Created once per server instance (all dependencies via constructor).
    Stateless with respect to individual requests — SessionContext is
    created fresh per request.
    """

    def __init__(
        self,
        llm:          LLMAdapterProtocol,
        verification: VerificationEngine,
        transformer:  LLMToneTransformer,
        store:        FingerprintStore,
        retry:        RetryController,
        status:       StatusReporter | None = None,
    ) -> None:
        self._llm          = llm
        self._verification = verification
        self._transformer  = transformer
        self._store        = store
        self._retry        = retry
        self._status: StatusReporter = status or QueueStatusReporter()

    def process(
        self,
        messages: list[dict],
        language: str,
    ) -> str:
        """
        Processes a complete LLM request through the MDAL pipeline.

        Parameters
        ----------
        messages: Chat messages in OpenAI format (role/content).
        language: Language code (e.g. "de", "en") for fingerprint lookup.

        Returns
        -------
        str: Final, conforming output — direct or after transformation.

        Raises
        ------
        RetryLimitError: When no conforming output could be produced.
        KeyError / FileNotFoundError: When no fingerprint exists for the language.
        """
        self._status.report(StatusMessage.PROCESSING)

        domain = _classify_domain(messages, self._llm)
        logger.info("Pillar B: detected text domain for request: %s", domain)

        fingerprint = self._store.load_current(language)
        version     = self._store.current_version(language) or 0
        context     = SessionContext(language=language, fingerprint_version=version)

        def initial_call() -> str:
            return self._llm.complete(messages)

        def refine_call(prev_output: str, error_summary: str) -> str:
            self._status.report(StatusMessage.REFINING)
            refined_messages = _build_refinement_messages(
                messages, prev_output, error_summary
            )
            return self._llm.complete(refined_messages)

        def verify(output: str, ctx: SessionContext) -> VerificationResult:
            self._status.report(StatusMessage.CHECKING)

            # F2: detect structured outputs
            is_structured = detect_format(output).is_structured()

            # F8: Hard Language Lock (block language drift)
            if not is_structured and detect is not None and len(output.split()) > 10:
                try:
                    detected_lang = detect(output)
                    if not language.startswith(detected_lang):
                        error_msg = f"Language drift (F8): expected '{language}', but '{detected_lang}' generated."
                        self._retry._notifier.notify_escalation(
                            session_id=ctx.session_id,
                            retry_count=self._retry._max,
                            last_error=error_msg,
                        )
                        raise RetryLimitError(ctx.session_id, self._retry._max)
                except LangDetectException:
                    pass  # Too short or ambiguous for language detection

            return self._verification.verify(output, fingerprint, ctx)

        def do_transform(output: str) -> str:
            self._status.report(StatusMessage.ADJUSTING)
            return self._transformer.transform(output, fingerprint, domain)

        final_output = self._retry.run(
            context      = context,
            initial_call = initial_call,
            refine_call  = refine_call,
            verify       = verify,
            transform    = do_transform,
        )

        self._status.report(StatusMessage.READY)

        # F21: Apply post-processing filter
        return _post_process(final_output)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _post_process(text: str) -> str:
    """
    F21: Removes generated meta-comments and LLM preambles before delivery.
    """
    # Remove typical LLM prologues such as "Here is the adapted version:"
    text = re.sub(
        r"^(?:Hier ist|Dies ist|Anbei)(?: eine| die)? (?:angepasste|überarbeitete|korrigierte) (?:Version|Antwort|Fassung).*?:\s*\n*",
        "", text, flags=re.IGNORECASE
    )
    # Remove bracket comments like (Here is the text) at the start or end
    text = re.sub(
        r"^\s*[\(\[].*(?:angepasst|transformiert|Version|Hier ist|überarbeitet|korrigiert).*?[\)\]]\s*\n?",
        "", text, flags=re.IGNORECASE | re.MULTILINE
    )
    return text.strip()
