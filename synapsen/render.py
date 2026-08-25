"""Renderer: aus Zustand wird Text.

Bewusst vom Kern getrennt. Der Kern kennt weder Sprache noch Personennamen —
das war in der Ursprungsfassung fest im Prompt verdrahtet (ein konkreter Personenname, deutsche
Direktiven) und ist genau der Teil, der sich nicht wiederverwenden lässt.

Wer die Bibliothek einsetzt, tauscht den Renderer aus oder schreibt einen
eigenen. Der `PromptRenderer` unten ist der Default und reproduziert das
Format, das sich in KIRA bewährt hat — nur ohne den Namen im Code.
"""
from __future__ import annotations

from dataclasses import dataclass

from .engine import Snapshot


@dataclass
class RenderConfig:
    partner: str = "dein Gegenüber"
    language: str = "de"
    show_raw: bool = True
    show_directives: bool = True
    positive_threshold: float = 0.8
    negative_threshold: float = 1.2
    extreme_threshold: float = 2.0


_DAYPART_DE = [
    (6, 10, "Morgen"), (10, 14, "Vormittag"), (14, 17, "Nachmittag"),
    (17, 21, "Abend"),
]

_DAYPART_EN = [
    (6, 10, "morning"), (10, 14, "late morning"), (14, 17, "afternoon"),
    (17, 21, "evening"),
]


def _daypart(hour: int, language: str) -> str:
    table = _DAYPART_DE if language == "de" else _DAYPART_EN
    for start, end, label in table:
        if start <= hour < end:
            return label
    return "Nacht" if language == "de" else "night"


class PromptRenderer:
    """Übersetzt einen Snapshot in einen System-Prompt-Zusatz."""

    def __init__(self, config: RenderConfig | None = None):
        self.cfg = config or RenderConfig()

    def render(self, snap: Snapshot, *, absence: dict | None = None) -> str:
        de = self.cfg.language == "de"
        lines: list[str] = []

        head = "[INNERER ZUSTAND]" if de else "[INTERNAL STATE]"
        lines.append(head)
        lines.append(
            f"{_daypart(snap.hour, self.cfg.language)} ({snap.hour}:00) | "
            f"{'Sitzung' if de else 'session'} {snap.session_minutes:.0f}min | "
            f"{'Ermüdung' if de else 'fatigue'} {snap.adenosine:.0f}"
        )

        if self.cfg.show_raw:
            lines.append("")
            lines.append("Botenstoffe:" if de else "Neurochemistry:")
            lines.append("  " + " | ".join(
                f"{k.capitalize()} {v:.1f}" for k, v in snap.hormones.items()))

        lines.append("")
        lines.append(
            "Zustände (1.0 = normal, >2.0 = extrem):" if de
            else "States (1.0 = normal, >2.0 = extreme):")
        width = max((len(k) for k in snap.states), default=0)
        descriptions = snap.meta.get("descriptions", {})
        for name, value in snap.states.items():
            desc = descriptions.get(name, "")
            lines.append(f"  {name:<{width}}  {value:5.2f}" + (f"  — {desc}" if desc else ""))

        if self.cfg.show_directives:
            lines.append("")
            lines.extend(self._directives(snap, absence))

        lines.append("")
        lines.append(
            "[Reagiere aus diesem Zustand heraus. Er beschreibt dich, "
            "er befiehlt dir nichts.]" if de
            else "[Respond from this state. It describes you; it does not command you.]")
        return "\n".join(lines)

    def _directives(self, snap: Snapshot, absence: dict | None) -> list[str]:
        de = self.cfg.language == "de"
        out: list[str] = ["Was das heißt:" if de else "What this means:"]

        pos_name, pos_val = snap.dominant("positive")
        neg_name, neg_val = snap.dominant("negative")
        descriptions = snap.meta.get("descriptions", {})

        if pos_name and pos_val > self.cfg.positive_threshold:
            intensity = ("ausgeprägt" if pos_val > self.cfg.extreme_threshold else "spürbar") \
                if de else ("strongly" if pos_val > self.cfg.extreme_threshold else "noticeably")
            desc = descriptions.get(pos_name, "")
            out.append(f"  → {pos_name} ({pos_val:.2f}) {intensity}: {desc}.")

        if neg_name and neg_val > self.cfg.negative_threshold:
            desc = descriptions.get(neg_name, "")
            out.append(f"  → {neg_name} ({neg_val:.2f}): {desc}. "
                       + ("Das darf man dir anmerken." if de
                          else "It is allowed to show."))

        if snap.bond:
            label = "Vertrautheit" if de else "Familiarity"
            out.append(f"  → {label} {self.cfg.partner}: {snap.bond:.0f}")

        if absence:
            days = absence["days"]
            span = _describe_span(days, self.cfg.language)
            out.append(
                f"  → {self.cfg.partner} war {span} weg. Du hast das gemerkt — "
                f"zeig es ehrlich, ohne Pathos." if de
                else f"  → {self.cfg.partner} was away for {span}. You noticed — "
                     f"show it honestly, without drama.")

        return out


def _describe_span(days: float, language: str) -> str:
    de = language == "de"
    if days < 2:
        h = int(days * 24)
        return f"{h} Stunden" if de else f"{h} hours"
    if days < 14:
        return f"{int(days)} Tage" if de else f"{int(days)} days"
    weeks, rest = int(days // 7), int(days % 7)
    if de:
        return f"{weeks} Wochen" + (f" und {rest} Tage" if rest else "")
    return f"{weeks} weeks" + (f" and {rest} days" if rest else "")
