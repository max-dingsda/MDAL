# MDAL — Projekt-Kontext für Claude Code

Dieses Dokument ist der primäre Kontext-Anker für KI-gestützte Arbeit an diesem Projekt.
Es beschreibt Projektziel, Architektur, aktuellen Stand und offene Entscheidungen.

---

## Projektziel

**MDAL — Model-agnostic Delivery Assurance Layer**

Ein Middleware-Layer zwischen einer Anwendung und einem LLM, der sicherstellt, dass der
vom Menschen wahrgenommene Output konsistent bleibt — unabhängig davon, welches Modell
oder welche Version im Hintergrund arbeitet.

Leitgedanke: Menschen und Organisationen behalten ihre gewohnten Arbeitsweisen, technischer
Wandel im Backend bleibt unsichtbar. Das System liefert entweder korrekten Output oder
meldet explizit warum nicht — kein stilles Durchleiten, keine Teilakzeptanz.

Zieldokumentation: `llm-normalization-layer-anforderungen.md` (F1–F20, NF1–NF10)

---

## Technologie-Stack-Entscheidung

Vollständige Begründung: `MDAL-Stack-Entscheidung.md`

**Zielarchitektur (nach PoC-Validierung):** Rust-Kern + Python-Adapter
- Rust für Scoring-Logik, Fingerprint-Vergleich, Evaluator-Kaskade (IP-Schutz, Performance)
- Python für LLM-Clients, Embedding-Bibliotheken, Trainer-Komponente, API-Proxy

**Aktueller Stand:** Python-PoC zur fachlichen Validierung. Die vier PoC-Kernfragen
(Fingerprint-Tragfähigkeit, Scoring-Kaskade, Transformer-Verlässlichkeit, Schwellwert-Defaults)
werden in Phase 6 beantwortet. Rust-Extraktion folgt danach.

---

## Architektur-Überblick

```
Anwendung / Client
       ↓ POST /v1/chat/completions (OpenAI-kompatibel)
  mdal/proxy/app.py  (FastAPI)
       ↓
  mdal/pipeline.py   (PipelineOrchestrator — zustandslos pro Request)
       ↓
  mdal/retry.py      (RetryController — max. 3 Versuche: 1 initial + 2 Refinements)
       ├─ mdal/llm/adapter.py          (LLM-Aufruf, Fallback-Modell F9)
       ├─ mdal/verification/engine.py  (Struktur + Semantik parallel)
       │    ├─ verification/structure.py   (Plugin-basiert, F2/F20)
       │    └─ verification/semantic/
       │         ├─ layer1.py  (Regelabgleich, deterministisch)
       │         ├─ layer2.py  (Embedding-Cosine-Similarity)
       │         ├─ layer3.py  (LLM-as-Judge, nur bei Tiebreak)
       │         └─ scorer.py  (Entscheidungstabelle → OUTPUT/TRANSFORM/REFINEMENT)
       └─ mdal/transformer.py          (Ton-Anpassung ohne LLM, F10)
       ↓
  mdal/session.py    (SessionContext — ephemer, pro Request-Durchlauf)
  mdal/audit.py      (AuditWriter — write-only, extern konfigurierbar)
```

**Fingerprint-Struktur** (`mdal/fingerprint/`):
- Layer 1: Stilregeln (Formalität, Satzlänge, Vokabular-Listen)
- Layer 2: Embedding-Centroid (Cosine-Similarity-Anker)
- Layer 3: Golden Samples (Referenz-Interaktionen für LLM-Judge)
- Versioniert im `FingerprintStore`, Rollback möglich (F7)

**Trainer** (`mdal/trainer/trainer.py`): Offline-Komponente, nicht Teil der Laufzeit-Pipeline.
Destilliert Fingerprint aus historischen Chat-Verläufen (JSON/OpenAI-Format).

---

## Aktueller Projektstand

**Abgeschlossene Phasen:** 1 (Foundation) → 2 (Fingerprint/Trainer) → 3 (Verification Engine)
→ 4 (Pipeline-Orchestrierung) → 5 (API Proxy) ✅

**Code-Review Phase 5** wurde durchgeführt (`Code-Review-Phase5.md`).
Finding #3 (max_retries Default) ist bereits behoben: `config.py:78` zeigt `max_retries: int = 2`.

**Nächste Phase: 5.1** (Pre-Go-Live Fixes), dann **Phase 6** (Validierung & Kalibrierung).
Vollständige Planung: `phasenplanung.txt`

---

## Offene Punkte aus Code-Review (zur Umsetzung geplant)

### Phase 5.1 — Muss vor Phase 6

