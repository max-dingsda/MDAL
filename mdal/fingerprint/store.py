"""
Fingerprint Store — versioned storage with rollback (F7, F3).

Directory structure per language:
    {base_path}/
      de/
        current      ← text file with the active version number ("3")
        v1.json
        v2.json
        v3.json
      en/
        current
        v1.json

The format is deliberately simple: one JSON file per version, one pointer to
the active version.

Locking strategy (CR-Finding #2):
  Write operations (save, rollback) hold an exclusive FileLock on a
  language-specific lock file ({base}/.{language}.lock).
  load_current holds the same lock during reading to close the TOCTOU race
  between _read_pointer() and load_version().
  Simple reads of a fixed version (load_version, list_versions) do not
  require a lock — they access immutable files.
"""

from __future__ import annotations

from pathlib import Path

from filelock import FileLock

from mdal.fingerprint.models import Fingerprint


class FingerprintStoreError(Exception):
    """Base for all store-specific errors."""


class FingerprintNotFoundError(FingerprintStoreError):
    """No fingerprint available for this language / version."""


class FingerprintStore:
    """
    Versioned, filesystem-based fingerprint store.

    Each language has its own subdirectory.
    Each version is a standalone JSON file.
    A pointer file (`current`) indicates the active version.

    Rollback (F7): set the pointer to any earlier version.

    Thread and process safety is ensured via language-specific FileLocks.
    Concurrent HTTP requests read consistent pointer states.
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, fingerprint: Fingerprint) -> int:
        """
        Saves a fingerprint as a new version.

        The version number is assigned automatically (last + 1).
        The new fingerprint immediately becomes the active version.

        Returns the assigned version number.
        """
        lang_dir = self._lang_dir(fingerprint.language)
        lang_dir.mkdir(parents=True, exist_ok=True)

        with FileLock(self._lock_path(fingerprint.language)):
            next_version = self._next_version(fingerprint.language)
            versioned = fingerprint.model_copy(update={"version": next_version})

            version_file = lang_dir / f"v{next_version}.json"
            version_file.write_text(versioned.to_json(), encoding="utf-8")

            self._write_pointer(fingerprint.language, next_version)
            return next_version

    def rollback(self, language: str, version: int) -> None:
        """
        Rolls back the active fingerprint to an earlier version (F7).

        Raises FingerprintNotFoundError if the version does not exist.
        """
        with FileLock(self._lock_path(language)):
            if not self._version_file(language, version).exists():
                raise FingerprintNotFoundError(
                    f"Fingerprint version {version} for language '{language}' not found."
                )
            self._write_pointer(language, version)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_current(self, language: str) -> Fingerprint:
        """
        Loads the currently active fingerprint for the given language.

        Holds the lock for the entire pointer-read + version-load sequence
        to avoid the TOCTOU race.

        Raises FingerprintNotFoundError if no fingerprint is available.
        """
        with FileLock(self._lock_path(language)):
            version = self._read_pointer(language)
            return self.load_version(language, version)

    def load_version(self, language: str, version: int) -> Fingerprint:
        """Loads a specific fingerprint version."""
        path = self._version_file(language, version)
        if not path.exists():
            raise FingerprintNotFoundError(
                f"Fingerprint v{version} for language '{language}' not found "
                f"({path})"
            )
        return Fingerprint.from_json(path.read_text(encoding="utf-8"))

    def list_versions(self, language: str) -> list[int]:
        """
        Returns all available version numbers for a language,
        sorted in ascending order.
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
        """Returns the active version number, or None if no fingerprint exists."""
        pointer = self._pointer_file(language)
        if not pointer.exists():
            return None
        return int(pointer.read_text(encoding="utf-8").strip())

    def has_fingerprint(self, language: str) -> bool:
        """Checks whether an active fingerprint exists for the language."""
        return self.current_version(language) is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _lang_dir(self, language: str) -> Path:
        return self._base / language

    def _lock_path(self, language: str) -> Path:
        """Lock file lives in the base directory, one per language."""
        return self._base / f".{language}.lock"

    def _version_file(self, language: str, version: int) -> Path:
        return self._lang_dir(language) / f"v{version}.json"

    def _pointer_file(self, language: str) -> Path:
        return self._lang_dir(language) / "current"

    def _read_pointer(self, language: str) -> int:
        pointer = self._pointer_file(language)
        if not pointer.exists():
            raise FingerprintNotFoundError(
                f"No active fingerprint for language '{language}'. "
                f"Run the trainer to create one."
            )
        return int(pointer.read_text(encoding="utf-8").strip())

    def _write_pointer(self, language: str, version: int) -> None:
        self._pointer_file(language).write_text(str(version), encoding="utf-8")

    def _next_version(self, language: str) -> int:
        versions = self.list_versions(language)
        return (max(versions) + 1) if versions else 1
