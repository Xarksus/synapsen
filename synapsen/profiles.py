"""Mitgelieferte Profile.

Drei Stück, absichtlich sehr verschieden. Solange es nur eines gäbe, wäre
„konfigurierbar" eine Behauptung — erst ein Profil ohne Bindung, ohne
Tagesrhythmus und mit ganz anderen Achsen beweist, dass der Kern wirklich
nichts über die Biochemie weiß.

    from synapsen.profiles import get, names
    engine = HomeostasisEngine(get("focus"))
"""
from __future__ import annotations

from .profile import (DEFAULT_PROFILE, Coupling, DerivedState, HormoneSpec,
                      Profile)

# ---------------------------------------------------------------------------
# focus — ein nüchterner Arbeitszustand
#
# Keine Bindung, keine Beziehung, kein Tagesrhythmus. Zwei Achsen: Antrieb und
# Unruhe. Gedacht für Agenten, die keine Persona haben, aber trotzdem nicht
# gleichförmig sein sollen — ein Coding-Agent, der nach dem fünften
# fehlgeschlagenen Build hörbar knapper wird.
# ---------------------------------------------------------------------------

FOCUS = Profile(
    name="focus",
    hormones={
        "drive": HormoneSpec(
            baseline=55.0, decay=0.45, ceiling=150.0, baseline_ceiling=90.0,
            label="Antrieb, Bereitschaft weiterzumachen"),
        "strain": HormoneSpec(
            baseline=12.0, decay=0.65, ceiling=150.0, baseline_ceiling=70.0,
            label="Anspannung durch Fehlschläge und Reibung"),
    },
    couplings=[
        Coupling("strain", "drive", gain=-5.0, threshold=40.0, per=30.0,
                 note="Anhaltende Reibung frisst den Antrieb auf."),
    ],
    states=[
        DerivedState("KLAR", {"drive": 0.9, "strain": -0.5}, scale=50.0,
                     valence="positive",
                     description="arbeitsfähig, sachlich, geduldig"),
        DerivedState("ANGESPANNT", {"strain": 1.0}, scale=50.0,
                     valence="negative",
                     description="knapper im Ton, weniger Umschweife"),
        DerivedState("ERSCHÖPFT", {"_adenosine": 0.7}, invert={"drive": 0.5},
                     scale=50.0, valence="negative",
                     description="Vorschläge werden vorsichtiger, Antworten kürzer"),
    ],
    circadian=[],
    adenosine_per_minute=0.5,
    adenosine_ceiling=150.0,
    adenosine_threshold=70.0,
    fatigue_gain=0.06,
    fatigue_targets={"drive": 1.0},
    rest_hours=(22, 8),
    habituation={},
    bond={},
    jitter=2.0,
    events={
        "task_success":  {"drive": +10.0, "strain": -4.0, "severity": +1.5},
        "task_failure":  {"drive": -5.0, "strain": +12.0, "severity": -2.0},
        "blocked":       {"strain": +18.0, "drive": -8.0, "severity": -3.0},
        "unblocked":     {"strain": -15.0, "drive": +12.0, "severity": +3.0},
        "review_passed": {"drive": +8.0, "strain": -6.0, "severity": +2.0},
        "review_failed": {"strain": +10.0, "drive": -4.0, "severity": -2.0},
        "context_switch": {"strain": +5.0, "drive": -3.0, "severity": -0.5},
        "session_end":   {"strain": -8.0, "severity": +1.0},
    },
)


# ---------------------------------------------------------------------------
# pad — das akademische Standardmodell, in diesem Rahmen ausgedrückt
#
# Pleasure–Arousal–Dominance (Mehrabian/Russell) ist das Modell, auf dem die
# meisten Emotionsschichten für Agenten aufsetzen. Es lässt sich hier
# vollständig abbilden — mit drei Trägern statt fünf, ohne Kopplungen, ohne
# Tagesrhythmus. Das ist der Interoperabilitäts-Beweis: wer PAD gewohnt ist,
# verliert nichts und gewinnt Zerfall, Trägheit und Simulierbarkeit.
#
# Die Skala läuft von 0 bis 100 mit Mittelpunkt 50, was dem üblichen
# PAD-Bereich [-1, +1] entspricht.
# ---------------------------------------------------------------------------

PAD = Profile(
    name="pad",
    hormones={
        "pleasure": HormoneSpec(
            baseline=50.0, decay=0.35, ceiling=100.0, baseline_ceiling=75.0,
            label="Valenz: angenehm bis unangenehm"),
        "arousal": HormoneSpec(
            baseline=50.0, decay=0.60, ceiling=100.0, baseline_ceiling=75.0,
            label="Aktivierung: ruhig bis erregt"),
        "dominance": HormoneSpec(
            baseline=50.0, decay=0.20, ceiling=100.0, baseline_ceiling=75.0,
            label="Kontrolle: unterlegen bis bestimmend"),
    },
    couplings=[],
    states=[
        # Die klassischen PAD-Oktanten, als benannte Zustände.
        DerivedState("FREUDIG", {"pleasure": 0.6, "arousal": 0.4},
                     valence="positive", description="+P +A"),
        DerivedState("GELASSEN", {"pleasure": 0.7, "dominance": 0.3},
                     invert={"arousal": 0.4}, valence="positive",
                     description="+P −A"),
        DerivedState("ÄNGSTLICH", {"arousal": 0.6},
                     invert={"pleasure": 0.5, "dominance": 0.4},
                     valence="negative", description="−P +A −D"),
        DerivedState("VERDROSSEN", {},
                     invert={"pleasure": 0.6, "arousal": 0.2, "dominance": 0.2},
                     valence="negative", description="−P −A"),
    ],
    circadian=[],
    adenosine_per_minute=0.0,
    adenosine_ceiling=0.0,
    fatigue_targets={},
    habituation={},
    bond={},
    jitter=0.0,
    events={
        "reward":     {"pleasure": +15.0, "arousal": +8.0, "dominance": +5.0,
                       "severity": +2.0},
        "punishment": {"pleasure": -15.0, "arousal": +10.0, "dominance": -8.0,
                       "severity": -2.5},
        "threat":     {"arousal": +20.0, "pleasure": -8.0, "dominance": -12.0,
                       "severity": -3.0},
        "mastery":    {"dominance": +15.0, "pleasure": +8.0, "severity": +2.0},
        "loss":       {"pleasure": -12.0, "arousal": -8.0, "dominance": -5.0,
                       "severity": -2.5},
        "calm":       {"arousal": -12.0, "pleasure": +4.0, "severity": +1.0},
    },
)


PROFILES: dict[str, Profile] = {
    "kira": DEFAULT_PROFILE,
    "focus": FOCUS,
    "pad": PAD,
}


def names() -> list[str]:
    return sorted(PROFILES)


def get(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"Unbekanntes Profil: {name!r}. "
                       f"Mitgeliefert: {', '.join(names())}") from None
