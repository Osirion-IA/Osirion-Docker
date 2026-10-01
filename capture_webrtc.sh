#!/usr/bin/env bash
# =============================================================================
# Capture des logs WebRTC MediaMTX pour diagnostiquer le « Signal perdu » sur un
# poste distant, SANS internet (le serveur est sur le réseau des caméras).
#
# Principe : on vide le log, tu reproduis le problème sur le poste distant, puis
# on fige la capture. Le fichier logs-mediamtx/mediamtx.log est lisible plus tard
# (une fois de retour sur internet) par Claude.
#
# Usage :  ./capture_webrtc.sh
# =============================================================================
set -e
cd "$(dirname "$0")"

LOG=logs-mediamtx/mediamtx.log
SERVER_IP="192.168.1.148"   # IP du serveur sur le réseau caméras (à adapter si besoin)

if [ ! -f "$LOG" ]; then
  echo "ERREUR : $LOG introuvable. MediaMTX tourne-t-il ? (docker ps)"
  exit 1
fi

echo "=========================================================="
echo " CAPTURE WEBRTC — diagnostic « Signal perdu » à distance"
echo "=========================================================="
echo
echo "1) On vide le log pour repartir propre..."
: > "$LOG"
echo "   OK."
echo
echo "2) MAINTENANT, sur le POSTE DISTANT (pas le serveur) :"
echo "   - ouvre http://$SERVER_IP:3000  puis  admin/live"
echo "   - RECHARGE de force la page :  Ctrl+Shift+R"
echo "   - clique sur UNE seule caméra (note bien son NUMÉRO)"
echo "   - laisse tourner ~30 s (ça va afficher « Signal perdu » et réessayer)"
echo
echo "   BONUS très utile (poste distant) : F12 -> onglet Console + onglet"
echo "   Network (filtre 'whep'), fais une capture d'écran des erreurs rouges."
echo
read -r -p "3) Appuie sur [Entrée] ICI une fois les ~30 s écoulées... " _
echo
LINES=$(wc -l < "$LOG")
echo "   Capture figée : $LINES lignes dans $LOG"
echo
echo "4) De retour sur internet, dis à Claude :"
echo "   « la caméra testée était le n°X » — il lira $LOG."
echo "=========================================================="
