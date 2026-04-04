# Begriffe und Abgrenzungen

## Zweck dieses Kapitels

Dieses Kapitel dient dazu, zentrale Begriffe in der MDAL-Dokumentation konsistent zu verwenden. Einige Begriffe liegen nah beieinander, beschreiben aber bewusst unterschiedliche fachliche oder operative Sachverhalte. Ohne diese Trennung entstehen schnell Missverständnisse in Architektur, Implementierung und Betriebslogik.

## Fingerprint

Der Fingerprint ist das Referenzniveau für erwartbares Modellverhalten in einem bestimmten Nutzungskontext. Er ist weder bloß ein Prompt noch einfach ein Satz von Few-Shot-Beispielen oder eine Policy. Sein Zweck ist die vergleichende Einordnung von Antworten gegen ein bekanntes akzeptiertes Niveau.

Faustregel:
- Prompt steuert Erzeugung
- Few-Shot demonstriert Muster im Prompt-Kontext
- Policy formuliert Soll-Regeln
- Fingerprint liefert das betriebliche Referenzniveau für Bewertung und Stabilisierung

## Transformation

Transformation bezeichnet die gezielte Umformung einer bereits vorliegenden Modellantwort. Das vorhandene Ergebnis bleibt dabei die Grundlage, wird jedoch angepasst, um näher an das gewünschte Referenzniveau oder an eine erwartete Form zu gelangen.

Beispiele:
- sprachliche Glättung
- Anpassung des Tons
- formale Umstrukturierung eines vorhandenen Inhalts
- Korrektur einzelner Schwächen, ohne den Antwortkern zu ersetzen

Transformation setzt also einen nutzbaren Ausgangsoutput voraus.

## Refinement

Refinement bezeichnet die qualitätsorientierte Nachschärfung eines bereits grundsätzlich brauchbaren Outputs. Fachlich ist Refinement damit ein spezieller Fall der Transformation.

Die Unterscheidung ist vor allem dann hilfreich, wenn betont werden soll, dass:
- der Antwortkern bereits tragfähig ist
- keine grobe Umformung, sondern eine feinere Verbesserung stattfindet
- das Ziel eher Veredelung als Reparatur ist

Kurz gesagt:
- jede Refinement-Maßnahme ist eine Transformation
- nicht jede Transformation ist bereits ein Refinement

## Retry

Retry bezeichnet einen erneuten Modelllauf. Im Unterschied zu Transformation und Refinement wird nicht auf dem bestehenden Ergebnis gearbeitet, sondern ein neuer Output angefordert.

Retry ist sinnvoll, wenn:
- der vorhandene Antwortkern nicht tragfähig genug ist
- die Abweichung vom Referenzniveau zu groß ist
- eine Neu-Erzeugung erfolgversprechender erscheint als eine Umarbeitung

## Stilprüfung

Stilprüfung bedeutet die Bewertung einer Antwort gegen das bekannte Referenzniveau, soweit es um Tonalität, Antwortcharakter, äußere Konsistenz und Nähe zum gewünschten Verhalten geht. Stilprüfung ist besonders für freie Prosa relevant.

Stilprüfung ist **keine** allgemeine fachliche Qualitätsprüfung des Inhalts.

## Validierung

Validierung bezeichnet in MDAL die zusätzliche formale oder fachliche Prüfung strukturierter Inhalte auf Basis einer konkreten Prüfbasis, etwa:
- Schema
- Parser
- domänenspezifisches Plugin
- Regelwerk

Validierung findet nur statt, wenn eine solche Prüfbasis tatsächlich vorhanden ist.

## Qualitätsniveau vs. Prüftiefe

Diese beiden Begriffe sollten nicht vermischt werden:

### Qualitätsniveau
Beschreibt, welches Ergebnisniveau MDAL für das Nutzererlebnis anstrebt.

### Prüftiefe
Beschreibt, wie tief ein konkretes Ergebnis im jeweiligen Kontext tatsächlich geprüft werden kann.

Ein System kann also ein hohes Zielniveau haben, ohne jede Antwort mit derselben Prüftiefe untersuchen zu können. Genau deshalb ist in MDAL die Trennung zwischen Stilprüfung und plugin-basierter Validierung so wichtig.

## Faustregel für die Doku

Wenn unklar ist, welcher Begriff verwendet werden soll, gilt:

- **Fingerprint**, wenn das betriebliche Referenzniveau gemeint ist
- **Transformation**, wenn ein vorhandener Output umgearbeitet wird
- **Refinement**, wenn ein bereits guter Output gezielt nachgeschärft wird
- **Retry**, wenn ein neuer Modelllauf erfolgt
- **Stilprüfung**, wenn freie Prosa gegen das Referenzniveau eingeordnet wird
- **Validierung**, wenn strukturierte Inhalte mit Plugin, Schema oder Regelwerk geprüft werden
