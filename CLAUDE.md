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

**Aktueller Stand:** Python-PoC abgeschlossen. Die vier PoC-Kernfragen wurden in Phase 6
beantwortet (alle positiv). Rust-Extraktion ist der nächste Schritt.

---
Stand 02.04.2026
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
→ 4 (Pipeline-Orchestrierung) → 5 (API Proxy) → 5.1 (Pre-Go-Live Fixes) → 6 (Validierung & Kalibrierung) ✅

**Phase 6 abgeschlossen** (2026-04-04). Alle vier PoC-Kernfragen positiv beantwortet.
Ergebnisse: `phase6_bericht.md`. Vollständige Planung: `phasenplanung.txt`

**Nächste Phase: Rust-Extraktion** (Scoring-Logik, Fingerprint-Vergleich, Evaluator-Kaskade).

---

## Offene Punkte aus Code-Review — alle umgesetzt ✅

Alle CR-Findings aus Phase 5 wurden in Phase 5.1 und Phase 6 implementiert:

- **#2** Thread-Sicherheit FingerprintStore → `filelock` in `mdal/fingerprint/store.py` ✅
- **#4** JSON-Parsing Trainer Layer 1 → 3-Stufen-Retry in `mdal/trainer/trainer.py` ✅
- **#5** CoT im LLM-Judge → `_JUDGE_PROMPT` + `_parse_judgment()` in `layer3.py` ✅
- **#6** Startup-Konnektivitätsprüfung → `connectivity_check()` in `mdal/proxy/startup.py` ✅

---

## Offene Punkte zur Team-Klärung

*Keine offenen Punkte — alle Entscheidungen getroffen.*

**[CR-Finding #1] F14 Multi-Turn-Konsistenz — GEKLÄRT**
- Entscheidung: F14 gilt nur innerhalb des Retry-Loops eines einzelnen Requests.
  MDAL ist konversationslos — Konversationskontext liegt bei der vorgelagerten Anwendung.
- Konsequenz: Kein Code-Änderungsbedarf. Aktuelle `session.py`-Implementierung ist korrekt.
- Dokumentiert in `llm-normalization-layer-anforderungen.md` (F14, Stand v0.5).

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


---
Update 05.04.2026
---
# MDAL – Projekt-Übergabedokument (Handover)

## 1. Projektkontext
**MDAL (Model-Driven Architecture Layer)** ist ein OpenAI-kompatibler API-Proxy, der zwischen Client-Applikationen und LLMs (wie Mistral oder Llama) geschaltet wird. 
Sein Hauptziel ist die **Dämpfung von Model-Shift-Effekten**: Er prüft Antworten des LLMs gegen einen definierten "Charakter-Fingerprint" (Stil, Vokabular, Format). Entsprechen Antworten nicht den Vorgaben, werden sie vom Proxy transformiert oder das LLM wird zu einem Retry gezwungen. Schlägt dies fehl, eskaliert MDAL hart (`HTTP 503`), statt schlechte Ergebnisse durchzuwinken ("Keine Graceful Degradation").

---

## 2. Abgeschlossener Meilenstein: Prosa-Semantik (Phase 6/7)
Die Text-Semantik-Prüfung wurde in den letzten Schritten massiv gehärtet und auf **"Defensive Normalisierung" (Demut des Systems)** umgestellt:
*   **LLM-basierter Transformer:** Der fehleranfällige Regex-Transformer wurde durch den `LLMToneTransformer` ersetzt.
*   **Neue Priorität:** Grammatik & Faktentreue stehen ab sofort **zwingend** über stilistischen Anpassungen.
*   **Confidence Scoring (Die Notbremse):** Wenn der Transformer mehr als 30 % des Textes ändert (Kaputtoptimierung / Neologismen), wird die Änderung demütig verworfen (`difflib`-Ratio < 0.70).
*   **Hard Language Lock (F8):** Ein `langdetect`-Filter am Eingang der Pipeline blockiert sofort jeden Sprach-Drift (z.B. Antworten auf Englisch statt Deutsch).
*   **Post-Processing (F21):** Meta-Kommentare des LLMs ("Hier ist die Antwort:") werden vor der Auslieferung per Regex abgeschnitten.
*   **Domänen-Profile (Säule B):** MDAL klassifiziert Prompts via vorgeschaltetem LLM-Call dynamisch in Domänen (`TECHNICAL`, `BUSINESS`, `CREATIVE`, `SHORT_COPY`), um Context-Leaks (wie das Wort "Dienstleister" in kreativen Texten) zu vermeiden.

---

## 3. Aktueller Status: Validierung Strukturierter Outputs (Anforderung F2)
Das System befindet sich aktuell mitten im Test der Verarbeitung von JSON und XML.

**Was bereits funktioniert (und implementiert ist):**
*   **Smarter Format-Detector:** Erkennt JSON/XML auch dann, wenn das LLM es in Markdown-Fences (```` ```json ````) verpackt oder Erklärtexte davorstellt.
*   **Semantik-Weiche:** Wenn JSON/XML erkannt wird, überspringt MDAL die Llama-Prosa-Prüfung (Layer 1 & 2 komplett) und nutzt nur den `StructureChecker`.
*   **Aggressiver Refinement-Prompt:** Bei defektem Code gibt MDAL dem LLM im Retry den kaputten Output mitsamt Fehlermeldung zurück ("Das hast du generiert, das ist der Fehler. Repariere es!").
*   **Syntax-Prüfung:** Das System blockiert erfolgreich malformed JSON (z.B. fehlende Klammern) und zwingt das LLM erfolgreich zur Selbstreparatur. Kaputtes XML (z.B. fehlende Namespace-Deklarationen) führt ebenfalls zum korrekten Abbruch.

---

## 4. Nächste anstehende Aufgaben für die neue Chat-Session

1.  **Plugin-Validierung testen:** 
    Wir haben ein ArchiMate-Dummy-Plugin in `plugins/` (`manifest.json` und `elements.json`) angelegt. (Morgen als Erstes: Dateien in einen sauberen Unterordner `plugins/archimate-3/` verschieben). Wir müssen prüfen, ob MDAL Mistral hart blockiert, wenn das Modell zwar valides XML, aber verbotene XML-Tags generiert.
2.  **Markdown-Fences im Final-Output:** 
    Aktuell liefert MDAL bei Code-Prompts den extrahierten Code manchmal noch inklusive Markdown-Backticks an den Client zurück. Es muss diskutiert werden, ob der Proxy den Code für den Client vor der Auslieferung komplett von Backticks und Erklärtexten (Prosa) "säubern" soll.
3.  **Feinschliff an Exception-Handlern:** 
    Die `mdal/proxy/server.py` wurde bereits so angepasst, dass technische Abstürze (FastAPI 503) sauber in der `escalations.log` landen.

---
*Bereit für Anweisung vom Lead-QA-Engineer.*