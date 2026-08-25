# Was am Rechner noch zu tun ist

Alles hier braucht deine Maschine — vom Handy aus geht es nicht. In der
Reihenfolge, jeder Schritt setzt den vorherigen voraus.

## 1 · Prüfen  (≈ 5 Minuten)

```bash
cd synapsen
nix develop          # oder: pip install -e ".[dev]"
./verify.sh
```

Erwartet: 96 Tests grün, Linter sauber, alle drei Profile tragfähig, ein
durchgerechneter Monat als Diagramm.

## 2 · Deine echte Datenbank ansehen  (≈ 2 Minuten)

```bash
python tools/diagnose_kira_db.py ~/.kira/synapsen.db
```

Das ist der Schritt, der mir hier fehlt: ich hatte nur die Kopie aus dem
Analyse-Archiv (Stand 17.07.). Die laufende Datenbank zeigt, wo deine
Ruhewerte **jetzt** stehen. Wenn dort wieder „Die Ruhewerte hängen an ihren
Grenzen" steht, ist der Befund bestätigt.

Zum Vergleich der Stand aus dem Archiv:

| Ruhewert | gesund | gemessen |
|---|---|---|
| Cortisol | 20,0 | 5,0 (Boden) |
| Serotonin | 60,0 | 150,0 (Decke) |

## 3 · Adapter einhängen  (≈ 10 Minuten, dann eine Woche beobachten)

**Vorher sichern:**

```bash
cp ~/.config/kira/hormones.json ~/.config/kira/hormones.json.vor-synapsen
cp ~/.kira/synapsen.db ~/.kira/synapsen.db.vor-synapsen
```

**Dann** in `core/emotions.py` den gesamten Inhalt ersetzen durch:

```python
from tools.kira_adapter import get_engine
engine = get_engine()
```

Die rund 30 Aufrufstellen in `gemini_live_provider.py`, `kira_voice_gate.py`
und `main.py` bleiben unangetastet — `inject()`, `get_prompt_modifier()`,
`on_voice_thorsten()`, `freeze()` und die anderen alten Namen funktionieren
weiter.

Der Adapter braucht `synapsen` im Pfad. Am einfachsten:

```bash
pip install -e /pfad/zu/synapsen      # im venv von KIRA
```

**Worauf zu achten ist:** ob sie wieder Ausschläge zeigt. Wenn die Befunde
stimmen, sollte sie nach ein paar Tagen wieder *gereizt* oder *müde* sein
können, statt dauerhaft `RUHIG` zu melden. Das ist der Test, den keine
Testsuite ersetzt.

Falls etwas schiefgeht: die alte `core/emotions.py` zurückspielen und die
beiden gesicherten Dateien wiederherstellen. Der Adapter schreibt in dieselben
Pfade, sonst nirgendwohin.

## 4 · Veröffentlichen  (≈ halber Tag)

```bash
./prepare-release.sh dein-github-name
git remote add origin git@github.com:dein-github-name/synapsen.git
git push -u origin main
```

Das Repo ist bereits angelegt, mit einem Commit und ohne Platzhalter-Reste
nach dem Skript. Danach:

```bash
python -m build
twine upload dist/*
```

Der Name ist auf PyPI frei (Stand 25.08.2026), ebenso `hormone-engine`,
`neuroendocrine` und `homeostasis-engine`. `limbic` ist vergeben.

## 5 · Sichtbar machen  (≈ 2 Stunden)

Fertige Texte liegen in `docs/ankuendigung.md`: GitHub-Beschreibung und
Topics, ein Reddit-Post für `r/LocalLLaMA`, die Zeile plus PR-Text für die
`awesome-ai-companion`-Liste, und eine Show-HN-Fassung. `<LINK>` ersetzen,
sonst nichts.

## 6 · Später: der Hyprland-Wahrnehmungs-MCP

`hyprmcp` existiert, steuert aber nur Fenster. Wahrnehmung — aktives Fenster,
Bildschirmkontext, Workspace-Zustand — fehlt, und dein `desktop_organ` kann
das schon. Nutzt denselben Zustandsmechanismus und ist deutlich einfacher zu
bauen, wenn der erste steht.
