"""
Plugin Registry (F20, NF1, NF2) — Ordnerstruktur-basiertes Plugin-System.

Verzeichnisstruktur:
    {registry_path}/
      bpmn-2.0/
        manifest.json      ← Pflicht
        schema.xsd         ← optional (mind. eine der beiden optional. Dateien)
        elements.json      ← optional
      archimate-3/
        manifest.json
        schema.xsd
        elements.json

manifest.json-Format:
  {
    "plugin_id":    "bpmn-2.0",
    "display_name": "BPMN 2.0",
    "version":      "2.0",
    "info":         "Business Process Model and Notation 2.0",
    "files":        ["schema.xsd", "elements.json"],
    "matches": {                        ← optional, für Auto-Erkennung
      "format":    "xml",               ← "xml" | "json"
      "namespace": "http://..."         ← XML-Namespace oder JSON-Schema-URI
    }
  }

Das Format unterscheidet nicht zwischen Community-Plugins und proprietären
Unternehmens-Plugins — der Unterschied liegt ausschließlich im Ablageort (NF1/NF2).
Auflösungsreihenfolge: private Registry → Community-Bibliothek.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class PluginError(Exception):
    """Wird geworfen bei ungültigen oder inkonsistenten Plugin-Definitionen."""


# ---------------------------------------------------------------------------
# Datenmodelle
# ---------------------------------------------------------------------------

@dataclass
class PluginMatchRule:
    """Optionale Auto-Erkennungsregel für das Plugin."""
    format:    str             # "xml" | "json"
    namespace: str | None = None


@dataclass
class Plugin:
    """Ein geladenes Plugin aus der Registry."""
    plugin_id:    str
    display_name: str
    version:      str
    info:         str
    base_path:    Path
    has_schema:   bool = False
    has_elements: bool = False
    match_rule:   PluginMatchRule | None = None

    @property
    def schema_path(self) -> Path:
        return self.base_path / "schema.xsd"

    @property
    def elements_path(self) -> Path:
        return self.base_path / "elements.json"

    def load_elements(self) -> dict:
        """Lädt elements.json. Wirft wenn nicht vorhanden."""
        if not self.has_elements:
            raise PluginError(f"Plugin '{self.plugin_id}' hat keine elements.json.")
        return json.loads(self.elements_path.read_text(encoding="utf-8"))

    def __str__(self) -> str:
        return f"{self.display_name} v{self.version} ({self.plugin_id})"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """
    Lädt und verwaltet Plugins aus einer Ordnerstruktur.

    Jeder Unterordner des Registry-Verzeichnisses wird als mögliches Plugin
    betrachtet. Ordner ohne manifest.json werden ignoriert.

    Unterstützt mehrere Registries mit Priorität (private vor community).
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}   # plugin_id → Plugin

    def load_from(self, path: str | Path) -> int:
        """
        Lädt alle Plugins aus dem gegebenen Verzeichnis.
        Bereits geladene Plugin-IDs werden nicht überschrieben
        (erste Registry gewinnt → private Plugins haben Vorrang).

        Gibt die Anzahl neu geladener Plugins zurück.
        """
        base = Path(path)
        if not base.is_dir():
            return 0

        loaded = 0
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                plugin = self._load_plugin(entry, manifest_path)
                if plugin.plugin_id not in self._plugins:
                    self._plugins[plugin.plugin_id] = plugin
                    loaded += 1
            except PluginError:
                # Ungültige Plugins überspringen, nicht abbrechen
                pass

        return loaded

    def get(self, plugin_id: str) -> Plugin | None:
        """Gibt das Plugin mit der gegebenen ID zurück oder None."""
        return self._plugins.get(plugin_id)

    def find_for_namespace(self, namespace: str) -> Plugin | None:
        """
        Sucht das erste Plugin das zum gegebenen XML-Namespace passt.
        Auflösungsreihenfolge entspricht der Ladereihenfolge (dict-Reihenfolge).
        """
        for plugin in self._plugins.values():
            if (
                plugin.match_rule
                and plugin.match_rule.namespace == namespace
            ):
                return plugin
        return None

    def find_for_format(self, format_name: str) -> list[Plugin]:
        """Gibt alle Plugins zurück die für das gegebene Format registriert sind."""
        return [
            p for p in self._plugins.values()
            if p.match_rule and p.match_rule.format == format_name
        ]

    def all_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    # ------------------------------------------------------------------
    # Internes
    # ------------------------------------------------------------------

    def _load_plugin(self, base_path: Path, manifest_path: Path) -> Plugin:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginError(
                f"Ungültige manifest.json in {base_path}: {exc}"
            ) from exc

        for required in ("plugin_id", "display_name", "version", "info", "files"):
            if required not in manifest:
                raise PluginError(
                    f"Pflichtfeld '{required}' fehlt in {manifest_path}"
                )

        files: list[str] = manifest["files"]
        has_schema   = "schema.xsd"    in files
        has_elements = "elements.json" in files

        # Mindestens eine optionale Datei muss vorhanden sein
        if not has_schema and not has_elements:
            raise PluginError(
                f"Plugin '{manifest['plugin_id']}': "
                f"Mindestens schema.xsd oder elements.json erforderlich."
            )

        # Dateien die in manifest.files deklariert sind, müssen auch existieren
        for filename in files:
            if not (base_path / filename).exists():
                raise PluginError(
                    f"Plugin '{manifest['plugin_id']}': "
                    f"Deklarierte Datei '{filename}' nicht gefunden in {base_path}."
                )

        match_rule = None
        if "matches" in manifest:
            match_rule = PluginMatchRule(
                format=manifest["matches"].get("format", "xml"),
                namespace=manifest["matches"].get("namespace"),
            )

        return Plugin(
            plugin_id=manifest["plugin_id"],
            display_name=manifest["display_name"],
            version=manifest["version"],
            info=manifest["info"],
            base_path=base_path,
            has_schema=has_schema,
            has_elements=has_elements,
            match_rule=match_rule,
        )
