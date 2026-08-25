"""Tests — insbesondere die Regression, die den gefundenen Fehler festnagelt."""
import math
import random
from datetime import datetime, timedelta

import pytest

from synapsen import (DEFAULT_PROFILE, FakeClock, HomeostasisEngine,
                      MemoryJournal, MemoryStore, PromptRenderer, mood_bias)


def make(clock=None, **kw):
    return HomeostasisEngine(
        clock=clock or FakeClock(start=1_780_000_000.0),
        store=MemoryStore(),
        journal=MemoryJournal(),
        rng=random.Random(0),
        **kw,
    )


# ── Grundverhalten ─────────────────────────────────────────────────────────

def test_inject_raises_on_unknown_hormone():
    e = make()
    with pytest.raises(KeyError):
        e.inject("adrenochrome", 5.0)


def test_inject_moves_value():
    e = make()
    before = e.hormones["dopamine"]
    e.inject("dopamine", +20.0)
    assert e.hormones["dopamine"] == pytest.approx(before + 20.0)


def test_decay_returns_toward_baseline():
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    e.inject("cortisol", +60.0)
    peak = e.hormones["cortisol"]
    base = e.baselines["cortisol"]
    c.advance(hours=4)
    e.snapshot()
    settled = e.hormones["cortisol"]
    assert settled < peak
    # deutlich näher am Ruhewert als am Ausschlag
    assert abs(settled - base) < abs(peak - base) / 4


def test_ceiling_is_enforced():
    e = make()
    for _ in range(200):
        e.inject("cortisol", +50.0)
    assert e.hormones["cortisol"] <= DEFAULT_PROFILE.hormones["cortisol"].ceiling


def test_hormones_never_go_negative():
    e = make()
    e.inject("dopamine", -10_000.0)
    assert e.hormones["dopamine"] >= 0.0


# ── Kopplung ist zeit-, nicht aufrufbasiert ────────────────────────────────

def test_coupling_does_not_compound_on_repeated_reads():
    """Der Kern-Regressionstest gegen aufrufbasierte Kopplung.

    30 Abfragen in derselben Sekunde dürfen nicht die 30-fache Wirkung einer
    einzelnen haben.
    """
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    e.inject("oxytocin", +100.0)
    e.inject("cortisol", +80.0)
    c.advance(seconds=1)
    baseline_reading = e.snapshot().hormones["cortisol"]

    e2 = make(FakeClock(start=1_780_000_000.0))
    e2.inject("oxytocin", +100.0)
    e2.inject("cortisol", +80.0)
    e2.clock.advance(seconds=1)
    for _ in range(30):
        e2.snapshot()
    many_readings = e2.hormones["cortisol"]

    assert abs(many_readings - baseline_reading) < 1.0


# ── Gewöhnung ──────────────────────────────────────────────────────────────

def test_habituation_blunts_repeated_bonding():
    e = make()
    first = e.inject("oxytocin", +10.0)
    second = e.inject("oxytocin", +10.0)
    third = e.inject("oxytocin", +10.0)
    assert first > second > third
    assert third < first / 2


def test_habituation_resets_after_window():
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    for _ in range(5):
        e.inject("oxytocin", +10.0)
    exhausted = e.inject("oxytocin", +10.0)
    c.advance(hours=2)
    recovered = e.inject("oxytocin", +10.0)
    assert exhausted == 0.0
    assert recovered > 0.0


# ── Der eigentliche Fehler: Log-Flut vergiftet die Baselines ───────────────

def test_mood_bias_is_independent_of_event_count():
    """Reproduziert den Fehler aus der Original-Engine.

    Dort war der Bias die *Summe* der gewichteten Schweren. 4.273 Ereignisse
    à +2.0 ergaben einen Bias von -1.337 — die Serotonin-Baseline landete bei
    1.397 statt 60 und wurde nur noch von der Sicherheitsdecke aufgefangen.

    Der Mittelwert liefert für 10 und für 10.000 gleichartige Ereignisse
    denselben Wert.
    """
    now = datetime(2026, 7, 17, 3, 49)
    few = [((now - timedelta(hours=i)).isoformat(), 2.0) for i in range(10)]
    many = [((now - timedelta(seconds=i * 60)).isoformat(), 2.0) for i in range(10_000)]

    bias_few = mood_bias(few, now)
    bias_many = mood_bias(many, now)

    assert abs(bias_few - bias_many) < 1.0
    assert abs(bias_many) <= 25.0


def test_mood_bias_is_bounded():
    now = datetime(2026, 7, 17, 3, 49)
    catastrophic = [((now - timedelta(minutes=i)).isoformat(), -500.0)
                    for i in range(5_000)]
    assert mood_bias(catastrophic, now) <= 25.0


def test_mood_bias_sign_follows_experience():
    now = datetime(2026, 7, 17, 3, 49)
    good = [((now - timedelta(hours=i)).isoformat(), +3.0) for i in range(20)]
    bad = [((now - timedelta(hours=i)).isoformat(), -3.0) for i in range(20)]
    assert mood_bias(good, now) < 0    # gute Woche -> weniger Stress-Baseline
    assert mood_bias(bad, now) > 0     # schlechte Woche -> mehr


