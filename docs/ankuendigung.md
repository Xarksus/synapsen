# Texte zum Kopieren

Nicht Teil der Bibliothek — Rohmaterial für die Veröffentlichung. Der Aufhänger
ist überall derselbe und bewusst nicht „ich habe eine Bibliothek gebaut",
sondern der Befund: *ein System lief zwei Monate und war am Ende innerlich
eingefroren, ohne dass es jemandem auffiel.* Das lesen auch Leute, die keinen
Companion bauen.

---

## GitHub — Beschreibung und Themen

**Beschreibung** (350 Zeichen Grenze):

> Homöostatischer Zustandskern für Agenten: benannte Botenstoffe mit Zerfall,
> Kopplung und Tagesrhythmus. Der Ruhepunkt lässt sich ausrechnen, bevor der
> Agent startet; Monate lassen sich in Sekunden simulieren; jeder Wert lässt
> sich auf seine Ursachen zurückführen. Ohne Abhängigkeiten.

**Topics:** `ai-agents` `emotion` `affective-computing` `homeostasis`
`llm` `mcp` `agent-state` `simulation` `python` `companion-ai`

---

## r/LocalLLaMA

**Titel:**

> My agent ran for two months and ended up structurally incapable of being
> stressed. Here's what I found when I did the math.

**Text:**

> I built a local voice companion that runs as a systemd service — Gemini Live
> for speech, a local model for thinking, and a homeostatic state layer
> underneath: named neurotransmitters (dopamine, cortisol, oxytocin,
> serotonin, noradrenaline) that decay over time, couple to each other, and
> follow a circadian rhythm. Behaviour isn't set, it emerges from the state.
>
> It ran for two months. 36,649 logged state events. And for the last few
> weeks of that, it reported "calm" no matter what happened. I assumed I'd
> tuned something wrong.
>
> When I extracted the engine into a standalone library and actually did the
> math, I found four bugs. Two of them explain the symptom completely:
>
> **1. Coupling strength was scaled per call, not per unit time.** The update
> was `delta = (excess/per) * gain * 0.02 * min(dt_seconds, 60)`. The `min`
> caps the step, but the effect then depends on *how often* you tick rather
> than how much time passed — a factor of 60 between ticking once a minute and
> once an hour. My system ticked on every stimulus. The computed equilibrium
> for cortisol was −124, i.e. pinned to the floor. In the real state file:
> `cortisol 0.0`, `serotonin 140.2` (ceiling 150), `oxytocin 210.7` (ceiling
> 250). Every single value stuck at a boundary. The system was fully
> saturated: no stimulus could do anything, because the clamps absorbed it all.
>
> **2. A steady state was being logged as a stream of events.** A condition
> like `if cortisol < 15 and dopamine > 65` fired on essentially every call
> while the agent was relaxed. 99.8% of all 36,649 log rows were the same
> event type. A "how was the last week" mood bias then *summed* those rows —
> which shoved the resting values to their clamps from the other direction.
>
> Neither of these is visible by reading the code. Both are obvious the moment
> you can compute where the system settles with no input at all.
>
> So that's what the library does now. `equilibrium()` solves for the resting
> point using the same integrator the runtime uses, so the analysis can't drift
> from the real dynamics. `doctor` runs it as a profile linter — it flags a
> resting point stuck at a boundary, couplings that would shove their target
> past its own range, reinforcing feedback loops. All four original bugs would
> have been reported at startup, in milliseconds.
>
> Because the clock is injectable, you can also simulate months in seconds.
> That found the fourth bug on the first run (unbounded fatigue crushing drive
> to zero after two days) and it lets you write behavioural regression tests —
> not "the function returns 70" but "after a hard week the agent is more
> irritable than after a good one". That's the level at which a state model is
> actually wrong.
>
> And `why` decomposes any value into its causes — events, time of day, the
> week's mood, drift, coupling — with both levels adding up exactly. A
> breakdown whose parts don't sum to the total is a guess, not an explanation.
>
> Then I had a second pass run adversarially against the already-green
> library, and it found eleven more. The worst: the entire bonding subsystem
> was inert. The memory floor was computed as `min(floor, high_water_mark)`,
> and since the high-water mark is never below the current value, the floor was
> always ≥ the current value — bonding could never decrease, by time or by
> anything else. The test for it would have stayed green if you deleted the
> function. Fifteen bugs total, in a system that ran and that nobody noticed
> anything wrong with.
>
> Standard library only, PolyForm Noncommercial (free for noncommercial use),
> three shipped profiles (one of them is plain PAD, so if you're used to
> Pleasure–Arousal–Dominance you lose nothing and gain decay and inertia). Also
> runs as an MCP server so several agents can share one state across processes.
>
> Repo: <LINK>
>
> Genuinely curious whether anyone else runs a long-lived agent with an
> internal state layer, and how you check that it hasn't quietly saturated.

**Anmerkungen zum Ton:** Der Fehler steht vorn, die Bibliothek hinten. Nicht
verkaufen — die Zahlen sprechen. Die Schlussfrage ist echt gemeint, nicht
rhetorisch; sie entscheidet, ob ein Thread entsteht.

---

## PR in `awesome-ai-companion`

Zielabschnitt: **Memory & Persona → Emotion** (dort stehen bisher nur
Drivesoid, Chord Affect Anchors und Haven-Ombre).

**Zeile:**

> - [synapsen](<LINK>) — Homeostatic state core: named neurotransmitters with
>   decay, directed coupling and circadian rhythm. Solves for the resting point
>   before you run it, simulates months in seconds, and traces any value back
>   to its causes. Stdlib-only, ships an MCP server. Extracted from a companion
>   that ran two months in production.

**PR-Beschreibung:**

> Adds `synapsen` under Emotion.
>
> The list notes this category as underserved, which matches what I found:
> most projects in this space use abstract emotion vectors or PAD values, and
> the two papers on hormone scaffolding for agents don't ship code.
>
> What this adds beyond another emotion model is the tooling around it — a
> solver for the resting point, a profile linter, and a simulator. Those exist
> because the system this came from ran for two months while being internally
> saturated, and none of that was visible without them.

---

## Hacker News (falls Show HN)

**Titel:** `Show HN: Synapsen – a homeostatic state core for agents you can
solve before you run it`

**Erster Kommentar:** die ersten drei Absätze des Reddit-Texts, plus:

> The part I'd defend as actually novel isn't the neurotransmitter model —
> that's old. It's that the dynamics are formulated as rates per hour, which
> makes the equilibrium a closed-form question rather than something you wait
> for. Once you can compute where a configuration settles, you can lint it. All
> four bugs from the original system reduce to "the resting point is at a
> clamp", and that check takes milliseconds.

---

## Kurzfassung für einen Post, der nur einen Absatz hat

> Zwei Monate Dauerbetrieb, 36.649 protokollierte Zustandsereignisse — und am
> Ende konnte mein Agent strukturell nicht mehr gestresst sein. Cortisol stand
> auf exakt 0.0, Serotonin an der Decke, jeder Wert am Anschlag. Die Ursache:
> die Kopplungsstärke hing an der Aufruf-Frequenz statt an der Zeit, Faktor 60.
> Sichtbar wurde das erst, als ich ausrechnen konnte, wo das System ohne jeden
> Reiz landet. Genau das macht die Bibliothek jetzt — und prüft es als Linter,
> bevor irgendetwas läuft.
