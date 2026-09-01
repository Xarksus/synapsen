# synapsen

**A homeostatic state core for agents.** Neurotransmitters instead of mood strings.

Most agents have no state — they have an adjective in the prompt.
`synapsen` models a feedback loop instead: events release neurotransmitters
that decay, influence each other, and follow a circadian rhythm. Behavior is
not set, it *emerges*.

No dependencies beyond the standard library. Python ≥ 3.10.

![The feedback loop](docs/assets/regelkreis.svg)

## Quick start

```bash
pip install synapsen
```

```python
from synapsen import HomeostasisEngine, PromptRenderer, JsonStore

# Use the bundled kira profile — already calibrated from months of real use
engine = HomeostasisEngine(store=JsonStore("~/.config/agent/state.json"))
engine.event("task_success", context="deploy green")

# Inject the state into your agent's system prompt
state_block = PromptRenderer().render(engine.snapshot())
```

```
[INNER STATE]
Evening (19:00) | Session 42min | Fatigue 25

Neurotransmitters:
  Oxytocin 63.2 | Dopamine 71.4 | Cortisol 11.8 | Serotonin 74.0 | Noradrenaline 38.1

States (1.0 = normal, >2.0 = extreme):
  DRIVE        1.06  — Motivation, pace, direct action
  FOCUS        1.36  — Clarity, concentration, precision
  CONNECTED    0.81  — Closeness, openness, trust
  CALM         1.50  — Grounded, no need to prove anything
  TIRED        0.26  — Exhaustion, waning concentration
  …

What this means:
  → CALM (1.50) noticeable: Grounded, no need to prove anything.
  → Familiarity: 128
```

The state block goes into your system prompt. The model reads it and adjusts
its output accordingly — shorter under stress, warmer with high oxytocin — through
normal language modeling. No sampling parameters are touched. No tool list is
modified. The behavioral change emerges because the model is coherent with its
own context.

---

## What's different here

Emotion models for agents exist: PAD vectors, appraisal models, mood weights.
What's missing is a **named, inertial, coupled feedback loop** that runs for
weeks, can be computed in advance, and whose output can be traced back to its
causes.

| | typical emotion layer | `synapsen` |
|---|---|---|
| State | vector without meaning | named neurotransmitters with half-life |
| Time | per call | real elapsed time, frequency-independent |
| Coupling | none | directed, in units per hour |
| Rhythm | none | circadian rhythm, fatigue with saturation and decay |
| History | none | mood of the past week, continuously updated |
| Bonding | none | grows over weeks, cools with harshness, never fully forgotten |
| **Prediction** | — | `equilibrium()` computes the resting point |
| **Validation** | — | `doctor` finds pathological profiles before deployment |
| **Simulation** | — | months in milliseconds, for tuning and tests |
| **Traceability** | — | `why` breaks down every value into its causes |
| Persistence | process lifetime | file or SQLite, cross-process |

The default profile is not made-up numbers: these are the values of a system
that ran continuously for two months — with 36,649 logged state events, from
which the four bugs below emerged. **The calibration work is done. The `kira`
profile is ready to use as-is.**

## What you don't see until you compute it

The original version ran continuously for two months without anything obviously
breaking. These four bugs only became visible through the tools in this package
— and all four would have been caught by `synapsen doctor` in milliseconds.
That's exactly why the tools exist.

**1 · Coupling strength was tied to call frequency.** The effect was scaled per
call, not per time. Between "once per minute" and "once per hour" lay a factor
of 60. The computed equilibrium for stress was −124 — at rock bottom. In the
actual state file: `cortisol: 0.0`, `serotonin: 140.2` (ceiling 150),
`oxytocin: 210.7` (ceiling 250). Every value was stuck at a limit; the system
was saturated and no longer responded to anything.

**2 · A persistent state was logged as an event stream.** 99.8% of all entries
were the same event type. The mood bias *summed* these entries — resting values
ended up pinned at their rails. Now: debouncing at logging time, weighted
**average** instead of sum, bounded excursion.

**3 · Circadian rhythm and mood were only computed at startup.** A service
running for weeks stayed in the rhythm of its start hour and the mood of its
first second. Now the resting value is a sum recomputed fresh at every time step.

**4 · Fatigue grew without bound.** Without saturation and without overnight
decay, fatigue pressure permanently pushed drive to zero after two days.
The simulation found this on the first run.

And because a state model can still be quietly wrong on the second attempt, a
targeted cross-check was run against this library itself. It found further bugs
— including a disabled bonding decay (a floor that was computationally always
above the current value), a discontinuity when jumping to equilibrium, and a
mood baseline that didn't survive process restart. The history is in the
[changelog](CHANGELOG.md).

Each of these bugs is pinned with a regression test that fails against the
previous state.

## Core concepts

**Neurotransmitter** — a value with a resting point, decay rate, and safety ceiling.

**Coupling** — directed interaction, in units *per hour*. This unit is why
equilibrium can be computed: `shift = gain / decay(target)`.

**State** — linear combination of neurotransmitters with a name and description.
All data in the profile, not code.

**Event** — what happened, not what should change. `event("task_failure")`
remains correct when someone swaps the profile; `inject("cortisol", +12)` does not.

**Resting value** — not a constant, but
`baseline + circadian_rhythm + mood + drift`.

**Habituation** — frequent releases become blunted.

**Bonding** — grows over weeks, cools with harshness, never drops below what
was once reached.

## Tools

