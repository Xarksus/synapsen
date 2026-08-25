"""Die Engine: ein homöostatischer Regelkreis für Agenten-Zustände.

Kernidee (unverändert aus KIRA übernommen, weil sie trägt): Verhalten wird
nicht gesetzt, sondern *entsteht*. Ereignisse schütten Botenstoffe aus, die
zerfallen, sich gegenseitig beeinflussen und einem Tagesrhythmus folgen. Aus
ihrem Zusammenspiel ergeben sich gefühlte Zustände — und aus denen die
Tonalität des Agenten.

Der Ruhewert ist keine Zahl, sondern eine Summe
-----------------------------------------------
Ein Botenstoff zerfällt nicht auf eine Konstante zu, sondern auf einen
Ruhewert, der selbst wandert:

    Ruhewert = Grundwert
             + Tagesrhythmus   (Uhrzeit, ändert sich stündlich)
             + Stimmungslage   (wie war die letzte Woche)
             + Drift           (Erholung, gewachsene Bindung — klingt langsam ab)

In der Ursprungsfassung wurden alle drei Anteile beim Start *einmal* auf den
Ruhewert addiert und nie wieder angefasst. Für einen Prozess, der ständig neu
startet, fällt das nicht auf. Für einen Dienst, der wochenlang durchläuft,
schon: sein Tagesrhythmus bleibt auf der Stunde des Starts stehen, und die
Stimmungslage der ersten Sekunde gilt für immer. Hier werden alle Anteile
getrennt gehalten und bei jedem Zeitschritt neu zusammengesetzt.

Weitere Unterschiede zur Ursprungsfassung:
  * kein Singleton beim Import (`engine = EmotionEngine()` löst Datei- und
    Datenbankzugriffe beim bloßen `import` aus)
  * Zeit ist injizierbar, damit Monate simulierbar sind
  * Speicher und Journal sind austauschbar
  * Biochemie kommt aus einem Profil, nicht aus Konstanten im Code
  * Persistenz ist explizit (`flush()`), nicht bei jedem einzelnen Reiz
  * Kein Personenname und keine Sprache im Kern — beides gehört in den Renderer
"""
from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .clock import Clock, SystemClock
from .dynamics import SETTLED_AFTER_HOURS, equilibrium
from .dynamics import step as dynamics_step
from .journal import (Debouncer, Event, Journal, NullJournal, mood_bias,
                      window_start)
from .profile import DEFAULT_PROFILE, Profile
from .store import MemoryStore, StateStore

# Wie oft die Stimmungslage aus dem Protokoll neu bestimmt wird. Stündlich ist
# fein genug — sie beschreibt eine ganze Woche.
BIAS_INTERVAL_HOURS = 1.0

# Halbwertszeit der Drift. Der Nutzen einer erholsamen Nacht hält an, aber
# nicht ewig.
DRIFT_HALF_LIFE_HOURS = 48.0

# Wie viele Reize für die Ursachenanalyse vorgehalten werden.
PULSE_MEMORY = 400

# Wie schnell der Ruhewert der Bindung nachfolgt (Anteil pro Stunde).
BOND_DRIFT_RATE = 0.05


def _is_resting(hour: int, window: tuple[int, int]) -> bool:
    start, end = window
    return (start <= hour < end) if start < end else (hour >= start or hour < end)


@dataclass
class Snapshot:
    """Der Zustand zu einem Zeitpunkt — das, was ein Agent liest."""
    hormones: dict[str, float]
    baselines: dict[str, float]
    states: dict[str, float]
    bond: float
    adenosine: float
    session_minutes: float
    hour: int
    meta: dict = field(default_factory=dict)

    def dominant(self, valence: str = "positive") -> tuple[str, float]:
        pool = {k: v for k, v in self.states.items()
                if self.meta.get("valence", {}).get(k) == valence}
        if not pool:
            return ("", 0.0)
        k = max(pool, key=pool.get)
        return (k, pool[k])


