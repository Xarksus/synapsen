#!/usr/bin/env python3
"""Diagnose einer bestehenden KIRA-Datenbank.

Rechnet vor, was die alte und die neue Bias-Formel aus denselben echten Daten
machen. Aufruf:

    python tools/diagnose_kira_db.py ~/.kira/synapsen.db
"""
from __future__ import annotations

import math
import pathlib
import sqlite3
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from synapsen import DEFAULT_PROFILE, mood_bias  # noqa: E402


def alte_formel(rows, now):
    """Wortgetreue Nachbildung von _apply_bias_from_history()."""
    lam, neg, pos = 0.015, 0.0, 0.0
    for ts_str, s in rows:
        if s is None:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            continue
        w = math.exp(-lam * (now - ts).total_seconds() / 3600.0)
        if s < 0:
            neg += abs(s) * w
        else:
            pos += s * w
    return (neg - pos) * 0.8


def main(path: str) -> int:
    resolved = pathlib.Path(path).expanduser()
    if not resolved.exists():
        print(f"Keine Datenbank unter {resolved}", file=sys.stderr)
        return 1

    con = sqlite3.connect(str(resolved))
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "emotional_log" not in tables:
        print(f"In {resolved} gibt es keine Tabelle 'emotional_log'.", file=sys.stderr)
        print(f"Vorhanden: {', '.join(sorted(tables)) or '(keine)'}", file=sys.stderr)
        return 1

    lo, hi, total = con.execute(
        "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM emotional_log").fetchone()
    if not total:
        print("Die Tabelle 'emotional_log' ist leer.")
        return 1
    path = str(resolved)
    now = datetime.fromisoformat(hi)

    print(f"Datenbank : {path}")
    print(f"Zeitraum  : {lo[:19]}  bis  {hi[:19]}")
    print(f"Einträge  : {total:,}")
    print()

    print("Ereignisverteilung")
    print("-" * 58)
    for kind, n in con.execute(
            "SELECT ereignis, COUNT(*) FROM emotional_log "
            "GROUP BY ereignis ORDER BY 2 DESC LIMIT 8"):
        share = n / total * 100
        bar = "█" * int(share / 2.5)
        print(f"  {n:>7,}  {share:5.1f}%  {bar:<40} {kind}")
    print()

    rows = con.execute(
        "SELECT timestamp, schwere FROM emotional_log WHERE timestamp >= ?",
        ((now - timedelta(days=7)).isoformat(),)).fetchall()

    alt = alte_formel(rows, now)
    neu = mood_bias(rows, now)

    cs = DEFAULT_PROFILE.hormones["cortisol"]
    ss = DEFAULT_PROFILE.hormones["serotonin"]

    def baselines(bias):
        return (max(cs.baseline_floor, min(cs.baseline_ceiling, cs.baseline + bias)),
                max(ss.baseline_floor, min(ss.baseline_ceiling, ss.baseline - bias)))

    ac, as_ = baselines(alt)
    nc, ns = baselines(neu)

    print(f"Bias-Berechnung über die letzten 7 Tage ({len(rows):,} Einträge)")
    print("-" * 58)
    print(f"{'':22}{'alte Formel':>16}{'neue Formel':>18}")
    print(f"{'Bias':22}{alt:>16,.1f}{neu:>18,.1f}")
    print(f"{'Cortisol-Ruhewert':22}{ac:>16,.1f}{nc:>18,.1f}   (gesund: {cs.baseline:.0f})")
    print(f"{'Serotonin-Ruhewert':22}{as_:>16,.1f}{ns:>18,.1f}   (gesund: {ss.baseline:.0f})")
    print()

    if ac <= cs.baseline_floor and as_ >= ss.baseline_ceiling:
        print("Befund: Die Ruhewerte hängen an ihren Grenzen. Der Agent kann")
        print("        strukturell nicht mehr gestresst sein — die Sicherheits-")
        print("        decken fangen den Ausreißer ab, aber die Gefühlswelt ist")
        print("        eingefroren. Das ist der 'immer RUHIG'-Effekt.")
    else:
        print("Befund: Ruhewerte im gesunden Bereich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1
                          else "~/.kira/synapsen.db"))
