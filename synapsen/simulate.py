"""Simulation: Wochen in Millisekunden.

Weil die Uhr injizierbar ist und die Dynamik in Zeiteinheiten formuliert ist,
lässt sich ein Profil durchrechnen, statt es abzuwarten. Das ist der
praktische Unterschied zwischen „Zahlen im Code" und „einem Modell, das man
justieren kann".

Wofür das gut ist:

  * **Justieren.** Ein Profil ändern, 30 Tage simulieren, Verlauf ansehen.
    Sekunden statt Wochen.
  * **Regressionstests fürs Verhalten.** Nicht nur „die Funktion gibt 70
    zurück", sondern „nach einer Woche mit lauter Fehlschlägen ist der Agent
    gereizt". Das ist die Ebene, auf der ein Zustandsmodell falsch sein kann.
  * **Zeigen.** Ein Verlauf über 30 Tage überzeugt schneller als jede
    Beschreibung.

    >>> from synapsen.simulate import Scenario, run
    >>> s = Scenario("harte Woche", days=7)
    >>> s.every(hours=4, event="task_failure")
    >>> t = run(s)
    >>> t.final()["cortisol"] > t.first()["cortisol"]
    True
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .clock import FakeClock
from .engine import HomeostasisEngine
from .journal import MemoryJournal
from .profile import DEFAULT_PROFILE, Profile
from .store import MemoryStore



@dataclass
class Beat:
    """Ein Ereignis zu einem Zeitpunkt (in Stunden seit Beginn)."""
    at_hours: float
    event: str | None = None
    mapping: dict[str, float] | None = None
    intensity: float = 1.0
    context: str = ""
    bond: float = 0.0     # >0 = warmer Kontakt, <0 = Härte

    def resolve(self, profile: Profile) -> tuple[dict[str, float], float, str]:
        if self.mapping is not None:
            return dict(self.mapping), 0.0, self.event or "custom"
        spec = profile.events.get(self.event or "")
        if spec is None:
            raise KeyError(
                f"Profil {profile.name!r} kennt kein Ereignis {self.event!r}. "
                f"Bekannt: {', '.join(sorted(profile.events)) or '(keine)'}")
        mapping = {k: v * self.intensity for k, v in spec.items()
                   if k != "severity" and k in profile.hormones}
        return mapping, spec.get("severity", 0.0) * self.intensity, self.event or ""


@dataclass
class Scenario:
    """Ein Drehbuch: was wann passiert."""
    name: str
    days: float = 7.0
    beats: list[Beat] = field(default_factory=list)
    sample_every_hours: float = 1.0
    start_hour: int = 9          # Wanduhrzeit beim Start (für den Tagesrhythmus)
    seed: int = 0

    # -- Bausteine ---------------------------------------------------------

    def at(self, hours: float, event: str, *, intensity: float = 1.0,
           context: str = "") -> "Scenario":
        self.beats.append(Beat(hours, event, intensity=intensity, context=context))
        return self

    def every(self, hours: float, event: str, *, intensity: float = 1.0,
              start: float = 0.0, until: float | None = None,
              context: str = "") -> "Scenario":
        end = until if until is not None else self.days * 24
        t = start
        while t < end:
            self.beats.append(Beat(t, event, intensity=intensity, context=context))
            t += hours
        return self

    def daily(self, at_hour: float, event: str, *, intensity: float = 1.0,
              days: Iterable[int] | None = None, context: str = "") -> "Scenario":
        """Jeden Tag zur selben Uhrzeit (relativ zum Start)."""
        span = days if days is not None else range(int(self.days))
        for d in span:
            self.beats.append(
                Beat(d * 24 + at_hour, event, intensity=intensity, context=context))
        return self

    def contact(self, hours: float, warmth: float = 1.0) -> "Scenario":
        """Warmer (warmth > 0) oder harter (warmth < 0) Kontakt."""
        self.beats.append(Beat(hours, bond=warmth))
        return self

    def gap(self, from_hours: float, to_hours: float) -> "Scenario":
        """Nur Dokumentation — eine Lücke entsteht automatisch, wenn zwischen
        zwei Beats nichts passiert."""
        return self


@dataclass
class Trajectory:
    """Der aufgezeichnete Verlauf."""
    scenario: str
    profile: str
    samples: list[dict] = field(default_factory=list)

    def first(self) -> dict:
        return self.samples[0]["hormones"] if self.samples else {}

    def final(self) -> dict:
        return self.samples[-1]["hormones"] if self.samples else {}

    def series(self, key: str) -> list[float]:
        """Zeitreihe eines Botenstoffs oder Zustands."""
        out = []
        for s in self.samples:
            if key in s["hormones"]:
                out.append(s["hormones"][key])
            elif key in s["states"]:
                out.append(s["states"][key])
            elif key in s:
                out.append(s[key])
        return out

    def keys(self) -> list[str]:
        if not self.samples:
            return []
        s = self.samples[0]
        return list(s["hormones"]) + list(s["states"]) + ["bond", "adenosine", "bias"]

    def summary(self, key: str) -> dict[str, float]:
        v = self.series(key)
        if not v:
            return {}
        return {"min": min(v), "max": max(v), "mean": sum(v) / len(v),
                "start": v[0], "end": v[-1]}

    def to_csv(self) -> str:
        if not self.samples:
            return ""
        cols = ["hours"] + list(self.samples[0]["hormones"]) \
            + list(self.samples[0]["states"]) + ["bond", "adenosine", "bias"]
        lines = [",".join(cols)]
        for s in self.samples:
            row = [f"{s['hours']:.2f}"]
            row += [f"{s['hormones'][k]:.3f}" for k in self.samples[0]["hormones"]]
            row += [f"{s['states'][k]:.3f}" for k in self.samples[0]["states"]]
            row += [f"{s['bond']:.3f}", f"{s['adenosine']:.3f}", f"{s['bias']:.3f}"]
            lines.append(",".join(row))
        return "\n".join(lines)


def run(scenario: Scenario, profile: Profile | None = None,
        *, on_sample: Callable[[dict], None] | None = None) -> Trajectory:
    """Spielt ein Szenario durch und zeichnet den Verlauf auf."""
    profile = profile or DEFAULT_PROFILE

    # Startzeit so wählen, dass die Wanduhr auf `start_hour` steht — der
    # Tagesrhythmus soll reproduzierbar sein.
    import datetime as _dt
    base = _dt.datetime(2026, 1, 5, scenario.start_hour, 0, 0)  # ein Montag
    clock = FakeClock(start=base.timestamp())

    engine = HomeostasisEngine(
        profile,
        store=MemoryStore(),
        journal=MemoryJournal(),
        clock=clock,
        rng=random.Random(scenario.seed),
        autosave=False,
    )

    traj = Trajectory(scenario.name, profile.name)
    beats = sorted(scenario.beats, key=lambda b: b.at_hours)
    total = scenario.days * 24
    step = scenario.sample_every_hours

    index = 0
    t = 0.0
    origin = clock.now()

    while t <= total + 1e-9:
        # alle Ereignisse bis zum aktuellen Zeitpunkt abarbeiten
        while index < len(beats) and beats[index].at_hours <= t:
            b = beats[index]
            clock.set(origin + b.at_hours * 3600)
            if b.bond:
                if b.bond > 0:
                    engine.reinforce_bond(b.bond)
                else:
                    engine.strain_bond(-b.bond)
            else:
                mapping, severity, kind = b.resolve(profile)
                engine.stimulus(mapping, kind=kind, context=b.context,
                                severity=severity)
            index += 1

        clock.set(origin + t * 3600)
        snap = engine.snapshot(jitter=False)
        sample = {
            "hours": t,
            "day": t / 24.0,
            "hormones": dict(snap.hormones),
            "baselines": dict(snap.baselines),
            "states": dict(snap.states),
            "bond": snap.bond,
            "adenosine": snap.adenosine,
            "bias": snap.meta.get("bias", 0.0),
        }
        traj.samples.append(sample)
        if on_sample:
            on_sample(sample)
        t += step

    return traj


# ---------------------------------------------------------------------------
# Darstellung ohne Fremdbibliotheken
# ---------------------------------------------------------------------------

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], *, lo: float | None = None,
              hi: float | None = None) -> str:
    """Eine Zeitreihe als eine Zeile."""
    if not values:
        return ""
    lo = min(values) if lo is None else lo
    hi = max(values) if hi is None else hi
    if hi - lo < 1e-9:
        return _BLOCKS[0] * len(values)
    out = []
    for v in values:
        idx = int((v - lo) / (hi - lo) * (len(_BLOCKS) - 1) + 0.5)
        out.append(_BLOCKS[max(0, min(len(_BLOCKS) - 1, idx))])
    return "".join(out)


def resample(values: list[float], width: int) -> list[float]:
    """Auf eine feste Breite eindampfen (Mittelwert je Eimer)."""
    if not values or width <= 0:
        return []
    if len(values) <= width:
        return list(values)
    out = []
    for i in range(width):
        a = int(i * len(values) / width)
        b = int((i + 1) * len(values) / width)
        chunk = values[a:max(b, a + 1)]
        out.append(sum(chunk) / len(chunk))
    return out


def chart(traj: Trajectory, keys: list[str] | None = None,
          *, width: int = 60) -> str:
    """Mehrere Zeitreihen untereinander, mit Wertebereich."""
    keys = keys or [k for k in traj.keys() if k not in ("bond", "adenosine")]
    label_width = max(len(k) for k in keys) if keys else 0
    lines = [f"{traj.scenario}  ·  Profil {traj.profile}  ·  "
             f"{traj.samples[-1]['day']:.0f} Tage"]
    lines.append("")
    for k in keys:
        v = traj.series(k)
        if not v:
            continue
        small = resample(v, width)
        lines.append(
            f"  {k:<{label_width}}  {sparkline(small)}  "
            f"{min(v):7.1f} … {max(v):6.1f}   Ende {v[-1]:6.1f}")
    return "\n".join(lines)


def profile_chart(traj: Trajectory, key: str, *, width: int = 64,
                  height: int = 12) -> str:
    """Eine einzelne Zeitreihe als grober Flächenplot."""
    v = resample(traj.series(key), width)
    if not v:
        return ""
    lo, hi = min(v), max(v)
    span = hi - lo or 1.0
    rows = []
    for r in range(height, 0, -1):
        threshold = lo + span * (r - 0.5) / height
        line = "".join("█" if value >= threshold else " " for value in v)
        axis = f"{lo + span * (r - 0.5) / height:7.1f} │"
        rows.append(axis + line)
    rows.append(" " * 7 + "└" + "─" * len(v))
    rows.append(" " * 8 + f"0{' ' * (len(v) - 12)}{traj.samples[-1]['day']:.0f} Tage")
    return f"{key}\n" + "\n".join(rows)
