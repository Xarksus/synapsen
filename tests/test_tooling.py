"""Tests für Profil-Prüfung, Simulation, Ursachenanalyse und Kommandozeile."""
import copy
import json

import pytest

from synapsen import DEFAULT_PROFILE, FakeClock, HomeostasisEngine, MemoryStore
from synapsen.cli import main as cli_main
from synapsen.dynamics import coupling_flux, equilibrium, flux, step
from synapsen.explain import explain
from synapsen.profile import Coupling, HormoneSpec, Profile
from synapsen.profiles import PROFILES, get, names
from synapsen.simulate import Scenario, chart, resample, run, sparkline
from synapsen.validate import ERROR, check


# ── Dynamik ────────────────────────────────────────────────────────────────

def test_step_is_independent_of_step_count():
    """Ein Schritt über 4 Stunden muss dasselbe ergeben wie 40 über je 0,1."""
    base = {k: s.baseline for k, s in DEFAULT_PROFILE.hormones.items()}
    start = dict(base, cortisol=90.0)

    one = step(DEFAULT_PROFILE, start, base, 4.0)
    many = dict(start)
    for _ in range(40):
        many = step(DEFAULT_PROFILE, many, base, 0.1)

    for name in one:
        assert one[name] == pytest.approx(many[name], abs=0.01)


def test_flux_is_zero_at_equilibrium():
    eq = equilibrium(DEFAULT_PROFILE)
    base = {k: s.baseline for k, s in DEFAULT_PROFILE.hormones.items()}
    rates = flux(DEFAULT_PROFILE, eq.values, base)
    assert max(abs(v) for v in rates.values()) < 0.01


def test_coupling_flux_respects_thresholds():
    """serotonin→cortisol hat threshold 50: unterhalb wirkungslos,
    oberhalb proportional zum Überschuss."""
    p = DEFAULT_PROFILE
    base = {k: 0.0 for k in p.hormones}

    below = coupling_flux(p, dict(base, serotonin=40.0))
    at = coupling_flux(p, dict(base, serotonin=50.0))
    above = coupling_flux(p, dict(base, serotonin=100.0))

    assert below["cortisol"] == 0.0
    assert at["cortisol"] == 0.0
    assert above["cortisol"] == pytest.approx(-4.0)   # (100-50)/50 * -4.0


def test_equilibrium_reports_saturation():
    broken = copy.deepcopy(DEFAULT_PROFILE)
    broken.couplings.append(
        Coupling("dopamine", "cortisol", gain=-500.0, per=10.0))
    eq = equilibrium(broken)
    assert not eq.healthy
    assert any("cortisol" in b for b in eq.at_bounds)


# ── Profil-Prüfung ─────────────────────────────────────────────────────────

def _minimal(**kw) -> Profile:
    defaults = dict(
        name="t",
        hormones={"a": HormoneSpec(baseline=50, decay=0.5, ceiling=100)},
        couplings=[], states=[], circadian=[],
        adenosine_per_minute=0.0, adenosine_ceiling=0.0,
        fatigue_targets={}, habituation={}, bond={}, jitter=0.0,
    )
    defaults.update(kw)
    return Profile(**defaults)


def test_validator_catches_zero_decay():
    p = _minimal(hormones={"a": HormoneSpec(baseline=50, decay=0.0, ceiling=100)})
    assert any(f.level == ERROR and "Zerfallsrate" in f.message
               for f in check(p).findings)


def test_validator_catches_baseline_above_its_cap():
    p = _minimal(hormones={
        "a": HormoneSpec(baseline=80, decay=0.5, ceiling=100, baseline_ceiling=40)})
    assert any(f.level == ERROR and "Ruhewert-Decke" in f.message
               for f in check(p).findings)


def test_validator_catches_unknown_hormone_in_state():
    from synapsen.profile import DerivedState
    p = _minimal(states=[DerivedState("X", {"gibtsnicht": 1.0})])
    assert any(f.level == ERROR and "gibtsnicht" in f.message
               for f in check(p).findings)


def test_validator_catches_unknown_hormone_in_event():
    p = _minimal(events={"boom": {"gibtsnicht": 5.0}})
    assert any(f.level == ERROR and "gibtsnicht" in f.message
               for f in check(p).findings)


def test_validator_catches_runaway_self_coupling():
    p = _minimal(couplings=[Coupling("a", "a", gain=+50.0, per=10.0)])
    report = check(p)
    assert not report.ok


def test_validator_accepts_every_shipped_profile():
    for name, profile in PROFILES.items():
        report = check(profile)
        assert report.ok, f"{name}: " + "\n".join(str(f) for f in report.errors)


# ── Profile ────────────────────────────────────────────────────────────────

def test_shipped_profiles_are_genuinely_different():
    """Wenn alle Profile dieselben Botenstoffe hätten, wäre 'konfigurierbar'
    eine Behauptung."""
    axes = {name: set(p.hormones) for name, p in PROFILES.items()}
    assert axes["kira"] != axes["focus"] != axes["pad"] != axes["kira"]


