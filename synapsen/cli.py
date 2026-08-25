"""Kommandozeile.

    synapsen doctor                    Profil prüfen
    synapsen show                      aktuellen Zustand ansehen
    synapsen why                       Zustand auf seine Ursachen zurückführen
    synapsen simulate --days 14        Verlauf durchrechnen
    synapsen events                    verfügbare Ereignisse auflisten
    synapsen profiles                  mitgelieferte Profile auflisten
    synapsen mcp                       als MCP-Server laufen

Alle Unterbefehle nehmen `--profile` (mitgeliefert oder Pfad zu einer
JSON-Datei) und `--state` (Zustandsdatei).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .profile import Profile
from .profiles import get as get_profile
from .profiles import names as profile_names


def _load_profile(spec: str) -> Profile:
    path = Path(spec).expanduser()
    if path.suffix == ".json" and path.exists():
        return Profile.from_json(path)
    return get_profile(spec)


def _engine(args):
    from .engine import HomeostasisEngine
    from .journal import SqliteJournal
    from .store import JsonStore
    profile = _load_profile(args.profile)
    return HomeostasisEngine(
        profile,
        store=JsonStore(args.state),
        journal=(SqliteJournal.for_profile(args.journal, profile)
                 if args.journal else None),
    )


# ── Unterbefehle ───────────────────────────────────────────────────────────

def cmd_doctor(args) -> int:
    from .validate import check
    profile = _load_profile(args.profile)
    report = check(profile)
    if args.profile != profile.name:
        print(f"Aufgerufen als: {args.profile}")
    print(report)
    print()
    if report.ok:
        print("✓ Profil ist tragfähig.")
    else:
        print(f"✗ {len(report.errors)} Fehler — so sollte das Profil nicht laufen.")
    return 0 if report.ok else 1


def cmd_show(args) -> int:
    from .render import PromptRenderer, RenderConfig
    engine = _engine(args)
    snap = engine.snapshot()
    if args.raw:
        import json
        print(json.dumps({
            "hormones": {k: round(v, 2) for k, v in snap.hormones.items()},
            "baselines": {k: round(v, 2) for k, v in snap.baselines.items()},
            "states": {k: round(v, 3) for k, v in snap.states.items()},
            "bond": round(snap.bond, 2),
            "fatigue": round(snap.adenosine, 2),
        }, ensure_ascii=False, indent=2))
    else:
        print(PromptRenderer(RenderConfig(
            partner=args.partner, language=args.language)).render(snap))
    engine.flush()
    return 0


def cmd_why(args) -> int:
    from .explain import explain
    print(explain(_engine(args)))
    return 0


def cmd_event(args) -> int:
    engine = _engine(args)
    engine.event(args.event, intensity=args.intensity, context=args.context)
    engine.flush()
    snap = engine.snapshot()
    pos, value = snap.dominant("positive")
    print(f"{args.event} verbucht.  "
          + "  ".join(f"{k} {v:.1f}" for k, v in snap.hormones.items()))
    print(f"Vorherrschend: {pos} {value:.2f}")
    return 0


def cmd_simulate(args) -> int:
    from .simulate import Scenario, chart, profile_chart, run

    profile = _load_profile(args.profile)
    days = args.days

    event = args.event or _default_event(profile)
    if args.scenario != "quiet" and event not in profile.events:
        print(f"Profil {profile.name!r} kennt kein Ereignis {event!r}.",
              file=sys.stderr)
        print(f"Bekannt: {', '.join(sorted(profile.events)) or '(keine)'}",
              file=sys.stderr)
        return 2

    if args.scenario == "workweek":
        # Nebenereignisse nur, wenn das Profil sie kennt — ein Arbeitsprofil
        # ohne Beziehung hat kein "warm_contact".
        morning = _first_known(profile, ["warm_contact", "session_start", "calm"])
        evening = _first_known(profile, ["conversation_end", "session_end", "calm"])
        s = Scenario(f"Arbeitswoche ({event})", days=days, start_hour=8)
        for d in range(int(days)):
            for hour in (9, 11, 14, 16, 18):
                s.at(d * 24 + hour, event)
            if morning:
                s.at(d * 24 + 8.5, morning)
            if evening:
                s.at(d * 24 + 22, evening)
    elif args.scenario == "steady":
        s = Scenario(f"gleichmäßig ({event})", days=days)
        s.every(hours=args.interval, event=event)
    elif args.scenario == "quiet":
        s = Scenario("ohne jeden Reiz", days=days)
    else:
        print(f"Unbekanntes Szenario: {args.scenario}", file=sys.stderr)
        return 2

    traj = run(s, profile)

    if args.csv:
        Path(args.csv).write_text(traj.to_csv(), encoding="utf-8")
        print(f"{len(traj.samples)} Messpunkte nach {args.csv} geschrieben.")
        return 0

    if args.plot:
        print(profile_chart(traj, args.plot))
        return 0

    keys = args.keys.split(",") if args.keys else None
    print(chart(traj, keys))
    return 0


def _first_known(profile, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in profile.events), None)


def _default_event(profile) -> str:
    """Ein Ereignis, das dieses Profil kennt — für den Aufruf ohne --event."""
    return (_first_known(profile, ["task_success", "reward", "praise"])
            or (sorted(profile.events)[0] if profile.events else ""))


def cmd_events(args) -> int:
    profile = _load_profile(args.profile)
    if not profile.events:
        print(f"Profil {profile.name!r} definiert keine benannten Ereignisse.")
        return 0
    print(f"Ereignisse in Profil {profile.name!r}:")
    for name, spec in sorted(profile.events.items()):
        parts = ", ".join(f"{k} {v:+g}" for k, v in spec.items() if k != "severity")
        print(f"  {name:<22} {parts}   (Schwere {spec.get('severity', 0):+g})")
    return 0


def cmd_profiles(args) -> int:
    from .dynamics import equilibrium
    from .validate import check
    for name in profile_names():
        p = get_profile(name)
        report = check(p)
        eq = equilibrium(p)
        mark = "✓" if report.ok and eq.healthy else "✗"
        print(f"  {mark} {name:<8} {len(p.hormones)} Botenstoffe, "
              f"{len(p.states)} Zustände, {len(p.couplings)} Kopplungen")
        print(f"      {', '.join(p.hormone_names())}")
    return 0


def cmd_mcp(args) -> int:
    from .mcp_server import serve
    return serve(_engine(args))


# ── Verdrahtung ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="synapsen",
        description="Homöostatischer Zustandskern für Agenten.")
    p.add_argument("--version", action="version", version=f"synapsen {__version__}")
    p.add_argument("--profile", default="kira",
                   help=f"mitgeliefert ({', '.join(profile_names())}) oder Pfad zu einer JSON-Datei")
    p.add_argument("--state", default="~/.config/synapsen/state.json")
    p.add_argument("--journal", default=None, help="SQLite-Datei fürs Ereignisprotokoll")

    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="Profil auf Fehler prüfen")
    d.set_defaults(func=cmd_doctor)

    s = sub.add_parser("show", help="aktuellen Zustand ansehen")
    s.add_argument("--raw", action="store_true", help="als JSON statt als Prompt")
    s.add_argument("--partner", default="dein Gegenüber")
    s.add_argument("--language", default="de", choices=["de", "en"])
    s.set_defaults(func=cmd_show)

    w = sub.add_parser("why", help="Zustand auf seine Ursachen zurückführen")
    w.set_defaults(func=cmd_why)

    e = sub.add_parser("event", help="ein Ereignis verbuchen")
    e.add_argument("event")
    e.add_argument("--intensity", type=float, default=1.0)
    e.add_argument("--context", default="")
    e.set_defaults(func=cmd_event)

    sim = sub.add_parser("simulate", help="Verlauf durchrechnen")
    sim.add_argument("--days", type=float, default=14)
    sim.add_argument("--scenario", default="workweek",
                     choices=["workweek", "steady", "quiet"])
    sim.add_argument("--event", default=None,
                     help="ohne Angabe ein Ereignis, das das Profil kennt")
    sim.add_argument("--interval", type=float, default=4.0)
    sim.add_argument("--keys", default=None, help="Komma-getrennt, z. B. cortisol,RUHIG")
    sim.add_argument("--plot", default=None, help="eine Reihe groß darstellen")
    sim.add_argument("--csv", default=None, help="in eine CSV-Datei schreiben")
    sim.set_defaults(func=cmd_simulate)

    ev = sub.add_parser("events", help="verfügbare Ereignisse auflisten")
    ev.set_defaults(func=cmd_events)

    pr = sub.add_parser("profiles", help="mitgelieferte Profile auflisten")
    pr.set_defaults(func=cmd_profiles)

    m = sub.add_parser("mcp", help="als MCP-Server laufen")
    m.set_defaults(func=cmd_mcp)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
