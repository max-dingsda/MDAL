# MDAL Code Review — Ende Phase 5 (PoC)

Dieses Dokument fasst die Ergebnisse des Code Reviews am Ende von Phase 5 zusammen, geprüft gegen die Anforderungsskizze v0.2 und die Architektur-Richtlinien.

## 🔴 HIGH IMPACT (Kritisch für Architektur & Betriebssicherheit)

### 1. Session Memory Leak & Verletzung von NF3 (Datenschutz)
**Datei:** `mdal/session.py`
**Kontext:** Anforderung F14 (Multi-Turn-Konsistenz) & NF3 (Ephemere Daten)
**Beschreibung:** Der `SessionContext` speichert die `_check_history` im Speicher ab. Da in der kommenden Phase 6 ein API-Proxy (F19) entwickelt wird, der systembedingt zustandslos (stateless) über HTTP angesprochen wird, muss sichergestellt werden, dass Session-Instanzen nicht unendlich im Speicher des Servers verbleiben. Aktuell gibt es keinen Mechanismus (wie TTL, Session-Timeouts oder serverseitiges Cleanup), der den RAM wieder freigibt und sicherstellt, dass die ephemeren Daten nach der Session wirklich physisch gelöscht werden (NF3).
**Empfehlung:** In Phase 6 muss ein aktiver Session-Manager implementiert werden, der verwaiste Sessions nach Ablauf eines Timeouts zwangsweise abräumt.

### 2. Fehlende Thread-Sicherheit im Fingerprint Store (Race Conditions)
**Datei:** `mdal/fingerprint/store.py`
**Kontext:** Anforderung F7 (Rollback) & NF7 (Performance)
**Beschreibung:** Die Klasse ist explizit als lock-frei und für "single-instance" kommentiert. Allerdings bedeutet API-Proxy-Betrieb (Phase 6), dass *mehrere asynchrone Web-Requests* gleichzeitig eingehen. Wenn ein Admin ein Rollback (`rollback()`) oder Trainer-Update (`save()`) ausführt, während ein User-Request `load_current()` aufruft, kann das System in inkonsistente Dateizustände laufen oder einen `FileNotFoundError` werfen, falls die Pointer-Datei im falschen Millisekunden-Zeitfenster gelesen wird.
**Empfehlung:** Ein einfaches Read/Write-Locking (z. B. `filelock`) im `FingerprintStore` ergänzen. Da Lesezugriffe überwiegen (Read-Heavy), ist der Performance-Impact minimal.

---

## 🟡 MEDIUM IMPACT (Logikfehler & Stabilität)

### 3. Widerspruch in der Eskalationslogik (F5)
**Datei:** `mdal/config.py`
**Kontext:** Anforderung F5 (Maximal 3 Versuche)
**Beschreibung:** F5 spezifiziert hart: "Das System unternimmt maximal 3 Versuche (initialer Output + 2 Refinements)." Der Pydantic-Default für `max_retries` steht jedoch auf `3`. Üblicherweise bedeutet `max_retries=3`, dass nach dem initialen Versuch noch 3 Retries erfolgen (insgesamt 4 Versuche).
**Empfehlung:** Standardwert von `max_retries` auf `2` senken, um strikt konform mit F5 zu sein. *(Bereits im obigen Code-Vorschlag behoben)*.

### 4. Fragiles JSON-Parsing im Offline-Trainer
**Datei:** `mdal/trainer/trainer.py`
**Kontext:** Anforderung F17 (Trainer-Komponente)
**Beschreibung:** Die Funktion `_extract_json()` sucht lediglich nach dem ersten `{` und dem letzten `}`. Da LLMs manchmal mehrere JSON-Blöcke generieren oder die Antwort mit Erklärtexten durchmischen, ist dieser Ansatz sehr fehleranfällig. Schlägt das Parsing fehl, wirft der Trainer direkt einen `TrainerError` ab.
**Empfehlung:** Für Layer 1 und Layer 3 Prompts sollte (falls das genutzte LLM dies unterstützt) die native "Structured Output"-API oder der "JSON Mode" (z. B. via OpenAI API) erzwungen werden. Alternativ sollten Pydantic-Parser eingesetzt werden, die bei fehlerhaftem Output selbstständig einen Korrektur-Prompt (Auto-Retry) an das LLM schicken.

---

## 🟢 LOW IMPACT (Architektonische Schulden / Tech Debt)

### 5. LLM-as-Judge Prompting ohne "Chain-of-Thought" (Schicht 3)
**Datei:** `mdal/verification/semantic/layer3.py`
**Kontext:** Layer-Kaskade (F6/F10)
**Beschreibung:** Der Judge wird angewiesen, binär mit "passt" oder "passt nicht" zu antworten. Studien zeigen, dass LLMs als Rater signifikant bessere und verlässlichere Entscheidungen treffen, wenn sie den Bewertungsgrund vor der endgültigen Klassifizierung ausschreiben dürfen (z. B. `Begründe zuerst in 1-2 Sätzen und ende dann mit PASST oder PASST NICHT`).
**Empfehlung:** Den Prompt in `_JUDGE_PROMPT` so anpassen, dass das LLM ein kurzes Reasoning ausgibt. Da Schicht 3 nur im Tiebreak-Fall getriggert wird, rechtfertigt die drastisch erhöhte Zuverlässigkeit die zusätzliche Latenz.

### 6. Laufzeitpfade Validierung ohne Protokoll/Verbindungsprüfung
**Datei:** `mdal/config.py`
**Kontext:** Anforderung F11 (Betriebsbereitschaft)
**Beschreibung:** `validate_runtime_paths` prüft nur lokale Datei-Pfade. Für ein "vollständig konfiguriertes Setup" (F11) wäre es in Phase 6 sinnvoll, beim Starten des Systems einen kurzen PING oder Konnektivitätstest an das eingestellte Ziel-LLM, Embedding-Modell und die externe Audit-Datenbank (F4) zu senden, um Stille Fehler zur Laufzeit zu vermeiden.