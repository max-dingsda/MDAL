"""
Structure check (F2) — two-stage validation of structured outputs.

Result is binary: passed or not. No partial acceptance.
A rejection includes a concrete error report for the refinement prompt.

Stage 1 — Schema validation (if schema.xsd is present):
  Is the output well-formed and structurally correct?

Stage 2 — Element list validation (if elements.json is present):
  Are all used elements permitted in this version?

At least one of the two stages must be provided by a plugin.
Prose outputs have no structure → structure check is skipped (F12).
"""

from __future__ import annotations

import json
import logging
import re

from lxml import etree

from mdal.interfaces.scoring import StructureCheckResult
from mdal.plugins.registry import Plugin, PluginRegistry
from mdal.verification.detector import DetectedOutput, OutputFormat, extract_code

logger = logging.getLogger(__name__)


class StructureChecker:
    """
    Checks structured outputs (XML, JSON) against plugin schemas.

    For prose outputs, check() always returns passed=True (F12).
    For structured outputs without a matching plugin: well-formedness only.
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def check(self, output: str, detected: DetectedOutput) -> StructureCheckResult:
        """
        Checks the output based on the detected format.

        Prose → directly passed.
        XML/JSON → find plugin, then validate.
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
        # Look up plugin by namespace
        plugin: Plugin | None = None
        namespace = detected.xml_namespace
        
        clean_xml = extract_code(output)
        # Fallback: Extract namespace manually via lxml if detector missed it
        if not namespace and clean_xml:
            try:
                root = etree.fromstring(clean_xml.encode("utf-8"))
                namespace = root.nsmap.get(root.prefix) if root.prefix else root.nsmap.get(None)
            except Exception:
                pass

        if namespace:
            plugin = self._registry.find_for_namespace(namespace)
            if plugin:
                logger.info("Found XML plugin '%s' for namespace '%s'", plugin.plugin_id, namespace)
            else:
                logger.warning("No XML plugin found for namespace '%s'", namespace)

        # Stage 1: XSD validation
        if plugin and plugin.has_schema:
            result = self._validate_xsd(output, plugin)
            if not result.passed:
                return result

        # Stage 2: Element list validation
        if plugin and plugin.has_elements:
            result = self._validate_elements_xml(output, plugin)
            if not result.passed:
                return result

        # No plugin: check well-formedness only
        if plugin is None:
            return self._check_xml_wellformed(output)

        return StructureCheckResult(passed=True)

    def _validate_xsd(self, xml_text: str, plugin: Plugin) -> StructureCheckResult:
        clean_xml = extract_code(xml_text)
        try:
            schema_doc = etree.parse(str(plugin.schema_path))
            schema     = etree.XMLSchema(schema_doc)
            doc        = etree.fromstring(clean_xml.encode("utf-8"))
            if schema.validate(doc):
                return StructureCheckResult(passed=True)
            errors = "; ".join(str(e) for e in schema.error_log)
            return StructureCheckResult(
                passed=False,
                error_report=f"XSD validation error: {errors}",
                failed_at="xsd",
            )
        except etree.XMLSyntaxError as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"XML not well-formed: {exc}",
                failed_at="xsd",
            )
        except Exception as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"Schema load error ({plugin.plugin_id}): {exc}",
                failed_at="xsd",
            )

    def _validate_elements_xml(self, xml_text: str, plugin: Plugin) -> StructureCheckResult:
        clean_xml = extract_code(xml_text)
        try:
            elements_def = plugin.load_elements()
            allowed:    set[str] = set(elements_def.get("allowed_elements", []))
            required:   set[str] = set(elements_def.get("required_elements", []))
            forbidden:  set[str] = set(elements_def.get("forbidden_elements", []))

            doc  = etree.fromstring(clean_xml.encode("utf-8"))
            used: set[str] = {etree.QName(el.tag).localname for el in doc.iter()}

            violations: list[str] = []

            if forbidden:
                found_forbidden = used & forbidden
                if found_forbidden:
                    violations.append(
                        f"Forbidden elements found: {sorted(found_forbidden)}"
                    )

            if allowed:
                unknown = used - allowed
                if unknown:
                    violations.append(
                        f"Unknown elements (not in elements.json): {sorted(unknown)}"
                    )

            if required:
                missing = required - used
                if missing:
                    violations.append(
                        f"Required elements missing: {sorted(missing)}"
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
                error_report=f"Element list validation failed: {exc}",
                failed_at="elements",
            )

    @staticmethod
    def _check_xml_wellformed(xml_text: str) -> StructureCheckResult:
        clean_xml = extract_code(xml_text)
        try:
            etree.fromstring(clean_xml.encode("utf-8"))
            return StructureCheckResult(passed=True)
        except etree.XMLSyntaxError as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"XML not well-formed: {exc}",
                failed_at="xsd",
            )

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _check_json(self, output: str, detected: DetectedOutput) -> StructureCheckResult:
        # JSON was already parsed (detect_format called json.loads)
        # Here: find a plugin for JSON
        json_plugins = self._registry.find_for_format("json")

        # For the PoC: use the first matching JSON plugin
        # (extension point: schema matching via $schema key or content analysis)
        plugin: Plugin | None = json_plugins[0] if json_plugins else None

        if plugin and plugin.has_elements:
            return self._validate_elements_json(output, plugin)

        # No extended validation → but well-formedness must still be checked
        clean_json = extract_code(output)
        try:
            json.loads(clean_json)
        except json.JSONDecodeError as exc:
            return StructureCheckResult(
                passed=False,
                error_report=f"JSON not well-formed: {exc}",
                failed_at="json_parsing"
            )
        return StructureCheckResult(passed=True)

    def _validate_elements_json(self, json_text: str, plugin: Plugin) -> StructureCheckResult:
        clean_json = extract_code(json_text)
        try:
            data         = json.loads(clean_json)
            elements_def = plugin.load_elements()
            required: set[str] = set(elements_def.get("required_elements", []))
            forbidden: set[str] = set(elements_def.get("forbidden_elements", []))

            if not isinstance(data, dict):
                return StructureCheckResult(passed=True)   # Arrays etc.: no key check

            top_keys = set(data.keys())
            violations: list[str] = []

            found_forbidden = top_keys & forbidden
            if found_forbidden:
                violations.append(f"Forbidden keys: {sorted(found_forbidden)}")

            missing_required = required - top_keys
            if missing_required:
                violations.append(f"Required keys missing: {sorted(missing_required)}")

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
                error_report=f"JSON element validation failed: {exc}",
                failed_at="elements",
            )
