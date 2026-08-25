#!/usr/bin/env bash
# Ersetzt die Platzhalter für das GitHub-Konto und legt das Repo an.
#
#   ./prepare-release.sh dein-github-name
#
# Danach fehlt nur noch:
#   git remote add origin git@github.com:<name>/synapsen.git
#   git push -u origin main
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
    echo "Aufruf: $0 <github-benutzername> [repo-name]" >&2
    exit 2
fi

USER_NAME="$1"
REPO="${2:-synapsen}"

for file in pyproject.toml flake.nix README.md; do
    [ -f "$file" ] || continue
    sed -i.bak "s|github.com/USER/synapsen|github.com/${USER_NAME}/${REPO}|g" "$file"
    sed -i.bak "s|github:USER/synapsen|github:${USER_NAME}/${REPO}|g" "$file"
    rm -f "$file.bak"
done

echo "Platzhalter ersetzt: USER -> ${USER_NAME}, Repo -> ${REPO}"
grep -rn "USER/" pyproject.toml flake.nix README.md 2>/dev/null && {
    echo "Es sind noch Platzhalter übrig — bitte prüfen." >&2
    exit 1
}

echo
echo "Jetzt noch:"
echo "  git remote add origin git@github.com:${USER_NAME}/${REPO}.git"
echo "  git push -u origin main"
