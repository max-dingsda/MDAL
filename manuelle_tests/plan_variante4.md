# Variante 4 — A/B/C Modell-Shift-Test: Implementierungsplan

**Ziel:** Zeigen, dass MDAL einen Modellwechsel (llama3.2 → mistral) für den Enduser kompensiert.

**Setup:**
```
A: llama3.2  direkt          → Baseline / Referenzstil
B: mistral   direkt          → roher Modellwechsel (ohne Kompensation)
C: mistral   via MDAL-Proxy  → MDAL-kompensierter Modellwechsel
```

**Kernfrage:** Kommt C näher an A heran als B?

---

## Schritt 1 — llama3.2-Trainingsdaten erzeugen

**Script:** `scripts/generate_llama_conversations.py`

### Was das Script tun soll

1. Lädt Prompts aus einer JSON-Datei (Training-Set, ~80 Prompts)
2. Sendet jeden Prompt als User-Message gegen ollama/llama3.2 (OpenAI-kompatibler Endpunkt)
3. Speichert jede Konversation (Prompt + Response) im OpenAI-Chat-Format
4. Gibt bei Fehlern eine Warnung aus, überspringt den Prompt, setzt fort
5. Zeigt Fortschritt (n/N abgeschlossen, geschätzte Restzeit)
6. Schreibt am Ende eine Zusammenfassung: Erfolg/Fehler-Zähler

### Aufrufparameter

| Parameter | Default | Beschreibung |
|---|---|---|
| `--prompts-file` | `manuelle_tests/prompts_training.json` | Pfad zur Prompt-Liste |
| `--output-file` | `manuelle_tests/llama_conversations.json` | Ausgabedatei (OpenAI-Format) |
| `--model` | `llama3.2` | Ollama-Modellname |
| `--base-url` | `http://localhost:11434/v1` | Ollama OpenAI-kompatibler Endpunkt |
| `--delay` | `0.5` | Pause zwischen Requests in Sekunden |
| `--system-prompt` | *(leer)* | Optionaler System-Prompt für alle Konversationen |

### Ausgabeformat (OpenAI-Chat-Format, direkt Trainer-kompatibel)

```json
[
  {
    "messages": [
      {"role": "user",      "content": "Erkläre den Unterschied zwischen..."},
      {"role": "assistant", "content": "Der Unterschied liegt darin..."}
    ]
  },
  ...
]
```

Wichtig: Dieses Format wird direkt von `mdal/trainer/trainer.py` verarbeitet —
kein Konvertierungsschritt nötig.

---

## Schritt 2 — llama3.2-Fingerprint trainieren

Kein neues Script nötig — vorhandenen Trainer verwenden. Der Trainer hat **keinen**
`--fingerprint-name`-Parameter; der Speicherpfad kommt aus der Config. Daher muss
eine separate Test-Config angelegt werden, damit der ChatGPT-Fingerprint nicht
überschrieben wird.

**Test-Config anlegen:** `config/proxy_llama32_test.yaml` — Kopie von `config/proxy.yaml`
mit geändertem `fingerprint_path`, z.B.:
```yaml
fingerprint_path: fingerprints_llama32/
```

**Trainer-Aufruf:**
```bash
conda run -n MDAL python -m mdal.trainer.trainer \
  --config config/proxy_llama32_test.yaml \
  --input manuelle_tests/llama_conversations.json \
  --language de
```

Voraussetzung: Ollama läuft, nomic-embed-text verfügbar.
Laufzeit: ~5–10 Minuten für 80 Konversationen.

**MDAL-Proxy für Schritt 3:** ebenfalls mit `proxy_llama32_test.yaml` starten,
damit der Proxy den llama3.2-Fingerprint lädt.

---

## Schritt 3 — Dreifach-Vergleichstest

**Script:** `scripts/comparison_test.py`

### Was das Script tun soll

