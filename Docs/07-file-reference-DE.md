# Datei-Referenz

Diese Referenz beschreibt den **tatsächlichen Zweck der vorhandenen Dateien** im aktuellen Repository.

## Top-Level-Dateien

### `.gitignore`
Ignoriert u. a. lokale Konfigurationen und typische Build-/Python-Artefakte.

### `CLAUDE.md`
Arbeits-/Hinweisdatei für die Entwicklung mit Claude bzw. KI-gestütztem Workflow.

### `MDAL-Architekturskizze-v05.docx`
Architekturartefakt außerhalb des Python-Codes; dient als begleitende Skizze.

### `MDAL-Stack-Entscheidung.md`
Begründet die Zielarchitektur **Rust-Kern + Python-Adapter** und ordnet den Python-Code explizit als PoC ein.

### `bearbeitungshinweise.txt`
Enthält drei konkrete Doku-/Designhinweise:
- Kalibrierungssensitivität in Layer 1
- tolerierter Offline-Fallback im Trainer
- Umgang mit malformed JSON in der Format-Erkennung

### `llm-normalization-layer-anforderungen.md`
Anforderungsbasis für den PoC; referenziert die funktionalen IDs F1–F20 und non-funktionale Leitplanken.

### `phasenplanung.txt`
Beschreibt die geplanten Umsetzungsphasen und nennt explizit noch offene Stabilitäts- und Go-Live-Fixes.

### `pyproject.toml`
Definiert Paket-Metadaten, Dependencies, optionale Dev-Dependencies und die CLI-Skripte:
- `mdal-server`
- `mdal-train`

### `config/mdal.yaml`
Beispielkonfiguration für LLM, Embedding, Fingerprint-Pfade, Plugin-Registry, Audit, Checks, Notifier und optionales Fallback-Modell.

### `config/config.html`
Einfache browserbasierte Konfigurations-UI, die mit den API-Endpunkten in `mdal/proxy/app.py` kommuniziert und Einstellungen in `config/mdal.yaml` speichert.

---

## Paket `mdal/`

### `mdal/__init__.py`
Paketmarker.

### `mdal/audit.py`
Write-only Audit-Komponente. Schreibt Ereignisse aktuell als JSONL in Dateien; DB-Ziele sind vorbereitet, aber noch nicht implementiert.

### `mdal/config.py`
Lädt und validiert die YAML-Konfiguration. Enthält Pydantic-Modelle für alle Konfigurationsbereiche und Runtime-Pfadprüfung.

### `mdal/notifier.py`
Admin-Benachrichtigung für Eskalationen und Fähigkeits-Asymmetrie. Unterstützt Logdatei und Webhook.

### `mdal/pipeline.py`
Zentraler Laufzeit-Orchestrator. Baut SessionContext, lädt Fingerprint, setzt Status und delegiert die Entscheidungsschleife an den RetryController.

### `mdal/retry.py`
Implementiert die Retry-Logik inklusive Eskalation und `RetryLimitError`.

### `mdal/session.py`
Ephemerer Session-Kontext für einen Request-/Session-Lauf.

### `mdal/status.py`
Definiert Statusmeldungen und Reporter-Implementierungen, z. B. Queue-/Logging-basierte Reporter.

### `mdal/transformer.py`
LLM-basierter Tone-Transformer inkl. Confidence-Scoring und Faktentreue-Prüfung.

---

## Unterpaket `mdal/fingerprint/`

### `mdal/fingerprint/__init__.py`
Paketmarker.

### `mdal/fingerprint/models.py`
Fingerprint-Datenmodell, inklusive:
- StyleRules
- EmbeddingProfile
- GoldenSamples
- Conversation-Importmodell für den Trainer

### `mdal/fingerprint/store.py`
Versionierter dateisystembasierter Store mit `save`, `load_current`, `load_version`, `list_versions`, `rollback`.

---

## Unterpaket `mdal/interfaces/`

### `mdal/interfaces/__init__.py`
Paketmarker.

### `mdal/interfaces/fingerprint.py`
Protokoll-/Schnittstellenmodul für Fingerprint-nahe Komponenten.

### `mdal/interfaces/llm.py`
Protokoll für LLM-/Embedding-Adapter.

### `mdal/interfaces/scoring.py`
Gemeinsame Typen und Enums für Check-Ergebnisse, Score-Levels, Strukturresultate und Scoring-Entscheidungen.

### `mdal/interfaces/transformer.py`
Protokoll für Transformer-Komponenten.

---

## Unterpaket `mdal/llm/`

### `mdal/llm/__init__.py`
Paketmarker.

### `mdal/llm/adapter.py`
OpenAI-kompatibler HTTP-Adapter für Chat-Completions, Embeddings und Health-Checks.

---

## Unterpaket `mdal/plugins/`

### `mdal/plugins/__init__.py`
Paketmarker.

### `mdal/plugins/registry.py`
Lädt Plugin-Ordner aus dem Dateisystem, validiert `manifest.json` und stellt Lookup-Methoden bereit.

---

## Unterpaket `mdal/proxy/`

### `mdal/proxy/__init__.py`
Paketmarker.

### `mdal/proxy/app.py`
FastAPI-App mit Endpunkten, Error-Handling, Health-Check, Audit-Schreiben und Anbindung an die Pipeline.

### `mdal/proxy/models.py`
OpenAI-kompatible Request-/Response-Modelle.

### `mdal/proxy/server.py`
CLI-Einstiegspunkt zum Start des Proxys inkl. Konfigurationsladen und Uvicorn-Bootstrap.

### `mdal/proxy/startup.py`
Factory-Modul zum Verdrahten sämtlicher Komponenten zur vollständigen Pipeline.

---

## Unterpaket `mdal/trainer/`

### `mdal/trainer/__init__.py`
Paketmarker.

### `mdal/trainer/trainer.py`
Offline-Trainingsmodul inklusive:
- Fingerprint-Erzeugung
- JSON-Extraktion aus LLM-Antworten
- Konversationsdatei-Import
- CLI-Einstiegspunkt

---

## Unterpaket `mdal/verification/`

### `mdal/verification/__init__.py`
Paketmarker.

### `mdal/verification/detector.py`
Format-Erkennung für JSON, XML und Prosa.

### `mdal/verification/engine.py`
Gesamt-Orchestrierung aller aktiven Prüfungen und Ableitung eines `VerificationResult`.

### `mdal/verification/structure.py`
Zweistufige Strukturprüfung für strukturierte Outputs, inklusive Plugin-Nutzung.

### `mdal/verification/semantic/__init__.py`
Paketmarker.

### `mdal/verification/semantic/layer1.py`
Deterministische Stilprüfung gegen StyleRules.

### `mdal/verification/semantic/layer2.py`
Embedding-basierte Stilprüfung via Cosine Similarity.

### `mdal/verification/semantic/layer3.py`
LLM-as-Judge für Grenzfälle.

### `mdal/verification/semantic/scorer.py`
Entscheidungslogik zwischen OUTPUT, TRANSFORM, REFINEMENT und TIEBREAK.

---

## Tests

### `tests/__init__.py`
Paketmarker.

### `tests/unit/*.py`
Modulnahe Unit-Tests für Kernkomponenten.

### `tests/integration/*.py`
Integrationspfade über mehrere Komponenten und API-Layer.

### `tests/regression/test_scoring_decisions.py`
Sichert die Entscheidungstabelle mit Fixture-Daten ab.

### `tests/regression/fixtures/scorer_decisions.json`
Fixture-Datei für Regressionstests der Scoring-Engine.

---

## Praktische Lesereihenfolge für neue Entwickler

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
