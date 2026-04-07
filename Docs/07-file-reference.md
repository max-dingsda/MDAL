# File Reference

This reference describes the **actual purpose of the existing files** in the current repository.

## Top-Level Files

### `.gitignore`
Ignores local configurations and typical build/Python artifacts, among others.

### `CLAUDE.md`
Working/guidance file for development with Claude and AI-assisted workflows.

### `MDAL-Architekturskizze-v05.docx`
Architecture artifact outside the Python code; serves as an accompanying sketch.

### `MDAL-Stack-Entscheidung.md`
Justifies the target architecture **Rust core + Python adapter** and explicitly classifies the Python code as a PoC.

### `bearbeitungshinweise.txt`
Contains three concrete documentation/design notes:
- calibration sensitivity in Layer 1
- tolerated offline fallback in the trainer
- handling of malformed JSON in format detection

### `llm-normalization-layer-anforderungen.md`
Requirements basis for the PoC; references functional IDs F1–F20 and non-functional guardrails.

### `phasenplanung.txt`
Describes the planned implementation phases and explicitly names open stability and go-live fixes.

### `pyproject.toml`
Defines package metadata, dependencies, optional dev-dependencies, and the CLI scripts:
- `mdal-server`
- `mdal-train`

### `config/mdal.yaml`
Example configuration for LLM, embedding, fingerprint paths, plugin registry, audit, checks, notifier, and optional fallback model.

---

## Package `mdal/`

### `mdal/__init__.py`
Package marker.

### `mdal/audit.py`
Write-only audit component. Currently writes events as JSONL to files; database targets are prepared but not yet implemented.

### `mdal/config.py`
Loads and validates the YAML configuration. Contains Pydantic models for all configuration areas and runtime path verification.

### `mdal/notifier.py`
Admin notification for escalations and capability asymmetry. Supports log file and webhook.

### `mdal/pipeline.py`
Central runtime orchestrator. Builds SessionContext, loads fingerprint, sets status, and delegates the decision loop to RetryController.

### `mdal/retry.py`
Implements retry logic including escalation and `RetryLimitError`.

### `mdal/session.py`
Ephemeral session context for a single request/session run.

### `mdal/status.py`
Defines status messages and reporter implementations, e.g. queue-based and logging-based reporters.

### `mdal/transformer.py`
LLM-based tone transformer including confidence scoring and factual accuracy check.

---

## Sub-Package `mdal/fingerprint/`

### `mdal/fingerprint/__init__.py`
Package marker.

### `mdal/fingerprint/models.py`
Fingerprint data model, including:
- StyleRules
- EmbeddingProfile
- GoldenSamples
- Conversation import model for the trainer

### `mdal/fingerprint/store.py`
Versioned filesystem-based store with `save`, `load_current`, `load_version`, `list_versions`, `rollback`.

---

## Sub-Package `mdal/interfaces/`

### `mdal/interfaces/__init__.py`
Package marker.

### `mdal/interfaces/fingerprint.py`
Protocol/interface module for fingerprint-adjacent components.

### `mdal/interfaces/llm.py`
Protocol for LLM/embedding adapters.

### `mdal/interfaces/scoring.py`
Shared types and enums for check results, score levels, structure results, and scoring decisions.

### `mdal/interfaces/transformer.py`
Protocol for transformer components.

---

## Sub-Package `mdal/llm/`

### `mdal/llm/__init__.py`
Package marker.

### `mdal/llm/adapter.py`
OpenAI-compatible HTTP adapter for chat completions, embeddings, and health checks.

---

## Sub-Package `mdal/plugins/`

### `mdal/plugins/__init__.py`
Package marker.

### `mdal/plugins/registry.py`
Loads plugin folders from the filesystem, validates `manifest.json`, and provides lookup methods.

---

## Sub-Package `mdal/proxy/`

### `mdal/proxy/__init__.py`
Package marker.

### `mdal/proxy/app.py`
FastAPI app with endpoints, error handling, health check, audit writing, and pipeline integration.

### `mdal/proxy/models.py`
OpenAI-compatible request/response models.

### `mdal/proxy/server.py`
CLI entry point for starting the proxy, including config loading and Uvicorn bootstrap.

### `mdal/proxy/startup.py`
Factory module for wiring all components into a complete pipeline.

---

## Sub-Package `mdal/trainer/`

### `mdal/trainer/__init__.py`
Package marker.

### `mdal/trainer/trainer.py`
Offline training module including:
- fingerprint generation
- JSON extraction from LLM responses
- conversation file import
- CLI entry point

---

## Sub-Package `mdal/verification/`

### `mdal/verification/__init__.py`
Package marker.

### `mdal/verification/detector.py`
Format detection for JSON, XML, and prose.

### `mdal/verification/engine.py`
Overall orchestration of all active checks and derivation of a `VerificationResult`.

### `mdal/verification/structure.py`
Two-stage structure check for structured outputs, including plugin usage.

### `mdal/verification/semantic/__init__.py`
Package marker.

### `mdal/verification/semantic/layer1.py`
Deterministic style check against StyleRules.

### `mdal/verification/semantic/layer2.py`
Embedding-based style check via cosine similarity.

### `mdal/verification/semantic/layer3.py`
LLM-as-Judge for edge cases.

### `mdal/verification/semantic/scorer.py`
Decision logic between OUTPUT, TRANSFORM, REFINEMENT, and TIEBREAK.

---

## Tests

### `tests/__init__.py`
Package marker.

### `tests/unit/*.py`
Module-level unit tests for core components.

### `tests/integration/*.py`
Integration paths across multiple components and the API layer.

### `tests/regression/test_scoring_decisions.py`
Secures the decision table with fixture data.

### `tests/regression/fixtures/scorer_decisions.json`
Fixture file for regression tests of the scoring engine.

---

## Recommended Reading Order for New Developers

1. `pyproject.toml`
2. `config/mdal.yaml`
3. `mdal/proxy/server.py`
4. `mdal/proxy/startup.py`
5. `mdal/pipeline.py`
6. `mdal/verification/engine.py`
7. `mdal/retry.py`
8. `mdal/transformer.py`
9. `mdal/fingerprint/models.py`
10. `mdal/trainer/trainer.py`
