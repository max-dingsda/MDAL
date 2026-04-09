# Proxy, Startup und Betrieb

## Proxy-Schicht

Die Proxy-Implementierung liegt in `mdal/proxy/`.

### Enthaltene Module

- `models.py` — OpenAI-kompatible Request/Response-Modelle
- `app.py` — FastAPI-App und Endpunkte
- `startup.py` — Factory-Funktionen zum Verdrahten der Pipeline
- `server.py` — CLI-Einstiegspunkt und Uvicorn-Start

## API-Oberfläche

Der zentrale Laufzeitendpunkt ist:

- `POST /v1/chat/completions`

Zusätzlich gibt es:

- `GET /health`

## Konfigurations-UI und Steuerungs-APIs

MDAL stellt eine einfache Browser-Konfigurationsoberfläche unter `GET /config` bereit.
Der Proxy bietet außerdem eine JSON-basierte Konfigurations-API:

- `GET /api/config` liest die aktuelle Konfiguration aus `config/mdal.yaml`
- `POST /api/config` schreibt die Konfiguration zurück in `config/mdal.yaml`

Zur Laufzeit-Steuerung stehen folgende Endpunkte zur Verfügung:

- `POST /api/proxy/state`, um den Proxy zwischen aktivem und Wartungsmodus zu wechseln
- `POST /api/trainer/start`, um den Trainer in einem neuen Windows-Terminal zu starten

Die UI deckt aktuell die Kernfelder für LLM, Embedding, Audit, Checks, Notifier, Fingerprint-Pfad, Plugin-Registry-Pfad und einen optionalen Startbefehl für die Umgebung ab. Fortgeschrittene Runtime-Felder wie `fallback_llm`, `max_retries` und `language` werden derzeit noch direkt in YAML konfiguriert.

## Request-/Response-Modell

`mdal/proxy/models.py` bildet absichtlich die OpenAI Chat Completions API nach.

Wesentliche Einschränkungen des aktuellen PoC:

- `stream=True` wird abgelehnt
- `usage`-Werte sind Platzhalter
- zusätzliche Request-Felder werden zugelassen und durchgereicht
- Tool-/Function-bezogene Felder werden nicht ausgewertet

## Startup-Reihenfolge

`mdal/proxy/server.py` zeigt die tatsächliche Boot-Reihenfolge:

```mermaid
flowchart TD
    A[Config laden] --> B[Config validieren]
    B --> C[Laufzeitpfade prüfen]
    C --> D[Pipeline bauen]
    D --> E[AuditWriter bauen]
    E --> F[FastAPI state befüllen]
    F --> G[Uvicorn starten]
```

## `build_pipeline()` in `startup.py`

Diese Factory verdrahtet:

- LLM-Adapter
- Embedding-Adapter
- PluginRegistry
- FingerprintStore
- Layer 1, 2, 3
- ScoringEngine
- VerificationEngine
- AdminNotifier
- RetryController
- LLMToneTransformer
- PipelineOrchestrator

Das Modul ist damit die zentrale technische Montage-Stelle des Systems.

## LLM-Adapter

`mdal/llm/adapter.py` implementiert einen OpenAI-kompatiblen HTTP-Adapter.

### Fähigkeiten

- `complete()` für Chat Completions
- `embed()` für Embeddings
- `health_check()` via `/v1/models`

### Fehlerklassen

- `LLMUnavailableError`
- `LLMResponseError`

Diese Fehler werden im Proxy gezielt in passende HTTP-Antworten übersetzt.

## Konfiguration

`mdal/config.py` + `config/mdal.yaml`

### Validierung
Die Konfiguration wird zweistufig geprüft:

1. **Strukturell** via Pydantic beim Laden
2. **operativ** via Pfadprüfung in `validate_runtime_paths()`

### Wichtige Konfigurationsbereiche

- `llm`
- `embedding`
- `fingerprint_path`
- `plugin_registry_path`
- `audit`
- `checks`
- `notifier`
- `fallback_llm`
- `max_retries`

## Audit und Benachrichtigung

### Audit
`mdal/audit.py` implementiert einen write-only AuditWriter, aktuell mit JSONL-Datei als Ziel.

### Notifier
`mdal/notifier.py` informiert Administratoren bei:

- erschöpftem Retry-Limit
- erkannter Fähigkeits-Asymmetrie

Die Kanäle sind:

- Logdatei
- Webhook

Fehler in der Benachrichtigung sollen den Hauptpfad nicht blockieren.

## Statusmeldungen

Die Status-API liegt in `mdal/status.py`.  
Im Proxy-Betrieb wird laut `startup.py` der `LoggingStatusReporter` verwendet.
