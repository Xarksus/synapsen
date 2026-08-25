"""Zustands-Persistenz — austauschbar, und gegen die üblichen Rennen gesichert.

Warum das eine eigene Schicht ist: In KIRA schreiben zwei Prozesse dieselbe
Datei (`hormones.json`) — die EmotionEngine und `kira_core_state.py`. Der
Kommentar im Original sagt es selbst: "core_state darf NICHT die ganze Datei
überschreiben — sonst friert es den Hormon-Block ein und kämpft gegen den
Decay".

`JsonStore` löst das zweistufig:

* **Feldweiser Merge.** Ein Schreiber überträgt nur die Schlüssel, die er
  besitzt. Fremde Felder bleiben unangetastet.
* **Dateisperre um Lesen und Schreiben.** Ohne sie ist selbst der Merge ein
  ungesichertes read-modify-write: zwei Prozesse lesen denselben Stand und
  der zweite überschreibt den ersten.

Was das *nicht* löst: zwei Engines, die beide `hormones` besitzen. Sie
schreiben dieselben Schlüssel, und der letzte gewinnt — kein Datenverlust an
fremden Feldern, aber eben auch keine Verschmelzung zweier Zustände. Dafür
gibt es `owner`: mit gesetztem Kennzeichen erkennt eine Engine, dass ein
anderer Schreiber am Zug war, und lädt dessen Stand nach, statt ihren eigenen
darüberzulegen. Ein Zustand gehört immer genau einem Prozess.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

try:                                     # POSIX
    import fcntl
except ImportError:                      # Windows
    fcntl = None                         # type: ignore[assignment]


class StateStore(Protocol):
    def load(self) -> dict: ...
    def save(self, patch: dict) -> None: ...


class MemoryStore:
    """Kein Dateisystem. Für Tests, Simulationen und kurzlebige Agenten."""

    def __init__(self, initial: dict | None = None):
        self._data: dict = dict(initial or {})

    def load(self) -> dict:
        return dict(self._data)

    def save(self, patch: dict) -> None:
        self._data.update(patch)


class JsonStore:
    """Atomarer, feldweiser Merge-Write auf eine JSON-Datei.

    `save()` bekommt einen *Patch*, nicht den Vollzustand: es liest frisch,
    mischt nur die übergebenen Schlüssel ein und schreibt über eine temporäre
    Datei plus `os.replace` (atomar). Damit können mehrere Schreiber
    nebeneinander existieren, ohne sich gegenseitig zu überschreiben.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @contextmanager
    def _locked(self):
        """Sperrt Lesen und Schreiben gegeneinander.

        Ohne diese Klammer ist der Merge ein ungesichertes read-modify-write:
        zwei Prozesse lesen denselben Stand, und der zweite überschreibt den
        ersten. Auf Systemen ohne `fcntl` fällt die Sperre weg — der Schreib-
        vorgang selbst bleibt durch `os.replace` atomar.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl is None:
            yield
            return
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        with open(lock, "a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def save(self, patch: dict) -> None:
        with self._locked():
            current = self.load()
            current.update(patch)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(current, fh, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
