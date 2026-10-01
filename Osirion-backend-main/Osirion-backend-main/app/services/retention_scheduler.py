# app/services/retention_scheduler.py
"""
Rétention PÉRIODIQUE des événements et de leurs captures (thread de fond).

Pourquoi. La campagne d'observation d'août 2026 a produit ~800 Mo de captures par
jour pour 9 postes surveillés. Sans politique de rotation, la partition (14 Go
libres, déjà occupée à 88 %) saturait sous une vingtaine de jours — l'exploitation
s'arrête alors d'elle-même, sans avertissement. La purge existait déjà mais était
MANUELLE (POST /maintenance/purge-events) : personne ne la déclenchait.

Ce thread rejoue la même logique automatiquement, toutes les
RETENTION_CHECK_HOURS, pour tout ce qui dépasse RETENTION_DAYS.
RETENTION_DAYS = 0 → désactivé (retour au fonctionnement manuel seul).

Best-effort : toute erreur est logguée sans jamais tuer le thread.

⚠️ Destructif par construction. Le défaut de RETENTION_DAYS est volontairement
généreux : mieux vaut un disque qui se remplit lentement qu'une purge trop
agressive qui détruit des preuves d'alerte encore utiles.
"""
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app.config import settings
from app.database import engine
from app.models.events import Event
from app.models.alerts import Alert

logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_thread: threading.Thread | None = None

# Répertoire des captures — sert au relevé d'espace libre.
SNAPSHOT_DIR = Path("snapshots")


def is_running() -> bool:
    """Le thread de rétention est-il actif ?"""
    return _thread is not None and _thread.is_alive()


def disk_usage() -> dict:
    """Espace de la partition qui porte les captures.

    Publié par /maintenance/disk et relevé à chaque cycle de rétention : la
    campagne 1 s'est déroulée sans aucune visibilité sur ce point, et c'est
    précisément ce qui rendait la saturation imprévisible.
    """
    cible = SNAPSHOT_DIR if SNAPSHOT_DIR.exists() else Path(".")
    total, used, free = shutil.disk_usage(cible)
    go = lambda n: round(n / 1024 ** 3, 2)  # noqa: E731
    return {
        "path": str(cible),
        "total_gb": go(total),
        "used_gb": go(used),
        "free_gb": go(free),
        "used_percent": round(100 * used / total, 1) if total else 0.0,
    }


def purge_older_than(session: Session, days: int) -> dict:
    """Supprime les événements antérieurs à `days` jours ET leurs captures.

    Même logique que l'endpoint manuel `POST /maintenance/purge-events`, extraite
    ici pour être partagée entre l'appel manuel et ce thread — une seule
    implémentation de la suppression, donc un seul comportement à vérifier.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    vieux = session.exec(select(Event).where(Event.timestamp < cutoff)).all()

    # Une alerte est une preuve métier indépendante : son FK passe à NULL lorsque
    # l'événement disparaît, mais son snapshot_url reste affiché dans le centre
    # d'alertes. Ces fichiers doivent donc survivre à la rétention des événements.
    urls = {str(ev.snapshot_url) for ev in vieux if ev.snapshot_url}
    proteges = set()
    if urls:
        proteges.update(session.exec(
            select(Alert.snapshot_url).where(Alert.snapshot_url.in_(urls))
        ).all())
        proteges.update(session.exec(
            select(Event.snapshot_url).where(
                Event.timestamp >= cutoff,
                Event.snapshot_url.in_(urls),
            )
        ).all())

    supprimes = fichiers = 0
    a_supprimer = []
    for ev in vieux:
        if ev.snapshot_url and str(ev.snapshot_url) not in proteges:
            a_supprimer.append(Path(str(ev.snapshot_url).lstrip("/")))
        session.delete(ev)
        supprimes += 1
    # La base est validée AVANT le disque. En cas d'échec SQL, aucune preuve ne
    # disparaît physiquement ; un éventuel fichier orphelin est moins grave qu'une
    # URL en base pointant vers une image supprimée.
    session.commit()
    for p in a_supprimer:
        try:
            if p.exists() and p.is_file():
                p.unlink()
                fichiers += 1
        except Exception:  # noqa: BLE001 — nettoyage best-effort
            logger.warning("[retention] capture non supprimée : %s", p, exc_info=True)
    return {"deleted_events": supprimes, "removed_snapshots": fichiers,
            "protected_snapshots": len(proteges),
            "older_than_days": days}


def _loop(interval_s: int, days: int, seuil_go: float) -> None:
    time.sleep(min(interval_s, 120))  # laisse le backend finir de démarrer
    while True:
        try:
            with Session(engine) as session:
                stats = purge_older_than(session, days)
            espace = disk_usage()
            if stats["deleted_events"]:
                logger.info(
                    "[retention] purge > %d j : %d événements, %d captures — "
                    "libre %.1f Go (%.0f %% occupé)",
                    days, stats["deleted_events"], stats["removed_snapshots"],
                    espace["free_gb"], espace["used_percent"],
                )
            if espace["free_gb"] < seuil_go:
                logger.error(
                    "[retention] ESPACE DISQUE CRITIQUE : %.1f Go libres sur %s "
                    "(seuil %.1f Go). Réduire RETENTION_DAYS ou libérer de la place — "
                    "sans quoi l'enregistrement des preuves s'arrêtera.",
                    espace["free_gb"], espace["path"], seuil_go,
                )
        except Exception:  # noqa: BLE001 — jamais fatal pour le thread
            logger.warning(
                "[retention] cycle en échec (réessai au prochain).", exc_info=True
            )
        time.sleep(interval_s)


def start_retention() -> None:
    """Démarre (une seule fois par processus) le thread de rétention."""
    global _started, _thread
    days = int(getattr(settings, "RETENTION_DAYS", 0) or 0)
    if days <= 0:
        logger.info("[retention] désactivée (RETENTION_DAYS=0) — purge manuelle seulement.")
        return
    heures = float(getattr(settings, "RETENTION_CHECK_HOURS", 24) or 24)
    seuil = float(getattr(settings, "RETENTION_MIN_FREE_GB", 10) or 10)
    with _start_lock:
        if _started:
            return
        _started = True
        _thread = threading.Thread(
            target=_loop, args=(int(heures * 3600), days, seuil),
            daemon=True, name="retention",
        )
        _thread.start()
    logger.info(
        "[retention] active : conservation %d j, contrôle toutes les %.0f h, "
        "alerte sous %.0f Go libres.", days, heures, seuil,
    )
