"""Die Dynamik: was sich pro Stunde ändert, und wo das System landet.

Diese Datei ist der Grund, warum die Bibliothek analysierbar ist statt nur
lauffähig. Alles, was den Zustand bewegt, ist hier als **Rate pro Stunde**
formuliert. Damit lässt sich das Gleichgewicht ausrechnen, statt es abzuwarten
— und ein Profil auf Stabilität prüfen, bevor es in Betrieb geht.

Warum das nötig war
-------------------
In der Ursprungsfassung war die Kopplung *aufrufbasiert*:

    delta = (excess / per) * gain * 0.02 * min(dt_sekunden, 60)

Der Faktor `min(dt, 60)` deckelt den Schritt, aber die Wirkung hängt damit
daran, **wie oft** getickt wird — nicht daran, wie viel Zeit vergeht:

    Tick jede Minute   ->  -115,2 Einheiten Cortisol pro Stunde
    Tick jede Stunde   ->    -1,9 Einheiten Cortisol pro Stunde

Ein Faktor 60 Unterschied, allein durch die Aufruf-Frequenz. In KIRAs Betrieb
wurde bei jedem Reiz und jeder Prompt-Erzeugung getickt, also oft. Das
rechnerische Gleichgewicht für Cortisol lag bei −124 — also am Boden.

In der echten `hormones.json` steht denn auch:

    cortisol      0.0      (Boden)
    serotonin   140.2      (Decke 150)
    oxytocin    210.7      (Ruhewert-Decke 250)

Jeder Wert klebt an einer Grenze. Das System war vollständig gesättigt: kein
Reiz konnte mehr etwas bewirken, weil die Grenzen alles auffingen.

Die Lösung
----------
Kopplungen sind jetzt in Einheiten *pro Stunde* definiert und werden über die
tatsächlich verstrichene Zeit integriert (Sub-Stepping mit fester Schrittweite).
Damit ist das Verhalten frequenzunabhängig — und `equilibrium()` kann
vorhersagen, wo es landet.
"""
from __future__ import annotations

from dataclasses import dataclass

from .profile import Profile

# Schrittweite für die numerische Integration. 6 Minuten ist deutlich kleiner
# als die schnellste Zeitkonstante im Standardprofil (Cortisol, 1/0.8 h = 75 min)
# und damit stabil, bleibt aber billig.
STEP_HOURS = 0.1

# Ab dieser Lücke wird nicht mehr integriert, sondern direkt auf das
# Gleichgewicht gesprungen — nach dem Fünffachen der langsamsten Zeitkonstante
# ist der Unterschied ohnehin nicht mehr messbar.
SETTLED_AFTER_HOURS = 30.0


def coupling_flux(profile: Profile, hormones: dict[str, float]) -> dict[str, float]:
    """Wirkung aller Kopplungen, in Einheiten pro Stunde."""
    out = {name: 0.0 for name in profile.hormones}
    for c in profile.couplings:
        src = hormones.get(c.source)
        if src is None or c.target not in out or not c.per:
            continue
        excess = src - c.threshold
        if excess <= 0:
            continue
        out[c.target] += (excess / c.per) * c.gain
    return out


def fatigue_flux(profile: Profile, adenosine: float) -> dict[str, float]:
    """Ermüdungsdruck auf Antrieb und Wachheit, in Einheiten pro Stunde."""
    out: dict[str, float] = {}
    excess = adenosine - profile.adenosine_threshold
    if excess <= 0:
        return out
    drag = excess * profile.fatigue_gain
    for name, share in profile.fatigue_targets.items():
        if name in profile.hormones:
            out[name] = -drag * share
    return out


def flux(profile: Profile, hormones: dict[str, float],
         baselines: dict[str, float], adenosine: float = 0.0) -> dict[str, float]:
    """Gesamte Änderungsrate je Botenstoff, in Einheiten pro Stunde.

    Setzt sich zusammen aus dem Rückzug zum Ruhewert, den Kopplungen und dem
    Ermüdungsdruck.
    """
    coup = coupling_flux(profile, hormones)
    fat = fatigue_flux(profile, adenosine)
    out: dict[str, float] = {}
    for name, spec in profile.hormones.items():
        pull = spec.decay * (baselines.get(name, spec.baseline) - hormones.get(name, spec.baseline))
        out[name] = pull + coup.get(name, 0.0) + fat.get(name, 0.0)
    return out