def test_profile_survives_json_roundtrip(tmp_path):
    path = tmp_path / "p.json"
    DEFAULT_PROFILE.to_json(path)
    again = Profile.from_json(path)
    assert again.name == DEFAULT_PROFILE.name
    assert set(again.hormones) == set(DEFAULT_PROFILE.hormones)
    assert len(again.couplings) == len(DEFAULT_PROFILE.couplings)
    assert len(again.states) == len(DEFAULT_PROFILE.states)
    assert again.events == DEFAULT_PROFILE.events
    assert equilibrium(again).values == pytest.approx(
        equilibrium(DEFAULT_PROFILE).values, abs=0.01)


def test_get_profile_rejects_unknown_name():
    with pytest.raises(KeyError):
        get("gibtsnicht")
    assert "kira" in names()


def test_engine_runs_on_every_shipped_profile():
    for name, profile in PROFILES.items():
        engine = HomeostasisEngine(profile, store=MemoryStore(),
                                   clock=FakeClock(start=1_780_000_000.0))
        for event in list(profile.events)[:3]:
            engine.event(event)
        snap = engine.snapshot()
        assert set(snap.states) == {s.name for s in profile.states}, name


def test_event_rejects_names_the_profile_does_not_know():
    engine = HomeostasisEngine(get("focus"), store=MemoryStore(),
                               clock=FakeClock(start=1_780_000_000.0))
    with pytest.raises(KeyError):
        engine.event("praise")          # gehört zum kira-Profil


# ── Simulation ─────────────────────────────────────────────────────────────

def test_sparkline_maps_range_to_blocks():
    assert sparkline([0, 1, 2, 3]) == "▁▃▆█"
    assert sparkline([5, 5, 5]) == "▁▁▁"
    assert sparkline([]) == ""


def test_resample_shrinks_to_requested_width():
    assert len(resample(list(range(100)), 10)) == 10
    assert resample([1, 2], 10) == [1, 2]


def test_trajectory_csv_has_a_row_per_sample():
    traj = run(Scenario("still", days=1))
    lines = traj.to_csv().splitlines()
    assert len(lines) == len(traj.samples) + 1
    assert lines[0].startswith("hours,")


def test_quiet_scenario_settles_at_the_computed_equilibrium():
    """Die Simulation und der Gleichgewichtslöser müssen übereinstimmen —
    sonst beschreibt die Analyse nicht die echte Dynamik.

    Verglichen wird gegen das Gleichgewicht der *Ruhewerte*, die im
    Endzustand gelten (nicht gegen die Endwerte selbst — das wäre ein
    Vergleich mit sich selbst).
    """
    # Geprüft am `pad`-Profil: ohne Tagesrhythmus steht der Ruhewert still,
    # das System kommt also wirklich zur Ruhe. Bei `kira` wandert der Ruhewert
    # stündlich weiter — dort jagt der Zustand einem beweglichen Ziel nach und
    # trifft es naturgemäß nie ganz.
    profile = get("pad")
    scenario = Scenario("still", days=3, start_hour=12)
    scenario.sample_every_hours = 0.5
    last = run(scenario, profile).samples[-1]

    predicted = equilibrium(profile, last["baselines"],
                            adenosine=last["adenosine"]).values
    for name, value in last["hormones"].items():
        assert value == pytest.approx(predicted[name], abs=0.05), name


def test_daily_rhythm_keeps_the_system_slightly_off_equilibrium():
    """Gegenstück: mit Tagesrhythmus darf der Zustand *nicht* exakt im
    Gleichgewicht stehen — sonst wäre der Rhythmus wirkungslos."""
    scenario = Scenario("still", days=3, start_hour=12)
    scenario.sample_every_hours = 0.5
    last = run(scenario, DEFAULT_PROFILE).samples[-1]

    predicted = equilibrium(DEFAULT_PROFILE, last["baselines"],
                            adenosine=last["adenosine"]).values
    gaps = [abs(last["hormones"][k] - predicted[k]) for k in predicted]
    assert max(gaps) > 0.1
    assert max(gaps) < 5.0, "aber auch nicht weit weg"


def test_equilibrium_prediction_is_not_trivially_self_confirming():
    """Gegenprobe zum Test darüber: mit fremden Ruhewerten muss der Löser
    ein anderes Ergebnis liefern."""
    absurd = {k: 200.0 for k in DEFAULT_PROFILE.hormones}
    assert equilibrium(DEFAULT_PROFILE, absurd).values["cortisol"] > 100


def test_chart_renders_without_dependencies():
    out = chart(run(Scenario("kurz", days=1)), ["cortisol"])
    assert "cortisol" in out
    assert any(block in out for block in "▁▂▃▄▅▆▇█")


# ── Ursachenanalyse ────────────────────────────────────────────────────────

