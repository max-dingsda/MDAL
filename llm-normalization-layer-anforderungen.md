# LLM Normalisierungs-Layer — Anforderungsskizze v0.2

## Kontext
Ein spezialisierter Layer zwischen Benutzer und LLM, der sicherstellt, dass der vom Menschen wahrgenommene Output konsistent bleibt — unabhängig davon, welches Modell oder welche Version die eigentliche Arbeit leistet.

---

## Leitgedanke

Dieses System verfolgt einen einzigen Leitgedanken: Menschen und Organisationen sollen ihre gewohnten Arbeitsweisen beibehalten können, unabhängig davon welches Modell oder welche Version im Hintergrund arbeitet. Die User Experience bleibt stabil — technischer Wandel bleibt unsichtbar.

Dabei gelten drei Prinzipien: maximale Transparenz gegenüber dem Betreiber, Datenhaltung auf das notwendige Minimum reduziert, und konsequente Strenge statt stiller Kompromisse. Das System liefert entweder korrekten Output oder meldet explizit warum nicht. Es gibt kein Dazwischen.

---

## Funktionale Anforderungen

**F1 — Stil-Normalisierung**
Das System muss in der Lage sein, den Output unterschiedlicher LLM so zu transformieren, dass ein menschlicher Benutzer keinen Unterschied feststellt. Dies umfasst Tonalität, Formulierungsstil und wahrgenommenes "Verhalten" des Systems.

**F2 — Validierung und Transformation strukturierter Outputs**
Das System muss strukturierte Outputs (z.B. JSON, XML, MCP-Formate) bewerten und bei Abweichung entweder transformieren oder zurückweisen. Eine Zurückweisung bedeutet: den Output an das produzierende Modell zurückgeben mit explizitem Hinweis auf fehlerhafte Elemente. Die Entscheidung ist binär — Teilakzeptanz ist nicht vorgesehen.

**F3 — Fingerabdruck-Definition**
Das System muss eine Möglichkeit bieten, den gewünschten Soll-Zustand zu definieren — den "Charakter-Fingerabdruck". Dies kann über Golden Samples (Referenz-Interaktionen), manuelle Konfiguration oder eine Kombination beider Ansätze erfolgen. Ohne diesen Anker kann das System keinen Vergleichsmaßstab anlegen.

**F4 — Audit und Transparenz**
Das System muss alle Prüf- und Transformationsereignisse in ein Audit-Log schreiben. Ziel, Format und Inhalt des Logs sind vom Betreiber konfigurierbar (Datei, Datenbank o.ä.). Das System selbst speichert keine Log-Inhalte — Speicherort, Aufbewahrungsdauer und Löschzeitpunkt liegen vollständig in der Verantwortung des Betreibers.

**F5 — Eskalationslogik**
Das System muss eine definierte Reaktion haben, wenn ein Modell nach mehrfacher Zurückweisung weiterhin abweichenden Output liefert. Das System unternimmt maximal 3 Versuche (initialer Output + 2 Refinements). Schlägt der dritte Versuch fehl, wird der Vorgang abgebrochen, kein Output ausgegeben, und der Administrator explizit benachrichtigt. Endlosschleifen müssen ausgeschlossen sein. Graceful Degradation ist nicht vorgesehen — jeder Fehler wird explizit gemeldet und der Output zurückgehalten. Halbgare Ergebnisse werden nicht durchgeleitet. Aus Nutzerperspektive wird während laufender Retries eine sichtbare Statusmeldung angezeigt (z.B. "Anfrage läuft, Ergebnis wird erzeugt") — kein stilles Warten.

**F6 — Vollständige Prüfabdeckung**
Jeder Output wird geprüft — ohne Ausnahme. Jeder Output hat entweder Struktur (→ F2) oder Ton (→ F1), beides ist prüfbar. Es gibt keinen Output-Typ der von der Prüfung ausgenommen ist. Prüfung erfolgt ausschließlich auf vollständigen Outputs — kein Eingriff während des Streamings. Der Redefluss des Modells wird nicht unterbrochen.

**F7 — Versionierung des Fingerabdrucks**
Wenn der Fingerabdruck bewusst weiterentwickelt wird, muss das System Versionen verwalten können. Rollback muss möglich sein.

