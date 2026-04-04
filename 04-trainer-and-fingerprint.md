# Trainer und Fingerprint-Modell

## Fingerprint-Datenmodell

Das Datenmodell liegt in `mdal/fingerprint/models.py`.

```mermaid
classDiagram
    class Fingerprint {
      +str id
      +int version
      +str language
      +datetime created_at
      +StyleRules layer1
      +EmbeddingProfile layer2
      +GoldenSamples layer3
    }

    class StyleRules {
      +int formality_level
      +int avg_sentence_length_max
      +list preferred_vocabulary
      +list avoided_vocabulary
      +list custom_rules
    }

    class EmbeddingProfile {
      +list centroid
      +str model_name
      +int sample_count
      +int dimensions
    }

    class GoldenSamples {
      +list samples
    }

    class GoldenSample {
      +str prompt
      +str response
    }

    Fingerprint --> StyleRules
    Fingerprint --> EmbeddingProfile
    Fingerprint --> GoldenSamples
    GoldenSamples --> GoldenSample
```

## FingerprintStore

`mdal/fingerprint/store.py` speichert Fingerprints dateisystembasiert und versioniert.

### Tatsächliche Verzeichnisstruktur

```text
{base_path}/
  de/
    current
    v1.json
    v2.json
  en/
    current
    v1.json
```

### Verhalten

- `save()` vergibt die nächste Versionsnummer
- `load_current()` lädt die aktive Version
- `load_version()` lädt explizite Versionen
- `rollback()` setzt den Pointer `current` zurück

Wichtig: Der Store ist laut Modulkommentar **nicht für gleichzeitige Schreibzugriffe ausgelegt**.  
In `phasenplanung.txt` ist deshalb ein späterer Locking-Fix als Pre-Go-Live-Maßnahme vermerkt.

## Offline-Trainer

Der Trainer liegt in `mdal/trainer/trainer.py` und wird per CLI über `mdal-train` aufgerufen.

## Trainer-Ablauf

```mermaid
flowchart TD
    A[Konversationsdateien laden] --> B[Assistent-Antworten sammeln]
    B --> C[Layer 1 per LLM extrahieren]
    B --> D[Layer 2 Embeddings berechnen]
    A --> E[Prompt-Response-Paare bilden]
    E --> F[Golden Samples per LLM selektieren]
    C --> G[Fingerprint bauen]
    D --> G
    F --> G
    G --> H[FingerprintStore.save]
```

## Was der Trainer konkret tut

### Layer 1
Aus Assistent-Antworten wird per LLM ein JSON mit Stilregeln extrahiert:

- Formalität
- maximale Satzlänge
- bevorzugtes Vokabular
- vermiedenes Vokabular
- Freitextregeln

### Layer 2
Für jede Assistent-Antwort wird ein Embedding erzeugt; daraus bildet der Trainer den Centroid.

### Layer 3
Aus User/Assistant-Turn-Paaren werden repräsentative Golden Samples selektiert.

## Wichtige Implementation Details

### Fallback bei Golden-Sample-Selektion
Wenn die LLM-Antwort für die Sample-Selektion kein brauchbares JSON liefert, verwendet der Trainer die ersten N Kandidaten.  
Das ist laut `bearbeitungshinweise.txt` bewusst die einzige tolerierte stille Fallback-Stelle, weil es sich um Offline-Kalibrierung handelt.

### Kein entsprechender Fallback in Layer 1
Die Stilregel-Extraktion bricht bei unbrauchbarem JSON ab und wirft `TrainerError`.

### CLI
`trainer.py` enthält neben der Kernlogik auch:

- Dateilader für JSON-Konversationen
- Argumentparser
- Startpunkt `main()`

Damit ist das Modul gleichzeitig Bibliotheks- und CLI-Einstiegspunkt.
