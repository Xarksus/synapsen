"""Verhaltenstests: nicht „gibt die Funktion 70 zurück", sondern
„ist der Agent nach einer harten Woche anders als nach einer guten".

Das ist die Ebene, auf der ein Zustandsmodell falsch sein kann, ohne dass ein
einziger Unit-Test rot wird. Möglich sind diese Tests nur, weil die Uhr
injizierbar ist — jeder hier simuliert Wochen und läuft in Millisekunden.
"""
import pytest

from synapsen import DEFAULT_PROFILE
from synapsen.dynamics import equilibrium, impulse_response
from synapsen.simulate import Scenario, run
from synapsen.validate import check


def workweek(name: str, event: str, days: int = 14) -> Scenario:
    """Ein realistischer Rhythmus: Arbeitstage mit Nächten dazwischen."""
    s = Scenario(name, days=days, start_hour=8)
    for d in range(days):
        for hour in (9, 11, 14, 16, 18):
            s.at(d * 24 + hour, event)
        s.at(d * 24 + 8.5, "warm_contact")
        s.at(d * 24 + 22, "conversation_end")
    return s


# ── Zwei Wochen, zwei Verläufe ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def good():
    return run(workweek("gut", "task_success"))


@pytest.fixture(scope="module")
def hard():
    return run(workweek("hart", "task_failure"))


def test_hard_weeks_raise_stress(good, hard):
    assert max(hard.series("cortisol")) > max(good.series("cortisol")) * 1.3


def test_hard_weeks_lower_stability(good, hard):
    assert hard.series("serotonin")[-1] < good.series("serotonin")[-1]


def test_mood_bias_diverges_by_experience(good, hard):
    """Der Stimmungs-Bias muss auseinanderlaufen — sonst wäre die Historie
    wirkungslos. In der Ursprungsfassung wurde er nur beim Start berechnet
    und blieb dann für immer stehen."""
    assert good.series("bias")[-1] < -1.0
    assert hard.series("bias")[-1] > +1.0


def test_neither_week_saturates_the_system(good, hard):
    """Kein Botenstoff darf über längere Zeit an einer Grenze kleben — dort
    reagiert er auf nichts mehr. Genau das war KIRAs Zustand."""
    for traj in (good, hard):
        for name, spec in DEFAULT_PROFILE.hormones.items():
            series = traj.series(name)
            at_floor = sum(1 for v in series if v <= spec.floor + 1e-6)
            at_ceiling = sum(1 for v in series if v >= spec.ceiling - 1e-6)
            assert at_floor < len(series) * 0.2, f"{name} klebt am Boden"
            assert at_ceiling < len(series) * 0.2, f"{name} klebt an der Decke"


# ── Tagesrhythmus ──────────────────────────────────────────────────────────

def test_fatigue_follows_a_daily_rhythm(good):
    """Ermüdung muss steigen und wieder fallen. Ohne Sättigung wächst sie
    endlos; ohne nächtlichen Abbau bleibt ein Dauerdienst erschöpft."""
    fatigue = good.series("adenosine")
    assert max(fatigue) > 100
    assert min(fatigue[24:]) < max(fatigue) * 0.5


def test_circadian_rhythm_keeps_moving(good):
    """Der Tagesrhythmus darf nicht auf der Startstunde einfrieren — in der
    Ursprungsfassung wurde er nur einmal beim Start angewandt."""
    calm = good.series("RUHIG")
    day_one = calm[:24]
    day_ten = calm[240:264]
    assert max(day_one) - min(day_one) > 0.05
    assert max(day_ten) - min(day_ten) > 0.05


# ── Bindung ────────────────────────────────────────────────────────────────

def close_contact(name: str, days: int, warmth: float = 1.0) -> Scenario:
    """Reger Kontakt: alle 20 Minuten während der Wachstunden."""
    s = Scenario(name, days=days, start_hour=8)
    for d in range(days):
        for step in range(42):                      # 8:00 bis 22:00
            s.contact(d * 24 + 8 + step / 3.0, warmth)
    return s


