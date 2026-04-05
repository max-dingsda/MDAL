"""
Regelbasierter Ton-Transformer (F10).

Passt ausschließlich Tonalität und Formulierungsstil an.
Kein LLM-Aufruf — zählt daher NICHT als Retry (F5).

Invarianten (F10):
  - Reihenfolge von Aussagen bleibt erhalten
  - Hierarchie und Aufzählungsstruktur bleibt erhalten
  - Vollständigkeit: kein Inhalt wird hinzugefügt oder entfernt
  - Nur Wortebene: informelle Füllwörter entfernen / ersetzen

Implementiert ToneTransformerProtocol → Rust-Kern (Zielarchitektur).
"""

from __future__ import annotations

import re
import difflib
import logging

from mdal.fingerprint.models import Fingerprint
from mdal.interfaces.llm import LLMAdapterProtocol

logger = logging.getLogger(__name__)

_TRANSFORM_PROMPT = """\
Deine Aufgabe ist es, einen Text anzupassen. Dabei gilt folgende STRIKTE Priorität (wichtigste zuerst):

1. SPRACHQUALITÄT: Die Grammatik muss einwandfrei, flüssig und natürlich sein. (Fremdsprachliche Fachbegriffe z.B. aus der IT sind erlaubt und kein Fehler).
2. FAKTENTREUE: Alle Fakten, Zahlen, Entitäten und Sinnzusammenhänge aus dem Original-Text MÜSSEN exakt erhalten bleiben. Erfinde nichts dazu, lasse nichts weg. Behalte Listen und Reihenfolgen exakt bei.
3. STIL-ANPASSUNG: Passe den Text (nur soweit unter strikter Beachtung von Priorität 1 und 2 möglich!) an folgende Stil-Vorgaben an.

Vorgaben (für Priorität 3):
- Formalitätslevel: {formality} (1=sehr informell, 5=sehr formal/akademisch)
- Bevorzugtes Vokabular: {preferred}
- Vermiedenes Vokabular: {avoided}

- Antworte AUSSCHLIESSLICH mit dem transformierten Text, ohne Einleitung oder Erklärung.

Original-Text:
{text}
"""

_VALIDATION_PROMPT = """\
Vergleiche Text A (Original) und Text B (Transformiert).

Text A (Original):
{original}

Text B (Transformiert):
{transformed}

Prüfe STRENG: Enthält Text B noch alle Fakten, Zahlen, Eigennamen, Orte und Zeiten aus Text A? Wurden Fakten weggelassen oder neue erfunden?
Antworte AUSSCHLIESSLICH mit "TRUE" (wenn alle Fakten exakt erhalten blieben) oder "FALSE" (wenn etwas fehlt oder hinzuerfunden wurde). Keine Erklärungen.
"""

_CORRECTION_PROMPT = """\
Deine letzte Transformation war fehlerhaft. Du hast inhaltliche Fakten (Namen, Zahlen, Orte, Zeiten) verändert, weggelassen oder hinzugefügt! Das verletzt die Regel zur Faktentreue.

Hier ist nochmal der Original-Text:
{text}

Vorgaben: Formalitätslevel {formality}, Bevorzugt: {preferred}, Vermieden: {avoided}.

Transformiere den Text stilistisch, aber behalte JEDEN FAKT und JEDE ZAHL zu 100% bei. Erfinde nichts dazu!
Antworte AUSSCHLIESSLICH mit dem korrigierten Text, ohne Einleitung oder Erklärung.
"""

class LLMToneTransformer:
    """
    LLM-basierter Ton-Transformer (F10).

    Passt Tonalität und Formulierungsstil mithilfe eines LLM an.
    Vermeidet grammatikalische Artefakte, die bei regelbasiertem Regex-Ersetzen
    in stark flektierenden Sprachen (wie Deutsch) entstehen.
    """

    def __init__(self, llm_adapter: LLMAdapterProtocol) -> None:
        self._llm = llm_adapter

    def transform(self, text: str, fingerprint: Fingerprint) -> str:
        rules = fingerprint.layer1
        
        preferred = ", ".join(rules.preferred_vocabulary) if rules.preferred_vocabulary else "Keine spezifischen Vorgaben"
        avoided = ", ".join(rules.avoided_vocabulary) if rules.avoided_vocabulary else "Keine spezifischen Vorgaben"

        current_prompt = _TRANSFORM_PROMPT.format(
            formality=rules.formality_level,
            preferred=preferred,
            avoided=avoided,
            text=text
        )
        
        max_attempts = 2
        
        for attempt in range(max_attempts):
            try:
                # 1. Transformation durchführen
                result = self._llm.complete([{"role": "user", "content": current_prompt}]).strip()
                
                # F10: Confidence Scoring (Schutz vor Kaputtoptimierung)
                # Wenn mehr als 30% des Textes verändert wurden, greift die "Demut"-Regel.
                ratio = difflib.SequenceMatcher(None, text.split(), result.split()).ratio()
                if ratio < 0.70:
                    logger.warning("Transformer Confidence Score zu niedrig (Ratio: %.2f). Transformation verworfen (Demut).", ratio)
                    return text

                # 2. Entity-Check (Validierung) durchführen
                val_prompt = _VALIDATION_PROMPT.format(original=text, transformed=result)
                val_response = self._llm.complete([{"role": "user", "content": val_prompt}]).strip().upper()
                
                if "TRUE" in val_response and "FALSE" not in val_response:
                    return result  # Fakten blieben erhalten -> Erfolgreich!
                
                logger.warning("Transformer Entity-Check fehlgeschlagen (Versuch %d/%d).", attempt + 1, max_attempts)
                
                # 3. Für den nächsten Versuch den strengeren Korrektur-Prompt laden
                current_prompt = _CORRECTION_PROMPT.format(
                    formality=rules.formality_level,
                    preferred=preferred,
                    avoided=avoided,
                    text=text
                )
                
            except Exception as exc:
                logger.error("LLMToneTransformer fehlgeschlagen: %s. Gebe Original-Text zurück.", exc)
                return text
                
        logger.error("Transformer konnte Faktentreue nicht sicherstellen. Fallback auf Original-Text.")
        return text

