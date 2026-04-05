"""
Format-Erkennung — identifiziert den Output-Typ vor der Strukturprüfung.

Erkannte Typen: JSON, XML, Prosa.
Bei reiner Prosa entfällt die Strukturprüfung (F2, F6).

Erkennungsreihenfolge:
  1. JSON: versucht json.loads() — schlägt nicht fehl bei Whitespace/BOM
  2. XML:  versucht lxml.etree.fromstring() — erkennt auch XML-Fragmente
  3. Prosa: alles andere
"""

from __future__ import annotations

import re
import json
from enum import Enum

from lxml import etree


class OutputFormat(str, Enum):
    JSON  = "json"
    XML   = "xml"
    PROSE = "prose"


class DetectedOutput:
    """Ergebnis der Format-Erkennung."""

    __slots__ = ("format", "xml_namespace", "xml_root_tag")

    def __init__(
        self,
        format: OutputFormat,
        xml_namespace: str | None = None,
        xml_root_tag:  str | None = None,
    ) -> None:
        self.format        = format
        self.xml_namespace = xml_namespace   # für Plugin-Matching
        self.xml_root_tag  = xml_root_tag    # für Plugin-Matching

    def is_structured(self) -> bool:
        return self.format != OutputFormat.PROSE

    def __repr__(self) -> str:
        if self.format == OutputFormat.XML:
            return (
                f"DetectedOutput(format=xml, ns={self.xml_namespace!r}, "
                f"root={self.xml_root_tag!r})"
            )
        return f"DetectedOutput(format={self.format})"


def extract_code(text: str) -> str:
    """Extrahiert reinen Code aus Markdown-Fences, falls vorhanden."""
    match = re.search(r"```(?:json|xml)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def detect_format(text: str) -> DetectedOutput:
    """
    Erkennt das Format des übergebenen Textes.

    Reihenfolge: JSON → XML → Prosa.
    Wirft keine Exception — unbekannte Formate sind Prosa.
    """
    clean_text = extract_code(text)
    if not clean_text:
        return DetectedOutput(OutputFormat.PROSE)
        
    # 1. Explizite Markdown-Tags prüfen (erzwingt das Format, auch wenn kaputt!)
    if re.search(r"```json", text, re.IGNORECASE):
        return DetectedOutput(OutputFormat.JSON)
        
    if re.search(r"```xml", text, re.IGNORECASE):
        try:
            root = etree.fromstring(clean_xml.encode("utf-8"))
            return DetectedOutput(
                format=OutputFormat.XML,
                xml_namespace=_extract_namespace(root.tag),
                xml_root_tag=etree.QName(root.tag).localname,
            )
        except Exception:
            return DetectedOutput(OutputFormat.XML) # Kaputtes XML wird an StructureChecker gereicht

    # 2. Heuristische Erkennung anhand des Inhalts
    if clean_text.startswith(("{", "[")):
        # Selbst wenn json.loads() fehlschlägt, ist es strukturell als JSON gedacht.
        # Der StructureChecker wird den Parsing-Fehler dann sauber werfen.
        return DetectedOutput(OutputFormat.JSON)

    if clean_text.startswith("<"):
        try:
            root = etree.fromstring(clean_text.encode("utf-8"))
            namespace = _extract_namespace(root.tag)
            root_tag  = etree.QName(root.tag).localname
            return DetectedOutput(
                format=OutputFormat.XML,
                xml_namespace=namespace,
                xml_root_tag=root_tag,
            )
        except etree.XMLSyntaxError:
            return DetectedOutput(OutputFormat.XML) # Kaputtes XML -> StructureChecker

    return DetectedOutput(OutputFormat.PROSE)


def _extract_namespace(clark_name: str) -> str | None:
    """Extrahiert den Namespace aus einem Clark-Notation-Tag ({ns}local)."""
    if clark_name.startswith("{"):
        end = clark_name.index("}")
        return clark_name[1:end]
    return None