**F8 — Mehrsprachigkeit**
Stil-Normalisierung muss sprachsensitiv sein. Was auf Deutsch "richtig klingt" ist nicht dasselbe wie die englische Übersetzung. Ein globaler Einsatz erfordert Fingerabdrücke pro Sprache.

**F9 — Fallback-Modell** *(niedrig priorisiert)*
Wenn das primäre LLM nicht erreichbar ist, muss das System auf ein alternatives Modell umschalten können — transparent für den Nutzer.

**F10 — Semantische Integrität**
Semantische Transformationen dürfen sich ausschließlich auf Tonalität und Ausdruck erstrecken. Strukturierende Elemente (z.B. Reihenfolge, Hierarchie, Vollständigkeit, Aufzählungen) sind unter allen Umständen beizubehalten.

**F11 — Betriebsbereitschaft**
Das System darf nur in vollständig konfiguriertem Zustand betrieben werden. Ein unvollständiges Setup führt zu einer Fehlermeldung und verhindert den Betrieb. Ein stiller Durchleitungsmodus ist nicht vorgesehen. Was "vollständig konfiguriert" bedeutet, wird im Lösungsraum definiert.

**F12 — Scope-Abgrenzung**
Das System prüft und normalisiert ausschließlich Text, Prosa und formalisierte Outputs (JSON, XML, MCP u.ä.). Code-Ausführung und Bildgenerierung sind explizit nicht im Scope.

**F13 — Fähigkeits-Asymmetrie-Erkennung**
Das System muss erkennen können, wenn ein Modellwechsel eine Fähigkeitslücke erzeugt — also wenn das neue Modell etwas schlicht nicht kann, was das vorherige konnte. In diesem Fall wird sowohl der aktuelle Benutzer als auch der Administrator explizit informiert. Normalisierung allein ist in diesem Fall nicht ausreichend.

**F14 — Multi-Turn-Konsistenz**
Das System stellt sicher, dass der Charakter-Fingerabdruck innerhalb einer Session konsistent angewendet wird. Output 3 darf im Verhalten nicht Output 1 widersprechen. Die Konsistenz ist auf die laufende Session begrenzt — eine session-übergreifende Konsistenz ist nicht vorgesehen, da sie Datenspeicherung erfordern würde und NF3 widerspricht.

**F15 — Prozess-Transparenz für den Endnutzer**
Das System gibt dem Endnutzer kontinuierlich Rückmeldung über seinen aktuellen Zustand. Während der Verarbeitung werden sichtbare Statusmeldungen angezeigt (z.B. "Anfrage wird verarbeitet", "Ergebnis wird geprüft", "Ergebnis wird aufbereitet"). Der Nutzer sieht zu keinem Zeitpunkt einen leeren Bildschirm ohne Kontext. Dies gilt sowohl im Normalfall als auch während laufender Retries.

**F16 — Administrations- und Konfigurationskomponente**
Das System muss eine Konfigurations-Schnittstelle bereitstellen, über die der Betreiber LLM-Verbindungen, Audit-Targets, Fingerprint-Verwaltung (inkl. Versionierung), Eskalationsstufen und Plugin Registry verwalten kann. Die Form der Schnittstelle (CLI, Konfigurationsdatei, Web-UI oder Kombination) ist Lösungsraum. Diese Komponente ist Voraussetzung für F11 (Betriebsbereitschaft) — ohne sie kann das System nicht vollständig konfiguriert werden.

**F17 — Trainer-Komponente (Fingerprint-Kalibrierung)**
Das System muss eine Offline-Komponente bereitstellen, die aus historischen Konversationsdaten den Charakter-Fingerabdruck ableitet. Der Trainer analysiert bestehende Chat-Verläufe mittels LLM und extrahiert daraus Golden Samples, Stilmuster und Embedding-Vektoren. Nach der Analyse werden die Rohdaten nicht weiter benötigt — gespeichert wird ausschließlich der destillierte Fingerabdruck. Der Trainer ist kein Bestandteil der Laufzeit-Pipeline, sondern wird bei Ersteinrichtung und bei bewusster Weiterentwicklung des Fingerabdrucks (F7) eingesetzt. Das für die Analyse verwendete LLM muss nicht identisch mit dem Produktiv-LLM sein.

