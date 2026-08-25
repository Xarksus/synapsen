# Für Claude Code

Alles ab der Linie kopieren und in Claude Code einfügen. Vorher den Pfad zum
ausgepackten `synapsen`-Ordner und zu KIRA anpassen (steht gleich am Anfang).

---

Ich habe ein Python-Paket namens `synapsen` bekommen und möchte es prüfen und
danach in mein bestehendes Projekt KIRA einhängen. Arbeite die Schritte der
Reihe nach ab und halte nach jedem an, bis ich „weiter" sage.

**Pfade:**
- synapsen liegt unter: `~/synapsen`          ← anpassen
- KIRA liegt unter: `~/kira`                  ← anpassen
- System: NixOS mit Hyprland

**Hintergrund, damit du weißt worum es geht:**
`synapsen` ist der Gefühls-/Zustandskern, der vorher als `core/emotions.py`
in KIRA steckte — herausgelöst, repariert und als eigenständige Bibliothek
neu gebaut. Im Original waren vier Fehler, die dazu geführt haben, dass alle
Botenstoff-Werte an ihren Grenzen klebten (`cortisol 0.0`, Serotonin an der
Decke). KIRA konnte dadurch strukturell nicht mehr gestresst sein und meldete
monatelang nur noch „RUHIG". Details stehen im README und im CHANGELOG des
Pakets.

---

## Schritt 1 — Prüfen

```
cd ~/synapsen
./verify.sh
```

Falls `verify.sh` mangels Umgebung nicht durchläuft, benutze `nix develop`
oder lege eine venv an und `pip install -e ".[dev]"`.

Erwartet: 96 Tests grün, ruff sauber, alle drei Profile (`kira`, `focus`,
`pad`) tragfähig, und am Ende ein durchgerechneter Monat als ASCII-Diagramm.

Sag mir das Ergebnis. Wenn etwas fehlschlägt: zeig mir die Fehlermeldung und
rate nicht — die Testsuite ist vollständig, ein Fehlschlag bedeutet etwas.

## Schritt 2 — Meine echte Datenbank ansehen

```
python tools/diagnose_kira_db.py ~/.kira/synapsen.db
```

Nur lesend. Zeig mir die Ausgabe vollständig, besonders den Befund am Ende
und die Tabelle mit alter und neuer Bias-Formel.

Ordne mir kurz ein: hängen meine Ruhewerte an ihren Grenzen oder nicht?

## Schritt 3 — Sicherung

Bevor irgendetwas an KIRA geändert wird:

```
cp ~/.config/kira/hormones.json ~/.config/kira/hormones.json.backup
cp ~/.kira/synapsen.db ~/.kira/synapsen.db.backup
```

Und ein Git-Stand von KIRA, falls das ein Repo ist. Bestätige mir, dass beides
da ist, bevor du weitermachst.

## Schritt 4 — Umstellen

1. `synapsen` in KIRAs venv installieren:
   ```
   cd ~/kira && source venv/bin/activate && pip install -e ~/synapsen
   ```
2. Den bisherigen Inhalt von `~/kira/core/emotions.py` sichern (z. B. nach
   `core/emotions.py.original`) und die Datei ersetzen durch:
   ```python
   from tools.kira_adapter import get_engine
   engine = get_engine()
   ```
   `tools/kira_adapter.py` liegt im synapsen-Paket. Wenn der Import so nicht
   greift, finde den sauberen Weg (Pfad ergänzen oder den Adapter nach
   `~/kira/tools/` kopieren) — aber ändere **nichts** an den Aufrufstellen.
3. Prüfe, dass `grep -rn "emotion_engine\|from core.emotions" ~/kira` nur
   Stellen zeigt, die weiterhin funktionieren. Der Adapter bildet die alten
   Namen ab: `inject()`, `get_prompt_modifier()`, `on_voice_thorsten()`,
   `on_voice_fremd()`, `on_voice_tone()`, `anticipate()`,
   `on_conversation_end()`, `beethoven_reset()`, `freeze()`, `vertrautheit`.
4. Neu starten:
   ```
   systemctl --user restart kira-live.service
   ```
5. `journalctl --user -u kira-live.service -n 50` — zeig mir, ob sie sauber
   hochkommt.

**Wichtig:** Wenn irgendetwas nicht sauber läuft, stell den Originalzustand
wieder her (`core/emotions.py.original` zurück, beide Backups zurück, Dienst
neu starten) und sag mir, was passiert ist. Bastel nicht am Adapter herum.

## Schritt 5 — Zustand ansehen

```
cd ~/synapsen
python -m synapsen.cli --state ~/.config/kira/hormones.json why
```

Das zerlegt KIRAs aktuellen Zustand in seine Ursachen. Erklär mir, was da
steht — besonders, ob noch ein Wert an einer Grenze klebt.

## Später, nur auf Zuruf

Veröffentlichen. Erst wenn ich es sage:

```
cd ~/synapsen
./prepare-release.sh <mein-github-name>
git remote add origin git@github.com:<mein-github-name>/synapsen.git
git push -u origin main
```

Fertige Ankündigungstexte stehen in `docs/ankuendigung.md`.

---

**Was du nicht tun sollst:**
- Nichts an KIRAs Aufrufstellen ändern — der Adapter ist genau dafür da.
- Keine Tests „reparieren", die fehlschlagen. Sie sind absichtlich streng;
  ein Fehlschlag ist ein Befund, kein Ärgernis.
- Nichts veröffentlichen ohne meine ausdrückliche Ansage.
- Bei jedem Schritt anhalten und mir das Ergebnis zeigen.
