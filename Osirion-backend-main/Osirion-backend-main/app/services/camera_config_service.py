# app/services/camera_config_service.py
"""
Calcul de la configuration EFFECTIVE des modules d'une caméra.

Règle métier (VMS) : un module (facial ou LPR) est effectivement actif pour une
caméra si, ET SEULEMENT SI, son drapeau LOCAL est vrai ET TOUS les groupes
auxquels la caméra appartient ont ce module activé. Une caméra sans groupe
retombe donc sur ses seuls drapeaux locaux (all([]) == True).

Ce module est la source de vérité partagée par les endpoints REST (ce que le
Core lit pour activer/désactiver le pipeline à chaud).
"""
from typing import List, Tuple

# Identifiants de module exposés dans `active_modules` (contrat frontend/Core).
MODULE_FACIAL = "facial"
MODULE_LPR = "lpr"


def effective_modules(camera) -> Tuple[bool, bool]:
    """Retourne (facial_effectif, lpr_effectif) pour une caméra ORM.

    `camera.groups` doit être chargé (lazy en contexte de session, ou eager via
    selectinload pour éviter le N+1 sur les listes).
    """
    groups = camera.groups or []
    facial = bool(camera.is_facial_active) and all(g.is_facial_active for g in groups)
    lpr = bool(camera.is_lpr_active) and all(g.is_lpr_active for g in groups)
    return facial, lpr


def active_module_names(facial: bool, lpr: bool) -> List[str]:
    """Traduit les booléens effectifs en liste plate de noms de modules."""
    modules: List[str] = []
    if facial:
        modules.append(MODULE_FACIAL)
    if lpr:
        modules.append(MODULE_LPR)
    return modules
