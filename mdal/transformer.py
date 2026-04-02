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

from mdal.fingerprint.models import Fingerprint

# ---------------------------------------------------------------------------
# Bekannte informelle Füllwörter → Ersatz (leer = Wort entfernen)
# ---------------------------------------------------------------------------
# Nur eindeutige Füllwort-Verwendungen — Wörter mit zentraler semantischer
# Bedeutung werden NICHT automatisch ersetzt.
_INFORMAL_SUBSTITUTIONS: dict[str, str] = {
    "halt":      "",           # "Das ist halt so." → "Das ist so."
    "irgendwie": "",           # "Das funktioniert irgendwie nicht." → "Das funktioniert nicht."
    "eigentlich": "",          # "Das sollte eigentlich klappen." → "Das sollte klappen."
    "quasi":     "im Wesentlichen",
    "sozusagen": "gewissermaßen",
    "okay":      "in Ordnung",
    "ok":        "in Ordnung",
    "super":     "sehr gut",
    "toll":      "gut",
    "mega":      "sehr",
    "echt":      "tatsächlich",
    "krass":     "deutlich",
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
