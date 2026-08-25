"""Warum ist der Agent gerade so?

Ein Zustandsmodell, dessen Ausgabe man nicht zurückverfolgen kann, ist beim
Debuggen wertlos — man sieht „Cortisol 47" und weiß nicht, ob das an einem
Fehlschlag vor zwei Stunden liegt, an der Uhrzeit, an der Woche oder an einer
Kopplung.

`explain()` zerlegt jeden Wert in zwei Ebenen, die beide **exakt aufgehen**:

    cortisol   47.3
      Ruhepunkt    14.0 = Grundwert 20.0 · Tagesrhythmus −3.0
                        · Stimmungslage +4.2 · Kopplung −7.2
      Abweichung  +33.3 = Ereignisse +30.1 · Nachlauf +3.2

Die Additivität ist der Punkt: eine Aufschlüsselung, deren Teile sich nicht zur
Summe fügen, ist eine Vermutung, keine Erklärung. Was sich nicht auf einen
benannten Anteil zurückführen lässt, steht als „Nachlauf" da — der Teil der
Bewegung, der noch unterwegs ist.

Genau diese Aufschlüsselung hätte den Ursprungsfehler in Minuten sichtbar
gemacht: der Anteil „Stimmungslage" hätte bei −1.337 gestanden.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .dynamics import equilibrium
from .engine import HomeostasisEngine

# Nur Anteile ab dieser Größe werden ausgewiesen; alles darunter fällt in den
# Nachlauf, damit die Aufstellung lesbar bleibt.
NOISE_FLOOR = 0.05


@dataclass
class Contribution:
    source: str
    amount: float
    detail: str = ""


@dataclass
class HormoneExplanation:
    name: str
    value: float
    resting: float
    baseline: float
    resting_parts: list[Contribution] = field(default_factory=list)
    deviation_parts: list[Contribution] = field(default_factory=list)

    @property
    def deviation(self) -> float:
        return self.value - self.resting

    def _fmt(self, parts: list[Contribution]) -> str:
        shown = [c for c in sorted(parts, key=lambda x: -abs(x.amount))
                 if abs(c.amount) >= NOISE_FLOOR]
        return " · ".join(f"{c.source} {c.amount:+.1f}" for c in shown) or "—"

    def __str__(self) -> str:
        return "\n".join([
            f"{self.name:<14} {self.value:7.1f}",
            f"   Ruhepunkt  {self.resting:7.1f} = {self._fmt(self.resting_parts)}",
            f"   Abweichung {self.deviation:+7.1f} = {self._fmt(self.deviation_parts)}",
        ])


@dataclass
class StateExplanation:
    name: str
    value: float
    drivers: list[Contribution] = field(default_factory=list)

    def __str__(self) -> str:
        top = sorted(self.drivers, key=lambda c: -abs(c.amount))[:3]
        parts = ", ".join(f"{c.source} {c.amount:+.2f}" for c in top)
        return f"{self.name:<12} {self.value:6.2f}   getragen von {parts}"


@dataclass
class Explanation:
    hormones: list[HormoneExplanation]
    states: list[StateExplanation]
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        blocks = ["Botenstoffe", "─" * 64]
        blocks += [str(h) for h in self.hormones]
        blocks += ["", "Zustände", "─" * 64]
        blocks += [str(s) for s in self.states]
        if self.notes:
            blocks += ["", "Hinweise", "─" * 64] + [f"  {n}" for n in self.notes]
        return "\n".join(blocks)


def explain(engine: HomeostasisEngine, *, window_hours: float = 12.0) -> Explanation:
    """Zerlegt den aktuellen Zustand in seine Ursachen."""
    snap = engine.snapshot(jitter=False)
    profile = engine.profile
    now = engine.clock.now()
    hour = engine.clock.local().hour

    baselines = snap.baselines
    resting = equilibrium(profile, baselines, adenosine=snap.adenosine).values
    circadian = engine._circadian(hour)

    hormones = [
        _explain_hormone(engine, profile, name, spec, snap, baselines,
                         resting, circadian, now, window_hours)
        for name, spec in profile.hormones.items()
    ]
    states = [_explain_state(profile, st, snap, engine)
              for st in profile.states]
    return Explanation(hormones, states, _notes(engine, snap))


def _explain_hormone(engine, profile, name, spec, snap, baselines, resting,
                     circadian, now, window_hours) -> HormoneExplanation:
    baseline = baselines[name]
    block = HormoneExplanation(name, snap.hormones[name], resting[name], baseline)

    # ── Woraus der Ruhepunkt entsteht ────────────────────────────────────
    block.resting_parts.append(Contribution("Grundwert", spec.baseline))
    if circadian.get(name):
        block.resting_parts.append(
            Contribution("Tagesrhythmus", circadian[name], _daypart(snap.hour)))
    weight = profile.bias_targets.get(name, 0.0)
    if weight and engine._bias:
        block.resting_parts.append(
            Contribution("Stimmungslage", engine._bias * weight, "letzte 7 Tage"))
    drift = engine._drift.get(name, 0.0)
    if drift:
        cfg = profile.bond
        label = "gewachsene Bindung" if cfg and cfg.get("drives") == name \
            else "Erholung"
        block.resting_parts.append(Contribution("Drift", drift, label))

    # Was durch Decken oder Böden abgeschnitten wurde
    raw = sum(c.amount for c in block.resting_parts)
    if abs(raw - baseline) > 1e-9:
        block.resting_parts.append(Contribution("Kappung", baseline - raw))

    # Kopplungen und Ermüdung verschieben den Ruhepunkt gegenüber dem Ruhewert
    shift = resting[name] - baseline
    if abs(shift) > 1e-9:
        sources = sorted({c.source for c in profile.couplings if c.target == name})
        fatigued = name in profile.fatigue_targets and \
            snap.adenosine > profile.adenosine_threshold
        detail = "von " + ", ".join(sources) if sources else ""
        if fatigued:
            detail = (detail + " und Ermüdung").lstrip(" und ")
        block.resting_parts.append(Contribution("Kopplung", shift, detail))

    # ── Woraus die Abweichung vom Ruhepunkt entsteht ─────────────────────
    pulses = _recent_pulses(engine, name, now, window_hours, spec.decay)
    attributed = sum(a for _, a in pulses)
    if abs(attributed) >= NOISE_FLOOR:
        labels = ", ".join(f"{ctx} vor {age:.1f} h"
                           for ctx, age in _label_pulses(engine, name, now,
                                                         window_hours)[:3])
        block.deviation_parts.append(Contribution("Ereignisse", attributed, labels))

    # Der Rest ist Bewegung, die noch unterwegs ist — ausdrücklich ausgewiesen,
    # damit die Aufstellung aufgeht statt ungefähr zu stimmen.
    remainder = block.deviation - attributed
    block.deviation_parts.append(Contribution("Nachlauf", remainder))
    return block


def _explain_state(profile, st, snap, engine) -> StateExplanation:
    drivers: list[Contribution] = []
    scale = st.scale or 1.0
    for key, w in st.weights.items():
        if key in snap.hormones:
            drivers.append(Contribution(key, snap.hormones[key] * w / scale))
        elif key == "_adenosine":
            drivers.append(Contribution("Ermüdung", snap.adenosine * w / scale))
        elif key == "_morning":
            drivers.append(Contribution(
                "Morgen", engine._morning_intensity() * w / scale))
        elif key == "_const":
            drivers.append(Contribution("Grundwert", w / scale))
    for key, w in st.invert.items():
        spec = profile.hormones.get(key)
        mid = spec.baseline if spec else 50.0
        drivers.append(Contribution(
            f"fehlendes {key}", (mid - snap.hormones.get(key, mid)) * w / scale))
    return StateExplanation(st.name, snap.states[st.name], drivers)


# ---------------------------------------------------------------------------


def _recent_pulses(engine: HomeostasisEngine, hormone: str, now: float,
                   window_hours: float, decay: float) -> list[tuple[float, float]]:
    """Was von den jüngsten Reizen noch übrig ist.

    Ein Reiz klingt exponentiell mit der Zerfallsrate des Botenstoffs ab —
    nach `1/decay` Stunden ist noch etwa ein Drittel übrig.
    """
    out = []
    for ts, name, amount, _ctx in engine._pulses:
        if name != hormone:
            continue
        age = (now - ts) / 3600.0
        if age > window_hours or age < 0:
            continue
        out.append((age, amount * math.exp(-decay * age)))
    return out


def _label_pulses(engine: HomeostasisEngine, hormone: str, now: float,
                  window_hours: float) -> list[tuple[str, float]]:
    out = []
    for ts, name, _amount, ctx in reversed(engine._pulses):
        age = (now - ts) / 3600.0
        if name == hormone and 0 <= age <= window_hours:
            out.append((ctx or "Reiz", age))
    return out


def _daypart(hour: int) -> str:
    if 6 <= hour < 10:
        return "Morgen"
    if 10 <= hour < 14:
        return "Vormittag"
    if 14 <= hour < 17:
        return "Nachmittag"
    if 17 <= hour < 21:
        return "Abend"
    return "Nacht"


def _notes(engine: HomeostasisEngine, snap) -> list[str]:
    notes: list[str] = []
    for name, spec in engine.profile.hormones.items():
        v = snap.hormones[name]
        if v <= spec.floor + 1e-6:
            notes.append(f"{name} liegt am Boden — weitere dämpfende Reize "
                         "bleiben ohne Wirkung.")
        elif v >= spec.ceiling - 1e-6:
            notes.append(f"{name} liegt an der Decke — weitere Reize bleiben "
                         "ohne Wirkung.")
    ceiling = engine.profile.adenosine_ceiling
    if ceiling and snap.adenosine >= ceiling * 0.95:
        notes.append("Die Ermüdung ist gesättigt. Ohne Ruhephase bleibt sie dort.")

    now = engine.clock.now()
    for hormone, cfg in engine.profile.habituation.items():
        window = float(cfg.get("window_seconds", 3600))
        # Nur was noch im Zeitfenster liegt — `_recent` wird erst beim nächsten
        # Reiz beschnitten, der Hinweis darf davon nicht abhängen.
        used = sum(a for t, a in engine._recent.get(hormone, [])
                   if now - t < window)
        if used >= float(cfg.get("budget", 15.0)) * 0.95:
            notes.append(f"Gewöhnung bei {hormone}: weitere Reize verpuffen "
                         "bis zum Ablauf des Zeitfensters.")
    return notes
