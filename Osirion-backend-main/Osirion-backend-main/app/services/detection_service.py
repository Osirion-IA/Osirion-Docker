import cv2
import os
import logging
from ultralytics import YOLO

logger = logging.getLogger(__name__)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
model_path = os.path.join(project_root, "yolov11n-face.pt")
model = YOLO(model_path)


def detect_face(image, confidence_threshold: float = 0.7):
    """
    Détecte le visage avec la meilleure confiance dans l'image.
    Retourne le crop BGR ou None si aucun visage ne passe le seuil.
    """
    results = model(image, verbose=False)[0]

    if results.boxes is None or len(results.boxes) == 0:
        return None

    # Sélectionne la box avec le score de confiance le plus élevé
    best_box = max(results.boxes, key=lambda b: float(b.conf[0]))
    conf = float(best_box.conf[0])

    if conf < confidence_threshold:
        return None

    x1, y1, x2, y2 = best_box.xyxy[0].int().tolist()
    return image[y1:y2, x1:x2]
