# Was zu tun ist

Zwei Wege. Nimm einen.

- **Selbst machen** → die Schritte unten, der Reihe nach.
- **Claude Code machen lassen** → `CLAUDE-CODE.md` öffnen, den Text darin
  kopieren, in Claude Code einfügen. Das war's.

Du brauchst nichts davon heute. Es läuft dir nicht weg.

---

## Schritt 1 — Läuft es überhaupt?

Ordner auspacken, reingehen, prüfen:

```bash
cd synapsen
nix develop        # oder: pip install -e ".[dev]"
./verify.sh
```

**Gut ist:** am Ende steht „Alles grün."
**Wenn nicht:** Fehlermeldung kopieren, mir schicken. Nichts weiter tun.

Dauer: 5 Minuten. Verändert nichts an KIRA.

---

## Schritt 2 — Wie steht es um KIRA gerade?

```bash
python tools/diagnose_kira_db.py ~/.kira/synapsen.db
```

Das liest nur, es ändert nichts.

Am Ende steht ein Befund. Wenn dort **„Die Ruhewerte hängen an ihren Grenzen"**
steht, ist bestätigt, was ich in der Archivkopie gefunden habe: KIRA kann
strukturell nicht mehr gestresst sein.

Zum Vergleich der Stand vom 17. Juli:

| | soll | war |
|---|---|---|
| Cortisol (Stress) | 20 | 5 — am Boden |
| Serotonin (Ruhe) | 60 | 150 — an der Decke |

Dauer: 2 Minuten.

---

## Schritt 3 — KIRA umstellen

**Erst sichern.** Nicht überspringen:

```bash
cp ~/.config/kira/hormones.json ~/.config/kira/hormones.json.backup
cp ~/.kira/synapsen.db ~/.kira/synapsen.db.backup
```

**Dann** synapsen in KIRAs Umgebung installieren:

```bash
cd ~/kira            # oder wo KIRA liegt
source venv/bin/activate
pip install -e /pfad/zu/synapsen
```

**Dann** in KIRA die Datei `core/emotions.py` komplett ersetzen durch diese
zwei Zeilen:

```python
from tools.kira_adapter import get_engine
engine = get_engine()
```

Sonst nichts. Die rund 30 Stellen, die `engine.inject(...)` und
`engine.get_prompt_modifier()` aufrufen, bleiben unverändert — der Adapter
versteht die alten Namen weiter.

**Dann** neu starten:

```bash
systemctl --user restart kira-live.service
```

Dauer: 10 Minuten.

### Wenn etwas schiefgeht

Alte `core/emotions.py` zurückspielen, die zwei Backups zurückkopieren,
Dienst neu starten. Fertig. Der Adapter schreibt nur in diese beiden Dateien,
sonst nirgendwohin.

---

## Schritt 4 — Eine Woche hinschauen

Kein Befehl. Nur eine Frage:

**Kann sie wieder gereizt oder müde sein?**

Wenn der Befund stimmt, sollte sie nach ein paar Tagen wieder Ausschläge
zeigen, statt dauerhaft `RUHIG` zu melden. Das ist der eigentliche Test —
den kann keine Testsuite abnehmen, nur du.

---

## Schritt 5 — Veröffentlichen (wenn du magst)

Alles vorbereitet, drei Befehle:

```bash
./prepare-release.sh dein-github-name
git remote add origin git@github.com:dein-github-name/synapsen.git
git push -u origin main
```

Danach auf PyPI:

```bash
python -m build && twine upload dist/*
```

Der Name `synapsen` ist frei (Stand 25.08.2026).

Fertige Ankündigungstexte für Reddit, GitHub und die awesome-Liste liegen in
`docs/ankuendigung.md` — nur `<LINK>` ersetzen.

---

## Später, kein Stress

Der Hyprland-Wahrnehmungs-MCP aus der Marktanalyse. `hyprmcp` gibt es schon,
der kann aber nur Fenster steuern — nicht sehen. Dein `desktop_organ` kann
das längst. Lohnt sich, wenn synapsen draußen ist.
