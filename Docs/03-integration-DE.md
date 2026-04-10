# Integration in bestehende Anwendungen

MDAL ist als **"Drop-In-Replacement"** für die OpenAI API konzipiert. Das bedeutet, dass Sie Ihre bestehenden Anwendungen (Skripte, Chatbots, Frameworks) kaum anpassen müssen. Da MDAL nach außen hin die exakt gleiche API-Schnittstelle (`POST /v1/chat/completions`) wie OpenAI anbietet, reicht es in den meisten Fällen aus, lediglich die Ziel-URL zu ändern.

## 1. Architektur-Prinzip
Anstatt dass Ihre Anwendung direkt mit dem LLM (z. B. OpenAI, Ollama, Anthropic) kommuniziert, sendet sie die Anfrage an den lokalen MDAL-Server. MDAL verifiziert die Antwort und leitet sie erst dann an Ihre Anwendung weiter, wenn sie den Fingerprint-Vorgaben entspricht.

## 2. Code-Beispiel (Python OpenAI SDK)
Sie können weiterhin die offiziellen OpenAI-Bibliotheken nutzen. Sie biegen lediglich die `base_url` auf Ihren MDAL-Server um:

```python
from openai import OpenAI

# Der Client wird initialisiert, leitet aber alle Anfragen an MDAL um!
client = OpenAI(
    base_url="http://localhost:6969/v1", 
    api_key="mdal-key" # MDAL ignoriert den Key oder leitet ihn transparent weiter
)

response = client.chat.completions.create(
    model="irrelevant", # Wird von MDAL ignoriert (Steuerung erfolgt via Control Center)
    messages=[
        {"role": "user", "content": "Schreibe eine kurze Absage auf eine Bewerbung."}
    ],
    # WICHTIG: MDAL unterstützt kein Streaming, da Texte als Ganzes geprüft werden
    stream=False, 
    
    # OPTIONAL: Erzwingt die Prüfung gegen einen bestimmten Sprach-Fingerprint
    extra_headers={"X-MDAL-Language": "de"} 
)

print(response.choices.message.content)
```

## 3. Wichtige Spielregeln für die Integration

* **Kein Streaming:** Der Parameter `stream=True` ist verboten. Da MDAL den Text bewerten, parsen und gegebenenfalls transformieren muss, benötigt es immer den vollständigen Text. Streaming-Anfragen werden von MDAL mit einem `HTTP 400` Fehler blockiert.

* **Modellnamen sind irrelevant:** Parameter wie `model="gpt-4"` im Code werden von MDAL ignoriert. Welches Modell tatsächlich die Arbeit macht, entscheidet der Administrator zentral im MDAL Control Center.

* **Sprachsteuerung:** Wenn Ihre Anwendung mehrsprachig ist, können Sie MDAL bei jedem Request über den HTTP-Header `X-MDAL-Language` (z. B. `en`, `de`) mitteilen, welcher Fingerprint zur Prüfung geladen werden soll. Fehlt der Header, greift die Standard-Sprache der Konfiguration.