"""Profil-Prüfung: Fehler finden, bevor sie zwei Monate lang wirken.

Alle vier Fehler, die in der Ursprungsfassung erst nach Wochen Betrieb
auffielen, hätte diese Datei beim Start gemeldet:

  * Gleichgewicht an einer Grenze  → „System gesättigt, reagiert nicht mehr"
  * zu starke Kopplung             → dieselbe Meldung, mit Nennung der Ursache
  * Ruhewert über seiner Decke     → „Ruhewert wird stumm gekappt"
  * Bindungs-Boden über dem Start  → „frischer Agent startet als vertraut"

`check()` läuft in Millisekunden und braucht keine Laufzeitdaten. Der Aufruf
gehört in die CI und in `synapsen doctor`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dynamics import equilibrium
from .profile import Profile

ERROR = "Fehler"
WARNING = "Warnung"
NOTE = "Hinweis"

_ORDER = {ERROR: 0, WARNING: 1, NOTE: 2}


@dataclass
class Finding:
    level: str
    where: str
    message: str
    hint: str = ""
    # Verhindert dieser Fehler, dass die Dynamik überhaupt gerechnet werden
    # kann? Eine zu starke Kopplung ist ein Fehler, aber rechenbar; ein Profil
    # ohne Botenstoffe oder eine Division durch null ist es nicht. Nur bei
    # letzteren wird die Gleichgewichtsprüfung übersprungen — sonst würde das
    # Werkzeug, das kaputte Profile sicher melden soll, selbst daran scheitern.
    blocks_dynamics: bool = False

    def __str__(self) -> str:
        base = f"[{self.level}] {self.where}: {self.message}"
        return f"{base}\n    → {self.hint}" if self.hint else base


@dataclass
class Report:
    profile: str
    findings: list[Finding]
    equilibrium_values: dict[str, float]

    @property
    def ok(self) -> bool:
        return not any(f.level == ERROR for f in self.findings)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNING]

    def __str__(self) -> str:
        lines = [f"Profil: {self.profile}"]
        if not self.findings:
            lines.append("Keine Beanstandungen.")
        for f in sorted(self.findings, key=lambda x: _ORDER[x.level]):
            lines.append(str(f))
        if self.equilibrium_values:
            lines.append("")
            lines.append("Gleichgewicht ohne Reiz:")
            for k, v in self.equilibrium_values.items():
                lines.append(f"  {k:<14} {v:7.2f}")
        return "\n".join(lines)


def check(profile: Profile) -> Report:
    """Prüft ein Profil auf strukturelle und dynamische Probleme."""
    f: list[Finding] = []

    _check_hormones(profile, f)
    _check_couplings(profile, f)
    _check_states(profile, f)
    _check_bond(profile, f)
    _check_circadian(profile, f)
    _check_events(profile, f)

    # Die dynamische Prüfung setzt eine tragfähige Struktur voraus. Bei
    # strukturellen Fehlern (kein Botenstoff, per=0, scale=0) würde sie nur
    # einen Traceback erzeugen — das Werkzeug, das kaputte Profile sicher
    # melden soll, darf selbst nicht daran scheitern.
    if any(x.blocks_dynamics for x in f):
        f.append(Finding(
            NOTE, "dynamik",
            "Gleichgewicht nicht berechnet — die Struktur trägt noch nicht."))
        return Report(profile.name, f, {})

    eq = _check_equilibrium(profile, f)
    return Report(profile.name, f, eq.values)


# ---------------------------------------------------------------------------


def _check_hormones(p: Profile, f: list[Finding]) -> None:
    if not p.hormones:
        f.append(Finding(ERROR, "hormones", "Profil enthält keine Botenstoffe.",
                         blocks_dynamics=True))
        return

    for name, spec in p.hormones.items():
        where = f"hormones.{name}"

        if spec.decay <= 0:
            f.append(Finding(
                ERROR, where,
                f"Zerfallsrate ist {spec.decay:g} — der Wert kehrt nie zum Ruhewert zurück.",
                "Zerfall muss größer als 0 sein. 0.2 = träge, 0.8 = flüchtig.",
                blocks_dynamics=True))
        elif spec.decay > 5.0:
            f.append(Finding(
                WARNING, where,
                f"Zerfallsrate {spec.decay:g} bedeutet eine Halbwertszeit unter "
                f"{0.7 / spec.decay * 60:.0f} Minuten.",
                "So kurzlebig, dass Reize praktisch keine Nachwirkung haben."))

        if spec.ceiling <= spec.floor:
            f.append(Finding(
                ERROR, where,
                f"Decke ({spec.ceiling:g}) liegt nicht über dem Boden ({spec.floor:g}).",
                blocks_dynamics=True))

        if not (spec.floor <= spec.baseline <= spec.ceiling):
            f.append(Finding(
                ERROR, where,
                f"Ruhewert {spec.baseline:g} liegt außerhalb von "
                f"[{spec.floor:g}, {spec.ceiling:g}].", blocks_dynamics=True))

        cap = spec.baseline_ceiling
        if cap is not None:
            if cap < spec.baseline:
                f.append(Finding(
                    ERROR, where,
                    f"Ruhewert-Decke {cap:g} liegt unter dem Ruhewert {spec.baseline:g} — "
                    "der Ruhewert wird beim Start stumm gekappt."))
            if cap > spec.ceiling:
                f.append(Finding(
                    WARNING, where,
                    f"Ruhewert-Decke {cap:g} liegt über der Wert-Decke {spec.ceiling:g}.",
                    "Wirkungslos: der Wert wird ohnehin vorher gekappt."))
        if spec.baseline_floor > spec.baseline:
            f.append(Finding(
                ERROR, where,
                f"Ruhewert-Boden {spec.baseline_floor:g} liegt über dem "
                f"Ruhewert {spec.baseline:g}."))


def _check_couplings(p: Profile, f: list[Finding]) -> None:
    for i, c in enumerate(p.couplings):
        where = f"couplings[{i}] {c.source}→{c.target}"

        if c.source not in p.hormones:
            f.append(Finding(ERROR, where, f"Unbekannte Quelle {c.source!r}.",
                             blocks_dynamics=True))
            continue
        if c.target not in p.hormones:
            f.append(Finding(ERROR, where, f"Unbekanntes Ziel {c.target!r}.",
                             blocks_dynamics=True))
            continue
        if c.per == 0:
            f.append(Finding(ERROR, where, "per darf nicht 0 sein (Division).",
                             blocks_dynamics=True))
            continue

        target = p.hormones[c.target]
        source = p.hormones[c.source]

        # Wie weit verschiebt diese Kopplung den Ruhewert, wenn die Quelle
        # ihren Höchstwert erreicht?
        reach = (source.ceiling - c.threshold) / c.per
        shift = reach * c.gain / target.decay if target.decay > 0 else float("inf")
        span = target.ceiling - target.floor

        if abs(shift) > span:
            f.append(Finding(
                ERROR, where,
                f"Bei maximaler Quelle verschiebt die Kopplung das Ziel um {shift:+.0f} — "
                f"mehr als dessen gesamter Wertebereich ({span:g}).",
                f"Das Ziel klebt dann an einer Grenze. Setze gain auf höchstens "
                f"{abs(target.decay * span / reach):.1f}."))
        elif abs(shift) > span * 0.5:
            f.append(Finding(
                WARNING, where,
                f"Bei maximaler Quelle verschiebt die Kopplung das Ziel um {shift:+.0f} "
                f"({abs(shift) / span * 100:.0f} % des Wertebereichs).",
                "Sehr stark. Prüfe, ob das Ziel noch auf eigene Reize reagieren kann."))

        if c.source == c.target and c.gain > 0:
            f.append(Finding(
                ERROR, where,
                "Selbstverstärkende Kopplung — der Wert läuft davon.",
                "Nur negative Selbstkopplung ist stabil."))

    _check_cycles(p, f)


def _check_cycles(p: Profile, f: list[Finding]) -> None:
    """Findet verstärkende Rückkopplungsschleifen.

    Eine Schleife mit insgesamt positivem Vorzeichen ist eine Aufschaukelung:
    A hebt B, B hebt A. Eine Schleife mit negativem Vorzeichen reguliert.
    """
    edges: dict[str, list[tuple[str, float]]] = {}
    for c in p.couplings:
        if c.source in p.hormones and c.target in p.hormones:
            edges.setdefault(c.source, []).append((c.target, c.gain))

    seen: set[tuple[str, ...]] = set()

    def walk(start: str, node: str, sign: float, path: list[str]) -> None:
        if len(path) > len(p.hormones):
            return
        for nxt, gain in edges.get(node, []):
            new_sign = sign * (1 if gain > 0 else -1)
            if nxt == start:
                key = tuple(sorted(path))
                if new_sign > 0 and key not in seen:
                    seen.add(key)
                    f.append(Finding(
                        NOTE, "couplings",
                        "Verstärkende Schleife: " + " → ".join(path + [start]) + ".",
                        "Zwei dämpfende Kopplungen hintereinander wirken zusammen "
                        "verstärkend — der Puffer baut sich selbst ab. Meist gewollt "
                        "(das ist die Stressspirale), aber sie muss gebändigt sein: "
                        "das Gleichgewicht unten zeigt, ob sie es ist."))
            elif nxt not in path:
                walk(start, nxt, new_sign, path + [nxt])

    for h in p.hormones:
        walk(h, h, 1.0, [h])


def _check_states(p: Profile, f: list[Finding]) -> None:
    special = {"_const", "_adenosine", "_morning"}
    names: set[str] = set()

    for st in p.states:
        where = f"states.{st.name}"
        if st.name in names:
            f.append(Finding(ERROR, where, "Zustandsname doppelt vergeben."))
        names.add(st.name)

        if st.scale == 0:
            f.append(Finding(ERROR, where, "scale darf nicht 0 sein (Division).",
                             blocks_dynamics=True))

        for key in list(st.weights) + list(st.invert):
            if key not in p.hormones and key not in special:
                f.append(Finding(
                    ERROR, where,
                    f"Bezieht sich auf {key!r}, das im Profil nicht existiert.",
                    f"Bekannt: {', '.join(sorted(p.hormones))}."))

        if not st.weights and not st.invert:
            f.append(Finding(WARNING, where, "Zustand ohne jede Gewichtung — immer 0."))

        if st.valence not in ("positive", "negative", "neutral"):
            f.append(Finding(
                ERROR, where,
                f"valence {st.valence!r} ist keins von positive/negative/neutral."))

    if p.states and not any(s.valence == "positive" for s in p.states):
        f.append(Finding(
            NOTE, "states", "Kein positiver Zustand definiert.",
            "`dominant('positive')` liefert dann nie etwas."))


def _check_bond(p: Profile, f: list[Finding]) -> None:
    cfg = p.bond
    if not cfg:
        return

    start = float(cfg.get("start", 50.0))
    floor = float(cfg.get("floor", 0.0))
    drives = cfg.get("drives")

    if floor > start:
        f.append(Finding(
            NOTE, "bond",
            f"Boden ({floor:g}) liegt über dem Startwert ({start:g}).",
            "Wird als Erinnerungswert behandelt: er greift erst, wenn die Bindung "
            "tatsächlich so hoch war. In der Ursprungsfassung sprang ein frischer "
            "Agent dadurch sofort auf 'sehr vertraut'."))

    if drives and drives not in p.hormones:
        f.append(Finding(
            ERROR, "bond.drives",
            f"Bindung soll {drives!r} steuern, das es im Profil nicht gibt."))

    if float(cfg.get("decay_per_hour", 1.0)) <= 0:
        f.append(Finding(
            WARNING, "bond",
            "Bindung zerfällt nicht — sie kann nur wachsen.",
            "Ohne Abkühlung wird der Wert über Monate bedeutungslos."))


def _check_circadian(p: Profile, f: list[Finding]) -> None:
    covered = [0] * 24
    for i, (start, end, deltas) in enumerate(p.circadian):
        where = f"circadian[{i}]"
        if not (0 <= start <= 23 and 0 <= end <= 24):
            f.append(Finding(ERROR, where, f"Stundenbereich {start}–{end} ist ungültig."))
            continue
        hours = range(start, end) if start < end else \
            list(range(start, 24)) + list(range(0, end))
        for h in hours:
            covered[h % 24] += 1
        for name in deltas:
            if name not in p.hormones:
                f.append(Finding(
                    ERROR, where, f"Verschiebt {name!r}, das im Profil nicht existiert."))

    overlapping = [h for h, n in enumerate(covered) if n > 1]
    if overlapping:
        f.append(Finding(
            WARNING, "circadian",
            f"Überlappende Zeitfenster bei Stunde {', '.join(map(str, overlapping))}.",
            "Die Verschiebungen addieren sich dort auf."))


def _check_events(p: Profile, f: list[Finding]) -> None:
    if not p.events:
        f.append(Finding(
            NOTE, "events", "Profil definiert keine benannten Ereignisse.",
            "Ohne sie muss der Aufrufer einzelne Botenstoffe setzen — das "
            "bindet ihn an dieses eine Profil."))
        return
    for name, spec in p.events.items():
        for key in spec:
            if key == "severity":
                continue
            if key not in p.hormones:
                f.append(Finding(
                    ERROR, f"events.{name}",
                    f"Verändert {key!r}, das dieses Profil nicht kennt.",
                    f"Bekannt: {', '.join(sorted(p.hormones))}."))
        if not any(k != "severity" for k in spec):
            f.append(Finding(WARNING, f"events.{name}", "Ereignis ohne Wirkung."))


def _check_equilibrium(p: Profile, f: list[Finding]):
    eq = equilibrium(p)

    if not eq.converged:
        f.append(Finding(
            ERROR, "dynamik",
            f"Das System kommt nicht zur Ruhe (Restbewegung {eq.residual:.3g} "
            "nach 30 simulierten Tagen).",
            "Meist eine zu starke oder aufschaukelnde Kopplung."))
        return eq

    for bound in eq.at_bounds:
        name = bound.split("=")[0]
        f.append(Finding(
            ERROR, "dynamik",
            f"Ohne jeden Reiz landet {bound} — das System ist dort gesättigt.",
            f"Reize auf {name} bleiben wirkungslos, weil die Grenze sie auffängt. "
            "Genau dieser Zustand lag in KIRAs Betrieb vor (Cortisol 0.0, "
            "Serotonin an der Decke)."))

    for name, spec in p.hormones.items():
        value = eq.values[name]
        span = spec.ceiling - spec.floor
        drift = value - spec.baseline
        if span > 0 and abs(drift) > span * 0.25:
            f.append(Finding(
                WARNING, "dynamik",
                f"{name} ruht bei {value:.1f}, weit weg vom gesetzten "
                f"Ruhewert {spec.baseline:g} (Abweichung {drift:+.1f}).",
                "Die Kopplungen ziehen den tatsächlichen Ruhepunkt stark weg. "
                "Entweder den Ruhewert anpassen oder die Kopplung abschwächen."))

    return eq
