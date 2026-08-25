"""Regressionen aus der zweiten Prüfrunde.

Die Fehler hier sind nicht aus dem Ursprungssystem, sondern aus dieser
Bibliothek — gefunden, nachdem die erste Fassung schon grün war. Jeder Test
schlägt gegen den Stand von damals fehl.
"""
import random

import pytest

from synapsen import (DEFAULT_PROFILE, FakeClock, HomeostasisEngine, JsonStore,
                      MemoryJournal, MemoryStore)
from synapsen.dynamics import equilibrium
from synapsen.profiles import get


def make(clock=None, **kw):
    return HomeostasisEngine(
        clock=clock or FakeClock(start=1_780_000_000.0),
        store=MemoryStore(), journal=MemoryJournal(),
        rng=random.Random(0), **kw)


# ── Der Bindungs-Boden hatte den Zerfall stillgelegt ───────────────────────

def test_bond_actually_decays():
    """`floor = min(cfg_floor, bond_high)` war immer ≥ bond, weil `bond_high`
    per Definition nie kleiner ist. Damit konnte die Bindung nie sinken —
    weder durch Zeit noch durch `strain_bond`."""
    clock = FakeClock(start=1_780_000_000.0)
    engine = make(clock)
    start = engine.bond
    clock.advance(days=10)
    engine.snapshot()
    assert engine.bond < start


def test_strain_bond_has_an_effect():
    engine = make()
    before = engine.bond
    engine.strain_bond(1.0)
    assert engine.bond == pytest.approx(before - 2.0)


def test_bond_floor_applies_only_once_reached():
    clock = FakeClock(start=1_780_000_000.0)
    engine = make(clock)
    floor = DEFAULT_PROFILE.bond["floor"]

    engine.bond = floor + 30
    engine._bond_high = floor + 30
    clock.advance(days=365)
    engine.snapshot()
    assert engine.bond == pytest.approx(floor)


# ── Der Sprung aufs Gleichgewicht verwarf die Ermüdung ─────────────────────

def test_long_gap_does_not_reset_fatigue_pressure():
    """Bei Lücken über `SETTLED_AFTER_HOURS` wurde `equilibrium()` ohne
    Ermüdungsdruck gerufen — eine *längere* Abwesenheit machte den Agenten
    dadurch *wacher*."""
    results = {}
    for gap in (29.9, 30.1):
        clock = FakeClock(start=1_780_000_000.0)
        engine = make(clock)
        clock.advance(hours=gap)
        snap = engine.snapshot(jitter=False)
        results[gap] = snap.hormones["dopamine"]

    assert abs(results[29.9] - results[30.1]) < 2.0


# ── Ein Profil ohne Bindung darf keine Vertrautheit melden ─────────────────

@pytest.mark.parametrize("name", ["focus", "pad"])
def test_profiles_without_bond_report_none(name):
    engine = HomeostasisEngine(get(name), store=MemoryStore(),
                               clock=FakeClock(start=1_780_000_000.0))
    assert engine.snapshot().bond == 0.0


def test_renderer_omits_bond_when_there_is_none():
    from synapsen import PromptRenderer
    engine = HomeostasisEngine(get("focus"), store=MemoryStore(),
                               clock=FakeClock(start=1_780_000_000.0))
    assert "Vertrautheit" not in PromptRenderer().render(engine.snapshot())


# ── Die Stimmungslage überlebt den Neustart ────────────────────────────────

def test_mood_bias_survives_a_restart_without_journal():
    """Ohne Protokoll wurde der gespeicherte Bias beim Start mit 0.0
    überschrieben — der Ruhewert sprang um die Hälfte seines Werts."""
    store = MemoryStore()
    clock = FakeClock(start=1_780_000_000.0)

    engine = HomeostasisEngine(store=store, clock=clock, journal=MemoryJournal())
    engine._bias = 12.0
    engine.flush()
    before = engine.baselines["cortisol"]

    again = HomeostasisEngine(store=store, clock=clock)     # ohne Journal
    assert again._bias == pytest.approx(12.0)
    assert again.baselines["cortisol"] == pytest.approx(before)


# ── Eine rückwärts laufende Uhr darf nichts einfrieren ─────────────────────

