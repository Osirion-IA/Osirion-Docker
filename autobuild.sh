#!/usr/bin/env bash
# =============================================================================
# autobuild.sh — Build auto-résilient + démarrage, en arrière-plan.
# Relance le build tant qu'il échoue (coupures réseau lentes) ; le cache pip
# BuildKit + --resume-retries font reprendre les téléchargements là où ils en
# étaient. Quand les 3 images sont prêtes, démarre la stack et vérifie le LPR.
# Tout est journalisé dans autobuild.log (avec horodatage).
# =============================================================================
cd "$(dirname "$0")" || exit 1
LOG="autobuild.log"

{
echo
echo "############################################################"
echo "AUTOBUILD démarré : $(date)"
echo "############################################################"

build_one() {
  # $1 = service ; relance jusqu'à succès (ou MAX tentatives)
  local svc="$1" attempt=0 max=80
  while [ "$attempt" -lt "$max" ]; do
    attempt=$((attempt+1))
    # Garde-fou disque : purge le cache de build si < 6 Go libres
    local avail
    avail=$(df --output=avail -BG / 2>/dev/null | tail -1 | tr -dc '0-9')
    echo ">>> [$(date +%H:%M:%S)] build $svc — tentative $attempt/$max (disque libre: ${avail:-?} Go)"
    if [ "${avail:-99}" -lt 6 ]; then
      echo "    Disque faible → docker builder prune -f"
      docker builder prune -f >/dev/null 2>&1
    fi
    if docker compose build "$svc"; then
      echo ">>> [$(date +%H:%M:%S)] $svc OK (tentative $attempt)"
      return 0
    fi
    echo ">>> [$(date +%H:%M:%S)] $svc échec — pause 30s puis reprise (cache conservé)"
    sleep 30
  done
  echo "!!! ABANDON $svc après $max tentatives ($(date))"
  return 1
}

# 1) Build séquentiel (ménage le disque) avec reprise auto
for svc in backend core frontend; do
  if ! build_one "$svc"; then
    echo "!!! AUTOBUILD ÉCHOUÉ sur $svc : $(date)"
    exit 1
  fi
done

echo
echo ">>> [$(date +%H:%M:%S)] Toutes les images sont construites."

# 2) Démarrage de la stack (ordre géré par depends_on/healthchecks)
echo ">>> [$(date +%H:%M:%S)] docker compose up -d"
docker compose up -d
sleep 10
echo
echo ">>> État des conteneurs :"
docker compose ps

# 3) Petite vérification LPR (après un délai pour laisser le core démarrer)
echo ">>> Attente 60s puis vérif LPR..."
sleep 60
echo "--- backend /health ---"; curl -sf http://localhost:8000/health || echo "(pas encore prêt)"
echo; echo "--- core /api/lpr/status ---"; curl -sf http://localhost:5000/api/lpr/status || echo "(pas encore prêt)"
echo
echo "############################################################"
echo "AUTOBUILD TERMINÉ : $(date)"
echo "############################################################"
} >> "$LOG" 2>&1
