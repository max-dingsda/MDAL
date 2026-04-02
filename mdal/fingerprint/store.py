"""
Fingerprint Store — versionierte Speicherung mit Rollback (F7, F3).

Verzeichnisstruktur pro Sprache:
    {base_path}/
      de/
        current      ← Textdatei mit aktiver Versionsnummer ("3")
        v1.json
        v2.json
        v3.json
      en/
        current
        v1.json

Das Format ist bewusst einfach: eine JSON-Datei pro Version, ein Pointer auf
die aktive Version. Kein Lock-Mechanismus — der Store ist nicht für
gleichzeitige Schreibzugriffe ausgelegt (v1 single-instance, NF-Scope).
"""

from __future__ import annotations

from pathlib import Path

from mdal.fingerprint.models import Fingerprint


class FingerprintStoreError(Exception):
    """Basis für alle Store-spezifischen Fehler."""


class FingerprintNotFoundError(FingerprintStoreError):
    """Kein Fingerprint für diese Sprache / Version vorhanden."""


class FingerprintStore:
    """
    Versionierter, dateisystembasierter Fingerprint-Store.

    Jede Sprache hat ihr eigenes Unterverzeichnis.
    Jede Version ist eine eigenständige JSON-Datei.
    Die aktive Version zeigt eine Pointer-Datei (`current`).

    Rollback (F7): Pointer auf beliebige frühere Version setzen.
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path)

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------

    def save(self, fingerprint: Fingerprint) -> int:
        """
        Speichert einen Fingerprint als neue Version.

        Die Versionsnummer wird automatisch vergeben (letzte + 1).
        Der neue Fingerprint wird sofort zur aktiven Version.

        Gibt die vergebene Versionsnummer zurück.
        """
        lang_dir = self._lang_dir(fingerprint.language)
        lang_dir.mkdir(parents=True, exist_ok=True)

        next_version = self._next_version(fingerprint.language)
        versioned = fingerprint.model_copy(update={"version": next_version})

        version_file = lang_dir / f"v{next_version}.json"
        version_file.write_text(versioned.to_json(), encoding="utf-8")

        self._write_pointer(fingerprint.language, next_version)
        return next_version

    def rollback(self, language: str, version: int) -> None:
        """
        Setzt den aktiven Fingerprint auf eine frühere Version zurück (F7).

        Wirft FingerprintNotFoundError wenn die Version nicht existiert.
        """
        if not self._version_file(language, version).exists():
            raise FingerprintNotFoundError(
                f"Fingerprint-Version {version} für Sprache '{language}' nicht gefunden."
            )
        self._write_pointer(language, version)

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    def load_current(self, language: str) -> Fingerprint:
        """
        Lädt den aktuell aktiven Fingerprint für die gegebene Sprache.

        Wirft FingerprintNotFoundError wenn kein Fingerprint vorhanden.
        """
        version = self._read_pointer(language)
        return self.load_version(language, version)

    def load_version(self, language: str, version: int) -> Fingerprint:
        """Lädt eine spezifische Fingerprint-Version."""
        path = self._version_file(language, version)
        if not path.exists():
            raise FingerprintNotFoundError(
                f"Fingerprint v{version} für Sprache '{language}' nicht gefunden "
                f"({path})"
            )
        return Fingerprint.from_json(path.read_text(encoding="utf-8"))

    def list_versions(self, language: str) -> list[int]:
        """
        Gibt alle vorhandenen Versionsnummern für eine Sprache zurück,
        aufsteigend sortiert.
        """
        lang_dir = self._lang_dir(language)
        if not lang_dir.exists():
            return []
        versions = [
            int(f.stem[1:])
            for f in lang_dir.glob("v*.json")
            if f.stem[1:].isdigit()
        ]
        return sorted(versions)

    def current_version(self, language: str) -> int | None:
        """Gibt die aktive Versionsnummer zurück, oder None wenn kein Fingerprint."""
        pointer = self._pointer_file(language)
        if not pointer.exists():
            return None
        return int(pointer.read_text(encoding="utf-8").strip())

    def has_fingerprint(self, language: str) -> bool:
        """Prüft ob ein aktiver Fingerprint für die Sprache vorhanden ist."""
        return self.current_version(language) is not None

    # ------------------------------------------------------------------
    # Internes
    # ------------------------------------------------------------------

    def _lang_dir(self, language: str) -> Path:
        return self._base / language

    def _version_file(self, language: str, version: int) -> Path:
        return self._lang_dir(language) / f"v{version}.json"

    def _pointer_file(self, language: str) -> Path:
        return self._lang_dir(language) / "current"

    def _read_pointer(self, language: str) -> int:
        pointer = self._pointer_file(language)
        if not pointer.exists():
            raise FingerprintNotFoundError(
                f"Kein aktiver Fingerprint für Sprache '{language}'. "
                f"Trainer ausführen um einen Fingerprint zu erstellen."
            )
        return int(pointer.read_text(encoding="utf-8").strip())

    def _write_pointer(self, language: str, version: int) -> None:
        self._pointer_file(language).write_text(str(version), encoding="utf-8")

    def _next_version(self, language: str) -> int:
        versions = self.list_versions(language)
        return (max(versions) + 1) if versions else 1
