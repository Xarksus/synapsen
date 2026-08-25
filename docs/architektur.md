# Architektur

    Ereignis  →  Engine  →  Snapshot  →  Renderer  →  Prompt
                   │
                   ├── Profile     (Biochemie als Daten)
                   ├── Dynamics    (Raten, Gleichgewicht)
                   ├── Store       (Zustand über Prozesse hinweg)
                   └── Journal     (Historie → Stimmungslage)

## Die Schichten

**`profile`** hält die gesamte Biochemie: welche Botenstoffe es gibt, wie sie
zerfallen, wie sie sich koppeln, welche Zustände daraus entstehen, welche
Ereignisse es gibt. Der Kern weiß nichts davon — er führt nur aus, was hier
steht. Das ist die Bedingung dafür, dass ein und derselbe Code sowohl ein
fünfachsiges Beziehungsmodell als auch ein zweiachsiges Arbeitsmodell trägt.

**`dynamics`** ist die Physik: `flux()` gibt die Änderungsrate je Botenstoff in
Einheiten pro Stunde, `step()` integriert sie über eine Zeitspanne,
`equilibrium()` rechnet aus, wo das System ohne jeden Reiz landet.

Dass `equilibrium()` dieselbe `step()`-Funktion benutzt wie der Betrieb, ist
Absicht: die Analyse kann nicht von der echten Dynamik abweichen, weil sie
dieselbe ist. Ein danebenstehendes Analysemodell würde mit der Zeit
auseinanderlaufen.

**`engine`** verwaltet den Zustand über die Zeit: Reize, Gewöhnung, Bindung,
Ermüdung, Protokoll. Der Ruhewert ist hier keine Konstante, sondern eine Summe
aus Grundwert, Tagesrhythmus, Stimmungslage und Drift, die bei jedem
Zeitschritt neu gebildet wird.

**`journal`** hält die Ereignishistorie und leitet daraus die Stimmungslage der
letzten Woche ab — als gewichteten Mittelwert, damit die Anzahl der Einträge
das Ergebnis nicht dominiert.

**`store`** schreibt den Zustand atomar und feldweise. Damit können mehrere
Prozesse dieselbe Datei benutzen, ohne sich zu überschreiben.

**`render`** übersetzt einen Snapshot in Text. Bewusst außerhalb des Kerns:
Sprache, Anrede und Tonfall gehören zur Anwendung, nicht zum Modell.

## Warum Raten pro Stunde

Jede Größe, die den Zustand bewegt, ist als Rate pro Stunde formuliert. Das hat
drei Folgen:

1. **Frequenzunabhängigkeit.** Das Ergebnis hängt davon ab, wie viel Zeit
   vergangen ist, nicht davon, wie oft eine Methode aufgerufen wurde.
2. **Vorhersagbarkeit.** Die Gleichgewichtsverschiebung einer Kopplung ist
   `gain / decay(ziel)` — man kann sie hinschreiben, statt sie zu messen.
3. **Prüfbarkeit.** `validate` kann daraus ableiten, ob eine Kopplung ihr Ziel
   an eine Grenze drückt, bevor irgendetwas läuft.

## Zeitschritte

Integriert wird mit fester Schrittweite (`STEP_HOURS = 0.1`), deutlich kleiner
als die schnellste Zeitkonstante im Standardprofil. Für Lücken über 30 Stunden
wird direkt auf das Gleichgewicht gesprungen: nach dem Vielfachen der
langsamsten Zeitkonstante ist der Unterschied nicht mehr messbar, und hunderte
Schritte zu rechnen wäre Verschwendung.

## Erweitern

Ein neuer Botenstoff, eine neue Kopplung, ein neuer Zustand oder ein neues
Ereignis sind Einträge im Profil — kein Codeeingriff. Was Code braucht:

- eine neue **Sonderquelle** in einem Zustand (wie `_adenosine`) →
  `engine._derive()`
- ein neuer **Speicher** oder ein neues **Journal** → das jeweilige Protokoll
  in `store.py` bzw. `journal.py` erfüllen
- eine andere **Ausgabeform** → einen eigenen Renderer schreiben
