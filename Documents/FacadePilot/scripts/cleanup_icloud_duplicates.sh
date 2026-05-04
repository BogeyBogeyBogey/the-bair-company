#!/usr/bin/env bash
# cleanup_icloud_duplicates.sh
# ─────────────────────────────────────────────────────────────────────
# Verwijdert iCloud Drive sync-conflict bestanden in de FacadePilot-map.
#
# iCloud maakt regelmatig "* 2.html", "* 3.txt" varianten bij sync-conflicten.
# Die zijn meestal niet wat je wil houden en kunnen subtiele bugs geven
# (PoolPilot had ooit "PadelPilot" in een PoolPilot-flyer omdat de " 2.html"
# versie inhoudelijk afweek).
#
# Default = DRY RUN (toont alleen wat verwijderd zou worden).
# Voer met --apply uit om echt te verwijderen.
#
# Veiligheid:
#   - Slaat _archive*/ over (oude versies blijven behouden)
#   - Slaat .git/, node_modules/, __pycache__/ over
#   - Toont eerst de lijst, vraagt bevestiging bij --apply
#
# Gebruik:
#   bash scripts/cleanup_icloud_duplicates.sh           # dry run
#   bash scripts/cleanup_icloud_duplicates.sh --apply   # echt verwijderen

set -euo pipefail

cd "$(dirname "$0")/.."
APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

# Patronen: " N.ext" voor N=2..9 voor de meeste relevante extensies
PATTERNS=(
  "* 2.txt" "* 3.txt" "* 4.txt"
  "* 2.md"  "* 3.md"
  "* 2.py"  "* 3.py"
  "* 2.html" "* 3.html"
  "* 2.json" "* 3.json"
  "* 2.csv"  "* 3.csv"
  "* 2.jpg"  "* 3.jpg"
  "* 2.png"  "* 3.png"
  "* 2.pdf"  "* 3.pdf"
  "* 2.eml"  "* 3.eml"
)

EXCLUDES=(
  "-not" "-path" "./_archive*/*"
  "-not" "-path" "./.git/*"
  "-not" "-path" "./node_modules/*"
  "-not" "-path" "./__pycache__/*"
  "-not" "-path" "*/__pycache__/*"
)

# Bouw find-expressie: -name "* 2.txt" -o -name "* 3.txt" -o ...
FIND_EXPR=()
first=1
for pat in "${PATTERNS[@]}"; do
  if [[ $first -eq 1 ]]; then
    FIND_EXPR+=("-name" "$pat")
    first=0
  else
    FIND_EXPR+=("-o" "-name" "$pat")
  fi
done

# Wrap in \( ... \)
FILES=$(find . -type f \( "${FIND_EXPR[@]}" \) "${EXCLUDES[@]}" 2>/dev/null || true)

if [[ -z "$FILES" ]]; then
  echo "✅ Geen iCloud-duplicaten gevonden."
  exit 0
fi

COUNT=$(echo "$FILES" | wc -l | tr -d ' ')
echo "Gevonden: $COUNT bestand(en) met sync-conflict suffix"
echo "─────────────────────────────────────────────────"
echo "$FILES" | sed 's|^|  |'
echo "─────────────────────────────────────────────────"

if [[ $APPLY -eq 0 ]]; then
  echo
  echo "ℹ️  Dit is een DRY RUN — niets verwijderd."
  echo "   Voer opnieuw uit met --apply om echt te verwijderen."
  exit 0
fi

echo
read -rp "⚠️  Verwijder bovenstaande bestanden? typ 'JA' om te bevestigen: " confirm
if [[ "$confirm" != "JA" ]]; then
  echo "Geannuleerd."
  exit 0
fi

# Verwijder een voor een (veiliger dan find -delete bij rare paden)
echo "$FILES" | while IFS= read -r f; do
  if [[ -f "$f" ]]; then
    rm -- "$f" && echo "  rm $f"
  fi
done
echo "✅ $COUNT bestand(en) verwijderd."
