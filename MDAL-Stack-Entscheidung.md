# MDAL — Technologie-Stack: Entscheidung

## Kontext

MDAL wird on-premise beim Betreiber installiert. Kundendaten verlassen das Netz des Betreibers nicht. Das stellt besondere Anforderungen an den Stack — nicht nur technisch, sondern auch im Hinblick auf Schutz des geistigen Eigentums.

---

## Entschiedene Punkte

### Zielarchitektur: Rust-Kern + Python-Adapter

**Rust für den Kern** (Scoring-Logik, Fingerprint-Vergleich, Evaluator-Kaskade):
- Kompilierter Binärcode — schwer zu reverse-engineeren, schützt proprietäre Logik
- Hohe Performance für mathematische Operationen (Embedding-Vergleich, Schicht 2)
- Statische Binaries vereinfachen on-premise Deployment erheblich — keine Runtime-Installation beim Kunden nötig
- Rust als "Puffer": Schicht 1 und 2 kosten kaum Latenz, das Performance-Budget bleibt für Schicht 3 (LLM-as-Judge) verfügbar

**Python als Integrationsschicht nach außen:**
- LLM-Clients, Embedding-Bibliotheken und Vektor-Datenbanken sind Python-first
- Niedrige Einstiegshürde für Entwickler die MDAL integrieren wollen

**F17 Trainer-Komponente: Python**
- Sitzt außerhalb der Laufzeit-Pipeline, nicht zeitkritisch
- IP-Schutz dort weniger kritisch als im Kern-Evaluator
- Python ist für LLM-Analyse-Aufgaben das natürlichere Werkzeug

### v1-Strategie: Python-PoC zuerst

Die Zielarchitektur ist klar — aber die eigentlichen v1-Risiken sind fachlicher Natur, nicht technischer:
- Ist das Fingerprint-Konzept in der Praxis tragfähig?
- Trifft die Scoring-Kaskade sinnvolle Entscheidungen?
- Funktioniert der Transformer ohne Strukturverletzung zuverlässig?
- Enden die Schwellwerte nicht im Nebel?

Diese Fragen beantwortet kein Stack. Deshalb: **Python-PoC zur fachlichen Validierung der Kernkonzepte, danach Extraktion des Kerns in Rust.**

Ein PoC der scheitert, soll schnell scheitern — nicht langsam an Sprachgrenzen und Tooling-Aufwand.

---

## Verworfene Alternativen

**Go:** Plausible Alternative zu Rust — Single-Binary, einfacheres Team-Onboarding. Nicht bevorzugt wegen schwächerem Ökosystem-Fit im AI/Embedding-Bereich, bleibt aber als Option wenn Rust im Umsetzungsteam keine reale Stärke ist.

**Java / C#:** Nicht bevorzugt wegen Deployment- und Ökosystem-Fit. Runtime-Abhängigkeit ist in Enterprise-Umgebungen kein automatisches Ausschlusskriterium, passt aber nicht zur Zielsetzung "minimale Abhängigkeiten beim Kunden".

**Python allein:** Ungeeignet als Endzustand — kompilierter Python-Code bietet keinen echten Schutz für proprietäre Logik. Als PoC-Sprache für fachliche Validierung hingegen sinnvoll.

---

## Externes Feedback (Zusammenfassung)

Drei unabhängige Einschätzungen wurden eingeholt. Konsens:
- Rust-Kern + Python-Adapter ist die richtige Zielarchitektur
- Die eigentliche Frage für v1 ist nicht der Stack, sondern ob das fachliche Konzept trägt
- Python-PoC vor Rust-Extraktion ist der pragmatischere Weg

---

*Stand: April 2026 — entschieden nach externer Validierung*
