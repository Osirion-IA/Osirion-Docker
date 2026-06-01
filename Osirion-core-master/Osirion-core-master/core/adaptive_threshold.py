# core/adaptive_threshold.py
"""
Seuil de reconnaissance faciale adaptatif par caméra.

Principe : les scores ArcFace forment deux populations —
  · visages connus    → scores élevés (~0.50–0.80)
  · visages inconnus  → scores faibles (~0.15–0.45)

La méthode d'Otsu trouve automatiquement la vallée entre ces deux groupes
et y place le seuil. Le lissage exponentiel évite les sauts brusques.
"""
import threading
import numpy as np
from collections import deque
from utils.logger import get_logger

logger = get_logger(__name__)


class AdaptiveThreshold:
    """
    Seuil adaptatif par caméra.

    Paramètres
    ----------
    initial   : seuil de démarrage avant que assez de données soient collectées
    floor     : seuil minimum absolu (sécurité anti-faux-positifs)
    ceiling   : seuil maximum absolu
    window    : taille de la fenêtre glissante de scores observés
    min_samples : nombre de scores minimum avant d'activer l'adaptation
    recalc_every: recalculer toutes les N nouvelles observations
    smoothing : coefficient EWM — 1.0 = pas de lissage, 0.0 = mémoire nulle
    """

    def __init__(
        self,
        initial: float = 0.45,   # recalibré : cosine ArcFace — ancienne valeur 0.30 était hors range
        floor: float = 0.35,     # recalibré : ancienne valeur 0.18 sous le minimum cosine possible
        ceiling: float = 0.80,   # recalibré : ancienne valeur 0.72 légèrement sous le max live
        window: int = 300,
        min_samples: int = 30,
        recalc_every: int = 15,
        smoothing: float = 0.80,
    ):
        self._value = initial
        self.floor = floor
        self.ceiling = ceiling
        self.min_samples = min_samples
        self.recalc_every = recalc_every
        self.smoothing = smoothing
        self._window: deque[float] = deque(maxlen=window)
        self._pending = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @property
    def value(self) -> float:
        return self._value

    def observe(self, score: float) -> None:
        """Enregistre un score retourné par l'API et recalcule si nécessaire."""
        with self._lock:
            self._window.append(float(score))
            self._pending += 1
            if (self._pending >= self.recalc_every
                    and len(self._window) >= self.min_samples):
                self._pending = 0
                self._update()

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _update(self) -> None:
        scores = np.array(self._window, dtype=np.float32)

        # Log de la distribution pour diagnostiquer la bimodalité (matches vs non-matches)
        # Avec IndexFlatIP + cosine : on attend μ_matches ≈ 0.62, μ_non_matches ≈ 0.18
        # Si μ global > 0.50, tous les scores sont des matches → seuil trop bas, augmenter
        # Si σ < 0.05, distribution unimodale → pas assez de diversité dans la base
        pct_above_floor = float((scores > self.floor).mean() * 100)
        logger.info(
            f"[AdaptiveThreshold] distribution : n={len(scores)}, "
            f"μ={scores.mean():.3f}, σ={scores.std():.3f}, "
            f"min={scores.min():.3f}, max={scores.max():.3f}, "
            f"p25={np.percentile(scores, 25):.3f}, p75={np.percentile(scores, 75):.3f}, "
            f">{self.floor:.2f}: {pct_above_floor:.0f}%"
        )

        candidate = _otsu_threshold(scores)
        if candidate is None:
            logger.debug(
                f"[AdaptiveThreshold] Otsu skipped — distribution trop étroite (σ={scores.std():.3f} < 0.02). "
                "Seuil maintenu. Cause probable : embeddings homogènes ou base trop petite."
            )
            return

        old = self._value
        smoothed = self.smoothing * old + (1.0 - self.smoothing) * candidate
        new = float(np.clip(smoothed, self.floor, self.ceiling))

        if abs(new - old) >= 0.005:
            self._value = new
            logger.info(
                f"[AdaptiveThreshold] seuil ajusté : {old:.4f} → {new:.4f} "
                f"(Otsu={candidate:.4f}, n={len(self._window)}, "
                f"μ={scores.mean():.3f}, σ={scores.std():.3f})"
            )


# ------------------------------------------------------------------
# Otsu 1D — séparation bimodale optimale
# ------------------------------------------------------------------

def _otsu_threshold(scores: np.ndarray, bins: int = 50) -> float | None:
    """
    Trouve le seuil qui maximise la variance inter-classes (méthode d'Otsu).
    Retourne None si la distribution est trop étroite pour être bimodale.
    """
    if scores.std() < 0.02:
        return None

    hist, edges = np.histogram(scores, bins=bins, range=(0.0, 1.0))
    centers = (edges[:-1] + edges[1:]) / 2.0
    total = hist.sum()
    if total == 0:
        return None

    cum_n = np.cumsum(hist).astype(np.float64)
    cum_w = np.cumsum(hist * centers)

    best_t = None
    best_var = 0.0

    for i in range(1, bins):
        n0 = cum_n[i - 1]
        n1 = total - n0
        if n0 < 2 or n1 < 2:
            continue
        mu0 = cum_w[i - 1] / n0
        mu1 = (cum_w[-1] - cum_w[i - 1]) / n1
        var = (n0 / total) * (n1 / total) * (mu0 - mu1) ** 2
        if var > best_var:
            best_var = var
            best_t = float(centers[i])

    return best_t
