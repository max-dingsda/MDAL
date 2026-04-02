"""Unit-Tests für Strukturprüfung, Format-Erkennung und Plugin Registry."""

import json
from pathlib import Path

import pytest
from lxml import etree

from mdal.plugins.registry import Plugin, PluginError, PluginRegistry
from mdal.verification.detector import OutputFormat, detect_format
from mdal.verification.structure import StructureChecker


# ---------------------------------------------------------------------------
# Format-Erkennung
# ---------------------------------------------------------------------------

class TestDetectFormat:
    def test_detects_json_object(self):
        r = detect_format('{"key": "value"}')
        assert r.format == OutputFormat.JSON

    def test_detects_json_array(self):
        r = detect_format('[1, 2, 3]')
        assert r.format == OutputFormat.JSON

    def test_detects_xml(self):
        r = detect_format('<root><child/></root>')
        assert r.format == OutputFormat.XML

    def test_extracts_xml_namespace(self):
        xml = '<root xmlns="http://example.com/ns"><child/></root>'
        r = detect_format(xml)
        assert r.xml_namespace == "http://example.com/ns"

    def test_extracts_xml_root_tag(self):
        r = detect_format('<Model xmlns="http://example.com/ns"/>')
        assert r.xml_root_tag == "Model"

    def test_detects_prose(self):
        r = detect_format("Das ist normaler Text ohne Struktur.")
        assert r.format == OutputFormat.PROSE

    def test_empty_string_is_prose(self):
        r = detect_format("")
        assert r.format == OutputFormat.PROSE

    def test_invalid_json_is_prose(self):
        r = detect_format("{kein: json}")
        assert r.format == OutputFormat.PROSE

    def test_invalid_xml_is_prose(self):
        r = detect_format("<unclosed>")
        assert r.format == OutputFormat.PROSE

    def test_prose_is_not_structured(self):
        r = detect_format("Plain text.")
        assert r.is_structured() is False

    def test_json_is_structured(self):
        r = detect_format('{"a": 1}')
        assert r.is_structured() is True

    def test_xml_is_structured(self):
        r = detect_format('<a/>')
        assert r.is_structured() is True


# ---------------------------------------------------------------------------
# Plugin Registry
# ---------------------------------------------------------------------------

def make_plugin_dir(
    base: Path,
    plugin_id: str,
    files: list[str],
    matches: dict | None = None,
    xsd_content: str | None = None,
    elements_content: dict | None = None,
) -> Path:
    d = base / plugin_id
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "plugin_id":    plugin_id,
        "display_name": plugin_id.upper(),
        "version":      "1.0",
        "info":         "Test plugin",
        "files":        files,
    }
    if matches:
        manifest["matches"] = matches
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if "schema.xsd" in files and xsd_content:
        (d / "schema.xsd").write_text(xsd_content, encoding="utf-8")
    if "elements.json" in files and elements_content:
        (d / "elements.json").write_text(
            json.dumps(elements_content), encoding="utf-8"
        )
    return d


