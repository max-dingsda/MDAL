# LinkedIn Artikel: Entwürfe

---

## Variante 1: Ursprünglicher Entwurf

**Titel-Ideen:**
1. Strenge statt stiller Kompromisse: Wie wir LLMs mit einem "Charakter-Fingerabdruck" zähmen.
2. Der Model-Shift-Effekt: Warum dein LLM morgen anders spricht als heute – und wie wir das ändern.
3. Die Gefahr der "Semantischen Korruption" in LLMs: Learnings aus unserem MDAL-Projekt.

---

## Einleitung: Der Schmerz in der Produktion
Karfreitag 2026 saß ich morgens auf dem Balkon und trank meinen Kaffee, während meine Gedanken um ein Thema kreisten, das mich schon länger beschäftigt. Seit der Umstellung von GPT-4o auf GPT-5, um genau zu sein. Damals merkte ich es zum ersten Mal extrem und in aller Deutlichkeit: Modelle (hier besonders: LLMs) verhalten sich unterschiedlich und kommunizieren spürbar anders – selbst wenn der Anbieter der gleiche ist und die System-Prompts identisch bleiben.

Ein zweiter, auf den ersten Blick nicht verwandter, aber extrem nerviger Punkt: LLMs haben gelegentlich massive Probleme damit, sich an korrekte Versionen von Standards zu halten. Ich habe mir beispielsweise mehr als einmal von einem LLM Unterstützung bei der ArchiMate-Modellierung gewünscht. Obwohl der aktuell geltende Standard keine "Use"-Beziehung mehr kennt (ältere jedoch schon), tauchte diese hartnäckig in den Antworten auf.

Daraus wurde die Idee geboren, ein Tool zu schaffen, das beides löst: den Model-Shift durch stilistische Überprüfung (und ggf. Korrektur) des Outputs dämpfen und die Strukturtreue durch harte Verifikation gegen Standards (XML-Schemas, Elementlisten) erzwingen.

Genau hier setzen wir mit unserem aktuellen Architektur-Projekt an: **MDAL (Model-Driven Architecture Layer)**.

## Die Idee: Der "Charakter-Fingerabdruck"
MDAL ist eine Middleware – ein OpenAI-kompatibler Proxy, der unsichtbar zwischen Anwendung und LLM sitzt. Der Leitgedanke: *Menschen und Organisationen sollen ihre gewohnten Arbeitsweisen beibehalten können, egal welches Modell im Hintergrund arbeitet.* 

Anstatt dem Modell blind zu vertrauen, prüft MDAL jede generierte Antwort gegen einen vorher kalibrierten, versionierten "Charakter-Fingerabdruck". Wir definieren einen Soll-Zustand (Tonalität, Formulierungsstil, Struktur) und zwingen das Modell durch eine mehrstufige Scoring-Kaskade (Embeddings & LLM-as-a-Judge), diesen einzuhalten.

## Das Vorgehen: Strenge statt stiller Kompromisse
In herkömmlichen Systemen nimmt man oft "Graceful Degradation" in Kauf – man leitet lieber eine halbgare Antwort durch, als den Nutzer warten zu lassen. Wir haben uns bei MDAL bewusst für das Gegenteil entschieden: **Qualität vor stiller Durchleitung.**

Das System liefert entweder korrekten Output oder es eskaliert. Dabei mussten wir auch Architektur-Rückschläge einstecken: Unser anfänglicher, regelbasierter Regex-Transformer zur automatischen Stil-Korrektur war zu fehleranfällig und ist in der Praxis krachend gescheitert. Unsere aktuelle Pipeline sieht daher so aus:
1. Weicht ein Text stilistisch ab, glättet nun ein dedizierter **LLM-basierter Transformer** (`LLMToneTransformer`) den Output.
2. Ist die Struktur kaputt (z.B. defektes JSON/XML), wird das primäre Modell mit der genauen Fehlermeldung zu einem Retry gezwungen. 
3. Scheitert das Modell nach 3 Versuchen, blockiert das System gnadenlos (`HTTP 503`).

🔒 **Privacy by Design: Keine stille Datensammlung**
Ein weiteres, zentrales Architektur-Prinzip, das uns wichtig ist: MDAL speichert *keine* Daten über den für den Betrieb zwingend notwendigen Moment hinaus. Konversationsinhalte und Prüfentscheidungen sind vollständig ephemer und werden nach der Session sofort verworfen.

## Die Ergebnisse: Unsere Learnings aus Phase 6 (Python-PoC)
Wir haben gerade die sechste Phase unseres Proof-of-Concepts (mit Mistral & Llama 3) abgeschlossen. Dabei haben wir fundamentale Erkenntnisse für den Produktivbetrieb gewonnen:

