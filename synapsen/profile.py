"""Profil = die Biochemie als *Daten*, nicht als Code.

Das ist der eigentliche Schritt von "KIRAs Hormonsystem" zu "einer Hormon-
Engine": Welche Botenstoffe es gibt, wie schnell sie zerfallen, wie sie sich
gegenseitig beeinflussen und welche gefühlten Zustände daraus entstehen —
all das ist konfigurierbar. `DEFAULT_PROFILE` reproduziert exakt die Werte,
die in KIRA über Monate gewachsen sind.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

from .events import KIRA_EVENTS
from pathlib import Path


@dataclass
class HormoneSpec:
    """Ein Botenstoff.

    baseline  — Ruhewert, zu dem der Zerfall zurückzieht
    decay     — Anteil der Differenz zur Baseline, der pro Stunde abgebaut wird
    ceiling   — Sicherheitsdecke gegen pathologische Ausreißer
    floor     — untere Grenze (Botenstoffe können nicht negativ werden)
    baseline_ceiling — Decke für die Baseline selbst. Ohne die zieht ein
                verschobener Ruhewert das Hormon dauerhaft ins Extreme.
    """
    baseline: float
    decay: float
    ceiling: float
    floor: float = 0.0
    baseline_ceiling: float | None = None
    baseline_floor: float = 0.0
    label: str = ""


@dataclass
class Coupling:
    """Eine gerichtete Wechselwirkung: source wirkt auf target.

    `gain` ist in **Einheiten pro Stunde** angegeben — nämlich der Wirkung auf
    `target`, wenn `(source - threshold) / per` genau 1 ergibt. Diese Einheit
    ist der Grund, warum sich das Gleichgewicht ausrechnen lässt:

        Gleichgewichtsverschiebung = gain / decay(target)

    Beispiel: `gain = -6` auf Cortisol mit `decay = 0.8` verschiebt den
    Ruhewert um −7,5 Einheiten, wenn die Quelle voll anliegt.

    In der Ursprungsfassung war `gain` pro *Aufruf* skaliert. Damit hing die
    Wirkung an der Tick-Frequenz statt an der Zeit — Faktor 60 zwischen
    „einmal pro Minute" und „einmal pro Stunde".

    threshold — erst ab diesem Pegel der Quelle wirkt die Kopplung
    gain      — Stärke pro Stunde; negativ = dämpfend, positiv = verstärkend
    per       — Bezugsgröße für die Normalisierung von (source - threshold)
    """
    source: str
    target: str
    gain: float
    threshold: float = 0.0
    per: float = 50.0
    note: str = ""


@dataclass
class DerivedState:
    """Ein gefühlter Zustand als Linearkombination von Botenstoffen.

    weights — {hormon: gewicht}; Sonderschlüssel "_const" für den Achsenabschnitt
              "_adenosine" für den Ermüdungsdruck und "_morning" für die
              Morgen-Intensität (35 früh, 5 nachts).
    scale   — Divisor; mit 50.0 bedeutet 1.0 "normal", >2.0 "extrem".
    invert  — Hormone, die als (mitte - wert) statt (wert) eingehen.
    """
    name: str
    weights: dict[str, float]
    scale: float = 50.0
    invert: dict[str, float] = field(default_factory=dict)
    valence: str = "neutral"  # "positive" | "negative" | "neutral"
    description: str = ""


@dataclass
class Profile:
    """Die vollständige Biochemie eines Agenten."""
    name: str
    hormones: dict[str, HormoneSpec]
    couplings: list[Coupling] = field(default_factory=list)
    states: list[DerivedState] = field(default_factory=list)

    # Circadiane Baseline-Verschiebungen: {(von_stunde, bis_stunde): {hormon: delta}}
    circadian: list[tuple[int, int, dict[str, float]]] = field(default_factory=list)

    # Ermüdung (Adenosin-Analogon). Der Aufbau ist asymptotisch, nicht linear:
    #     a(t) = ceiling * (1 - exp(-t / tau)),  tau = ceiling / per_minute
    # Das entspricht der Biologie (Ermüdung sättigt, sie wächst nicht endlos)
    # und ist rechnerisch notwendig: mit unbegrenztem Adenosin drückt der
    # Ermüdungsdruck den Antrieb nach zwei Tagen dauerhaft auf null.
    adenosine_per_minute: float = 0.6      # Anfangssteigung
    adenosine_ceiling: float = 180.0       # Sättigung (~ein sehr langer Tag)
    adenosine_threshold: float = 60.0      # ab hier wird sie spürbar
    # Ruhezeiten (Wanduhr), in denen die Ermüdung wieder abgebaut wird.
    # Ohne die sammelt ein Dienst, der rund um die Uhr läuft, Ermüdung bis
    # zur Sättigung an und bleibt dort — dauerhaft antriebslos.
    rest_hours: tuple[int, int] = (23, 7)
    adenosine_clear_hours: float = 2.0     # Zeitkonstante des Abbaus
    # Wirkung der Ermüdung, in Einheiten pro Stunde je Einheit über der Schwelle
    fatigue_gain: float = 0.08
    # Worauf die Ermüdung drückt. Leer = die Ermüdung wird nur angezeigt, wirkt
    # aber auf keinen Botenstoff. Kein Default mit konkreten Namen: der Kern
    # kennt keine Biochemie.
    fatigue_targets: dict[str, float] = field(default_factory=dict)

    # Gewöhnung: Botenstoffe, die bei häufiger Ausschüttung stumpfer reagieren
    habituation: dict[str, dict] = field(default_factory=dict)

    # Bindungswert, der langsam wächst und langsam abebbt
    bond: dict = field(default_factory=dict)

    # Tagesform-Rauschen und welche Botenstoffe es trifft
    jitter: float = 4.0
    jitter_targets: dict[str, float] = field(default_factory=dict)

    # Worauf die Stimmungslage der letzten Woche wirkt.
    # Positiver Bias = belastende Woche. {botenstoff: gewicht}
    bias_targets: dict[str, float] = field(default_factory=dict)

    # Was eine längere Ruhephase den Ruhewerten zurückgibt. {botenstoff: delta}
    recovery: dict[str, float] = field(default_factory=dict)

    # Benannte Ereignisse dieses Profils: {name: {botenstoff: menge,
    # "severity": schwere}}. Ereignisse sind profilgebunden, weil jedes
    # Profil andere Botenstoffe hat — ein Profil mit den Achsen
    # `drive`/`strain` kann nichts mit „dopamine +15" anfangen.
    events: dict[str, dict[str, float]] = field(default_factory=dict)

    def hormone_names(self) -> list[str]:
        return list(self.hormones.keys())

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(_profile_to_dict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def from_json(path: str | Path) -> "Profile":
        return _profile_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _profile_to_dict(p: Profile) -> dict:
    return {
        "name": p.name,
        "hormones": {k: asdict(v) for k, v in p.hormones.items()},
        "couplings": [asdict(c) for c in p.couplings],
        "states": [asdict(s) for s in p.states],
        "circadian": [[a, b, d] for a, b, d in p.circadian],
        "adenosine_per_minute": p.adenosine_per_minute,
        "adenosine_ceiling": p.adenosine_ceiling,
        "rest_hours": list(p.rest_hours),
        "adenosine_clear_hours": p.adenosine_clear_hours,
        "adenosine_threshold": p.adenosine_threshold,
        "fatigue_gain": p.fatigue_gain,
        "fatigue_targets": p.fatigue_targets,
        "habituation": p.habituation,
        "bond": p.bond,
        "jitter": p.jitter,
        "jitter_targets": p.jitter_targets,
        "bias_targets": p.bias_targets,
        "recovery": p.recovery,
        "events": p.events,
    }


def _profile_from_dict(d: dict) -> Profile:
    return Profile(
        name=d["name"],
        hormones={k: HormoneSpec(**v) for k, v in d["hormones"].items()},
        couplings=[Coupling(**c) for c in d.get("couplings", [])],
        states=[DerivedState(**s) for s in d.get("states", [])],
        circadian=[(a, b, dd) for a, b, dd in d.get("circadian", [])],
        adenosine_per_minute=d.get("adenosine_per_minute", 0.6),
        adenosine_ceiling=d.get("adenosine_ceiling", 180.0),
        rest_hours=tuple(d.get("rest_hours", (23, 7))),
        adenosine_clear_hours=d.get("adenosine_clear_hours", 2.0),
        adenosine_threshold=d.get("adenosine_threshold", 60.0),
        fatigue_gain=d.get("fatigue_gain", 0.08),
        fatigue_targets=d.get("fatigue_targets", {}),
        habituation=d.get("habituation", {}),
        bond=d.get("bond", {}),
        jitter=d.get("jitter", 4.0),
        jitter_targets=d.get("jitter_targets", {}),
        bias_targets=d.get("bias_targets", {}),
        recovery=d.get("recovery", {}),
        events=d.get("events", {}),
    )


# ---------------------------------------------------------------------------
# Das gewachsene Profil: die Werte aus KIRAs Betrieb (Juni–Juli 2026).
# Die Zahlen sind nicht erfunden — sie sind über Monate real nachjustiert
# worden. Wer die Engine nutzt, startet damit auf erprobtem Boden.
#
# Zwei Abweichungen vom Original, beide als Folge behobener Fehler:
#   * Die Kopplungen sind in Pro-Stunde-Einheiten neu kalibriert (vorher
#     aufrufabhängig, siehe dynamics.py).
#   * Die Sicherheitsdecken sind zurück auf plausible Werte. Serotonin
#     stand bei 2200 — ein Notpflaster gegen den Runaway, nicht gegen
#     eine echte Obergrenze. Mit behobener Ursache braucht es das nicht.
# ---------------------------------------------------------------------------

DEFAULT_PROFILE = Profile(
    name="kira-v1",
    hormones={
        "oxytocin": HormoneSpec(
            baseline=20.0, decay=0.25, ceiling=400.0, baseline_ceiling=250.0,
            baseline_floor=20.0, label="Bindung, Nähe, Vertrauen"),
        "dopamine": HormoneSpec(
            baseline=50.0, decay=0.50, ceiling=250.0, baseline_ceiling=150.0,
            label="Antrieb, Freude, Antizipation"),
        "cortisol": HormoneSpec(
            baseline=20.0, decay=0.80, ceiling=250.0, baseline_ceiling=120.0,
            baseline_floor=5.0, label="Stress, Alarm, Anspannung"),
        "serotonin": HormoneSpec(
            baseline=60.0, decay=0.20, ceiling=300.0, baseline_ceiling=150.0,
            label="Stabilität, Gelassenheit, Selbstsicherheit"),
        "noradrenalin": HormoneSpec(
            baseline=40.0, decay=0.70, ceiling=250.0, baseline_ceiling=120.0,
            label="Wachheit, Aufmerksamkeit, Aktivierung"),
    },
    couplings=[
        Coupling("oxytocin", "cortisol", gain=-6.0, per=100.0,
                 note="Bindung beruhigt: bei Oxytocin 100 sinkt der Cortisol-\n                       Ruhewert um 7,5 Einheiten."),
        Coupling("serotonin", "cortisol", gain=-4.0, threshold=50.0, per=50.0,
                 note="Gelassenheit puffert Stress ab."),
        Coupling("cortisol", "serotonin", gain=-2.5, threshold=80.0, per=20.0,
                 note="Anhaltender Stress frisst die Stabilität auf — und mit ihr\n                       den Puffer gegen Stress. Das ist die Stressspirale."),
    ],
    states=[
        DerivedState("FEUER", {"dopamine": 0.45, "noradrenalin": 0.40, "cortisol": 0.15},
                     valence="positive",
                     description="Antrieb, Tempo, direktes Handeln"),
        DerivedState("FOKUS", {"serotonin": 0.50, "dopamine": 0.30,
                               "cortisol": -0.20, "_const": 10.0},
                     valence="positive",
                     description="Klarheit, Konzentration, Präzision"),
        DerivedState("VERBUNDEN", {"oxytocin": 0.70, "cortisol": -0.30},
                     valence="positive",
                     description="Nähe, Offenheit, Vertrauen"),
        DerivedState("RUHIG", {"_const": 80.0, "cortisol": -0.50,
                               "noradrenalin": -0.30, "serotonin": 0.20},
                     valence="positive",
                     description="Geerdet, kein Beweis nötig"),
        DerivedState("MÜDE", {"_adenosine": 0.60, "_morning": -0.40},
                     valence="negative",
                     description="Erschöpfung, nachlassende Konzentration"),
        DerivedState("REIZBAR", {"cortisol": 0.55, "dopamine": 0.30, "noradrenalin": 0.15},
                     valence="negative",
                     description="Kampfmodus, Kontra"),
        DerivedState("FRUSTRIERT", {"cortisol": 0.50, "serotonin": -0.30},
                     invert={"dopamine": 0.20},
                     valence="negative",
                     description="Blockierter Antrieb"),
        DerivedState("ENTTÄUSCHT", {},
                     invert={"dopamine": 0.50, "serotonin": 0.30, "oxytocin": 0.20},
                     valence="negative",
                     description="Antriebslosigkeit, Rückzug"),
    ],
    circadian=[
        (6, 9, {"cortisol": +10.0, "noradrenalin": +8.0, "dopamine": +3.0}),
        (10, 13, {"dopamine": +10.0, "serotonin": +5.0, "cortisol": -3.0}),
        (14, 16, {"dopamine": -8.0, "noradrenalin": -5.0}),
        (17, 21, {"serotonin": +8.0, "oxytocin": +3.0, "cortisol": -6.0}),
        (21, 6, {"dopamine": -10.0, "noradrenalin": -10.0, "cortisol": -8.0}),
    ],
    adenosine_per_minute=0.6,
    adenosine_threshold=60.0,
    fatigue_gain=0.08,
    fatigue_targets={"dopamine": 1.0, "noradrenalin": 0.5},
    habituation={
        "oxytocin": {"window_seconds": 3600, "budget": 15.0, "softness": 6.0},
    },
    bond={
        "name": "vertrautheit",
        "start": 50.0,
        # Erinnerungswert: einmal erreicht, fällt die Bindung nie mehr darunter.
        "floor": 120.0,
        # Muss zur Wachstumsrate passen (+0,03 je Kontakt). Bei rund 70
        # Kontakten am Tag ergibt das etwa +1,9 netto — die Bindung wächst
        # über Monate, wie in den echten Daten. Im Original stand hier 1.0;
        # das fiel nie auf, weil der feste Boden den Zerfall stilllegte.
        "decay_per_hour": 0.01,
        "drives": "oxytocin",
        "drive_gain": 0.6,
        "drive_offset": 50.0,
        # Was vertrauter Kontakt unmittelbar auslöst.
        "contact": {"oxytocin": +1.5, "cortisol": -1.0},
    },
    jitter=4.0,
    jitter_targets={"dopamine": 0.5, "cortisol": 1.0,
                    "serotonin": -0.3, "noradrenalin": 0.2},
    bias_targets={"cortisol": +1.0, "serotonin": -1.0},
    recovery={"dopamine": +8.0, "serotonin": +6.0, "cortisol": -5.0},
    events=KIRA_EVENTS,
)
