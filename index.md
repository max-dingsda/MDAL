# MDAL Dokumentation

Diese Doku ist **repo-basiert**: Sie wurde aus der tatsächlich vorliegenden Projektstruktur und den vorhandenen Python-Modulen abgeleitet, nicht aus einer Idealstruktur.

## Zielgruppe

- **Kapitel 1–2** aus der früheren Fassung adressieren Nicht-Techniker.
- **Diese modulare Doku** fokussiert die technischen Kapitel für Entwickler.

## Navigationshilfe

1. [Systemüberblick](01-system-overview.md)
2. [Runtime-Pipeline](02-runtime-pipeline.md)
3. [Verifikation und Scoring](03-verification.md)
4. [Trainer und Fingerprint-Modell](04-trainer-and-fingerprint.md)
5. [Proxy, Startup und Betrieb](05-proxy-and-operations.md)
6. [Repository-Struktur](06-repository-structure.md)
7. [Datei-Referenz](07-file-reference.md)

## Leitgedanke des Systems

MDAL ist im aktuellen Repo als **Python-PoC** umgesetzt. Die Zielarchitektur ist laut `MDAL-Stack-Entscheidung.md` ein **Rust-Kern mit Python-Adaptern**, aber der vorliegende Code validiert die fachlichen Kernfragen zunächst in Python:

- Fingerprint-Konzept
- Verifikationskaskade
- regelbasierte Transformation
- Retry- und Eskalationslogik
- OpenAI-kompatibler Proxy

## Technischer Scope des aktuellen Repos

Der Code deckt bereits zentrale Teile der Laufzeit- und Offline-Architektur ab:

- Fingerprint-Datenmodell und versionierter Store
- Offline-Trainer zur Fingerprint-Erzeugung
- semantische und strukturelle Verifikation
- Retry, Eskalation und Statusmeldungen
- OpenAI-kompatibler FastAPI-Proxy
- Tests auf Unit-, Integrations- und Regressionsebene

Nicht enthalten ist im aktuellen Repo insbesondere:

- produktionsreife Admin-Oberfläche
- echte DB-Audit-Backends
- finaler Rust-Kern
- vollständige Plugin-Beispiele im Repository