def test_explain_attributes_a_recent_event():
    clock = FakeClock(start=1_780_000_000.0)
    engine = HomeostasisEngine(store=MemoryStore(), clock=clock)
    engine.event("task_failure", context="Build rot")
    clock.advance(minutes=20)

    result = explain(engine)
    cortisol = next(h for h in result.hormones if h.name == "cortisol")
    events = next(c for c in cortisol.deviation_parts if c.source == "Ereignisse")
    assert events.amount > 5
    assert "Build rot" in events.detail


def test_explain_decomposition_adds_up():
    """Eine Aufschlüsselung, deren Teile sich nicht zur Summe fügen, ist eine
    Vermutung. Beide Ebenen müssen exakt aufgehen."""
    clock = FakeClock(start=1_780_000_000.0)
    engine = HomeostasisEngine(store=MemoryStore(), clock=clock)
    engine.event("task_failure")
    clock.advance(hours=2)
    engine.event("praise")
    clock.advance(minutes=40)

    for block in explain(engine).hormones:
        assert sum(c.amount for c in block.resting_parts) == pytest.approx(
            block.resting, abs=1e-6), f"{block.name}: Ruhepunkt"
        assert sum(c.amount for c in block.deviation_parts) == pytest.approx(
            block.deviation, abs=1e-6), f"{block.name}: Abweichung"


def test_explain_names_the_morning_driver():
    """`_morning` trägt den MÜDE-Wert mit — es darf nicht durchfallen."""
    engine = HomeostasisEngine(store=MemoryStore(),
                               clock=FakeClock(start=1_780_000_000.0))
    tired = next(s for s in explain(engine).states if s.name == "MÜDE")
    assert any(d.source == "Morgen" for d in tired.drivers)


def test_habituation_note_respects_the_window():
    """Der Hinweis darf nicht hängen bleiben, nachdem das Zeitfenster
    abgelaufen ist."""
    clock = FakeClock(start=1_780_000_000.0)
    engine = HomeostasisEngine(store=MemoryStore(), clock=clock)
    for _ in range(8):
        engine.inject("oxytocin", +10.0)
    assert any("Gewöhnung" in n for n in explain(engine).notes)
    clock.advance(hours=5)
    assert not any("Gewöhnung" in n for n in explain(engine).notes)


def test_explain_warns_when_a_value_is_stuck_at_a_bound():
    clock = FakeClock(start=1_780_000_000.0)
    engine = HomeostasisEngine(store=MemoryStore(), clock=clock)
    engine.inject("dopamine", -500.0)
    notes = explain(engine).notes
    assert any("Boden" in n for n in notes)


def test_explain_covers_every_hormone_and_state():
    engine = HomeostasisEngine(store=MemoryStore(),
                               clock=FakeClock(start=1_780_000_000.0))
    result = explain(engine)
    assert {h.name for h in result.hormones} == set(DEFAULT_PROFILE.hormones)
    assert {s.name for s in result.states} == {s.name for s in DEFAULT_PROFILE.states}


# ── Kommandozeile ──────────────────────────────────────────────────────────

def test_cli_doctor_succeeds_for_shipped_profiles(capsys):
    for name in names():
        assert cli_main(["--profile", name, "doctor"]) == 0
    assert "Gleichgewicht" in capsys.readouterr().out


def test_cli_doctor_fails_on_a_broken_profile(tmp_path, capsys):
    broken = copy.deepcopy(DEFAULT_PROFILE)
    for c in broken.couplings:
        c.gain *= 72                      # die ursprüngliche, aufrufskalierte Stärke
    path = tmp_path / "broken.json"
    broken.to_json(path)
    assert cli_main(["--profile", str(path), "doctor"]) == 1
    assert "gesättigt" in capsys.readouterr().out


def test_cli_simulate_writes_csv(tmp_path):
    out = tmp_path / "run.csv"
    assert cli_main(["simulate", "--days", "2", "--csv", str(out)]) == 0
    assert out.read_text().count("\n") > 10


def test_cli_show_and_event_share_state(tmp_path, capsys):
    state = str(tmp_path / "state.json")
    assert cli_main(["--state", state, "event", "praise"]) == 0
    assert cli_main(["--state", state, "show", "--raw"]) == 0
    payload = json.loads(capsys.readouterr().out.split("Vorherrschend")[-1]
                         .split("\n", 1)[-1])
    assert set(payload["hormones"]) == set(DEFAULT_PROFILE.hormones)


def test_cli_events_lists_the_profiles_own_events(capsys):
    assert cli_main(["--profile", "focus", "events"]) == 0
    out = capsys.readouterr().out
    assert "blocked" in out and "praise" not in out


def test_cli_why_runs(tmp_path):
    state = str(tmp_path / "state.json")
    cli_main(["--state", state, "event", "criticism"])
    assert cli_main(["--state", state, "why"]) == 0