**[CR-Finding #2] Thread-Sicherheit FingerprintStore** (`mdal/fingerprint/store.py`)
- TOCTOU-Race zwischen `_read_pointer()` und `load_version()` bei parallelen HTTP-Requests
- Maßnahme: `filelock`-basiertes Read/Write-Locking; Schreiben exklusiv, Lesen shared
- Aktuell: `FileNotFoundError` wird in `app.py:145` als 503 aufgefangen — kein Crash,
  aber inkonsistentes Verhalten möglich

**[CR-Finding #4] JSON-Parsing Layer 1 im Trainer** (`mdal/trainer/trainer.py`)
- `_extract_json()` verarbeitet Markdown-Fences bereits korrekt, aber Layer 1 hat keinen
  Fallback bei Parsing-Fehler → `TrainerError` bricht den gesamten Trainer-Lauf ab
- Layer 3 hat bereits einen Fallback (erste N Samples), Layer 1 nicht
- Maßnahme: JSON-Mode des LLM erzwingen oder Auto-Retry mit Korrektur-Prompt

### Phase 6 — Im Rahmen der Kalibrierungsphase

**[CR-Finding #6] Startup-Konnektivitätsprüfung** (`mdal/proxy/startup.py`)
- `validate_runtime_paths()` prüft nur lokale Dateipfade
- Maßnahme: `connectivity_check(config)` nach `build_pipeline()` — Ping an LLM,
  Embedding-Endpunkt und DB-Verbindung bei nicht-file-Audit-Targets

**[CR-Finding #5] Chain-of-Thought im LLM-as-Judge** (`mdal/verification/semantic/layer3.py`)
- `_JUDGE_PROMPT` erzwingt binäre Antwort ohne Begründung
- Maßnahme: CoT-Prefix ergänzen (`Begründe in 1-2 Sätzen, dann PASST / PASST NICHT`),
  `_parse_judgment()` auf letztes Wort/letzte Zeile umstellen statt Anfang der Antwort

---

## Offene Punkte zur Team-Klärung (noch nicht entschieden)

**[CR-Finding #1] F14 Multi-Turn-Konsistenz — Scope-Frage**
- Aktuell: `SessionContext` ist eine lokale Variable in `pipeline.process()`, lebt nur
  für die Dauer des Retry-Loops eines einzelnen HTTP-Requests. Nach dem Request weg.
- Die `_check_history` akkumuliert also maximal 3 Einträge (1 initial + 2 Refinements)
  innerhalb eines Requests — nicht über mehrere HTTP-Requests einer Konversation.
- Frage ans Team: Soll F14 "Multi-Turn-Konsistenz" nur innerhalb des Retry-Loops gelten
  (aktueller Stand, kein Bug), oder über mehrere HTTP-Requests einer User-Konversation?
- Wenn letzteres: optionaler `session_id`-Header + TTL-basierter In-Memory-Store nötig
  (neue Feature-Entscheidung, kein Bug-Fix)

---

## Wichtige Designprinzipien (nicht verhandelbar)

- **Kein stiller Durchleitungsmodus** (F11): Unvollständiges Setup → Fehlermeldung + Stop
- **Keine Teilakzeptanz** (F2): Entscheidungen sind binär
- **Keine Graceful Degradation** (F5): Retry-Limit erschöpft → Output zurückhalten + Admin
- **Ephemerität** (NF3): Konversationsinhalte, Inputs/Outputs werden nicht persistiert;
  `SessionContext` ist ausdrücklich nicht für Persistierung vorgesehen
- **Modell-Agnostizität** (NF4): Keine Anbieter-Abhängigkeiten, alle LLM-URLs konfigurierbar
- **Transformer zählt nicht als LLM-Aufruf** (F5): `RuleBasedToneTransformer` ist regelbasiert,
  verbraucht keinen der 3 Versuche
- **Streaming wird gepuffert** (F6): Kein Eingriff während Streaming, nur vollständige Outputs;
  `stream=True` im API-Proxy wird mit 400 abgelehnt

---

## Konventionen im Code

- Sprache: Deutsch in Docstrings und Kommentaren, Englisch in Code-Bezeichnern
- Fehlerbehandlung: Eigene Exception-Klassen pro Modul (z. B. `FingerprintStoreError`,
  `TrainerError`, `ConfigError`, `RetryLimitError`)
- Config: Pydantic-Modelle in `config.py`, laden via `load_config(path)` → `MDALConfig`
- Interfaces: Protocol-Klassen in `mdal/interfaces/` (für Rust-Extraktion vorbereitet)
- Kein stiller Fallback anywhere — entweder korrekt oder Exception

---

## Schlüsseldateien

| Datei | Zweck |
|---|---|
| `mdal/config.py` | Konfigurationsmodell + Loader + Runtime-Pfadprüfung |
| `mdal/pipeline.py` | Zentraler Orchestrator, zustandslos pro Request |
| `mdal/retry.py` | Retry-Schleife, F5-Implementierung |
| `mdal/session.py` | Ephemerer Session-Kontext (pro Request-Durchlauf) |
| `mdal/fingerprint/store.py` | Versionierter Fingerprint-Store mit Rollback |
| `mdal/verification/engine.py` | Parallele Verifikation Struktur + Semantik |
| `mdal/verification/semantic/scorer.py` | Entscheidungstabelle OUTPUT/TRANSFORM/REFINEMENT |
| `mdal/trainer/trainer.py` | Offline-Trainer, Fingerprint-Destillation |
| `mdal/proxy/app.py` | FastAPI-Endpunkte /v1/chat/completions + /health |
| `mdal/proxy/startup.py` | Factory `build_pipeline()` beim Server-Start |
| `phasenplanung.txt` | Vollständige Phasenplanung inkl. 5.1 und 6 |
| `llm-normalization-layer-anforderungen.md` | Anforderungsskizze v0.2 (F1–F20, NF1–NF10) |
| `MDAL-Stack-Entscheidung.md` | Stack-Begründung (Rust+Python, PoC-Strategie) |
| `Code-Review-Phase5.md` | Code-Review-Ergebnisse Ende Phase 5 |