1. Lädt Prompts aus der Comparison-Prompt-Datei (20 Prompts)
2. Sendet jeden Prompt gegen **drei Endpunkte** nacheinander:
   - A: llama3.2 direkt (Ollama)
   - B: mistral direkt (Ollama)
   - C: mistral via MDAL-Proxy
3. Speichert alle drei Responses pro Prompt
4. Schreibt zwei Output-Dateien:
   - `comparison_results_TIMESTAMP.json` — Rohdaten
   - `comparison_results_TIMESTAMP.md` — Markdown-Tabelle für menschliche Auswertung
5. Optional: berechnet einfache Ähnlichkeitsmetrik (Zeichenlänge, Formalitäts-Indikator)

### Aufrufparameter

| Parameter | Default | Beschreibung |
|---|---|---|
| `--prompts-file` | `manuelle_tests/prompts_comparison.json` | Pfad zur Comparison-Prompt-Liste |
| `--output-dir` | `manuelle_tests/results/` | Ausgabeverzeichnis |
| `--llama-url` | `http://localhost:11434/v1` | Ollama-Endpunkt für llama3.2 |
| `--llama-model` | `llama3.2` | Modellname Baseline |
| `--mistral-url` | `http://localhost:11434/v1` | Ollama-Endpunkt für mistral |
| `--mistral-model` | `mistral` | Modellname Vergleich |
| `--mdal-url` | `http://localhost:8080/v1` | MDAL-Proxy-Endpunkt |
| `--mdal-model` | `mistral` | Modell das MDAL gegen Ollama schickt |
| `--delay` | `1.0` | Pause zwischen Prompt-Runden |
| `--skip-on-error` | `true` | Fehler überspringen statt abbrechen |

### Markdown-Ausgabeformat

```markdown
# Vergleichstest — 2026-04-04 14:32

| # | Prompt | llama3.2 (A) | mistral direkt (B) | mistral+MDAL (C) |
|---|---|---|---|---|
| 1 | Erkläre... | Lorem... | Lorem... | Lorem... |
...

## Beobachtungen
*(manuell ausfüllen)*
```

---

## Prompt-Dateien

### Format (beide Dateien gleich)

```json
[
  {
    "id": 1,
    "category": "erklaerung",
    "prompt": "Erkläre den Unterschied zwischen REST und GraphQL.",
    "note": ""
  },
  ...
]
```

Kategorien helfen bei der späteren Auswertung (hat MDAL bei technischen Fragen
besser normalisiert als bei informellen?).

### Datei 1: `manuelle_tests/prompts_training.json` — 80 Prompts für llama3.2-Fingerprint

Kategorien-Verteilung (je ~13–14 Prompts):
- `erklaerung` — "Erkläre X", "Was ist Y" (technisch-sachlich)
- `vergleich` — "Was ist der Unterschied zwischen A und B"
- `anleitung` — "Wie gehe ich vor, um X zu tun"
- `analyse` — "Was sind die Vor- und Nachteile von X"
- `kurz` — sehr kurze Prompts (1 Satz, Testfall für Kurz-Antworten)
- `softwareentwicklung` — Code, Architektur, Tooling

### Datei 2: `manuelle_tests/prompts_comparison.json` — 20 Prompts für Vergleichstest

Subset aus den 80 Training-Prompts: je ~3–4 pro Kategorie, repräsentativ verteilt.
Exakt dieselben Prompt-Texte wie in Training-Datei (damit kein Novelty-Effekt).

---

## Abhängigkeiten / Voraussetzungen

- Ollama läuft mit `llama3.2` und `mistral` verfügbar
- MDAL-Proxy läuft mit llama3.2-Fingerprint geladen (nach Schritt 2)
- Conda-Env: `conda run -n MDAL python scripts/...`
- Python-Abhängigkeiten: `openai` (bereits im Env vorhanden für MDAL-Tests)

## Noch offen

*(keine offenen Punkte — alle Fragen geklärt)*
