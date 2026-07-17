# utils/measurement.py
"""
Dispositif de MESURE pour l'évaluation du mémoire (chapitre 4).

Objectif : produire, en fonctionnement réel et SANS connexion à l'extérieur, un
journal exploitable hors-ligne pour renseigner les tableaux 4.4 (facial) et
4.5 (multi-caméras). Tout est écrit en JSON Lines dans UN fichier
(`MEASURE_FILE`, par défaut /app/measurements/metrics.jsonl) que l'on dépouille
ensuite avec tools/analyze_metrics.py.

Principe : un singleton thread-safe expose
  - emit(event, **payload)         → 1 ligne JSON {ts, event, scenario?, ...}
  - mark(label)                    → borne de scénario (toutes les lignes suivantes
                                     portent ce libellé dans le champ "scenario")
  - set_expected(cam_id, person)   → vérité terrain visage de la caméra

La vérité terrain et les marques se pilotent à chaud via les endpoints
/api/measure/* du Core (cf. core/web_streaming.py) — donc en local, sans internet.

Désactivable via MEASURE_ENABLED=false (emit devient un no-op → zéro surcoût).
"""
import os
import json
import time
import threading
from typing import Optional, Dict, Any

from utils.logger import get_logger

logger = get_logger(__name__)

_TRUE = {"1", "true", "yes", "on"}


class _Measurement:
    def __init__(self) -> None:
        self.enabled = os.getenv("MEASURE_ENABLED", "true").lower() in _TRUE
        self.path = os.getenv("MEASURE_FILE", "/app/measurements/metrics.jsonl")
        self._lock = threading.Lock()
        self._fh = None

        # État de campagne (piloté par les endpoints /api/measure/*).
        self.expected_by_cam: Dict[int, str] = {}   # {cam_id: nom attendu | "Inconnu"}
        self.current_mark: Optional[str] = None       # libellé de scénario courant

        if self.enabled:
            self._open()

    def _open(self) -> None:
        try:
            d = os.path.dirname(self.path)
            if d:
                os.makedirs(d, exist_ok=True)
            # buffering=1 → ligne par ligne : le fichier est exploitable même si le
            # conteneur est arrêté brutalement (pas de perte du buffer).
            self._fh = open(self.path, "a", buffering=1, encoding="utf-8")
            logger.info(f"[MESURE] journal des métriques actif → {self.path}")
            self.emit("session_start", pid=os.getpid())
        except Exception as e:
            logger.error(f"[MESURE] ouverture impossible de {self.path} : {e}")
            self.enabled = False

    # ── Écriture ──────────────────────────────────────────────────────────────
    def emit(self, event: str, **payload: Any) -> None:
        """Écrit une ligne JSON {ts, event, scenario?, **payload}. Best-effort."""
        if not self.enabled or self._fh is None:
            return
        rec: Dict[str, Any] = {"ts": round(time.time(), 3), "event": event}
        if self.current_mark is not None:
            rec["scenario"] = self.current_mark
        rec.update(payload)
        try:
            line = json.dumps(rec, ensure_ascii=False)
        except Exception:
            return
        try:
            with self._lock:
                self._fh.write(line + "\n")
        except Exception:
            pass

    # ── Vérité terrain & scénarios ─────────────────────────────────────────────
    def set_expected(self, camera_id: int, person: Optional[str]) -> None:
        """Définit (ou efface si person vide) l'identité attendue devant la caméra."""
        with self._lock:
            if not person:
                self.expected_by_cam.pop(camera_id, None)
            else:
                self.expected_by_cam[camera_id] = person
        self.emit("groundtruth", kind="face", camera_id=camera_id, expected=person)

    def get_expected(self, camera_id: int) -> Optional[str]:
        return self.expected_by_cam.get(camera_id)

    def mark(self, label: Optional[str]) -> None:
        """Borne de scénario : les événements suivants porteront ce libellé."""
        self.current_mark = label or None
        self.emit("mark", label=label)

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "file": self.path,
            "scenario": self.current_mark,
            "expected_by_cam": dict(self.expected_by_cam),
        }


_INSTANCE: Optional[_Measurement] = None
_INSTANCE_LOCK = threading.Lock()


def get_measurement() -> _Measurement:
    """Accès au singleton de mesure (créé à la première demande)."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = _Measurement()
    return _INSTANCE