# ---------------------------------------------------------------------------
# Bekannte informelle Füllwörter → Ersatz (leer = Wort entfernen)
# ---------------------------------------------------------------------------
# Nur eindeutige Füllwort-Verwendungen — Wörter mit zentraler semantischer
# Bedeutung werden NICHT automatisch ersetzt.
_INFORMAL_SUBSTITUTIONS: dict[str, str] = {
    # Eindeutige Füllwörter ohne eigenständige Bedeutung → entfernen
    "halt":       "",          # "Das ist halt so." → "Das ist so."
    "irgendwie":  "",          # "Das funktioniert irgendwie nicht." → "Das funktioniert nicht."
    "eigentlich": "",          # "Das sollte eigentlich klappen." → "Das sollte klappen."
    "lol":        "",
    "haha":       "",
    "hey":        "",          # Als Anrede am Satzanfang — nur Füllwert
    # Umgangssprache → Standardsprache
    "quasi":      "im Wesentlichen",
    "sozusagen":  "gewissermaßen",
    "okay":       "in Ordnung",
    "ok":         "in Ordnung",
    "super":      "sehr gut",
    "toll":       "gut",
    "mega":       "sehr",
    "echt":       "tatsächlich",
    "krass":      "deutlich",
    "cool":       "gut",
    "nice":       "gut",
    "jo":         "ja",
    "nö":         "nein",
    "grad":       "gerade",
}

# Formalitätsstufe ab der informelle Füllwörter automatisch entfernt werden
_FORMALITY_SUBSTITUTION_THRESHOLD = 3


class RuleBasedToneTransformer:
    """
    Passt den Ton eines Textes regelbasiert an den Fingerprint an.

    Schritt 1: Avoided vocabulary aus dem Fingerprint entfernen.
    Schritt 2: Allgemeine informelle Füllwörter entfernen (ab Formalität ≥ 3).
    Schritt 3: Leerzeichen-Artefakte normalisieren.

    Implementiert ToneTransformerProtocol.
    """

    def transform(self, text: str, fingerprint: Fingerprint) -> str:
        """
        Transformiert den Ton des Textes anhand des Fingerprints.

        Gibt immer einen String zurück — auch wenn keine Änderungen nötig sind.
        Verändert niemals die Struktur, Reihenfolge oder Vollständigkeit.
        """
        rules  = fingerprint.layer1
        result = text

        # Schritt 1: Avoided vocabulary aus dem Fingerprint entfernen
        for word in rules.avoided_vocabulary:
            result = _replace_word(result, word, "")

        # Schritt 2: Allgemeine informelle Füllwörter (ab Formalität ≥ threshold)
        if rules.formality_level >= _FORMALITY_SUBSTITUTION_THRESHOLD:
            for informal, replacement in _INFORMAL_SUBSTITUTIONS.items():
                result = _replace_word(result, informal, replacement)

        # Schritt 3: Leerzeichen normalisieren (Artefakte durch Entfernungen)
        result = _normalize_whitespace(result)

        return result


# ---------------------------------------------------------------------------
# Hilfsfunktionen (öffentlich für Tests)
# ---------------------------------------------------------------------------

def _replace_word(text: str, word: str, replacement: str) -> str:
    """
    Ersetzt ein Wort (Wortgrenzen-sensitiv, case-insensitiv).

    Wortgrenzen stellen sicher dass "ok" nicht in "okay" oder "Token" gefunden wird.
    """
    pattern = r"\b" + re.escape(word) + r"\b"
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)


def _normalize_whitespace(text: str) -> str:
    """
    Bereinigt Leerzeichen-Artefakte nach Wortentfernungen.

      - Mehrfache Leerzeichen → einfaches Leerzeichen
      - Leerzeichen vor Satzzeichen → kein Leerzeichen
      - Führende/nachfolgende Leerzeichen entfernen
    """
    result = re.sub(r" {2,}", " ", text)
    result = re.sub(r" ([,.:;!?])", r"\1", result)
    return result.strip()