**1. Die Gefahr der "Semantischen Korruption" (Das LLM als Pleaser)**
Dies war unsere wichtigste (und amüsanteste) Erkenntnis. LLMs wollen um jeden Preis die Anweisungen im System-Prompt erfüllen. Wenn wir extrem harte Stilvorgaben machten (z.B. ein formelles Vokabular rund um "Dienstleister" und "Verträge" erzwangen), fing das Modell an, Fakten völlig absurd zu verfälschen, um dem Stil gerecht zu werden. 

*Ein reales Beispiel aus unseren Logs (Aufgabe: Einladung zum IT-Sommerfest):* 
🎯 **1. Der Llama-Standard (Unser Soll-Zustand):** 
> *"Herzlich Einladung zum Sommerfest der IT-Abteilung! Liebe Kollegen, der Zeit ist gekommen..."* (Locker, kollegial)
🤖 **2. Der Model-Shift (Mistral ohne MDAL):** 
> *"Titel: 🌞 Hochzeit der Codes! 💻 Liebe Kolleginnen und Kollegen..."* (Spürbar anderer, stark überdrehter Stil)
💥 **3. Die Semantische Korruption (Mistral mit unserem alten, zu strengen MDAL-Transformer):** 
> *"Es ist uns sehr erfreut, Ihnen die formale Einladung zum jährlichen IT-Abteilungs-Sommerfest in Form einer Vertragsverhandlung zukommen zu lassen. Wir hoffen auf eine erfolgreiche Anwendung des Dienstleistervertrages..."* (Das Modell erfindet eine Vertragsverhandlung, nur um unsere Stilvorgabe zu erfüllen!)

*Unsere Lösung:* Semantische Integrität steht zwingend über stilistischer Perfektion! Wir haben ein hartes "Confidence Scoring" eingebaut. Ändert der Transformer mehr als 30 % des Originaltextes (sogenannte Kaputtoptimierung), wird die Anpassung sofort demütig verworfen. MDAL greift also in Schritt 3 ein und unterbindet die Korruption, bevor sie den Nutzer erreicht.

**2. Hard Language Lock verhindert Sprach-Drift**
Wenn kleine Modelle eine deutsche Stilvorgabe nicht sauber transformieren können, "flüchten" sie gerne in die englische Sprache. Ein vorgeschalteter Validator vergleicht nun zwingend Input- und Output-Locale und unterbindet diesen Sprach-Drift rigoros.

**3. Context-Leaks & Domänen-Profile**
Nutzt man statische Phrasen als Referenz (z.B. "Herr/Frau Dienstleister"), baut das LLM diese teils kontextfremd überall ein. Die Lösung war die Einführung dynamischer Domänen-Profile (`TECHNICAL`, `BUSINESS`, `CREATIVE`), in die Prompts im Vorfeld klassifiziert werden.

## Wie geht es weiter?
Dank dieser defensiven Normalisierungs-Architektur konnten wir die Abbruch-Quote erfolgreich auf unter 5 % senken und den Model-Shift-Effekt massiv dämpfen. 

Unsere nächsten Meilensteine für das Projekt:
* **Härtung strukturierter Outputs:** Wir bauen die Plugin-Architektur für harte XML/JSON-Validierungen weiter aus.
* **Der kommerzielle Härtetest:** Können wir Claude dazu bringen, exakt wie ChatGPT zu klingen? (Als Basis für unseren Offline-Trainer liegen hierfür potenziell 90 MB an historischen ChatGPT-Verläufen bereit).
* **Admin-UI:** Entwicklung einer Oberfläche für Administratoren zur komfortablen Steuerung des Systems.
* **Externe Audit-Logs:** Support für die Auslagerung von Audit-Logs in externe, betreibergesteuerte Systeme (z.B. Datenbanken).

---

Hat jemand von euch in Produktion schon ähnliche Erfahrungen mit "Semantischer Korruption" bei LLMs gemacht? Oder wie geht ihr mit Format-Abbrüchen nach einem Modell-Update um? Lasst uns in den Kommentaren diskutieren!

#SoftwareArchitecture #ArtificialIntelligence #LLM #MDAL #Python #MachineLearning #EnterpriseArchitecture 

----

## Variante 2: Überarbeitete Version (Fokus auf Storytelling & Authentizität)
*Dieser Entwurf geht morgen früh raus.*

Karfreitag 2026. Ich saß auf dem Balkon, Kaffee in der Hand, und ärgerte mich zum wiederholten Mal über dasselbe Problem.

Seit der Umstellung von GPT-4o auf GPT-5 war es mir erstmals richtig deutlich aufgefallen: Dasselbe System-Prompt, derselbe Anbieter — und trotzdem spricht das Modell plötzlich anders. Andere Tonalität. Anderer Stil. Als hätte jemand heimlich den Praktikanten ausgetauscht.

Dazu ein zweites, nerviges Detail aus meiner Arbeit mit ArchiMate: Obwohl der aktuelle Standard eine bestimmte Beziehungsart nicht mehr kennt, taucht sie in LLM-Antworten hartnäckig auf. Halluziniertes Fachwissen aus älteren Trainingsdaten.

