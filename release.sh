#!/usr/bin/env bash
# Bereitet ein Release vor: prüft alles, baut die Pakete, kontrolliert die
# Metadaten. Lädt bewusst NICHTS hoch — der letzte Schritt bleibt bei dir,
# weil dafür dein PyPI-Token nötig ist und ein Upload nicht rückgängig geht.
#
#   ./release.sh
#
# Danach nennt dir das Skript die zwei Befehle, die noch fehlen.
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$1"; }
fail() { printf '\033[31m  ✗ %s\033[0m\n' "$1" >&2; exit 1; }

VERSION=$(python3 -c "import tomllib,pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")
NAME=$(python3 -c "import tomllib,pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['name'])")

step "Version"
echo "  ${NAME} ${VERSION}"
if git rev-parse "v${VERSION}" >/dev/null 2>&1; then
    fail "Tag v${VERSION} existiert bereits. Version in pyproject.toml erhöhen."
fi

step "Arbeitsverzeichnis"
if [ -n "$(git status --porcelain)" ]; then
    warn "Es gibt uncommittete Änderungen:"
    git status --short | sed 's/^/    /'
    warn "Das Paket wird aus den Dateien auf der Platte gebaut, nicht aus dem letzten Commit."
else
    echo "  sauber"
fi

step "Alle Prüfungen"
./verify.sh >/dev/null || fail "verify.sh ist rot. Erst reparieren, dann releasen."
echo "  verify.sh grün"

step "Name auf PyPI"
CODE=$(curl -sS -o /dev/null -w "%{http_code}" "https://pypi.org/pypi/${NAME}/json" || echo "000")
case "$CODE" in
    404) echo "  ${NAME} ist frei" ;;
    200) warn "${NAME} ist auf PyPI bereits vergeben — prüfe, ob das dein Projekt ist." ;;
    *)   warn "PyPI nicht erreichbar (HTTP ${CODE}) — übersprungen." ;;
esac

step "Pakete bauen"
python3 -m pip install --quiet --upgrade build >/dev/null 2>&1 || warn "build konnte nicht aktualisiert werden"
rm -rf dist
python3 -m build >/dev/null || fail "Der Build ist fehlgeschlagen."
ls -1 dist | sed 's/^/  /'

step "Metadaten kontrollieren"
python3 - "$VERSION" <<'PY'
import sys, zipfile, pathlib
version = sys.argv[1]
whl = next(pathlib.Path("dist").glob("*.whl"))
z = zipfile.ZipFile(whl)
md = z.read(f"{whl.name.split('-')[0]}-{version}.dist-info/METADATA").decode()
fields = dict(
    (line.split(": ", 1)[0], line.split(": ", 1)[1])
    for line in md.splitlines() if ": " in line and not line.startswith(" ")
)
problems = []
lic = fields.get("License-Expression") or fields.get("License", "")
if "PolyForm" not in lic:
    problems.append(f"Lizenz in den Metadaten ist {lic!r}, erwartet PolyForm")
if not any("LICENSE" in n.upper() for n in z.namelist()):
    problems.append("Die LICENSE-Datei liegt dem Paket nicht bei")
summary = fields.get("Summary", "")
if any(c in summary for c in "äöüßÄÖÜ"):
    problems.append("Summary ist noch deutsch — das ist der Text auf der PyPI-Seite")
print(f"  Lizenz   {lic}")
print(f"  Summary  {summary[:70]}…")
print("  LICENSE  liegt bei")
if problems:
    print()
    for p in problems:
        print(f"\033[31m  ✗ {p}\033[0m")
    sys.exit(1)
PY

step "Installation aus dem gebauten Paket testen"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
python3 -m venv "$TMP/venv"
"$TMP/venv/bin/pip" install --quiet dist/*.whl >/dev/null || fail "Das gebaute Paket lässt sich nicht installieren."
"$TMP/venv/bin/python" -c "import ${NAME}" || fail "Das installierte Paket lässt sich nicht importieren."
"$TMP/venv/bin/${NAME}" doctor >/dev/null || fail "Der Befehl '${NAME} doctor' läuft nicht."
echo "  installiert, importiert, CLI läuft"

printf '\n\033[1mAlles vorbereitet.\033[0m Es fehlen noch zwei Befehle:\n\n'
if ! python3 -c "import twine" 2>/dev/null; then
    printf '  \033[2m# twine fehlt noch:  python3 -m pip install twine\033[0m\n'
fi
printf '  python3 -m twine upload dist/*\n'
printf '  git tag v%s && git push origin v%s\n\n' "$VERSION" "$VERSION"
printf '\033[2mBeim Upload fragt twine nach Benutzername und Passwort.\n'
printf 'Benutzername ist __token__, das Passwort ist dein PyPI-API-Token.\033[0m\n'
