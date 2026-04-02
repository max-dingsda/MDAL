"""
Strukturprüfung (F2) — zweistufige Validierung strukturierter Outputs.

Ergebnis ist binär: bestanden oder nicht. Keine Teilakzeptanz.
Eine Zurückweisung enthält einen konkreten Fehlerbericht für das Refinement-Prompt.

Stufe 1 — Schema-Validierung (sofern schema.xsd vorhanden):
  Ist der Output wohlgeformt und strukturell korrekt?

Stufe 2 — Elementlisten-Validierung (sofern elements.json vorhanden):
  Sind alle verwendeten Elemente in dieser Version erlaubt?

Mindestens eine der beiden Stufen muss von einem Plugin bereitgestellt werden.
Prosa-Outputs haben keine Struktur → Strukturprüfung entfällt (F12).
"""

from __future__ import annotations

import json
import re

from lxml import etree

from mdal.interfaces.scoring import StructureCheckResult
from mdal.plugins.registry import Plugin, PluginRegistry
from mdal.verification.detector import DetectedOutput, OutputFormat


class StructureChecker:
    """
    Prüft strukturierte Outputs (XML, JSON) gegen Plugin-Schemata.

    Für Prosa-Outputs gibt check() immer passed=True zurück (F12).
    Für strukturierte Outputs ohne passendes Plugin: nur Wohlgeformtheit.
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def check(self, output: str, detected: DetectedOutput) -> StructureCheckResult:
        """
        Prüft den Output anhand des erkannten Formats.

        Prosa → direkt passed.
        XML/JSON → Plugin suchen, dann validieren.
        """
        if detected.format == OutputFormat.PROSE:
            return StructureCheckResult(passed=True)

        if detected.format == OutputFormat.XML:
            return self._check_xml(output, detected)

        if detected.format == OutputFormat.JSON:
            return self._check_json(output, detected)

        return StructureCheckResult(passed=True)

    # ------------------------------------------------------------------
    # XML
    # ------------------------------------------------------------------

    def _check_xml(self, output: str, detected: DetectedOutput) -> StructureCheckResult:
        # Plugin per Namespace suchen
        plugin: Plugin | None = None
        if detected.xml_namespace:
            plugin = self._registry.find_for_namespace(detected.xml_namespace)

        # Stufe 1: XSD-Validierung
        if plugin and plugin.has_schema:
            result = self._validate_xsd(output, plugin)
            if not result.passed:
                return result

        # Stufe 2: Elementlisten-Validierung
        if plugin and plugin.has_elements:
            result = self._validate_elements_xml(output, plugin)
            if not result.passed:
                return result

        # Kein Plugin: nur Wohlgeformtheit prüfen
        if plugin is None:
            return self._check_xml_wellformed(output)

        return StructureCheckResult(passed=True)

    def _validate_xsd(self, xml_text: str, plugin: Plugin) -> StructureCheckResult:
        try:
            schema_doc = etree.parse(str(plugin.schema_path))
            schema     = etree.XMLSchema(schema_doc)
            doc        = etree.fromstring(xml_text.encode("utf-8"))
            if schema.validate(doc):
                return StructureCheckResult(passed=True)
            errors = "; ".join(str(e) for e in schema.error_log)
            return StructureCheckResult(
                passed=False,
                error_report=f"XSD-Validierungsfehler: {errors}",
                failed_at="xsd",
            )
        except etree.XMLSyntaxError as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"XML nicht wohlgeformt: {exc}",
                failed_at="xsd",
            )
        except Exception as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"Schema-Ladefehler ({plugin.plugin_id}): {exc}",
                failed_at="xsd",
            )

    def _validate_elements_xml(self, xml_text: str, plugin: Plugin) -> StructureCheckResult:
        try:
            elements_def = plugin.load_elements()
            allowed:    set[str] = set(elements_def.get("allowed_elements", []))
            required:   set[str] = set(elements_def.get("required_elements", []))
            forbidden:  set[str] = set(elements_def.get("forbidden_elements", []))

            doc  = etree.fromstring(xml_text.encode("utf-8"))
            used: set[str] = {etree.QName(el.tag).localname for el in doc.iter()}

            violations: list[str] = []

            if forbidden:
                found_forbidden = used & forbidden
                if found_forbidden:
                    violations.append(
                        f"Verbotene Elemente gefunden: {sorted(found_forbidden)}"
                    )

            if allowed:
                unknown = used - allowed
                if unknown:
                    violations.append(
                        f"Unbekannte Elemente (nicht in elements.json): {sorted(unknown)}"
                    )

            if required:
                missing = required - used
                if missing:
                    violations.append(
                        f"Pflicht-Elemente fehlen: {sorted(missing)}"
                    )

            if violations:
                return StructureCheckResult(
                    passed=False,
                    error_report="; ".join(violations),
                    failed_at="elements",
                )
            return StructureCheckResult(passed=True)

        except Exception as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"Elementlisten-Validierung fehlgeschlagen: {exc}",
                failed_at="elements",
            )

    @staticmethod
    def _check_xml_wellformed(xml_text: str) -> StructureCheckResult:
        try:
            etree.fromstring(xml_text.encode("utf-8"))
            return StructureCheckResult(passed=True)
        except etree.XMLSyntaxError as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"XML nicht wohlgeformt: {exc}",
                failed_at="xsd",
            )

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _check_json(self, output: str, detected: DetectedOutput) -> StructureCheckResult:
        # JSON ist bereits geparst worden (detect_format hat json.loads aufgerufen)
        # Hier: Plugin für JSON suchen
        json_plugins = self._registry.find_for_format("json")

        # Für den PoC: erstes passendes JSON-Plugin nehmen
        # (Erweiterungspunkt: Schema-matching über $schema-Key oder Content-Analyse)
        plugin: Plugin | None = json_plugins[0] if json_plugins else None

        if plugin and plugin.has_elements:
            return self._validate_elements_json(output, plugin)

        # Keine erweiterte Validierung → wohlgeformt reicht
        return StructureCheckResult(passed=True)

    def _validate_elements_json(self, json_text: str, plugin: Plugin) -> StructureCheckResult:
        try:
            data         = json.loads(json_text)
            elements_def = plugin.load_elements()
            required: set[str] = set(elements_def.get("required_elements", []))
            forbidden: set[str] = set(elements_def.get("forbidden_elements", []))

            if not isinstance(data, dict):
                return StructureCheckResult(passed=True)   # Arrays etc.: kein Key-Check

            top_keys = set(data.keys())
            violations: list[str] = []

            found_forbidden = top_keys & forbidden
            if found_forbidden:
                violations.append(f"Verbotene Keys: {sorted(found_forbidden)}")

            missing_required = required - top_keys
            if missing_required:
                violations.append(f"Pflicht-Keys fehlen: {sorted(missing_required)}")

            if violations:
                return StructureCheckResult(
                    passed=False,
                    error_report="; ".join(violations),
                    failed_at="elements",
                )
            return StructureCheckResult(passed=True)

        except Exception as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"JSON-Elementvalidierung fehlgeschlagen: {exc}",
                failed_at="elements",
            )
