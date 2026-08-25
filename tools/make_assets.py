#!/usr/bin/env python3
"""Erzeugt die Bilder für README und Doku.

Alles als SVG und ohne Fremdbibliotheken, damit die Bilder jederzeit neu
entstehen können, wenn sich ein Profil ändert — ein Diagramm, das man nicht
nachziehen kann, wird still falsch.

    python tools/make_assets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synapsen.simulate import Scenario, run  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets"

W, H = 900, 300
PAD_L, PAD_R, PAD_T, PAD_B = 58, 16, 26, 34

# Farben, die auf hellem wie dunklem Grund tragen. Die Neutralen wechseln per
# Media-Query, die Kurvenfarben bleiben — sie sind auf beiden Gründen lesbar.
STYLE = """
  .bg    { fill: #FBFCFB; }
  .grid  { stroke: #E3E8E6; stroke-width: 1; }
  .axis  { stroke: #D5DCD9; stroke-width: 1; }
  .label { fill: #5C6B67; font: 500 11px 'IBM Plex Mono', ui-monospace, monospace; }
  .title { fill: #16211F; font: 600 14px 'Zilla Slab', Georgia, serif; }
  .note  { fill: #8C9A95; font: 400 10.5px 'IBM Plex Mono', ui-monospace, monospace; }
  .band  { fill: #A94A24; opacity: 0.07; }
  .bandl { fill: #A94A24; opacity: 0.75;
           font: 500 10.5px 'IBM Plex Mono', ui-monospace, monospace; }
  @media (prefers-color-scheme: dark) {
    .bg    { fill: #161F1C; }
    .grid  { stroke: #222D2A; }
    .axis  { stroke: #2C3835; }
    .label { fill: #93A29D; }
    .title { fill: #E3EAE7; }
    .note  { fill: #6D7C77; }
    .band  { fill: #E08050; opacity: 0.10; }
    .bandl { fill: #E08050; }
  }
"""

SERIES = [
    ("cortisol", "#C25A2C", "Stress"),
    ("serotonin", "#2E8B74", "Stabilität"),
    ("dopamine", "#4A7FB5", "Antrieb"),
]


def month_scenario(days: int = 30) -> Scenario:
    """Zwei gute Wochen, zwei harte, dann Erholung."""
    s = Scenario("Ein Monat", days=days, start_hour=8)
    s.sample_every_hours = 0.5
    for d in range(days):
        hard = 9 <= d < 16
        event = "task_failure" if hard else "task_success"
        for hour in (9, 11, 14, 16, 18):
            s.at(d * 24 + hour, event)
        s.at(d * 24 + 8.5, "warm_contact")
        s.at(d * 24 + 22, "conversation_end")
    return s


def _path(values: list[float], lo: float, hi: float, total_days: float) -> str:
    span = hi - lo or 1.0
    width = W - PAD_L - PAD_R
    height = H - PAD_T - PAD_B
    points = []
    for i, v in enumerate(values):
        x = PAD_L + width * i / max(1, len(values) - 1)
        y = PAD_T + height * (1 - (v - lo) / span)
        points.append(f"{x:.1f},{y:.1f}")
    return "M" + " L".join(points)


def trajectory_svg(traj, days: float) -> str:
    lo, hi = 0.0, 80.0
    height = H - PAD_T - PAD_B
    width = W - PAD_L - PAD_R

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="Simulierter Verlauf über {days:.0f} Tage">',
        f"<style>{STYLE}</style>",
        f'<rect class="bg" width="{W}" height="{H}"/>',
    ]

    # Die harten Wochen als Band
    x0 = PAD_L + width * 9 / days
    x1 = PAD_L + width * 16 / days
    parts.append(f'<rect class="band" x="{x0:.1f}" y="{PAD_T}" '
                 f'width="{x1 - x0:.1f}" height="{height}"/>')
    parts.append(f'<text class="bandl" x="{(x0 + x1) / 2:.0f}" y="{PAD_T + 14}" '
                 f'text-anchor="middle">zwei harte Wochen</text>')

    # Waagerechte Hilfslinien
    for value in (0, 20, 40, 60, 80):
        y = PAD_T + height * (1 - (value - lo) / (hi - lo))
        parts.append(f'<line class="grid" x1="{PAD_L}" y1="{y:.1f}" '
                     f'x2="{W - PAD_R}" y2="{y:.1f}"/>')
        parts.append(f'<text class="label" x="{PAD_L - 10}" y="{y + 4:.1f}" '
                     f'text-anchor="end">{value}</text>')

    # Tagesmarken
    for day in range(0, int(days) + 1, 5):
        x = PAD_L + width * day / days
        parts.append(f'<line class="axis" x1="{x:.1f}" y1="{PAD_T + height}" '
                     f'x2="{x:.1f}" y2="{PAD_T + height + 5}"/>')
        parts.append(f'<text class="label" x="{x:.1f}" y="{H - 14}" '
                     f'text-anchor="middle">{day}</text>')
    parts.append(f'<text class="note" x="{W - PAD_R}" y="{H - 14}" '
                 f'text-anchor="end">Tage</text>')

    # Kurven
    for key, colour, label in SERIES:
        values = traj.series(key)
        parts.append(f'<path d="{_path(values, lo, hi, days)}" fill="none" '
                     f'stroke="{colour}" stroke-width="1.6" '
                     f'stroke-linejoin="round"/>')

    # Legende
    x = PAD_L
    for key, colour, label in SERIES:
        parts.append(f'<rect x="{x}" y="{PAD_T - 16}" width="9" height="9" '
                     f'fill="{colour}"/>')
        parts.append(f'<text class="label" x="{x + 14}" y="{PAD_T - 8}">'
                     f'{label}</text>')
        x += 24 + len(label) * 7.2
    parts.append(f'<text class="note" x="{W - PAD_R}" y="{PAD_T - 8}" '
                 f'text-anchor="end">Profil kira · simuliert in 0,4 s</text>')

    parts.append("</svg>")
    return "\n".join(parts)


LOOP_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 340"
     width="880" height="340" role="img"
     aria-label="Der Regelkreis: Ereignis, Botenstoffe, Zustände, Prompt">
<style>
  .bg   { fill: #FBFCFB; }
  .box  { fill: #F1F4F2; stroke: #D5DCD9; stroke-width: 1.2; }
  .core { fill: #F0DED5; stroke: #A94A24; stroke-width: 1.4; }
  .t    { fill: #16211F; font: 600 14px 'Zilla Slab', Georgia, serif; }
  .s    { fill: #5C6B67; font: 400 11px 'Source Sans 3', system-ui, sans-serif; }
  .m    { fill: #8C9A95; font: 500 10px 'IBM Plex Mono', ui-monospace, monospace; }
  .a    { stroke: #8C9A95; stroke-width: 1.4; fill: none; }
  .af   { fill: #8C9A95; }
  .back { stroke: #A94A24; stroke-width: 1.4; fill: none; stroke-dasharray: 4 3; }
  .backf{ fill: #A94A24; }
  .backl{ fill: #A94A24; font: 500 10px 'IBM Plex Mono', ui-monospace, monospace; }
  @media (prefers-color-scheme: dark) {
    .bg   { fill: #161F1C; }
    .box  { fill: #1C2724; stroke: #2C3835; }
    .core { fill: #3A2318; stroke: #E08050; }
    .t    { fill: #E3EAE7; }
    .s    { fill: #93A29D; }
    .m    { fill: #6D7C77; }
    .a    { stroke: #6D7C77; }
    .af   { fill: #6D7C77; }
    .back { stroke: #E08050; }
    .backf{ fill: #E08050; }
    .backl{ fill: #E08050; }
  }
</style>
<rect class="bg" width="880" height="340"/>
<defs>
  <marker id="h" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
    <path d="M0,0 L7,3.5 L0,7 z" class="af"/>
  </marker>
  <marker id="hb" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
    <path d="M0,0 L7,3.5 L0,7 z" class="backf"/>
  </marker>
</defs>

<rect class="box" x="20" y="112" width="150" height="66" rx="2"/>
<text class="t" x="95" y="140" text-anchor="middle">Ereignis</text>
<text class="s" x="95" y="160" text-anchor="middle">„Build ist rot"</text>

<line class="a" x1="176" y1="145" x2="222" y2="145" marker-end="url(#h)"/>

<rect class="core" x="228" y="60" width="196" height="170" rx="2"/>
<text class="t" x="326" y="88" text-anchor="middle">Botenstoffe</text>
<text class="s" x="326" y="110" text-anchor="middle">schütten aus · zerfallen</text>
<text class="s" x="326" y="127" text-anchor="middle">koppeln sich</text>
<text class="m" x="326" y="156" text-anchor="middle">Rate pro Stunde</text>
<line class="a" x1="256" y1="172" x2="396" y2="172"/>
<text class="s" x="326" y="192" text-anchor="middle">Ruhewert =</text>
<text class="m" x="326" y="210" text-anchor="middle">Grund · Rhythmus</text>
<text class="m" x="326" y="224" text-anchor="middle">Stimmung · Drift</text>

<line class="a" x1="430" y1="145" x2="476" y2="145" marker-end="url(#h)"/>

<rect class="box" x="482" y="96" width="164" height="98" rx="2"/>
<text class="t" x="564" y="124" text-anchor="middle">Zustände</text>
<text class="s" x="564" y="145" text-anchor="middle">FEUER · FOKUS</text>
<text class="s" x="564" y="162" text-anchor="middle">RUHIG · MÜDE</text>
<text class="m" x="564" y="182" text-anchor="middle">aus dem Profil</text>

<line class="a" x1="652" y1="145" x2="698" y2="145" marker-end="url(#h)"/>

<rect class="box" x="704" y="112" width="156" height="66" rx="2"/>
<text class="t" x="782" y="140" text-anchor="middle">Tonfall</text>
<text class="s" x="782" y="160" text-anchor="middle">Prompt-Zusatz</text>

<path class="back" d="M782,186 L782,272 L326,272 L326,238" marker-end="url(#hb)"/>
<text class="backl" x="554" y="290" text-anchor="middle">
  Was daraus wird, verändert wieder den Zustand
</text>

<text class="m" x="95" y="200" text-anchor="middle">event()</text>
<text class="m" x="782" y="200" text-anchor="middle">render()</text>
<text class="m" x="326" y="46" text-anchor="middle">equilibrium() sagt vorher, wo das landet</text>
</svg>
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    scenario = month_scenario()
    traj = run(scenario)
    (OUT / "verlauf-30-tage.svg").write_text(
        trajectory_svg(traj, scenario.days), encoding="utf-8")

    (OUT / "regelkreis.svg").write_text(LOOP_SVG, encoding="utf-8")

    print(f"{OUT / 'verlauf-30-tage.svg'}  ({len(traj.samples)} Messpunkte)")
    print(f"{OUT / 'regelkreis.svg'}")
    for key, _colour, label in SERIES:
        values = traj.series(key)
        print(f"  {label:12} {min(values):6.1f} … {max(values):6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