def test_clock_going_backwards_does_not_freeze_the_state():
    """Stand `last_update` in der Zukunft (Zeitumstellung, NTP, zweiter
    Rechner), stand der Zustand still und entlud sich dann in einem Satz."""
    clock = FakeClock(start=1_780_000_000.0)
    engine = make(clock)
    engine.inject("cortisol", +100.0)

    clock.advance(hours=-4)          # Uhr springt zurück
    engine.snapshot()
    clock.advance(hours=4)           # und wieder vor
    engine.snapshot()

    reference = make(FakeClock(start=1_780_000_000.0))
    reference.inject("cortisol", +100.0)
    reference.clock.advance(hours=4)
    reference.snapshot()

    assert engine.hormones["cortisol"] == pytest.approx(
        reference.hormones["cortisol"], abs=5.0)


# ── Entprellung über Prozessgrenzen ────────────────────────────────────────

def test_debounce_survives_a_restart(tmp_path):
    """Die Entprellung lag nur im Arbeitsspeicher — bei einem Prozess je
    Ereignis (die Kommandozeile) griff sie nie."""
    state = tmp_path / "state.json"
    journal = MemoryJournal()
    clock = FakeClock(start=1_780_000_000.0)

    for _ in range(6):
        engine = HomeostasisEngine(store=JsonStore(state), journal=journal,
                                   clock=clock)
        engine.note("dauerzustand", severity=+2.0)
        engine.flush()
        clock.advance(seconds=30)

    assert len(journal.events) == 1


# ── Erholung nicht doppelt anrechnen ───────────────────────────────────────

def test_resume_does_not_count_recovery_twice():
    """`resume()` schrieb die Erholung gut, obwohl `_recover()` sie für
    dieselbe Lücke schon verbucht hatte."""
    def drift_after(with_resume: bool) -> float:
        clock = FakeClock(start=1_780_000_000.0)
        engine = make(clock)
        snapshot = engine.suspend()
        clock.advance(days=10)
        if with_resume:
            engine.resume(snapshot)
        else:
            engine.snapshot()
        return engine._drift["serotonin"]

    plain, resumed = drift_after(False), drift_after(True)
    assert resumed == pytest.approx(plain, rel=0.35)


# ── Entartete Profile melden statt abstürzen ───────────────────────────────

@pytest.mark.parametrize("mutate,expect", [
    (lambda p: p.hormones.clear(), "keine Botenstoffe"),
    (lambda p: setattr(p.couplings[0], "per", 0.0), "per darf nicht 0"),
    (lambda p: setattr(p.states[0], "scale", 0.0), "scale darf nicht 0"),
])
def test_validation_reports_degenerate_profiles(mutate, expect):
    import copy

    from synapsen.validate import check
    profile = copy.deepcopy(DEFAULT_PROFILE)
    mutate(profile)
    report = check(profile)          # darf nicht werfen
    assert not report.ok
    assert any(expect in f.message for f in report.errors)


def test_equilibrium_handles_a_profile_without_hormones():
    import copy
    empty = copy.deepcopy(DEFAULT_PROFILE)
    empty.hormones.clear()
    assert equilibrium(empty).values == {}


# ── Das Journal legt die Spalten des Profils an ────────────────────────────

@pytest.mark.parametrize("name", ["kira", "focus", "pad"])
def test_journal_matches_the_profiles_hormones(tmp_path, name):
    import sqlite3

    from synapsen import SqliteJournal
    profile = get(name)
    path = tmp_path / f"{name}.db"
    SqliteJournal.for_profile(path, profile)

    columns = {r[1] for r in sqlite3.connect(path).execute(
        'PRAGMA table_info("emotional_log")')}
    assert set(profile.hormone_names()) <= columns


# ── Ein Ereignis schreibt einmal, nicht je Botenstoff ──────────────────────

def test_one_event_causes_one_write():
    class CountingStore(MemoryStore):
        writes = 0

        def save(self, patch):
            CountingStore.writes += 1
            super().save(patch)

    engine = HomeostasisEngine(store=CountingStore(),
                               clock=FakeClock(start=1_780_000_000.0))
    CountingStore.writes = 0
    engine.event("breakthrough")     # verändert drei Botenstoffe
    assert CountingStore.writes == 1