def test_bond_grows_over_weeks_not_hours():
    bond = run(close_contact("Nähe", 28)).series("bond")
    assert bond[-1] > bond[0] + 20, "über vier Wochen muss die Bindung wachsen"
    assert bond[24] - bond[0] < 2.0, "aber nicht innerhalb eines Tages"


def test_bond_cools_without_contact():
    """Der eigentliche Test gegen den stillgelegten Zerfall: ohne Kontakt
    muss die Bindung abkühlen. Im Original konnte sie das nie, weil ein
    fester Boden sie über dem Startwert festhielt."""
    quiet = run(Scenario("kein Kontakt", days=14, start_hour=9)).series("bond")
    assert quiet[-1] < quiet[0], "ohne Kontakt darf die Bindung nicht stehen bleiben"


def test_harshness_cools_the_bond():
    warm = run(close_contact("warm", 7, +1.0)).series("bond")[-1]
    cold = run(close_contact("hart", 7, -1.0)).series("bond")[-1]
    assert warm > cold
    assert cold < 50.0, "Härte muss die Bindung unter den Startwert drücken"


def test_grown_bond_survives_a_long_silence():
    """Was gewachsen ist, bleibt: der Boden greift, sobald er erreicht wurde."""
    s = close_contact("erst Nähe, dann Stille", 120)
    s.days = 200                                     # danach 80 Tage nichts
    bond = run(s).series("bond")
    assert max(bond) > 120
    assert bond[-1] >= 120 - 1e-6


# ── Frequenzunabhängigkeit ─────────────────────────────────────────────────

@pytest.mark.parametrize("samples_per_hour", [0.25, 1.0, 4.0, 12.0])
def test_result_does_not_depend_on_sampling_rate(samples_per_hour):
    """Der zentrale Regressionstest gegen den vierten Befund.

    In der Ursprungsfassung war die Kopplung pro *Aufruf* skaliert: zwischen
    „einmal pro Minute" und „einmal pro Stunde" lag ein Faktor 60. Dadurch
    landete Cortisol rechnerisch bei −124 und damit dauerhaft am Boden — was
    in KIRAs echter `hormones.json` als `cortisol: 0.0` steht.
    """
    s = workweek("takt", "task_success", days=3)
    s.sample_every_hours = 1.0 / samples_per_hour
    final = run(s).series("cortisol")[-1]
    assert 5.0 < final < 40.0

    reference = workweek("referenz", "task_success", days=3)
    reference.sample_every_hours = 1.0
    assert abs(final - run(reference).series("cortisol")[-1]) < 2.0


# ── Gleichgewicht und Profilprüfung ────────────────────────────────────────

def test_default_profile_passes_validation():
    report = check(DEFAULT_PROFILE)
    assert report.ok, "\n".join(str(f) for f in report.errors)


def test_default_profile_settles_away_from_its_limits():
    eq = equilibrium(DEFAULT_PROFILE)
    assert eq.converged
    assert eq.healthy, f"an Grenzen: {eq.at_bounds}"


def test_original_coupling_scale_is_detected_as_broken():
    """Gegenprobe: mit den ursprünglichen, aufrufskalierten Verstärkungen
    muss die Prüfung anschlagen — und zwar mit demselben Ergebnis, das in
    KIRAs echter Zustandsdatei steht."""
    import copy
    broken = copy.deepcopy(DEFAULT_PROFILE)
    for c, original_gain in zip(broken.couplings, (-8.0, -5.0, -3.0)):
        c.gain = original_gain * 72       # Umrechnung: pro Aufruf → pro Stunde

    report = check(broken)
    assert not report.ok
    assert equilibrium(broken).values["cortisol"] == pytest.approx(0.0, abs=1e-6)


def test_impulse_response_has_a_sane_half_life():
    r = impulse_response(DEFAULT_PROFILE, "dopamine", 40.0)
    assert 0.5 < r.half_life_hours < 6.0


def test_bond_hormone_impulse_reaches_the_stress_axis():
    """Kopplungen müssen sich auswirken: ein Bindungsreiz senkt den Stress."""
    r = impulse_response(DEFAULT_PROFILE, "oxytocin", 80.0, horizon_hours=6)
    assert r.side_effects.get("cortisol", 0.0) < 0
