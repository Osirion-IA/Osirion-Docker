#!/usr/bin/env bash
# =============================================================================
# Osirion — Lancement propre, étape par étape (build complet + démarrage ordonné)
# =============================================================================
# Usage :
#   ./launch.sh           → build complet + démarrage + vérifications
#   ./launch.sh --no-build → démarre sans reconstruire (images déjà à jour)
#   ./launch.sh --build-only → construit les images puis s'arrête
#
# Le script s'arrête à la première erreur (set -e) et explique chaque étape.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

# ── Couleurs ─────────────────────────────────────────────────────────────────
BOLD=$'\e[1m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; CYAN=$'\e[36m'; DIM=$'\e[2m'; RESET=$'\e[0m'
step(){ echo; echo "${BOLD}${CYAN}━━━ $* ━━━${RESET}"; }
ok(){   echo "${GREEN}✔${RESET} $*"; }
warn(){ echo "${YELLOW}⚠${RESET} $*"; }
err(){  echo "${RED}✗${RESET} $*" >&2; }

# ── Détection de la commande compose ─────────────────────────────────────────
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  err "docker compose introuvable. Installe Docker Compose v2."; exit 1
fi

DO_BUILD=1; BUILD_ONLY=0
for a in "$@"; do
  case "$a" in
    --no-build) DO_BUILD=0 ;;
    --build-only) BUILD_ONLY=1 ;;
    *) warn "argument inconnu ignoré : $a" ;;
  esac
done

# ── Attente de l'état "healthy" d'un conteneur ───────────────────────────────
wait_healthy(){
  local name="$1" timeout="${2:-300}" waited=0 status
  printf "   Attente santé de %-18s " "$name"
  while true; do
    status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || echo "absent")
    case "$status" in
      healthy|running) echo "${GREEN}[$status]${RESET}"; return 0 ;;
      exited|dead) echo "${RED}[$status]${RESET}"; docker logs --tail 40 "$name" || true; return 1 ;;
    esac
    if [ "$waited" -ge "$timeout" ]; then
      echo "${RED}[timeout après ${timeout}s — $status]${RESET}"
      docker logs --tail 40 "$name" || true; return 1
    fi
    sleep 3; waited=$((waited+3)); printf "."
  done
}

# =============================================================================
step "ÉTAPE 0 — Vérifications préalables"
# =============================================================================
docker info >/dev/null 2>&1 || { err "Le démon Docker ne répond pas. Démarre Docker."; exit 1; }
ok "Docker opérationnel ($(docker --version | awk '{print $3}' | tr -d ,))"
ok "Compose : $DC"

[ -f .env ] || { err ".env absent. Copie .env.example en .env puis remplis-le."; exit 1; }
ok ".env présent"

# Variables critiques
for v in POSTGRES_PASSWORD SECRET_KEY FERNET_KEY AUTH_EMAIL AUTH_PASSWORD; do
  if ! grep -qE "^${v}=.+" .env; then err "Variable manquante dans .env : ${v}"; exit 1; fi
done
ok "Variables .env essentielles présentes"

MODEL="Osirion-core-master/Osirion-core-master/license_plate_detector.pt"
if [ -f "$MODEL" ]; then ok "Modèle plaque présent ($(du -h "$MODEL" | cut -f1))"
else warn "Modèle plaque absent ($MODEL) — le LPR se désactivera proprement (le facial marche)."; fi

if grep -qE "^ENABLE_PLATE_RECOGNITION=true" .env; then ok "LPR activé (ENABLE_PLATE_RECOGNITION=true)"
else warn "LPR désactivé par défaut — activable via le toggle frontend."; fi

# GPU / nvidia-container-toolkit
if nvidia-smi >/dev/null 2>&1; then
  ok "GPU NVIDIA : $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  if docker info 2>/dev/null | grep -qi 'Runtimes:.*nvidia' || [ -f /etc/docker/daemon.json ] && grep -qi nvidia /etc/docker/daemon.json 2>/dev/null; then
    ok "Runtime NVIDIA configuré pour Docker"
  else
    warn "nvidia-container-toolkit peut-être non configuré pour Docker."
    warn "Si le service 'core'/'backend' refuse de démarrer (erreur GPU) :"
    warn "  sudo apt install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
  fi
else
  warn "Pas de GPU détecté — les services exigent un GPU (deploy.resources). Le démarrage échouera sans GPU/toolkit."
fi

# =============================================================================
if [ "$DO_BUILD" -eq 1 ]; then
  step "ÉTAPE 1 — Construction des images (long au 1er build : torch + ML, plusieurs Go)"
  echo "${DIM}   Cela télécharge torch CUDA, onnxruntime-gpu, ultralytics, easyocr, etc.${RESET}"
  echo "${DIM}   Les poids InsightFace (~183 Mo) et EasyOCR (~100 Mo) sont préchargés dans l'image.${RESET}"
  $DC build
  ok "Images construites"
  [ "$BUILD_ONLY" -eq 1 ] && { ok "Build terminé (--build-only)."; exit 0; }
else
  warn "ÉTAPE 1 ignorée (--no-build)"
fi

# =============================================================================
step "ÉTAPE 2 — Base de données PostgreSQL (pgvector)"
$DC up -d db
wait_healthy osirion-db 90
ok "Base de données prête"

# =============================================================================
step "ÉTAPE 3 — Backend FastAPI (migrations Alembic + admin par défaut)"
echo "${DIM}   L'entrypoint attend la DB, applique 'alembic upgrade head' (crée la table vehicle"
echo "   + colonnes plaque sur event), crée l'admin, puis lance uvicorn.${RESET}"
$DC up -d backend
# start_period backend = 300s (chargement InsightFace + FAISS) → on patiente large
wait_healthy osirion-backend 420
ok "Backend prêt (migrations appliquées)"

# =============================================================================
step "ÉTAPE 4 — Core (surveillance + LPR) et Frontend"
$DC up -d core frontend
wait_healthy osirion-core 180
wait_healthy osirion-frontend 120
ok "Core et Frontend prêts"

# =============================================================================
step "ÉTAPE 5 — Vérifications"
echo "• Santé backend :"
curl -sf http://localhost:8000/health && echo || warn "backend /health KO"
echo "• État LPR du Core :"
curl -sf http://localhost:5000/api/lpr/status && echo || warn "core /api/lpr/status KO"
echo "• Recherche des lignes LPR dans les logs du core :"
$DC logs core 2>/dev/null | grep -iE "LPR|EasyOCR|plaque" | tail -5 || true

echo
echo "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
ok "Osirion est lancé."
echo "   Frontend  : ${BOLD}http://localhost:3000${RESET}"
echo "   Backend   : ${BOLD}http://localhost:8000/docs${RESET}  (Swagger, section 🚗 License Plates)"
echo "   Core API  : ${BOLD}http://localhost:5000/api/cameras${RESET}"
echo
echo "   Connexion admin (depuis .env) :"
echo "     email    : $(grep -E '^AUTH_EMAIL=' .env | cut -d= -f2)"
echo "     password : $(grep -E '^AUTH_PASSWORD=' .env | cut -d= -f2)"
echo
echo "   Suivre les logs : ${DIM}$DC logs -f core${RESET}"
echo "   Arrêter         : ${DIM}$DC down${RESET}   (ajouter -v pour effacer la BDD)"
echo "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
