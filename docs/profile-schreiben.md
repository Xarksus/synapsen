# Ein eigenes Profil schreiben

## In fünf Schritten

**1 · Achsen wählen.** Zwei bis fünf. Jede sollte etwas bedeuten, das man
benennen kann — „Anspannung", nicht „Faktor 3".

**2 · Zerfallsraten setzen.** Die Rate ist der Anteil der Differenz zum
Ruhewert, der pro Stunde abgebaut wird.

| Rate | Halbwertszeit | wofür |
|---|---|---|
| 0.2 | ~3,5 h | träge Stimmungslagen |
| 0.5 | ~1,4 h | Antrieb, Freude |
| 0.8 | ~50 min | Alarm, Anspannung |

**3 · Kopplungen in Pro-Stunde-Einheiten.** Die Verschiebung des Ruhewerts ist

    Verschiebung = gain / decay(ziel)

Beispiel: `gain = -6` auf ein Ziel mit `decay = 0.8` verschiebt den Ruhewert um
−7,5 Einheiten, wenn die Quelle voll anliegt. Als Faustregel sollte keine
Kopplung ihr Ziel um mehr als ein Drittel seines Wertebereichs verschieben —
darüber reagiert es kaum noch auf eigene Reize.

**4 · Zustände als Linearkombinationen.** Gewichte werden durch `scale`
geteilt; mit `scale = 50` bedeutet 1.0 „normal" und >2.0 „extrem".
Sonderschlüssel: `_const` (Achsenabschnitt), `_adenosine` (Ermüdungsdruck),
`_morning` (Morgen-Intensität).

**5 · Ereignisse benennen.** Beschreibe, *was passiert ist*, nicht was sich
ändern soll. `severity` fließt in die Stimmungslage der nächsten Tage.

## Prüfen, bevor es läuft

```bash
synapsen --profile ./mein-profil.json doctor
synapsen --profile ./mein-profil.json simulate --days 30
```

`doctor` meldet unter anderem: Ruhewerte über ihren Decken, Kopplungen, die ihr
Ziel an eine Grenze drücken, verstärkende Rückkopplungsschleifen, unbekannte
Botenstoffe in Zuständen und Ereignissen — und, als wichtigsten Test, wo das
System ohne jeden Reiz landet. Klebt dieser Ruhepunkt an einer Grenze, ist das
Profil kaputt, auch wenn jede einzelne Zahl plausibel aussieht.

## Häufige Fehler

**Zu starke Kopplungen.** Der verbreitetste Fehler, und der am schwersten von
Hand zu sehende: erst das Gleichgewicht zeigt, dass das Ziel am Anschlag steht.

**Decken als Notpflaster.** Eine Sicherheitsdecke, die im Normalbetrieb
erreicht wird, ist kein Schutz mehr, sondern der Betriebspunkt. Sie soll nie
greifen.

**Ereignisse, die auf einzelne Botenstoffe zielen.** Wer `inject()` in der
Anwendung benutzt, bindet sich an ein Profil. `event()` bleibt richtig, wenn
das Profil getauscht wird.

**Alles gleich träge.** Wenn alle Achsen dieselbe Zerfallsrate haben, bewegen
sie sich im Gleichschritt und tragen keine zusätzliche Information.
