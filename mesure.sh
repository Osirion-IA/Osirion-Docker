#!/usr/bin/env bash
# =============================================================================
# mesure.sh — pilotage de la campagne de MESURE (chapitre 4) en LOCAL, hors-ligne
# =============================================================================
# Tout passe par l'API du Core sur localhost (aucune connexion internet requise).
# Le Core journalise dans ./measurements/metrics.jsonl (bind mount).
#
# Usage :
#   ./mesure.sh status                      # état courant (scénario, vérité terrain)
#   ./mesure.sh mark "4 cameras"            # borne de scénario (libellé libre)
#   ./mesure.sh expect 6 Alice              # devant la caméra 6 : Alice (vérité terrain)
#   ./mesure.sh expect 6 Inconnu            # imposteur (non enrôlé) devant la caméra 6
#   ./mesure.sh unexpect 6                   # efface la vérité terrain de la caméra 6
#   ./mesure.sh plate BB4060                 # plaque attendue (vérité terrain)
#   ./mesure.sh unplate                      # efface la plaque attendue
#   ./mesure.sh tail                         # suit le journal en direct
#   ./mesure.sh count                        # nb de lignes par type d'événement
#
# Variable d'env : CORE_URL (défaut http://localhost:5000)
# =============================================================================
set -euo pipefail

CORE_URL="${CORE_URL:-http://localhost:5000}"
FILE="${MEASURE_FILE_HOST:-measurements/metrics.jsonl}"

_post() { curl -fsS -X POST "$CORE_URL$1" -H 'Content-Type: application/json' -d "$2"; echo; }
_get()  { curl -fsS "$CORE_URL$1"; echo; }

cmd="${1:-help}"
case "$cmd" in
  status)   _get  "/api/measure/status" ;;
  mark)     _post "/api/measure/mark"   "{\"label\": \"${2:-}\"}" ;;
  expect)   _post "/api/measure/expect" "{\"camera_id\": ${2:?camera_id requis}, \"person\": \"${3:?personne requise}\"}" ;;
  unexpect) _post "/api/measure/expect" "{\"camera_id\": ${2:?camera_id requis}, \"person\": \"\"}" ;;
  plate)    _post "/api/measure/plate"  "{\"plate\": \"${2:?plaque requise}\"}" ;;
  unplate)  _post "/api/measure/plate"  "{\"plate\": \"\"}" ;;
  tail)     tail -f "$FILE" ;;
  count)
    if [ -f "$FILE" ]; then
      grep -oE '"event": *"[^"]+"' "$FILE" | sort | uniq -c | sort -rn
    else
      echo "Fichier $FILE introuvable (le Core a-t-il démarré avec MEASURE_ENABLED=true ?)"
    fi ;;
  help|*)
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
