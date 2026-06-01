import cv2
import numpy as np

def bytes_to_image(image_bytes):
    """
    Convertit des bytes en image OpenCV (numpy array).

    Args:
        image_bytes (bytes): Contenu du fichier image.
    
    Returns:
        numpy.ndarray: Image OpenCV au format BGR.
    """
# Convertir les bytes en tableau numpy
    nparr = np.frombuffer(image_bytes, np.uint8)

# Décoder l'image
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    return img


