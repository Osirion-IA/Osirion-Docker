# core/trackers/__init__.py
"""Sous-package des trackers multi-objets d'Osirion (implémentations autonomes).

Les pipelines importent directement le module concret, p. ex. :
    from core.trackers.oc_sort import OCSortTrackerAdapter

Aucun import paresseux ici afin de ne pas forcer le chargement de filterpy quand
on n'utilise pas OC-SORT.
"""
