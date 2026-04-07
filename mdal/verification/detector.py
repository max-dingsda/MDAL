"""
Format detection — identifies the output type before structure checking.

Detected types: JSON, XML, prose.
For pure prose, structure checking is skipped (F2, F6).

Detection order:
  1. JSON: attempts json.loads() — does not fail on whitespace/BOM
  2. XML:  attempts lxml.etree.fromstring() — also detects XML fragments
  3. Prose: everything else
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
    """Result of format detection."""

    __slots__ = ("format", "xml_namespace", "xml_root_tag")

    def __init__(
        self,
        format: OutputFormat,
        xml_namespace: str | None = None,
        xml_root_tag:  str | None = None,
    ) -> None:
        self.format        = format
        self.xml_namespace = xml_namespace   # for plugin matching
        self.xml_root_tag  = xml_root_tag    # for plugin matching

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
    """Extracts raw code from markdown fences if present."""
    match = re.search(r"```(?:json|xml)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def detect_format(text: str) -> DetectedOutput:
    """
    Detects the format of the given text.

    Order: JSON → XML → prose.
    Never raises — unknown formats are treated as prose.
    """
    clean_text = extract_code(text)
    if not clean_text:
        return DetectedOutput(OutputFormat.PROSE)

    # 1. Check explicit markdown tags (forces the format, even if malformed)
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
            return DetectedOutput(OutputFormat.XML)  # Malformed XML is passed to StructureChecker

    # 2. Heuristic detection based on content
    if clean_text.startswith(("{", "[")):
        # Even if json.loads() fails, it is structurally intended as JSON.
        # StructureChecker will raise the parsing error cleanly.
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
            return DetectedOutput(OutputFormat.XML)  # Malformed XML → StructureChecker

    return DetectedOutput(OutputFormat.PROSE)


def _extract_namespace(clark_name: str) -> str | None:
    """Extracts the namespace from a Clark-notation tag ({ns}local)."""
    if clark_name.startswith("{"):
        end = clark_name.index("}")
        return clark_name[1:end]
    return None