def test_baseline_stays_healthy_after_long_calm_run():
    """Ende-zu-Ende: ein langer ruhiger Betrieb darf den Agenten nicht
    strukturell stressunfähig machen."""
    c = FakeClock(start=1_780_000_000.0)
    journal = MemoryJournal()
    e = HomeostasisEngine(clock=c, store=MemoryStore(), journal=journal,
                          rng=random.Random(0))
    for _ in range(5_000):
        e.inject("dopamine", +0.5)
        e.note("calm_positive", severity=+2.0)
        c.advance(seconds=30)

    e2 = HomeostasisEngine(clock=c, store=MemoryStore(), journal=journal,
                           rng=random.Random(0))
    spec = DEFAULT_PROFILE.hormones["serotonin"]
    assert e2.baselines["serotonin"] < spec.baseline_ceiling
    assert e2.baselines["cortisol"] > 0.0


def test_debouncer_prevents_log_flood():
    """Die Ursache, nicht nur die Wirkung: ein Dauerzustand wird nicht
    tausendfach protokolliert."""
    c = FakeClock(start=1_780_000_000.0)
    journal = MemoryJournal()
    e = HomeostasisEngine(clock=c, store=MemoryStore(), journal=journal,
                          debounce_seconds=900.0, rng=random.Random(0))
    for _ in range(1_000):
        e.note("calm_positive", severity=+2.0)
        c.advance(seconds=10)
    hours = 1_000 * 10 / 3600
    assert len(journal.events) <= math.ceil(hours * 4) + 1


# ── Bindung ────────────────────────────────────────────────────────────────

def test_bond_grows_slowly():
    e = make()
    start = e.bond
    for _ in range(100):
        e.reinforce_bond(1.0)
    assert e.bond - start < 5.0, "Bindung darf nicht in Minuten entstehen"


def test_fresh_bond_is_not_gifted_a_floor():
    """Ein fester Boden darf einen frischen Agenten nicht sofort auf
    'sehr vertraut' heben — im Original tat er genau das."""
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    start = e.bond
    c.advance(days=400)
    e.snapshot()
    assert e.bond <= start
    assert e.bond < DEFAULT_PROFILE.bond["floor"]


def test_grown_bond_never_fully_vanishes():
    """Was gewachsen ist, bleibt: nach langer Abwesenheit kühlt die Bindung ab,
    fällt aber nicht unter den erreichten Erinnerungswert."""
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    e.bond = 200.0
    e._bond_high = 200.0
    c.advance(days=400)
    e.snapshot()
    assert e.bond == pytest.approx(DEFAULT_PROFILE.bond["floor"])


# ── Abwesenheit ────────────────────────────────────────────────────────────

def test_short_absence_is_ignored():
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    snap = e.suspend()
    c.advance(hours=2)
    assert e.resume(snap) is None


def test_long_absence_produces_reunion():
    c = FakeClock(start=1_780_000_000.0)
    e = make(c)
    snap = e.suspend()
    c.advance(days=9)
    result = e.resume(snap)
    assert result is not None
    assert 8.9 < result["days"] < 9.1


# ── Zustände & Renderer ────────────────────────────────────────────────────

def test_states_are_derived_from_profile():
    e = make()
    snap = e.snapshot(jitter=False)
    assert set(snap.states) == {s.name for s in DEFAULT_PROFILE.states}


def test_stress_raises_irritability():
    e = make()
    calm = e.snapshot(jitter=False).states["REIZBAR"]
    e.inject("cortisol", +80.0)
    stressed = e.snapshot(jitter=False).states["REIZBAR"]
    assert stressed > calm


def test_renderer_contains_no_hardcoded_name():
    import inspect
    from synapsen import render
    assert "Thorsten" not in inspect.getsource(render)
    from synapsen import engine as engine_mod
    assert "Thorsten" not in inspect.getsource(engine_mod)


def test_renderer_produces_text():
    e = make()
    out = PromptRenderer().render(e.snapshot())
    assert "FEUER" in out and "Botenstoffe" in out


# ── Persistenz ─────────────────────────────────────────────────────────────

def test_state_survives_restart():
    store = MemoryStore()
    c = FakeClock(start=1_780_000_000.0)
    e = HomeostasisEngine(clock=c, store=store, journal=MemoryJournal())
    e.inject("oxytocin", +40.0)
    e.flush()
    value = e.hormones["oxytocin"]

    e2 = HomeostasisEngine(clock=c, store=store, journal=MemoryJournal())
    assert e2.hormones["oxytocin"] == pytest.approx(value, abs=0.5)


def test_no_import_side_effects(tmp_path):
    """Kein Singleton beim Import: `import synapsen` darf weder Dateien
    anlegen noch lesen. Im Original lief `engine = EmotionEngine()` auf
    Modulebene und griff dabei auf Zustandsdatei und Datenbank zu."""
    import subprocess
    import sys

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import builtins, sqlite3\n"
        "touched = []\n"
        "real_open, real_connect = builtins.open, sqlite3.connect\n"
        "builtins.open = lambda f, *a, **k: (touched.append(str(f)),\n"
        "                                    real_open(f, *a, **k))[1]\n"
        "sqlite3.connect = lambda f, *a, **k: (touched.append(str(f)),\n"
        "                                      real_connect(f, *a, **k))[1]\n"
        "import synapsen  # noqa: F401\n"
        "assert not touched, touched\n"
        "print('sauber')\n",
        encoding="utf-8")

    r = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sauber" in r.stdout
