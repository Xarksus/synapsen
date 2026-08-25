# Änderungsverlauf

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.1.0] — nicht veröffentlicht

Erste Fassung. Herausgelöst aus einem Companion-System, das zwei Monate im
Dauerbetrieb lief; die vier Fehler unten stammen aus diesem Betrieb und wurden
erst durch die hier neu gebauten Werkzeuge sichtbar.

### Neu

- `HomeostasisEngine` — Regelkreis aus Botenstoffen, Kopplungen, Tagesrhythmus,
  Ermüdung, Gewöhnung und Bindung
- `Profile` — die gesamte Biochemie als Daten, inklusive eigener Ereignistabelle
- `dynamics` — Änderungsraten pro Stunde, Gleichgewichtslöser, Impulsantwort
- `validate.check()` — Profil-Prüfung, findet pathologische Konfigurationen
  vor dem Betrieb
- `simulate` — Szenarien, Verläufe, ASCII-Diagramme, CSV-Ausgabe
- `explain()` — Zerlegung des Zustands in Ereignisse, Rhythmus, Stimmungslage,
  Drift und Kopplung
- `PromptRenderer` — Zustand als Text, getrennt vom Kern, de/en
- `JsonStore` mit atomarem Merge-Write; `SqliteJournal`, das sich einem
  vorhandenen Schema anpasst
- MCP-Server (stdio-JSON-RPC, ohne SDK-Abhängigkeit) mit sieben Werkzeugen
- Kommandozeile: `doctor`, `show`, `why`, `event`, `simulate`, `events`,
  `profiles`, `mcp`
- Drei mitgelieferte Profile: `kira`, `focus`, `pad`
- `flake.nix` für NixOS

### Behoben (gegenüber der Ursprungsfassung)

- **Kopplungsstärke hing an der Aufruf-Frequenz** statt an der Zeit — Faktor 60
  zwischen minütlichem und stündlichem Tick. Das rechnerische Gleichgewicht für
  Stress lag bei −124, also am Boden; in der echten Zustandsdatei stand
  `cortisol: 0.0` bei gleichzeitig gesättigtem Serotonin und Oxytocin.
  Kopplungen sind jetzt in Einheiten pro Stunde definiert und werden über die
  verstrichene Zeit integriert.
- **Ein Dauerzustand wurde als Ereignisstrom protokolliert** (99,8 % aller
  Einträge derselbe Typ). Der Stimmungs-Bias summierte diese Einträge und
  schob die Ruhewerte an ihre Anschläge. Jetzt: Entprellung, gewichteter
  Mittelwert statt Summe, begrenzter Ausschlag.
- **Tagesrhythmus und Stimmungslage wurden nur beim Start berechnet.** Ein
  durchlaufender Dienst blieb im Rhythmus seiner Startstunde stehen. Der
  Ruhewert wird jetzt bei jedem Zeitschritt neu zusammengesetzt.
- **Ermüdung wuchs unbegrenzt** und drückte den Antrieb nach zwei Tagen
  dauerhaft auf null. Jetzt asymptotisch gesättigt, mit Abbau in den
  Ruhestunden des Profils.
- **Ein fester Bindungs-Boden hob jeden frischen Agenten sofort auf „sehr
  vertraut".** Der Boden ist jetzt ein Erinnerungswert und greift nur bis zu
  dem Wert, der tatsächlich einmal erreicht wurde.
- **Singleton beim Import** entfernt: `import` löst keine Datei- oder
  Datenbankzugriffe mehr aus.
- **Schreibkonflikt** zwischen zwei Prozessen auf derselben Zustandsdatei:
  feldweiser Merge unter Dateisperre, plus ein Besitzkennzeichen, an dem eine
  Engine erkennt, dass ein anderer Schreiber am Zug war.

### Behoben (aus der Gegenprüfung dieser Bibliothek)

Eine gezielte Prüfrunde gegen die erste grüne Fassung. Alle Punkte sind mit
Regressionstests belegt, die gegen den Stand von vorher fehlschlagen.

- **Der Bindungszerfall war stillgelegt.** Der Erinnerungsboden wurde als
  `min(boden, höchststand)` gerechnet und lag damit rechnerisch immer über dem
  aktuellen Wert — die Bindung konnte weder durch Zeit noch durch `strain_bond()`
  je sinken. Der zugehörige Test bemerkte es nicht, weil er nur „warm > kalt"
  prüfte. Der Boden greift jetzt erst, wenn er tatsächlich erreicht wurde;
  `decay_per_hour` ist neu kalibriert (1.0 → 0.01), weil der Wert nie wirken
  konnte und darum nie stimmen musste.
- **Unstetigkeit beim Sprung aufs Gleichgewicht.** Bei Lücken über 30 Stunden
  fiel der Ermüdungsdruck weg; eine längere Abwesenheit machte den Agenten
  dadurch wacher.
- **Die Stimmungslage überlebte den Neustart nicht.** Ohne Protokoll wurde der
  gespeicherte Wert beim Start mit 0.0 überschrieben.
- **Eine rückwärts laufende Uhr fror den Zustand ein**, bis die Wanduhr
  aufgeholt hatte — und entlud sich dann in einem Satz.
- **Die Entprellung lag nur im Arbeitsspeicher** und griff darum bei einem
  Prozess je Ereignis (der Kommandozeile) nie.
- **`resume()` rechnete die Erholung doppelt** an.
- **Profile ohne Bindung meldeten trotzdem eine Vertrautheit von 50.**
- **Entartete Profile brachten die Prüfung zum Absturz**, statt gemeldet zu
  werden — beim Werkzeug, dessen Zweck genau das Melden ist.
- **`explain()` lieferte eine Zerlegung, deren Teile sich nicht zur Summe
  fügten.** Beide Ebenen gehen jetzt exakt auf; was übrig bleibt, steht als
  „Nachlauf" ausdrücklich da.
- **Das Journal legte für jedes Profil KIRAs fünf Spalten an**; `simulate`
  funktionierte nur mit dem `kira`-Profil; `mcp` verwarf ein mitgeliefertes
  Profil stillschweigend.
- **`fatigue_targets` hatte konkrete Botenstoffnamen als Vorgabe im Kern** und
  überschrieb beim JSON-Roundtrip ein bewusst leeres Feld.
- **Ein Ereignis löste einen Schreibvorgang je Botenstoff aus** statt einen.
- **Vier Tests prüften nichts** (eine Zusicherung war konstant wahr, eine
  verglich einen Wert mit sich selbst) und wurden durch echte ersetzt.