Zwei Probleme, eine Idee: **MDAL — Model Drift Avoidance Layer.** (Ja, ich hatte "Model Drift" und "Model Shift" anfangs verwechselt. Der Name blieb trotzdem.)

---

## Erst denken, dann coden

Ich hab das Projekt nicht einfach drauflos gebaut. Ich hab angefangen wie bei jedem ordentlichen Software-Projekt: Requirements. Dann eine Architekturskizze. Dann Code. Dann Iterationen über alle drei Ebenen.

Das klingt selbstverständlich — ist es bei Hobby-Projekten aber meistens nicht. Und es hat sich gelohnt, dazu gleich mehr.

---

## Was MDAL ist

MDAL ist eine Middleware — ein OpenAI-kompatibler Proxy, der unsichtbar zwischen Anwendung und LLM sitzt.

Die Grundidee: Anstatt dem Modell blind zu vertrauen, prüft MDAL jede Antwort gegen einen vorher kalibrierten "Charakter-Fingerabdruck". Ich definiere einen Soll-Zustand — Tonalität, Formulierungsstil, Struktur — und das System zwingt das Modell, diesen einzuhalten.

Qualität vor stiller Durchleitung. Wenn der Output nicht passt, eskaliert das System. Nach drei gescheiterten Versuchen: HTTP 503. Gnadenlos.

---

## Die wichtigste Erkenntnis: Semantische Korruption

Das war mein faszinierendster — und amüsantester — Fund aus Phase 6 des Proof-of-Concepts.

LLMs wollen um jeden Preis die Anweisungen im System-Prompt erfüllen. Wenn ich extrem harte Stilvorgaben setze, fängt das Modell irgendwann an, Fakten zu verbiegen, um dem Stil gerecht zu werden.

Ein reales Beispiel aus meinen Logs. Aufgabe: eine Einladung zum IT-Sommerfest schreiben.

**Llama (mein Soll-Zustand):**
"Herzliche Einladung zum Sommerfest der IT-Abteilung! Liebe Kollegen..."
Locker. Kollegial. Passt.

**Mistral ohne MDAL:**
"Titel: 🌞 Hochzeit der Codes! 💻 Liebe Kolleginnen und Kollegen..."
Überdreht — aber wenigstens noch eine Einladung.

**Mistral mit meinem alten, zu strengen Transformer:**
"Es ist uns sehr erfreut, Ihnen die formale Einladung zum jährlichen IT-Abteilungs-Sommerfest in Form einer Vertragsverhandlung zukommen zu lassen. Wir hoffen auf eine erfolgreiche Anwendung des Dienstleistervertrages..."

Das Modell hat eine Vertragsverhandlung erfunden. Nur um meine Stilvorgabe zu erfüllen.

Das war auch der Moment, an dem mein erster Lösungsansatz krachend scheiterte. Mein regelbasierter Regex-Transformer zur automatischen Stil-Korrektur war schlicht zu fehleranfällig. Also zurück zur Architektur: Ich hab ihn durch einen dedizierten `LLMToneTransformer` ersetzt — ein LLM korrigiert den Stil eines anderen. Und weil LLMs dabei gerne übertreiben, kam das Confidence Scoring dazu: Ändert der Transformer mehr als 30% des Originaltextes, wird die Anpassung verworfen.

Genau für diesen Fall hatte ich keine Anforderung formuliert. Lücke erkannt, Architektur angepasst: Semantische Integrität steht über stilistischer Perfektion.

---

## Weitere Learnings

**Sprach-Drift:** Kleine Modelle "flüchten" bei schwierigen Stilvorgaben gerne ins Englische. Ein vorgeschalteter Locale-Validator unterbindet das jetzt hart.

**Context-Leaks:** Statische Referenzphrasen baut das LLM teils kontextfremd überall ein. Lösung: dynamische Domänen-Profile (`TECHNICAL`, `BUSINESS`, `CREATIVE`), in die Prompts vorab klassifiziert werden.

**Privacy by Design:** MDAL speichert nichts über den zwingend notwendigen Verarbeitungsmoment hinaus. Kein Logging von Konversationsinhalten.

---

## Stand heute

Die Abbruch-Quote liegt unter 5%. Der Model-Shift-Effekt ist deutlich gedämpft.

Als nächstes: härtere XML/JSON-Validierung, ein Admin-UI und — der spannendste Test — kann ich Claude dazu bringen, exakt wie ChatGPT zu klingen?

Ich hab 90 MB historische ChatGPT-Verläufe als Trainingsbasis. Der Versuch kommt.

---

Hat jemand in Produktion ähnliche Erfahrungen mit semantischer Korruption gemacht? Oder wie geht ihr mit unerwartetem Modell-Verhalten nach einem Update um?

#LLM #SoftwareArchitektur #KI #Python #EnterpriseArchitecture
