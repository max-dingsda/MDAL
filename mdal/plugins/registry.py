"""
Plugin Registry (F20, NF1, NF2) — folder-structure-based plugin system.

Directory structure:
    {registry_path}/
      bpmn-2.0/
        manifest.json      ← required
        schema.xsd         ← optional (at least one of the two optional files required)
        elements.json      ← optional
      archimate-3/
        manifest.json
        schema.xsd
        elements.json

manifest.json format:
  {
    "plugin_id":    "bpmn-2.0",
    "display_name": "BPMN 2.0",
    "version":      "2.0",
    "info":         "Business Process Model and Notation 2.0",
    "files":        ["schema.xsd", "elements.json"],
    "matches": {                        ← optional, for auto-detection
      "format":    "xml",               ← "xml" | "json"
      "namespace": "http://..."         ← XML namespace or JSON schema URI
    }
  }

The format does not distinguish between community plugins and proprietary
enterprise plugins — the difference lies solely in the storage location (NF1/NF2).
Resolution order: private registry → community library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class PluginError(Exception):
    """Raised for invalid or inconsistent plugin definitions."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PluginMatchRule:
    """Optional auto-detection rule for the plugin."""
    format:    str             # "xml" | "json"
    namespace: str | None = None


@dataclass
class Plugin:
    """A loaded plugin from the registry."""
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
        """Loads elements.json. Raises if not present."""
        if not self.has_elements:
            raise PluginError(f"Plugin '{self.plugin_id}' has no elements.json.")
        return json.loads(self.elements_path.read_text(encoding="utf-8"))

    def __str__(self) -> str:
        return f"{self.display_name} v{self.version} ({self.plugin_id})"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """
    Loads and manages plugins from a folder structure.

    Each subdirectory of the registry path is treated as a potential plugin.
    Folders without manifest.json are ignored.

    Supports multiple registries with priority (private before community).
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}   # plugin_id → Plugin

    def load_from(self, path: str | Path) -> int:
        """
        Loads all plugins from the given directory.
        Already-loaded plugin IDs are not overwritten
        (first registry wins → private plugins take precedence).

        Returns the number of newly loaded plugins.
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
                # Skip invalid plugins, do not abort
                pass

        return loaded

    def get(self, plugin_id: str) -> Plugin | None:
        """Returns the plugin with the given ID or None."""
        return self._plugins.get(plugin_id)

    def find_for_namespace(self, namespace: str) -> Plugin | None:
        """
        Finds the first plugin matching the given XML namespace.
        Resolution order follows load order (dict order).
        """
        for plugin in self._plugins.values():
            if (
                plugin.match_rule
                and plugin.match_rule.namespace == namespace
            ):
                return plugin
        return None

    def find_for_format(self, format_name: str) -> list[Plugin]:
        """Returns all plugins registered for the given format."""
        return [
            p for p in self._plugins.values()
            if p.match_rule and p.match_rule.format == format_name
        ]

    def all_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    def __len__(self) -> int:
        return len(self._plugins)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_plugin(self, base_path: Path, manifest_path: Path) -> Plugin:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PluginError(
                f"Invalid manifest.json in {base_path}: {exc}"
            ) from exc

        for required in ("plugin_id", "display_name", "version", "info", "files"):
            if required not in manifest:
                raise PluginError(
                    f"Required field '{required}' missing in {manifest_path}"
                )

        files: list[str] = manifest["files"]
        has_schema   = "schema.xsd"    in files
        has_elements = "elements.json" in files

        # At least one optional file must be present
        if not has_schema and not has_elements:
            raise PluginError(
                f"Plugin '{manifest['plugin_id']}': "
                f"At least schema.xsd or elements.json is required."
            )

        # Files declared in manifest.files must also exist
        for filename in files:
            if not (base_path / filename).exists():
                raise PluginError(
                    f"Plugin '{manifest['plugin_id']}': "
                    f"Declared file '{filename}' not found in {base_path}."
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
