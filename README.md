# MDAL (Model-Driven Architecture Layer)

## Was ist das?
MDAL ist ein spezialisierter Normalisierungs-Layer (Proxy), der als Middleware zwischen Applikationen/Nutzern und Large Language Models (LLMs) sitzt. 

Das Ziel von MDAL ist es, den sogenannten **"Model-Shift-Effekt"** zu dämpfen: Die User Experience, der Tonfall und die Struktur der Antworten bleiben absolut konsistent, unabhängig davon, welches KI-Modell (oder welche Modell-Version) im Hintergrund die eigentliche Generierungsarbeit leistet.

## Was macht MDAL? (High-Level)
MDAL fängt die Antworten eines LLMs ab und prüft sie gegen einen vorher definierten "Charakter-Fingerabdruck" (den Soll-Zustand). MDAL leitet Antworten erst an den Nutzer weiter, wenn sie den Qualitätskriterien entsprechen:

- **Stil-Normalisierung:** MDAL prüft Formalitätslevel, Satzstruktur und Vokabular (z.B. konsequentes "Siezen" statt "Duzen").
- **Struktur-Validierung:** Harte Überprüfung von strukturierten Outputs (z.B. JSON oder XML) gegen definierte Schemata.
- **Semantische Integrität:** Ein LLM-basierter Transformer glättet bei Bedarf den Textstil, blockiert aber strikt "Halluzinationen" oder das Vergessen von Fakten (Entity-Check).
- **Gnadenlose Eskalationslogik:** Wenn das Modell Vorgaben nicht trifft, zwingt MDAL es zu Retries. Scheitert das Modell mehrfach, blockiert MDAL die Antwort hart mit einem `HTTP 503 Service Unavailable`, statt schlechten Output durchzuwinken ("Strenge statt stiller Kompromisse").

---

## Wie starte ich was?

Das System ist leichtgewichtig, "API-First" konzipiert und ideal für die Nutzung mit z.B. Ollama oder OpenAI-kompatiblen Endpunkten.

### 1. Voraussetzungen installieren
Es wird lediglich eine aktuelle Python-Umgebung benötigt:
```bash
pip install -r requirements.txt
```

### 2. MDAL-Proxy starten (Laufzeit-Umgebung)
Der Proxy fungiert als Drop-In-Replacement für die Standard-OpenAI-API (Endpunkt `/v1/chat/completions`). 
*(Stelle sicher, dass deine `config/mdal.yaml` korrekt eingerichtet ist).*
```bash
# Startet standardmäßig auf Port 8080.
# Der Port kann optional über die Umgebungsvariable MDAL_PORT geändert werden.
set MDAL_PORT=8081
python -m mdal.proxy.server
```

### 3. MDAL-Trainer starten (Fingerprint-Kalibrierung)
Die Offline-Komponente, um aus historischen Chat-Verläufen (Golden Samples) einen neuen, versionierten Charakter-Fingerabdruck abzuleiten:
```bash
python -m mdal.trainer.trainer --config config/mdal.yaml --input deine_chats.json --language de
```

---

## Weitere Dokumentation
Für tiefergehende Informationen zur Architektur, den detaillierten Layer-Konzepten, der Konfiguration sowie der Plugin-Entwicklung verweisen wir auf die umfassende Benutzerdokumentation:
👉 **Benutzerdokumentation öffnen**