**F18 — Betriebsmodus-Konfiguration**
Das System muss die Möglichkeit bieten, via Konfiguration einzelne Prüfungen (Semantik, Struktur) zu deaktivieren. Diese werden im Ablauf dann nicht aufgerufen. Eine Abschaltung aller Prüfungen gleichzeitig ist nicht zulässig.

---

## Nicht-funktionale Anforderungen

**NF1 — Erweiterbarkeit**
Das System muss erweiterbar sein, insbesondere hinsichtlich der Bibliothek validierbarer Strukturen. Benutzer und Unternehmen müssen eigene Formate, Schemata und Konventionen einbringen und dauerhaft aufnehmen können — ohne Eingriff in den Kern des Systems. Das Plug-in-Prinzip gilt als Architekturgrundlage.

**NF2 — Community-Bibliothek**
Das System sieht eine öffentliche Bibliothek für Standard-Strukturen vor, zu der externe Beitragende beitragen können. Private Erweiterungen des Betreibers bleiben davon vollständig getrennt und unberührt.

**NF3 — Datenschutz**
Das System unterscheidet zwei Datenkategorien: Persistente Daten (Regelwerk, Golden Samples, Fingerabdruck, Versionen) sind integraler Bestandteil des Systems und werden dauerhaft gespeichert. Ephemere Daten (Konversationsinhalte, konkrete Inputs und Outputs, Prüfentscheidungen) existieren nur für die Dauer einer Session und werden danach verworfen. Das Audit-Log (F4) wird extern und betreiberseitig gespeichert. Das System selbst persistiert keine Log-Inhalte.

**NF4 — Modell-Agnostizität**
Das System darf keine Abhängigkeit zu einem spezifischen LLM-Anbieter haben. Das ist gleichzeitig das Kernversprechen und eine Architekturpflicht.

**NF5 — Audit-Ziel-Kompatibilität**
Das System muss in externe Audit-Ziele schreiben können: gängige Datenbanksysteme (z.B. PostgreSQL, MySQL, MSSQL) sowie gängige Dateisysteme (FAT, NTFS, ext4 u.a.). Die Schnittstelle ist write-only — das System liest, bearbeitet oder löscht keine externen Daten.

**NF6 — Betriebssystem-Unabhängigkeit**
Das System muss auf gängigen Betriebssystemen lauffähig sein: Windows, macOS und gängige Linux-Distributionen. Dies ist Voraussetzung für NF5 und den breiten Enterprise-Einsatz.

**NF7 — Performance**
Das System muss performant genug sein, um jeden Output zu prüfen ohne wahrnehmbare Verzögerung für den Endnutzer zu erzeugen.

**NF8 — Konfigurierbarkeit**
Fingerabdruck, Eskalationsstufen, Audit-Ziel und weitere Betriebsparameter müssen ohne Code-Eingriff konfigurierbar sein.

**NF9 — Beobachtbarkeit**
Das System muss seinen eigenen Zustand nach außen melden können: Betriebsstatus, aktuelle Transformationsrate, Fehlerzustände. Dies ermöglicht die Integration in bestehende Monitoring-Infrastrukturen des Betreibers.

**NF10 — On-Premise-Fähigkeit**
Das System muss ohne Cloud-Abhängigkeit on-premise betreibbar sein. Das darunterliegende LLM kann dabei lokal oder kommerziell über API betrieben werden — beides ist explizit unterstützt.

---

## Offene Fragen (zur weiteren Diskussion)
- Wie genau wird der Fingerabdruck technisch repräsentiert? *(Richtung: Kombination aus Golden Samples, Stilregeln und Embedding-Vektoren — wird durch F17 Trainer-Komponente abgeleitet, Details in Ausarbeitung)*

---

