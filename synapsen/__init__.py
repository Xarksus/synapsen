"""synapsen — ein homöostatischer Zustandskern für Agenten.

Botenstoffe statt Stimmungs-Strings: Ereignisse schütten aus, Werte zerfallen,
koppeln sich, folgen einem Tagesrhythmus. Verhalten wird nicht gesetzt, es
entsteht.

    from synapsen import HomeostasisEngine, PromptRenderer, JsonStore

    engine = HomeostasisEngine(store=JsonStore("~/.config/agent/state.json"))
    engine.stimulus({"dopamine": +15}, kind="tool_success", context="deploy")
    prompt_suffix = PromptRenderer().render(engine.snapshot())
"""
from .clock import Clock, FakeClock, SystemClock
from .dynamics import Equilibrium, equilibrium, impulse_response
from .engine import HomeostasisEngine, Snapshot
from .explain import explain
from .journal import (Event, MemoryJournal, NullJournal, SqliteJournal,
                      mood_bias)
from .profile import (DEFAULT_PROFILE, Coupling, DerivedState, HormoneSpec,
                      Profile)
from .profiles import PROFILES
from .profiles import get as get_profile
from .render import PromptRenderer, RenderConfig
from .simulate import Scenario, Trajectory, chart
from .simulate import run as simulate
from .validate import Report, check
from .store import JsonStore, MemoryStore, StateStore

__version__ = "0.1.0"

__all__ = [
    "HomeostasisEngine", "Snapshot",
    "Profile", "DEFAULT_PROFILE", "HormoneSpec", "Coupling", "DerivedState",
    "JsonStore", "MemoryStore", "StateStore",
    "SqliteJournal", "MemoryJournal", "NullJournal", "Event", "mood_bias",
    "PromptRenderer", "RenderConfig",
    "Clock", "SystemClock", "FakeClock",
    "equilibrium", "Equilibrium", "impulse_response",
    "check", "Report",
    "Scenario", "Trajectory", "simulate", "chart",
    "explain", "PROFILES", "get_profile",
    "__version__",
]
