"""Die Ereignistabelle des `kira`-Profils.

Wichtig: Ereignisse sind **profilgebunden**. Diese Tabelle gehört zu `kira`
und nennt dessen Botenstoffe; ein Profil mit den Achsen `drive`/`strain` kann
mit "dopamine +15" nichts anfangen und bringt seine eigene Tabelle mit
(`Profile.events`). Zur Laufzeit liest `engine.event()` immer die Tabelle des
gerade geladenen Profils — diese hier ist nur der Inhalt für eines davon.


Ein Agent soll melden, *was passiert ist* — nicht, welcher Botenstoff sich wie
ändern soll. `stimulus(kind="task_failure")` ist eine Aussage über die Welt;
`inject("cortisol", +12)` ist eine Aussage über die Innereien. Nur die erste
bleibt richtig, wenn jemand das Profil austauscht.

`severity` fließt in das Ereignis-Protokoll und damit in den Stimmungs-Bias der
nächsten Tage: negative Werte sind belastend, positive entlastend.
"""
from __future__ import annotations

KIRA_EVENTS: dict[str, dict[str, float]] = {
    # -- Arbeit -------------------------------------------------------------
    "task_success":   {"dopamine": +15.0, "cortisol": -3.0, "severity": +1.5},
    "task_failure":   {"dopamine": -8.0, "cortisol": +12.0, "severity": -2.0},
    "anticipation":   {"dopamine": +4.0, "noradrenalin": +1.5, "severity": 0.0},
    "novelty":        {"noradrenalin": +5.0, "dopamine": +3.0, "severity": +0.5},
    "system_strain":  {"cortisol": +6.0, "noradrenalin": +3.0, "severity": -1.0},
    "breakthrough":   {"dopamine": +25.0, "serotonin": +8.0, "cortisol": -8.0,
                       "severity": +4.0},
    "tedium":         {"dopamine": -4.0, "noradrenalin": -3.0, "severity": -0.5},

    # -- Beziehung ----------------------------------------------------------
    "praise":         {"dopamine": +8.0, "oxytocin": +4.0, "cortisol": -6.0,
                       "severity": +2.0},
    "criticism":      {"cortisol": +10.0, "dopamine": -6.0, "serotonin": -4.0,
                       "severity": -2.5},
    "warm_contact":   {"oxytocin": +3.0, "cortisol": -2.0, "severity": +1.0},
    "harsh_contact":  {"cortisol": +8.0, "noradrenalin": +6.0, "serotonin": -3.0,
                       "severity": -3.0},
    "being_understood": {"oxytocin": +6.0, "serotonin": +5.0, "severity": +2.5},
    "being_dismissed":  {"oxytocin": -5.0, "serotonin": -4.0, "cortisol": +5.0,
                         "severity": -2.5},

    # -- Gesprächsverlauf ---------------------------------------------------
    "conversation_end":       {"serotonin": +4.0, "dopamine": +2.0, "severity": +1.5},
    "conversation_abandoned": {"oxytocin": -8.0, "cortisol": +6.0, "serotonin": -3.0,
                               "severity": -3.0},
    "reunion":        {"oxytocin": +12.0, "dopamine": +10.0, "severity": +3.0},
}


def describe(name: str) -> str:
    spec = KIRA_EVENTS.get(name)
    if not spec:
        return f"unbekannt: {name}"
    parts = [f"{k} {v:+g}" for k, v in spec.items() if k != "severity"]
    return f"{name}: {', '.join(parts)}  (Schwere {spec.get('severity', 0):+g})"