## Entschiedene Fragen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Fingerabdruck-Kalibrierung | Offline-Trainer-Komponente (F17) analysiert historische Chats und extrahiert Fingerabdruck | Vermeidet manuellen Aufbau, nutzt echte Daten als Grundlage, Rohdaten nach Analyse nicht mehr nötig |
| Teilakzeptanz von Outputs | Nicht vorgesehen — binäre Entscheidung | Graubereiche machen das System unberechenbar |
| Durchleitungsmodus bei unvollständigem Setup | Nicht vorgesehen — Fehlermeldung und Betriebsstopp | Stiller Betrieb erweckt falschen Eindruck der Funktionsfähigkeit |
| Graceful Degradation | Nicht vorgesehen — explizite Fehlermeldung | Halbgare Ergebnisse führen den Benutzer auf den falschen Schuldigen |
| Datenhaltung von Konversationsinhalten | Ephemer — Löschung nach Session | Minimale Datenhaltung, Datenschutz by design |
| Audit-Log Speicherung | Extern, betreiberseitig konfigurierbar | Datenschutzverantwortung liegt beim Betreiber |
| Gewollte Evolution des Fingerabdrucks | Möglich, aber bewusste Entscheidung des Betreibers | Unterschied zwischen ungewolltem Drift und kontrollierter Weiterentwicklung |
| Eskalationsstufen | 3 Retries, dann Fehlermeldung und Admin-Benachrichtigung, kein Output | Halbgare Ergebnisse widersprechen dem Leitgedanken |
| Mehrinstanzfähigkeit in v1 | Nicht vorgesehen — mehrere unabhängige Installationen mit je eigenem Fingerabdruck sind jedoch explizit erlaubt | Komplexität in v1 vermeiden ohne zukünftige Nutzung auszuschließen |
| Lizenzmodell Community-Bibliothek | Open Source — frei nutzbar und frei modifizierbar | Qualität durch Community-Beiträge, keine Einschränkung der Nutzung |
| Zielgruppe v1 | Organisationen die LLM einsetzen und den Layer on-prem betreiben — unabhängig ob das LLM lokal oder kommerziell über API läuft | Consumer zahlen nicht, klassisches Enterprise hat zu lange Verkaufszyklen |
| Betriebsmodus | Einzelne Prüfungen deaktivierbar (F18); Abschaltung aller Prüfungen gleichzeitig nicht zulässig | Performance + Flexibilität ohne stillen Durchleitungsmodus |

---

*Stand: v0.5 — F18 ergänzt (Betriebsmodus-Konfiguration)*

**F19 — Integrationsmodell**
MDAL ist eine Middleware — der Endnutzer interagiert nicht direkt mit MDAL, sondern mit einer vorgelagerten Oberfläche oder Anwendung. MDAL sitzt unsichtbar zwischen dieser Anwendung und dem LLM. Das System muss mindestens folgende Integrationsformen unterstützen:

- **API-Proxy:** MDAL stellt einen OpenAI-kompatiblen Endpunkt bereit. Bestehende Anwendungen können MDAL durch einfaches Ändern der API-URL einbinden — ohne Anpassung am Client-Code.
- **Library/SDK:** MDAL kann direkt als Bibliothek in eine Anwendung eingebunden werden, ohne separaten Service.

Die konkrete Auswahl und Priorisierung der Integrationsformen ist Lösungsraum. Der API-Proxy-Ansatz wird als primäre Integrationsform für v1 empfohlen, da er minimale Integrationsarbeit beim Betreiber erfordert.

**F20 — Plugin-Registry-Architektur**
Plugins werden als Ordnerstruktur im Dateisystem abgelegt. Jedes Plugin liegt in einem eigenen Unterordner und besteht aus:

- `manifest.json` — Pflichtdatei: Plugin-ID, Anzeigename, Version, beschreibender Infotext, Angabe welche Dateien vorhanden sind
- `schema.xsd` — optional: formales XML-Schema zur Strukturvalidierung (kann ein offizieller Standard oder ein proprietäres Unternehmensschema sein)
- `elements.json` — optional: Liste erlaubter Elemente, ermöglicht versionsabhängige Validierung (z.B. ArchiMate 2.x vs. 3.x)

Die Validierung läuft zweistufig: erst Schema-Validierung (sofern schema.xsd vorhanden), dann Elementlisten-Validierung (sofern elements.json vorhanden). Mindestens eine der beiden Dateien muss vorhanden sein.

Das Format unterscheidet nicht zwischen Community-Plugins und proprietären Unternehmens-Plugins — der Unterschied liegt ausschließlich im Ablageort (Community-Bibliothek vs. private Erweiterung, siehe NF1/NF2).
