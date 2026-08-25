"""Ereignis-Journal und Stimmungs-Bias aus der Vergangenheit.

Hier sitzt die wichtigste Korrektur gegenüber der Ursprungsfassung.

Das Problem im Original
-----------------------
`inject()` protokolliert bei jedem Aufruf, wenn `cortisol < 15 and dopamine > 65`
gilt, ein Ereignis `ruhig_positiv` mit Schwere +2.0. Diese Bedingung ist in
einem entspannten Zustand aber *dauerhaft* wahr — also wird sie bei praktisch
jedem Aufruf erneut geschrieben.

In KIRAs echter Datenbank: 36.588 von 36.649 Einträgen (99,8 %) sind
`ruhig_positiv`. Im 7-Tage-Fenster summieren sich daraus 1.672 Punkte
positiver Schwere.

`_apply_bias_from_history()` bildet `net = neg_sum - pos_sum` und setzt
    baseline_cortisol  = max(0, 20 + net*0.8)   ->  0.0
    baseline_serotonin = max(0, 60 - net*0.8)   ->  1.397,6
Die Serotonin-Baseline landet also am Sicherheits-Ceiling (150) statt bei 60,
die Cortisol-Baseline bei 0 statt 20. Der Zerfall zieht die Botenstoffe dann
*dauerhaft* dorthin. Ergebnis: ein Agent, der strukturell nicht mehr gestresst
sein kann und permanent "RUHIG" meldet.

Die Lösung
----------
1. **Entprellung** (`min_interval`): Ein Ereignistyp wird pro Zeitfenster nur
   einmal geschrieben. Ein Dauerzustand ist ein Zustand, kein Ereignisstrom.
2. **Normalisierter Bias**: Der Bias wird über den *gewichteten Mittelwert*
   der Schweren gebildet, nicht über die Summe. Damit kann die schiere Anzahl
   von Einträgen das Ergebnis nicht mehr dominieren.
3. **Begrenzter Ausschlag** (`max_shift`): Die Historie darf eine Baseline
   nur um einen definierten Betrag verschieben — nie ins Pathologische.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol


@dataclass
class Event:
    timestamp: str
    kind: str
    context: str
    severity: float
    hormones: dict


class Journal(Protocol):
    def write(self, event: Event) -> None: ...
    def since(self, iso_timestamp: str) -> list[tuple[str, float]]: ...


class NullJournal:
    """Kein Protokoll. Für zustandslose oder kurzlebige Agenten."""

    def write(self, event: Event) -> None:
        return None

    def since(self, iso_timestamp: str) -> list[tuple[str, float]]:
        return []


class MemoryJournal:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def write(self, event: Event) -> None:
        self.events.append(event)

    def since(self, iso_timestamp: str) -> list[tuple[str, float]]:
        return [(e.timestamp, e.severity) for e in self.events
                if e.timestamp >= iso_timestamp]


_KIRA_COLUMNS = ["cortisol", "dopamine", "serotonin", "oxytocin", "noradrenalin"]


class SqliteJournal:
    """Schreibt in eine SQLite-Tabelle.

    Beugt sich einem vorhandenen Schema, statt es zu ersetzen — dieselbe Regel,
    die KIRAs Seelen-Vertrag aufstellt. Mit `table="emotional_log"` und den
    Standard-Spaltennamen ist eine bestehende `synapsen.db` direkt kompatibel.
    """

    def __init__(self, path: str | Path, table: str = "emotional_log",
                 create: bool = True, hormones: list[str] | None = None):
        self.path = str(Path(path).expanduser())
        self.table = table
        # Ohne Angabe die fünf Spalten der bestehenden KIRA-Datenbanken, damit
        # ein Bestand ohne Zutun weiterläuft. Für jedes andere Profil gehören
        # dessen eigene Botenstoffe hierher — `for_profile()` nimmt einem das ab.
        self._hormones = list(hormones) if hormones else list(_KIRA_COLUMNS)
        if create:
            self._ensure_table()
        # Welche Botenstoff-Spalten die Tabelle wirklich hat. So passt sich der
        # Schreiber einem bestehenden Schema an, statt es vorauszusetzen —
        # dieselbe Regel wie in KIRAs Seelen-Vertrag: der Code beugt sich den
        # Daten, nie umgekehrt.
        self._columns = self._existing_columns()

    @classmethod
    def for_profile(cls, path: str | Path, profile, **kw) -> "SqliteJournal":
        """Legt das Protokoll mit den Botenstoffen dieses Profils an."""
        return cls(path, hormones=profile.hormone_names(), **kw)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _ensure_table(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        columns = ",\n                    ".join(
            f'"{name}" REAL' for name in self._hormones)
        with self._conn() as c:
            c.execute(f"""
                CREATE TABLE IF NOT EXISTS "{self.table}" (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ereignis  TEXT NOT NULL,
                    kontext   TEXT,
                    {columns}{"," if columns else ""}
                    schwere REAL DEFAULT 0.0
                )""")
            c.execute(f'CREATE INDEX IF NOT EXISTS idx_{self.table}_ts '
                      f'ON "{self.table}"(timestamp)')

    def _existing_columns(self) -> list[str]:
        try:
            with self._conn() as c:
                rows = c.execute(f'PRAGMA table_info("{self.table}")').fetchall()
        except sqlite3.Error:
            return []
        present = {r[1] for r in rows}
        return [h for h in self._hormones if h in present]

    def write(self, event: Event) -> None:
        cols = ["timestamp", "ereignis", "kontext"] + self._columns + ["schwere"]
        values = [event.timestamp, event.kind, event.context]
        values += [event.hormones.get(name) for name in self._columns]
        values.append(event.severity)
        placeholders = ",".join("?" * len(values))
        try:
            with self._conn() as c:
                c.execute(
                    f'INSERT INTO "{self.table}" ({", ".join(cols)}) '
                    f'VALUES ({placeholders})', values)
        except sqlite3.Error:
            pass  # Protokollieren darf den Zustand nie zum Absturz bringen

    def since(self, iso_timestamp: str) -> list[tuple[str, float]]:
        try:
            with self._conn() as c:
                return c.execute(
                    f'SELECT timestamp, schwere FROM "{self.table}" WHERE timestamp >= ?',
                    (iso_timestamp,),
                ).fetchall()
        except sqlite3.Error:
            return []


# ---------------------------------------------------------------------------


class Debouncer:
    """Verhindert, dass ein Dauerzustand als Ereignisstrom protokolliert wird."""

    def __init__(self, min_interval: float = 900.0):
        self.min_interval = min_interval
        self._last: dict[str, float] = {}

    def allow(self, kind: str, now: float) -> bool:
        last = self._last.get(kind)
        if last is not None and (now - last) < self.min_interval:
            return False
        self._last[kind] = now
        return True


def mood_bias(rows: list[tuple[str, float]], now: datetime, *,
              half_life_hours: float = 46.2, max_shift: float = 25.0,
              min_events: int = 5) -> float:
    """Stimmungs-Bias aus der jüngeren Vergangenheit.

    Rückgabe: ein Wert in [-max_shift, +max_shift]. Positiv = die Historie war
    belastend (Stress-Baseline hoch, Stabilität runter), negativ = sie war gut.

    Anders als im Original wird der *gewichtete Mittelwert* gebildet, nicht die
    Summe. Damit ist der Bias unabhängig davon, wie oft protokolliert wurde —
    tausend ruhige Einträge verschieben die Baseline genauso weit wie zehn.
    """
    if len(rows) < min_events:
        return 0.0

    lam = math.log(2) / half_life_hours
    weighted = 0.0
    total_weight = 0.0
    for ts_str, severity in rows:
        if severity is None:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue
        age_h = (now - ts).total_seconds() / 3600.0
        if age_h < 0:
            continue
        w = math.exp(-lam * age_h)
        weighted += (-float(severity)) * w   # negative Schwere = Belastung
        total_weight += w

    if total_weight <= 0:
        return 0.0

    mean = weighted / total_weight          # typische Schwere, nicht Summe
    bias = mean * 4.0                       # Skalierung auf Baseline-Einheiten
    return max(-max_shift, min(max_shift, bias))


def window_start(now: datetime, days: float = 7.0) -> str:
    return (now - timedelta(days=days)).isoformat()
