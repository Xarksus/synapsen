"""Zeitquelle — injizierbar, damit die Engine testbar und simulierbar ist.

Der Grund: die Original-Engine ruft an ~20 Stellen `time.time()` und
`datetime.now()` direkt auf. Damit lässt sich kein Verlauf über Tage testen,
ohne wirklich Tage zu warten. Eine injizierte Uhr macht aus dem Zustandsmodell
ein *simulierbares* Modell — man kann 6 Monate Beziehungsverlauf in
Millisekunden durchrechnen.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Unix-Zeitstempel in Sekunden."""
        ...

    def local(self) -> datetime:
        """Lokale Wanduhrzeit (für circadiane Rhythmen)."""
        ...


class SystemClock:
    """Echte Zeit. Der Default im Betrieb."""

    def now(self) -> float:
        return time.time()

    def local(self) -> datetime:
        return datetime.now()


class FakeClock:
    """Steuerbare Zeit für Tests und Simulationen.

    >>> c = FakeClock(start=0.0)
    >>> c.advance(hours=8)
    >>> c.now()
    28800.0
    """

    def __init__(self, start: float = 0.0):
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def local(self) -> datetime:
        return datetime.fromtimestamp(self._t)

    def advance(self, seconds: float = 0.0, minutes: float = 0.0,
                hours: float = 0.0, days: float = 0.0) -> None:
        self._t += seconds + minutes * 60 + hours * 3600 + days * 86400

    def set(self, t: float) -> None:
        self._t = float(t)
