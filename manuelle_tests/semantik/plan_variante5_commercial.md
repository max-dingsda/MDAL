# Variante 5 — Commercial Heavyweights: GPT-4o vs. Claude Sonnet

**Ziel:** Beweisen, dass MDAL den "Model-Shift-Effekt" auch bei kommerziellen State-of-the-Art-Modellen kompensieren kann. Wir bringen Claude dazu, exakt den Charakter von GPT-4o anzunehmen.

**Setup:**
*   **A:** GPT-4o (OpenAI) → Baseline / Referenzstil
*   **B:** Claude Sonnet (Anthropic) direkt → Roher Modellwechsel
*   **C:** Claude Sonnet via MDAL → MDAL-kompensierter Modellwechsel

---

## Vorbereitung (API Keys & Tools)

Du benötigst zwei API-Keys als Umgebungsvariablen in deinem Terminal:
```bash
set OPENAI_API_KEY=sk-...
set ANTHROPIC_API_KEY=sk-ant-api03-...
```

Installiere die benötigten Python-Pakete (falls noch nicht vorhanden):
```bash
pip install openai anthropic "litellm[proxy]"
```

---

## Schritt 1 — GPT-4o Baseline erzeugen (Die "ChatGPT-Chats")
Wir jagen unsere 80 Training-Prompts gegen GPT-4o, um den perfekten Soll-Zustand zu generieren.

```bash
python scripts/generate_gpt4o_conversations.py
```
*Output:* `manuelle_tests/semantik/gpt4o_chats.json`

---

## Schritt 2 — MDAL Fingerprint trainieren
Wir lassen den MDAL-Trainer den Stil von GPT-4o extrahieren (Vokabular, Formalität, Embeddings). 
*(Da du die Umgebungsvariable `OPENAI_API_KEY` im Terminal gesetzt hast, zieht sich der Trainer den Key für die Embeddings vollautomatisch).*

```bash
python -m mdal.trainer.trainer --config config/trainer_commercial.yaml --input manuelle_tests/semantik/gpt4o_chats.json --language de
```

---

## Schritt 3 — LiteLLM & MDAL-Proxy starten
Da MDAL das OpenAI-API-Format spricht, Claude aber ein eigenes Format hat, starten wir `litellm` in einem separaten Terminal. Es fungiert als Übersetzer auf Port 4000.

**Terminal 2 (LiteLLM):**
```bash
litellm --model anthropic/claude-sonnet-4-6 --port 4000
```

**Terminal 3 (MDAL Proxy):**
```bash
python -m mdal.proxy.server
```

---

## Schritt 4 — Der finale Vergleichstest
Wir nehmen nun die vollen 85 Prompts aus den GPT-4o-Trainingsdaten und vergleichen sie. GPT-4o wird dabei direkt aus der JSON-Datei gelesen (keine neuen API-Kosten!), während Claude 3.5 live einmal roh und einmal via MDAL befragt wird.

**Terminal 1:**
```bash
python scripts/comparison_test_commercial.py
```

*Ergebnis:* Eine fertige Markdown-Datei in `manuelle_tests/results/`, die den Model-Shift direkt sichtbar macht!