def step(profile: Profile, hormones: dict[str, float],
         baselines: dict[str, float], hours: float,
         adenosine: float = 0.0) -> dict[str, float]:
    """Integriert die Dynamik über `hours` und gibt den neuen Zustand zurück.

    Frequenzunabhängig: hundert Aufrufe à 0,01 h ergeben dasselbe wie ein
    Aufruf à 1 h (bis auf Integrationsfehler).
    """
    if hours <= 0:
        return dict(hormones)

    current = dict(hormones)
    remaining = hours
    while remaining > 1e-9:
        dt = min(STEP_HOURS, remaining)
        rates = flux(profile, current, baselines, adenosine)
        for name, spec in profile.hormones.items():
            value = current.get(name, spec.baseline) + rates[name] * dt
            current[name] = max(spec.floor, min(spec.ceiling, value))
        remaining -= dt
    return current


@dataclass
class Equilibrium:
    """Wo ein Profil ohne jeden Reiz landet."""
    values: dict[str, float]
    converged: bool
    iterations: int
    residual: float
    at_bounds: list[str]

    @property
    def healthy(self) -> bool:
        """Ein Gleichgewicht an einer Grenze ist keins — dort ist das System
        gesättigt und reagiert nicht mehr auf Reize."""
        return self.converged and not self.at_bounds


def equilibrium(profile: Profile, baselines: dict[str, float] | None = None,
                *, adenosine: float = 0.0, start: dict[str, float] | None = None,
                max_hours: float = 720.0, tolerance: float = 1e-4) -> Equilibrium:
    """Rechnet den Ruhezustand aus, statt ihn abzuwarten.

    Integriert von den Ruhewerten aus vorwärts, bis sich nichts mehr ändert.
    Weil dieselbe `step()`-Funktion verwendet wird wie im Betrieb, beschreibt
    das Ergebnis garantiert die echte Dynamik — es ist kein Parallelmodell,
    das auseinanderlaufen kann.

    >>> from synapsen import DEFAULT_PROFILE
    >>> eq = equilibrium(DEFAULT_PROFILE)
    >>> eq.healthy
    True
    """
    base = dict(baselines) if baselines else {
        k: s.baseline for k, s in profile.hormones.items()}
    current = dict(start) if start else dict(base)

    if not current:
        # Ein Profil ohne Botenstoffe hat ein triviales Gleichgewicht. Das ist
        # ein Fall für die Prüfung, kein Grund für einen Abbruch.
        return Equilibrium({}, converged=True, iterations=0,
                           residual=0.0, at_bounds=[])

    elapsed = 0.0
    iterations = 0
    residual = float("inf")

    while elapsed < max_hours:
        previous = dict(current)
        current = step(profile, current, base, STEP_HOURS, adenosine)
        iterations += 1
        elapsed += STEP_HOURS
        residual = max(abs(current[k] - previous[k]) for k in current)
        if residual < tolerance:
            break

    at_bounds = []
    for name, spec in profile.hormones.items():
        v = current[name]
        if v <= spec.floor + 1e-6:
            at_bounds.append(f"{name}=Boden({spec.floor:g})")
        elif v >= spec.ceiling - 1e-6:
            at_bounds.append(f"{name}=Decke({spec.ceiling:g})")

    return Equilibrium(
        values=current,
        converged=residual < tolerance,
        iterations=iterations,
        residual=residual,
        at_bounds=at_bounds,
    )


@dataclass
class Response:
    """Wie das System auf einen einzelnen Reiz reagiert."""
    hormone: str
    amount: float
    peak: dict[str, float]
    half_life_hours: float
    settles_to: dict[str, float]
    side_effects: dict[str, float]


def impulse_response(profile: Profile, hormone: str, amount: float = 50.0,
                     *, horizon_hours: float = 48.0) -> Response:
    """Ein Reiz, dann Ruhe — was passiert?

    Zeigt Halbwertszeit und Nebenwirkungen über die Kopplungen. Nützlich, um
    ein Profil zu justieren: „Ein Lob wirkt wie lange nach, und was zieht es
    sonst noch mit?"
    """
    base = {k: s.baseline for k, s in profile.hormones.items()}
    eq = equilibrium(profile, base)
    rest = eq.values

    current = dict(rest)
    spec = profile.hormones[hormone]
    current[hormone] = max(spec.floor, min(spec.ceiling, current[hormone] + amount))
    peak = dict(current)

    start_offset = current[hormone] - rest[hormone]
    half_life = float("inf")
    elapsed = 0.0

    while elapsed < horizon_hours:
        current = step(profile, current, base, STEP_HOURS)
        elapsed += STEP_HOURS
        if half_life == float("inf") and start_offset != 0:
            offset = current[hormone] - rest[hormone]
            if abs(offset) <= abs(start_offset) / 2:
                half_life = elapsed

    side = {k: round(current[k] - rest[k], 3) for k in current
            if k != hormone and abs(current[k] - rest[k]) > 0.05}

    return Response(
        hormone=hormone, amount=amount, peak=peak,
        half_life_hours=half_life, settles_to=current, side_effects=side,
    )