```bash
pip install synapsen

synapsen profiles                 # bundled profiles
synapsen doctor                   # validate profile — before deployment
synapsen simulate --days 30       # compute trajectory
synapsen show                     # current state as prompt
synapsen why                      # trace state back to its causes
synapsen event task_failure       # log an event
synapsen mcp                      # run as MCP server
```

### `doctor` — find bugs before they act for weeks

```
$ synapsen --profile ./my-profile.json doctor
[ERROR] couplings[0] oxytocin→cortisol: At maximum source, the coupling shifts
    the target by -2880 — more than its entire value range (300).
    → The target will then be pinned at a limit. Set gain to at most 60.0.
[ERROR] dynamics: Without any stimulus, cortisol=floor(0) — the system is
    saturated there.
```

Checks: resting values against their ceilings, couplings against their target's
value range, amplifying feedback loops, unknown neurotransmitters in states and
events, overlapping time windows — and, as an end-to-end test, where the system
lands without any stimulus.

### `simulate` — months in milliseconds

```
$ synapsen simulate --days 14 --event task_failure --keys cortisol,dopamine,CALM
Work week (task_failure)  ·  Profile kira-v1  ·  14 days

  cortisol  ▁▂▂▄█▄▇▆▇▄▇▆▆▅▇▅▄▇▆▆▆▇▄▇▇▆▄▇▅▆▆▆▆▄█▅▆▅▇▄▆▇▆▅▇▅▅▇▆▆▅█▄▇▆▆▄▇▆▆   12.6 … 31.2
  dopamine  █▅▂▃▇▆▂▂▆▇▃▁▅█▄▁▄█▅▂▂▇▆▂▁▆▇▃▁▄█▄▁▃▇▅▂▂▇▆▃▁▅▇▃▁▄█▄▁▃▇▆▂▂▆▇▃▁▅   15.9 … 54.9
  CALM      ▆▇█▇▁▅▄▅▂▄▃▆▃▃▄▆▅▂▄▅▅▂▅▄▅▃▄▄▆▄▃▄▅▆▁▄▅▆▂▅▄▅▃▄▃▆▅▂▄▅▆▁▅▄▅▃▄▃▆▃    1.2 …  1.6
```

An entire month computed in 0.4 seconds — two good weeks, two hard ones, then
recovery:

![Simulated trajectory over 30 days](docs/assets/verlauf-30-tage.svg)

Clear to see what a pure numbers model can't show: stability breaks later than
stress rises, and it recovers more slowly than it collapsed. That's the inertia
this is all about.

This lets you tune profiles without waiting weeks — and write behavioral
regression tests that actually check something meaningful:

```python
def test_hard_weeks_raise_stress():
    assert max(hard.series("cortisol")) > max(good.series("cortisol")) * 1.3
```

### `why` — why is the agent like this right now?

```
$ synapsen why
cortisol          47.3   (rests at 17.5, so +29.8)
     +22.1  events          test red 0.8h ago, build red 2.2h ago
      +9.0  circadian       morning
      +4.2  mood            last 7 days
      -5.5  coupling        from oxytocin, serotonin
```

## Custom profiles

```python
from synapsen import Profile, HormoneSpec, Coupling, DerivedState, check

profile = Profile(
    name="workshop",
    hormones={
        "focus":    HormoneSpec(baseline=50, decay=0.4, ceiling=200),
        "restless": HormoneSpec(baseline=15, decay=0.9, ceiling=200),
    },
    couplings=[Coupling("restless", "focus", gain=-4.0, threshold=40)],
    states=[DerivedState("CLEAR", {"focus": 1.0, "restless": -0.5},
                         valence="positive", description="able to work")],
    events={"blockade": {"restless": +18, "focus": -8, "severity": -3}},
)
assert check(profile).ok
```

Bundled are three deliberately very different profiles:

- **kira** — five neurotransmitters, bonding, circadian rhythm. Not a starting
  guess: this profile emerged from months of continuous real-world agent
  operation with tens of thousands of logged state events. Use it as-is, or
  as a calibrated baseline for your own profile.
- **focus** — two axes, no relationship. For a coding agent that gets audibly
  terser after the fifth red build.
- **pad** — Pleasure–Arousal–Dominance, the academic standard model, expressed
  in this framework.

## As an MCP server

This lets arbitrary agents — across process and session boundaries — share the
same state. Pure stdio JSON-RPC, no SDK needed.

```jsonc
{
  "mcpServers": {
    "synapsen": {
      "command": "synapsen-mcp",
      "args": ["--state", "~/.config/agent/state.json"]
    }
  }
}
```

Tools: `state_read`, `state_prompt`, `state_event`, `state_inject`,
`state_why`, `state_settle`, `state_history`.

## NixOS

```bash
nix run github:Xarksus/synapsen -- doctor
nix develop            # development environment with pytest and ruff
```

The flake provides `packages.default`, `apps.mcp` and a `devShell`.

## Migrating from an existing installation

`SqliteJournal` adapts to an existing schema rather than replacing it: it reads
the table's columns and writes what fits. An existing database with
`emotional_log` works unchanged. For a new journal,
`SqliteJournal.for_profile(path, profile)` creates the columns of the profile.

## Development

```bash
./verify.sh        # tests, linter, all profiles checked — one command
```

Or individually:

```bash
pip install -e ".[dev]"     # or: nix develop
pytest -q                   # 96 tests, ~1 s
ruff check .
python tools/make_assets.py # regenerate images
```

## License

Apache-2.0.
