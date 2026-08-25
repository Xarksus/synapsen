"""Rückwärtskompatible Brücke für die bestehende KIRA-Installation.

Ziel: KIRA läuft auf der neuen Engine, ohne dass an den ~30 Aufrufstellen in
`gemini_live_provider.py`, `kira_voice_gate.py` und `main.py` etwas geändert
werden muss.

Einbau — eine Zeile in `core/emotions.py` ersetzt die alte Datei:

    from tools.kira_adapter import get_engine
    engine = get_engine()

Danach funktionieren `engine.inject(...)`, `engine.get_prompt_modifier()`,
`engine.on_voice_thorsten(...)` usw. unverändert weiter — nur eben auf dem
korrigierten Kern.

Sobald das läuft, können die Aufrufstellen nach und nach auf `stimulus()`
mit benannten Ereignissen umgestellt werden. Das ist die eigentliche
Verbesserung: `stimulus(kind="tool_failure")` sagt, *was passiert ist*;
`inject("cortisol", +12)` sagt nur, *was sich ändern soll*.
"""
from __future__ import annotations

import os
from pathlib import Path

from synapsen import (DEFAULT_PROFILE, HomeostasisEngine, JsonStore,
                      PromptRenderer, RenderConfig, SqliteJournal)

STATE_FILE = Path(os.path.expanduser("~/.config/kira/hormones.json"))
FREEZE_FILE = Path(os.path.expanduser("~/.config/kira/kira_freeze.json"))
DB_PATH = Path(os.path.expanduser("~/.kira/synapsen.db"))

# Der Name des Gegenübers kommt aus der Umgebung — er gehört nicht in den
# ausgelieferten Code.
PARTNER = os.getenv("KIRA_PARTNER", "du")


class KiraEngine(HomeostasisEngine):
    """Die alte Oberfläche auf dem neuen Kern."""

    def __init__(self) -> None:
        super().__init__(
            DEFAULT_PROFILE,
            store=JsonStore(STATE_FILE),
            journal=SqliteJournal(DB_PATH, create=False),
        )
        self._renderer = PromptRenderer(RenderConfig(partner=PARTNER, language="de"))
        self._absence = self._wake()

    # -- alte Namen ---------------------------------------------------------

    @property
    def vertrautheit(self) -> float:
        return self.bond

    @vertrautheit.setter
    def vertrautheit(self, value: float) -> None:
        self.bond = float(value)

    def get_prompt_modifier(self) -> str:
        text = self._renderer.render(self.snapshot(), absence=self._absence)
        self._absence = None          # Wiedersehen nur einmal erwähnen
        return text

    def on_voice_thorsten(self, sim: float = 1.0) -> None:
        self.reinforce_bond(sim)

    def on_voice_fremd(self, sim: float = 0.0) -> None:
        self.stimulus({"noradrenalin": +3.5}, context="voice:unknown")

    def on_voice_tone(self, lautstaerke: float, schaerfe: float = 0.0) -> None:
        """Vor-sprachliche Wahrnehmung: der Klang, nicht die Worte.

        Vergleicht gegen einen gleitenden Normalpegel, reagiert also auf
        *Abweichung* — lauter und härter als sonst.
        """
        if not hasattr(self, "_voice_norm") or self._voice_norm <= 0:
            self._voice_norm = max(0.01, lautstaerke)
        self._voice_norm += (lautstaerke - self._voice_norm) * 0.05
        rel = (lautstaerke - self._voice_norm) / (self._voice_norm + 1e-3)
        rel = max(-1.0, min(2.0, rel))
        sharp = max(0.0, min(1.0, schaerfe))
        hardness = max(0.0, rel) * (0.4 + 0.6 * sharp)
        warmth = max(0.0, 0.2 - rel) * (1.0 - sharp)

        if hardness > 0.15:
            self.stimulus({"noradrenalin": +6.0 * hardness,
                           "cortisol": +5.0 * hardness,
                           "serotonin": -2.5 * hardness},
                          kind="harsh_tone", context="tone:hard",
                          severity=-2.0 * hardness)
            self.strain_bond(hardness)
        elif warmth > 0.10:
            self.stimulus({"oxytocin": +1.0 * warmth,
                           "serotonin": +1.5 * warmth,
                           "noradrenalin": -2.0 * warmth},
                          kind="warm_tone", context="tone:warm",
                          severity=+1.0 * warmth)

    def anticipate(self, staerke: float = 5.0, kontext: str = "") -> None:
        self.stimulus({"dopamine": staerke * 0.8, "noradrenalin": staerke * 0.3},
                      context=kontext or "anticipation")

    def on_conversation_end(self, abrupt: bool = False, kontext: str = "") -> None:
        if abrupt:
            self.stimulus({"oxytocin": -8.0, "cortisol": +6.0, "serotonin": -3.0},
                          kind="conversation_abandoned", context=kontext, severity=-3.0)
        else:
            self.stimulus({"serotonin": +4.0, "dopamine": +2.0},
                          kind="conversation_end", context=kontext, severity=+1.5)

    def beethoven_reset(self, kontext: str = "manueller Reset") -> None:
        self.settle(0.6, context=kontext)

    # -- Freeze / Wakeup über Dateien (wie bisher) --------------------------

    def freeze(self) -> None:
        import json
        FREEZE_FILE.parent.mkdir(parents=True, exist_ok=True)
        FREEZE_FILE.write_text(json.dumps(self.suspend(), indent=2),
                               encoding="utf-8")

    def _wake(self):
        import json
        if not FREEZE_FILE.exists():
            return None
        try:
            snap = json.loads(FREEZE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        result = self.resume(snap)
        try:
            FREEZE_FILE.unlink()
        except OSError:
            pass
        return result

    # -- alte Signatur von inject() (deutsches Schlüsselwort) ---------------

    def inject(self, hormone: str, amount: float, kontext: str = "",
               *, context: str = "") -> float:  # type: ignore[override]
        return super().inject(hormone, amount, context=kontext or context)


_engine: KiraEngine | None = None


def get_engine() -> KiraEngine:
    """Die Engine, beim ersten Aufruf gebaut.

    Ausdrücklich *kein* Singleton auf Modulebene: genau das war in der
    Ursprungsfassung das Problem — ein blosses `import` öffnete Zustandsdatei
    und Datenbank und veränderte den Zustand, noch bevor irgendwer die Engine
    haben wollte.
    """
    global _engine
    if _engine is None:
        _engine = KiraEngine()
    return _engine