SIMPLE_XSD = """\
<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="root">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="child" type="xs:string" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""


class TestPluginRegistry:
    def test_loads_plugin_with_schema(self, tmp_path):
        make_plugin_dir(tmp_path, "test-plugin", ["schema.xsd"], xsd_content=SIMPLE_XSD)
        reg = PluginRegistry()
        count = reg.load_from(tmp_path)
        assert count == 1

    def test_loads_plugin_with_elements_only(self, tmp_path):
        make_plugin_dir(tmp_path, "test-plugin", ["elements.json"],
                        elements_content={"allowed_elements": ["root"]})
        reg = PluginRegistry()
        assert reg.load_from(tmp_path) == 1

    def test_ignores_folder_without_manifest(self, tmp_path):
        (tmp_path / "no-manifest").mkdir()
        reg = PluginRegistry()
        assert reg.load_from(tmp_path) == 0

    def test_raises_on_plugin_with_no_optional_files(self, tmp_path):
        d = tmp_path / "empty-plugin"
        d.mkdir()
        manifest = {
            "plugin_id": "empty", "display_name": "E", "version": "1",
            "info": "x", "files": [],
        }
        (d / "manifest.json").write_text(json.dumps(manifest))
        reg = PluginRegistry()
        reg.load_from(tmp_path)   # Soll den Fehler schlucken, nicht crashen
        assert reg.get("empty") is None

    def test_get_returns_plugin(self, tmp_path):
        make_plugin_dir(tmp_path, "my-plugin", ["schema.xsd"], xsd_content=SIMPLE_XSD)
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        assert reg.get("my-plugin") is not None

    def test_get_returns_none_for_unknown(self, tmp_path):
        reg = PluginRegistry()
        assert reg.get("nonexistent") is None

    def test_find_for_namespace(self, tmp_path):
        make_plugin_dir(
            tmp_path, "ns-plugin", ["schema.xsd"],
            xsd_content=SIMPLE_XSD,
            matches={"format": "xml", "namespace": "http://example.com/ns"},
        )
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        plugin = reg.find_for_namespace("http://example.com/ns")
        assert plugin is not None
        assert plugin.plugin_id == "ns-plugin"

    def test_find_for_namespace_returns_none_when_no_match(self, tmp_path):
        reg = PluginRegistry()
        assert reg.find_for_namespace("http://unknown.com") is None

    def test_private_plugin_wins_over_community(self, tmp_path):
        """Erste geladene Registry hat Vorrang — private vor community."""
        private_dir   = tmp_path / "private"
        community_dir = tmp_path / "community"
        private_dir.mkdir()
        community_dir.mkdir()
        make_plugin_dir(private_dir, "same-id", ["schema.xsd"], xsd_content=SIMPLE_XSD)
        make_plugin_dir(community_dir, "same-id", ["elements.json"],
                        elements_content={"allowed_elements": ["x"]})
        reg = PluginRegistry()
        reg.load_from(private_dir)
        reg.load_from(community_dir)
        plugin = reg.get("same-id")
        assert plugin.has_schema is True      # privates Plugin
        assert plugin.has_elements is False

    def test_len_returns_plugin_count(self, tmp_path):
        make_plugin_dir(tmp_path, "p1", ["schema.xsd"], xsd_content=SIMPLE_XSD)
        make_plugin_dir(tmp_path, "p2", ["schema.xsd"], xsd_content=SIMPLE_XSD)
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        assert len(reg) == 2


# ---------------------------------------------------------------------------
# Strukturprüfung — XML
# ---------------------------------------------------------------------------

VALID_XML   = "<root><child>text</child></root>"
INVALID_XML = "<root><unclosed>"

ELEMENTS_DEF = {
    "allowed_elements":  ["root", "child"],
    "required_elements": ["root"],
    "forbidden_elements": ["forbidden"],
}


class TestStructureCheckerXML:
    def test_prose_always_passes(self, tmp_path):
        reg = PluginRegistry()
        checker = StructureChecker(reg)
        detected = detect_format("normaler Text")
        result = checker.check("normaler Text", detected)
        assert result.passed is True

    def test_wellformed_xml_without_plugin_passes(self, tmp_path):
        reg = PluginRegistry()
        checker = StructureChecker(reg)
        detected = detect_format(VALID_XML)
        assert checker.check(VALID_XML, detected).passed is True

    def test_malformed_xml_without_plugin_fails(self, tmp_path):
        reg = PluginRegistry()
        checker = StructureChecker(reg)
        # force XML detection by mocking detected format
        from mdal.verification.detector import DetectedOutput, OutputFormat
        detected = DetectedOutput(format=OutputFormat.XML)
        result = checker.check(INVALID_XML, detected)
        assert result.passed is False

    def test_valid_xml_passes_xsd(self, tmp_path):
        make_plugin_dir(
            tmp_path, "test", ["schema.xsd"],
            xsd_content=SIMPLE_XSD,
            matches={"format": "xml", "namespace": ""},
        )
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        checker = StructureChecker(reg)
        # without namespace matching, falls back to wellformed check
        detected = detect_format(VALID_XML)
        result = checker.check(VALID_XML, detected)
        assert result.passed is True

    def test_elements_validation_detects_forbidden(self, tmp_path):
        make_plugin_dir(
            tmp_path, "test", ["elements.json"],
            elements_content={
                "allowed_elements": ["root", "child", "forbidden"],
                "forbidden_elements": ["forbidden"],
            },
            matches={"format": "xml", "namespace": "http://test.com"},
        )
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        checker = StructureChecker(reg)
        xml = '<root xmlns="http://test.com"><forbidden/></root>'
        detected = detect_format(xml)
        result = checker.check(xml, detected)
        assert result.passed is False
        assert "forbidden" in result.error_report.lower()
        assert result.failed_at == "elements"

    def test_elements_validation_detects_missing_required(self, tmp_path):
        make_plugin_dir(
            tmp_path, "test", ["elements.json"],
            elements_content={
                "allowed_elements": ["root", "required-child"],
                "required_elements": ["required-child"],
            },
            matches={"format": "xml", "namespace": "http://test.com"},
        )
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        checker = StructureChecker(reg)
        xml = '<root xmlns="http://test.com"/>'
        detected = detect_format(xml)
        result = checker.check(xml, detected)
        assert result.passed is False
        assert result.failed_at == "elements"


# ---------------------------------------------------------------------------
# Strukturprüfung — JSON
# ---------------------------------------------------------------------------

class TestStructureCheckerJSON:
    def test_valid_json_without_plugin_passes(self, tmp_path):
        reg = PluginRegistry()
        checker = StructureChecker(reg)
        detected = detect_format('{"key": "value"}')
        assert checker.check('{"key": "value"}', detected).passed is True

    def test_json_elements_required_key_missing_fails(self, tmp_path):
        make_plugin_dir(
            tmp_path, "json-plugin", ["elements.json"],
            elements_content={"required_elements": ["required_key"]},
            matches={"format": "json"},
        )
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        checker = StructureChecker(reg)
        detected = detect_format('{"other_key": "value"}')
        result = checker.check('{"other_key": "value"}', detected)
        assert result.passed is False
        assert "required_key" in result.error_report

    def test_json_elements_forbidden_key_fails(self, tmp_path):
        make_plugin_dir(
            tmp_path, "json-plugin", ["elements.json"],
            elements_content={"forbidden_elements": ["secret"]},
            matches={"format": "json"},
        )
        reg = PluginRegistry()
        reg.load_from(tmp_path)
        checker = StructureChecker(reg)
        detected = detect_format('{"secret": "value"}')
        result = checker.check('{"secret": "value"}', detected)
        assert result.passed is False