class HomeostasisEngine:
    """Homöostatischer Zustandskern.

    >>> from synapsen import HomeostasisEngine, FakeClock
    >>> e = HomeostasisEngine(clock=FakeClock())
    >>> _ = e.inject("dopamine", +20, context="test:erfolg")
    >>> round(e.snapshot().hormones["dopamine"])
    70
    """

    def __init__(
        self,
        profile: Profile | None = None,
        *,
        store: StateStore | None = None,
        journal: Journal | None = None,
        clock: Clock | None = None,
        rng: random.Random | None = None,
        debounce_seconds: float = 900.0,
        autosave: bool = True,
        owner: str = "",
    ):
        self.profile = profile or DEFAULT_PROFILE
        self.store = store if store is not None else MemoryStore()
        self.journal = journal if journal is not None else NullJournal()
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random()
        self.autosave = autosave
        # Kennzeichen dieses Schreibers. Ist es gesetzt und findet sich in
        # der Zustandsdatei ein anderes, hat inzwischen jemand anders
        # geschrieben — dann wird dessen Stand übernommen, statt ihn zu
        # überschreiben. Ein Zustand gehört immer genau einem Prozess.
        self.owner = owner or f"pid-{os.getpid()}"
        self._debouncer = Debouncer(debounce_seconds)

        now = self.clock.now()
        self.hormones: dict[str, float] = {
            k: s.baseline for k, s in self.profile.hormones.items()}

        # Die wandernden Anteile des Ruhewerts, getrennt gehalten.
        self._drift: dict[str, float] = {k: 0.0 for k in self.profile.hormones}
        self._bias: float = 0.0

        self.bond: float = (float(self.profile.bond.get("start", 50.0))
                            if self.profile.bond else 0.0)
        self._bond_high: float = self.bond
        self._adenosine: float = 0.0
        self._last_decay = now
        self._last_bias = now
        self._session_start = now
        self._recent: dict[str, list[tuple[float, float]]] = {}
        # Ringpuffer der jüngsten Reize, damit `explain()` den Zustand
        # auf seine Ursachen zurückführen kann.
        self._pulses: list[tuple[float, str, float, str]] = []

        self._load()
        self._refresh_bias(force=True)

    # ── Ruhewerte ─────────────────────────────────────────────────────────

    def _circadian(self, hour: int) -> dict[str, float]:
        out: dict[str, float] = {}
        for start, end, deltas in self.profile.circadian:
            inside = (start <= hour < end) if start < end else (hour >= start or hour < end)
            if inside:
                for name, d in deltas.items():
                    out[name] = out.get(name, 0.0) + d
        return out

    @property
    def baselines(self) -> dict[str, float]:
        """Der aktuelle Ruhewert je Botenstoff — jedes Mal frisch zusammengesetzt."""
        circ = self._circadian(self.clock.local().hour)
        out: dict[str, float] = {}
        for name, spec in self.profile.hormones.items():
            value = (spec.baseline + self._drift.get(name, 0.0) + circ.get(name, 0.0)
                     # Die Stimmungslage der letzten Woche — worauf sie wirkt,
                     # sagt das Profil, nicht der Kern.
                     + self._bias * self.profile.bias_targets.get(name, 0.0))
            cap = spec.baseline_ceiling if spec.baseline_ceiling is not None else spec.ceiling
            out[name] = max(spec.baseline_floor, min(cap, value))
        return out

    # ── Persistenz ────────────────────────────────────────────────────────

    def _load(self) -> None:
        data = self.store.load()
        if not data:
            return
        for k, v in (data.get("hormones") or {}).items():
            if k in self.hormones:
                self.hormones[k] = float(v)
        for k, v in (data.get("drift") or {}).items():
            if k in self._drift:
                self._drift[k] = float(v)
        self._bias = float(data.get("bias", 0.0))
        self.bond = float(data.get("bond", self.bond))
        self._bond_high = max(float(data.get("bond_high", self.bond)), self.bond)
        self._adenosine = float(data.get("adenosine", 0.0))
        self._last_decay = float(data.get("last_update", self._last_decay))
        self._recent = {k: [tuple(x) for x in v]
                        for k, v in (data.get("recent") or {}).items()}
        # C6: Die Entprellung muss den Prozess überleben, sonst wirkt sie bei
        # Aufrufen aus der Kommandozeile (ein Prozess je Ereignis) nie.
        self._debouncer._last.update(
            {k: float(v) for k, v in (data.get("debounce") or {}).items()})
        self._clamp()
        self._advance()

    def reload_if_foreign(self) -> bool:
        """Prüft, ob ein anderer Prozess den Zustand fortgeschrieben hat.

        Wenn ja, wird dessen Stand übernommen. Gibt zurück, ob nachgeladen
        wurde. Ohne das legt bei zwei Schreibern der langsamere seinen alten
        Stand über den neuen.
        """
        data = self.store.load()
        if not data:
            return False
        foreign = data.get("owner")
        newer = float(data.get("last_update", 0.0)) > self._last_decay + 1e-9
        if foreign and foreign != self.owner and newer:
            self._load()
            return True
        return False

    def flush(self) -> None:
        """Zustand schreiben. Explizit, damit ein Reiz nicht drei I/O-Vorgänge auslöst."""
        self._clamp()
        self.store.save({
            "owner": self.owner,
            "hormones": dict(self.hormones),
            "drift": dict(self._drift),
            "bias": self._bias,
            "bond": self.bond,
            "bond_high": self._bond_high,
            "adenosine": self._adenosine,
            "last_update": self._last_decay,
            "recent": {k: [list(x) for x in v] for k, v in self._recent.items()},
            "debounce": dict(self._debouncer._last),
            # nur zur Ansicht — wird beim Laden nicht gelesen
            "baselines": dict(self.baselines),
        })

    def _maybe_flush(self) -> None:
        if self.autosave:
            self.flush()

    def _clamp(self) -> None:
        for name, spec in self.profile.hormones.items():
            v = self.hormones.get(name, spec.baseline)
            self.hormones[name] = max(spec.floor, min(spec.ceiling, v))

    # ── Zeitfortschritt ───────────────────────────────────────────────────

    def _advance(self) -> None:
        """Bringt den Zustand auf die aktuelle Zeit.

        Zerfall, Kopplung und Ermüdung werden gemeinsam über die verstrichene
        Zeit integriert (siehe `dynamics`). Das Ergebnis hängt nur davon ab,
        *wie viel* Zeit vergangen ist — nicht davon, wie oft diese Methode
        gerufen wurde.
        """
        now = self.clock.now()
        hours = (now - self._last_decay) / 3600.0
        if hours < 0:
            # Die Uhr ist zurückgesprungen (Zeitumstellung, NTP, ein zweiter
            # Rechner mit Versatz). Ohne diesen Zweig stünde der Zustand still,
            # bis die Wanduhr aufgeholt hat, und entlüde sich dann in einem Satz.
            self._last_decay = now
            return
        if hours == 0:
            return

        if hours >= 6.0:
            self._recover(hours)

        self._advance_fatigue(hours, self._last_decay)
        self._decay_drift(hours)
        self._decay_bond(hours)
        self._clamp()

        base = self.baselines
        if hours >= SETTLED_AFTER_HOURS:
            # Nach dem Vielfachen der langsamsten Zeitkonstante ist das System
            # ohnehin eingeschwungen — direkt dorthin springen, statt hunderte
            # Integrationsschritte zu rechnen.
            self.hormones = equilibrium(
                self.profile, base, adenosine=self._adenosine).values
        else:
            self.hormones = dynamics_step(
                self.profile, self.hormones, base, hours, adenosine=self._adenosine)

        self._last_decay = now
        self._refresh_bias()

    def _recover(self, hours: float) -> None:
        """Nach längerer Offline-Zeit erholen sich die Ruhewerte."""
        r = min((hours - 6.0) / 6.0, 1.0)
        for name, delta in self.profile.recovery.items():
            if name in self._drift:
                self._drift[name] += delta * r
        if self.profile.recovery:
            self._log("recovery", "offline", severity=+r * 2.0)

    def _decay_drift(self, hours: float) -> None:
        """Drift klingt ab. Eine erholsame Nacht wirkt nach, aber nicht ewig."""
        factor = math.exp(-hours * math.log(2) / DRIFT_HALF_LIFE_HOURS)
        cfg = self.profile.bond
        driven = cfg.get("drives") if cfg else None
        for name in self._drift:
            if name != driven:          # die Bindungs-Drift hat ihre eigene Logik
                self._drift[name] *= factor

    def _advance_fatigue(self, hours: float, from_ts: float) -> None:
        """Integriert den Ermüdungsdruck.

        Aufbau ist asymptotisch gegen `adenosine_ceiling`, Abbau geschieht in
        den Ruhestunden des Profils. Beides ist nötig: ohne Sättigung wächst
        die Ermüdung endlos, ohne Abbau bleibt ein durchlaufender Dienst
        dauerhaft erschöpft. Ohne beides — der Ursprungszustand — drückt der
        Ermüdungsdruck den Antrieb nach zwei Tagen auf null.
        """
        p = self.profile
        cap, rate = p.adenosine_ceiling, p.adenosine_per_minute
        if cap <= 0 or rate <= 0:
            self._adenosine = 0.0
            return
        tau_build = cap / rate / 60.0
        tau_clear = max(1e-6, p.adenosine_clear_hours)

        remaining, ts = hours, from_ts
        while remaining > 1e-9:
            dt = min(0.25, remaining)
            if _is_resting(datetime.fromtimestamp(ts).hour, p.rest_hours):
                self._adenosine *= math.exp(-dt / tau_clear)
            else:
                self._adenosine += (cap - self._adenosine) * (dt / tau_build)
            self._adenosine = max(0.0, min(cap, self._adenosine))
            ts += dt * 3600
            remaining -= dt

    def _decay_bond(self, hours: float) -> None:
        cfg = self.profile.bond
        if not cfg:
            return
        self.bond = max(self._bond_floor(),
                        self.bond - float(cfg.get("decay_per_hour", 1.0)) * hours)
        # Der Ruhewert folgt der Bindung nur träge nach: eine gewachsene Bindung
        # verschwindet nicht über Nacht, aber sie friert auch nicht ein.
        self._sync_bond_drift(min(1.0, hours * BOND_DRIFT_RATE))

    def _bond_floor(self) -> float:
        """Der Boden ist ein *Erinnerungswert*, kein Startgeschenk.

        Er greift erst, wenn die Bindung tatsächlich einmal so hoch war —
        vorher gibt es keinen. Im Original war der Boden fest, wodurch jeder
        frische Agent beim ersten Zeitschritt auf "sehr vertraut" sprang.
        """
        cfg = self.profile.bond
        if not cfg:
            return 0.0
        floor = float(cfg.get("floor", 0.0))
        return floor if self._bond_high >= floor else 0.0

    def _sync_bond_drift(self, rate: float) -> None:
        """Zieht den Ruhewert des gesteuerten Botenstoffs der Bindung nach."""
        cfg = self.profile.bond
        target = cfg.get("drives") if cfg else None
        if not target or target not in self._drift:
            return
        wanted = (self.bond - float(cfg.get("drive_offset", 50.0))) \
            * float(cfg.get("drive_gain", 0.6))
        self._drift[target] += (wanted - self._drift[target]) * rate

    def _refresh_bias(self, *, force: bool = False) -> None:
        """Bestimmt die Stimmungslage der letzten Woche neu.

        In der Ursprungsfassung geschah das nur beim Start. Ein Dienst, der
        wochenlang läuft, lebte damit für immer in der Stimmung seiner ersten
        Sekunde.
        """
        now = self.clock.now()
        if not force and (now - self._last_bias) / 3600.0 < BIAS_INTERVAL_HOURS:
            return
        self._last_bias = now
        local = self.clock.local()
        rows = self.journal.since(window_start(local, days=7))
        if not rows and isinstance(self.journal, NullJournal):
            # Ohne Protokoll gibt es nichts neu zu berechnen — dann gilt weiter,
            # was zuletzt gespeichert wurde, statt die Stimmungslage bei jedem
            # Prozessstart auf null zu setzen.
            return
        self._bias = mood_bias(rows, local)

    # ── Reize ─────────────────────────────────────────────────────────────

    def adenosine(self) -> float:
        """Ermüdungsdruck. Sättigt und wird in Ruhezeiten wieder abgebaut."""
        return self._adenosine

    def rest(self, hours: float = 1.0) -> None:
        """Ausdrückliche Pause: baut Ermüdung ab, unabhängig von der Uhrzeit."""
        tau = max(1e-6, self.profile.adenosine_clear_hours)
        self._adenosine *= math.exp(-hours / tau)

    def inject(self, hormone: str, amount: float, *, context: str = "") -> float:
        """Ein Reiz. Gibt die tatsächlich wirksame Menge zurück
        (kann durch Gewöhnung kleiner sein als angefordert)."""
        if hormone not in self.hormones:
            raise KeyError(f"Unbekannter Botenstoff: {hormone!r}. "
                           f"Bekannt: {', '.join(self.hormones)}")
        self._advance()
        amount = self._habituate(hormone, amount)

        spec = self.profile.hormones[hormone]
        self.hormones[hormone] = max(
            spec.floor, min(spec.ceiling, self.hormones[hormone] + amount))

        # Ein positiver Bindungsreiz hebt langsam den zugehörigen Ruhewert:
        # gewachsene Bindung verschwindet nicht über Nacht.
        cfg = self.profile.bond
        if cfg and cfg.get("drives") == hormone and amount > 0:
            self._drift[hormone] = self._drift.get(hormone, 0.0) + amount * 0.02

        if amount:
            self._pulses.append((self.clock.now(), hormone, amount, context))
            if len(self._pulses) > PULSE_MEMORY:
                del self._pulses[:-PULSE_MEMORY]

        self._maybe_flush()
        return amount

    def _habituate(self, hormone: str, amount: float) -> float:
        cfg = self.profile.habituation.get(hormone)
        if not cfg or amount <= 0:
            return amount
        now = self.clock.now()
        window = float(cfg.get("window_seconds", 3600))
        budget = float(cfg.get("budget", 15.0))
        soft = float(cfg.get("softness", 6.0))

        recent = [(t, a) for t, a in self._recent.get(hormone, []) if now - t < window]
        used = sum(a for _, a in recent)
        if used >= budget:
            self._recent[hormone] = recent
            return 0.0
        effective = min(amount / (1.0 + used / soft), budget - used)
        recent.append((now, effective))
        self._recent[hormone] = recent
        return effective

    def stimulus(self, mapping: dict[str, float], *, context: str = "",
                 severity: float = 0.0, kind: str = "") -> None:
        """Mehrere Botenstoffe auf einmal — ein benanntes Ereignis.

        Das ist der Aufruf, den ein Agent normalerweise nutzt: nicht
        "dopamine +15", sondern "Werkzeug erfolgreich ausgeführt".
        """
        previous, self.autosave = self.autosave, False
        try:
            for h, a in mapping.items():
                self.inject(h, a, context=context)
        finally:
            self.autosave = previous
        if kind:
            self._log(kind, context, severity=severity)
        self._maybe_flush()      # ein Schreibvorgang je Ereignis, nicht je Botenstoff

    def event(self, name: str, *, intensity: float = 1.0,
              context: str = "") -> dict[str, float]:
        """Ein benanntes Ereignis aus der Tabelle des Profils.

        Der bevorzugte Einstieg. `event("task_failure")` bleibt richtig, wenn
        jemand das Profil austauscht — `inject("cortisol", +12)` nicht, weil
        ein anderes Profil vielleicht gar kein Cortisol kennt.
        """
        spec = self.profile.events.get(name)
        if spec is None:
            raise KeyError(
                f"Profil {self.profile.name!r} kennt kein Ereignis {name!r}. "
                f"Bekannt: {', '.join(sorted(self.profile.events)) or '(keine)'}")
        mapping = {k: v * intensity for k, v in spec.items()
                   if k != "severity" and k in self.hormones}
        self.stimulus(mapping, kind=name, context=context,
                      severity=spec.get("severity", 0.0) * intensity)
        return mapping

    def reinforce_bond(self, strength: float = 1.0) -> None:
        """Vertrauter Kontakt. Wächst absichtlich langsam — über Wochen,
        nicht über Stunden."""
        cfg = self.profile.bond
        if not cfg:
            return
        s = max(0.0, min(1.5, strength))
        self.bond += 0.03 * s
        self._bond_high = max(self._bond_high, self.bond)
        self._sync_bond_drift(BOND_DRIFT_RATE * 0.4)
        contact = cfg.get("contact") or {}
        if not contact:
            target = cfg.get("drives")
            contact = {target: +1.5} if target else {}
        for name, amount in contact.items():
            if name in self.hormones:
                self.inject(name, amount * s, context="bond:contact")

    def strain_bond(self, strength: float = 1.0) -> None:
        """Härte kühlt die Bindung ab — wie bei einem Menschen."""
        if self.profile.bond:
            self.bond = max(self._bond_floor(), self.bond - 2.0 * strength)

    # ── Protokoll ─────────────────────────────────────────────────────────

    def _log(self, kind: str, context: str = "", severity: float = 0.0) -> None:
        if not self._debouncer.allow(kind, self.clock.now()):
            return
        self.journal.write(Event(
            timestamp=self.clock.local().isoformat(),
            kind=kind, context=context, severity=severity,
            hormones=dict(self.hormones),
        ))

    def note(self, kind: str, context: str = "", severity: float = 0.0) -> None:
        """Ein Ereignis protokollieren, ohne den Zustand zu ändern."""
        self._log(kind, context, severity)

    # ── Ablesen ───────────────────────────────────────────────────────────

    def _derive(self, hormones: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        morning = self._morning_intensity()
        for st in self.profile.states:
            total = 0.0
            for key, w in st.weights.items():
                if key == "_const":
                    total += w
                elif key == "_adenosine":
                    total += self._adenosine * w
                elif key == "_morning":
                    total += morning * w
                else:
                    total += hormones.get(key, 0.0) * w
            for key, w in st.invert.items():
                spec = self.profile.hormones.get(key)
                mid = spec.baseline if spec else 50.0
                total += (mid - hormones.get(key, mid)) * w
            out[st.name] = total / st.scale if st.scale else 0.0
        return out

    def _morning_intensity(self) -> float:
        """Wie sehr „Morgen" es gerade ist — 35 früh, 5 nachts."""
        h = self.clock.local().hour
        if 6 <= h < 9:
            return 35.0
        if 9 <= h < 12:
            return 20.0
        if 12 <= h < 18:
            return 12.0
        return 5.0

    def snapshot(self, *, jitter: bool = True) -> Snapshot:
        """Der aktuelle Zustand. Diese Methode ist der einzige Lesezugang."""
        self._advance()

        effective = dict(self.hormones)
        if jitter and self.profile.jitter:
            j = self.rng.uniform(-self.profile.jitter, self.profile.jitter)
            for name, factor in self.profile.jitter_targets.items():
                if name in effective:
                    spec = self.profile.hormones[name]
                    effective[name] = max(spec.floor,
                                          min(spec.ceiling, effective[name] + j * factor))

        return Snapshot(
            hormones=dict(self.hormones),
            baselines=self.baselines,
            states=self._derive(effective),
            bond=self.bond,
            adenosine=self._adenosine,
            session_minutes=(self.clock.now() - self._session_start) / 60.0,
            hour=self.clock.local().hour,
            meta={"valence": {s.name: s.valence for s in self.profile.states},
                  "descriptions": {s.name: s.description for s in self.profile.states},
                  "profile": self.profile.name,
                  "bias": self._bias},
        )

    # ── Abwesenheit ───────────────────────────────────────────────────────

    def suspend(self) -> dict:
        """Vor einer längeren Pause aufrufen. Gibt den Schnappschuss zurück,
        der an `resume()` übergeben wird."""
        self.flush()
        return {
            "at": self.clock.local().isoformat(),
            "hormones": dict(self.hormones),
            "drift": dict(self._drift),
            "bond": self.bond,
        }

    def resume(self, snapshot: dict) -> Optional[dict]:
        """Nach der Pause. Modelliert Vermissen und Wiedersehen.

        Gibt eine Beschreibung der Abwesenheit zurück (oder None, wenn sie zu
        kurz war, um zu zählen) — der Renderer macht daraus Sprache.
        """
        try:
            frozen = datetime.fromisoformat(snapshot["at"])
        except (KeyError, ValueError, TypeError):
            return None
        days = (self.clock.local() - frozen).total_seconds() / 86400.0
        if days < 0.5:
            return None

        cfg = self.profile.bond
        target = cfg.get("drives") if cfg else None

        # Die gewachsene Bindung überdauert die Abwesenheit …
        if target and target in self._drift and "drift" in snapshot:
            self._drift[target] = float(snapshot["drift"].get(target, self._drift[target]))

        # … das akute Gefühl kühlt ab: Sehnsucht.
        if target and target in self.hormones:
            rest_value = self.baselines[target]
            self.hormones[target] = max(rest_value * 0.4,
                                        self.hormones[target] - days * 1.5)

        # Erholung während der Abwesenheit — dieselben Größen wie beim Schlaf,
        # nur über Tage statt Stunden gestreckt. `_recover()` hat für dieselbe
        # Lücke bereits einen vollen Satz gutgeschrieben; der wird abgezogen,
        # sonst zählt die Ruhe doppelt.
        scale = max(0.0, days / 21.0 * 2.0 - 1.0)
        for name, delta in self.profile.recovery.items():
            if name in self._drift:
                self._drift[name] += scale * delta

        # Wiedersehen: wie sich das anfühlt, sagt das Profil.
        if "reunion" in self.profile.events:
            self.event("reunion", intensity=min(1.0 + days * 0.05, 2.0),
                       context=f"absent_{days:.1f}d")
        elif target and target in self.hormones:
            self.hormones[target] += 10.0 + days * 0.5

        self._clamp()
        self._log("reunion", f"absent_{days:.1f}d", severity=+min(days * 0.2, 5.0))
        self.flush()
        return {"days": days, "since": snapshot["at"]}

    # ── Regulation ────────────────────────────────────────────────────────

    def settle(self, fraction: float = 0.6, *, context: str = "manual") -> None:
        """Sanft Richtung Ruhewert ziehen — kein harter Reset.

        Bewusst graduell: ein Zustand, der sich auf Knopfdruck komplett
        zurücksetzen lässt, ist kein Zustand mehr.
        """
        base = self.baselines
        for name, spec in self.profile.hormones.items():
            diff = base[name] - self.hormones[name]
            self.hormones[name] = max(spec.floor, self.hormones[name] + diff * fraction)
        self._log("settle", context, severity=+1.0)
        self.flush()
