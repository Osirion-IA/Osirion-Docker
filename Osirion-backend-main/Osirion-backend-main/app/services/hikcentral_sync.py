# app/services/hikcentral_sync.py
"""
Synchronisation du CATALOGUE HikCentral → base Osirion.

- Areas HikCentral → CameraGroup (mapping par hik_region_code).
- Caméras HikCentral → Camera (mapping par hik_index_code), rattachées à leur
  groupe via regionIndexCode, `hik_status` mis à jour.

IMPORTANT : les caméras sont importées NON traitées (is_active=False) — elles
forment un catalogue. Une caméra ne devient « traitée » (ingérée + IA) que
lorsqu'on la CONFIGURE (1re zone/ligne). La synchro ne touche JAMAIS les caméras
RTSP saisies manuellement (source_type="rtsp") ni les groupes manuels.
"""
import logging
import threading

from sqlmodel import Session, select

from app.models.cameras import Camera
from app.models.camera_groups import CameraGroup
from app.services import hikcentral_connector as hik

logger = logging.getLogger(__name__)

# Sérialise les synchros (manuelle via /sync + périodique du scheduler) : deux
# upserts concurrents sur le même catalogue pourraient dupliquer des lignes.
_sync_lock = threading.Lock()


def _ensure_group(session: Session, region_code: str, region_name) -> CameraGroup:
    """Récupère (ou crée) le CameraGroup correspondant à une Area HikCentral.
    Match par hik_region_code ; sinon adopte un groupe de même nom sans area ;
    sinon crée. Nom unique → suffixe le code en cas de collision."""
    g = session.exec(select(CameraGroup).where(CameraGroup.hik_region_code == region_code)).first()
    if g:
        return g
    name = (region_name or f"Zone {region_code}")[:100]
    by_name = session.exec(select(CameraGroup).where(CameraGroup.name == name)).first()
    if by_name and by_name.hik_region_code is None:
        by_name.hik_region_code = region_code  # adopte un groupe manuel homonyme
        session.add(by_name)
        return by_name
    if by_name:
        name = f"{name} [{region_code}]"[:100]
    g = CameraGroup(name=name, hik_region_code=region_code, description="Importé de HikCentral")
    session.add(g)
    session.flush()
    return g


def sync_catalog(session: Session) -> dict:
    """Synchronise groupes + caméras depuis HikCentral. Retourne des compteurs.
    Sérialisé (verrou global) : un seul catalogue synchronisé à la fois."""
    with _sync_lock:
        return _sync_catalog_locked(session)


def _sync_catalog_locked(session: Session) -> dict:
    regions = hik.get_regions()
    cameras = hik.get_all_cameras()

    group_by_region = {code: _ensure_group(session, code, info.get("name")) for code, info in regions.items()}
    session.flush()

    stats = {"areas": len(regions), "cameras_total": len(cameras), "created": 0, "updated": 0}
    for c in cameras:
        idx = str(c.get("cameraIndexCode"))
        rid = str(c.get("regionIndexCode")) if c.get("regionIndexCode") is not None else None
        name = (c.get("cameraName") or f"Caméra {idx}")[:50]
        status = c.get("status")

        cam = session.exec(select(Camera).where(Camera.hik_index_code == idx)).first()
        if cam is None:
            cam = Camera(cam_name=name, rtsp_url=None, is_active=False,
                         source_type="hikcentral", hik_index_code=idx, hik_status=status)
            session.add(cam)
            session.flush()
            stats["created"] += 1
        else:
            cam.cam_name = name
            cam.hik_status = status
            session.add(cam)
            stats["updated"] += 1

        # Rattache la caméra au groupe de son area (crée le groupe si l'area n'était
        # pas dans la liste). On reconcilie les liens « area HikCentral » et on
        # préserve les groupes manuels (sans hik_region_code).
        if rid is not None:
            target = group_by_region.get(rid) or _ensure_group(session, rid, None)
            group_by_region.setdefault(rid, target)
            if target not in cam.groups:
                cam.groups = [g for g in cam.groups if g.hik_region_code is None] + [target]

    session.commit()
    logger.info(f"[hik] synchro catalogue : {stats}")
    return stats
