#!/usr/bin/env bash
# Ein Befehl, der alles prüft. Läuft in jeder Umgebung, in der Python 3.10+
# und pytest verfügbar sind — unter NixOS am einfachsten in `nix develop`.
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

step "Tests"
python3 -m pytest -q

step "Linter"
if command -v ruff >/dev/null 2>&1; then
    ruff check .
else
    echo "ruff nicht installiert — übersprungen"
fi

step "Mitgelieferte Profile"
for profile in kira focus pad; do
    printf '  %-6s ' "$profile"
    if python3 -m synapsen.cli --profile "$profile" doctor >/dev/null; then
        echo "tragfähig"
    else
        echo "BEANSTANDET"; exit 1
    fi
done

step "Ein Monat, durchgerechnet"
python3 -m synapsen.cli simulate --days 30 --keys cortisol,serotonin,RUHIG

printf '\n\033[1mAlles grün.\033[0m\n'
