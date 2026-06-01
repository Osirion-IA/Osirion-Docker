import cv2
from ultralytics import YOLO
from insightface.app import FaceAnalysis
import numpy as np
import threading
import queue
from typing import Optional, List, Tuple

# ----------------------
# Initialisation des modèles
# ----------------------
model = YOLO("yolov11n-face.pt")  # YOLO léger pour CPU


# INITIALISATION OPTIMISÉE POUR CPU (à faire UNE SEULE FOIS au démarrage)
app = FaceAnalysis(
    name='buffalo_l',                    # meilleur modèle généraliste
    providers=['CPUExecutionProvider'],  # force CPU
    allowed_modules=['detection', 'recognition']  # charge uniquement ce qu'il faut
)

# Aligné sur (640,640) — même résolution que face_detection.py et embeddings_service.py.
# Une résolution différente produit des embeddings incompatibles avec la base d'enrollment
# (cosine_sim réduit de 0.05–0.15), ce qui dégrade la reconnaissance.
# Si la latence CPU est un problème, préférer face_detection.py avec GPU.
app.prepare(ctx_id=-1, det_size=(640, 640))

# ----------------------
# Fonction : Détection de visages avec YOLO
# ----------------------
# def detect_faces(frame, confidence_threshold=0.7):
#     detected = model(frame)[0]
#     faces = []

#     for box in detected.boxes:
#         x1, y1, x2, y2 = box.xyxy[0].int().tolist()
#         conf = float(box.conf[0])

#         if conf >= confidence_threshold:
#             face = frame[y1:y2, x1:x2]
#             faces.append((face, conf))
#             cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)

#     return frame, faces

# ----------------------
# Fonction : Générer embeddings InsightFace
# ----------------------
# def generate_face_embeddings(face):
#     rgb_face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
#     rgb_face = rgb_face.astype("float32") / 255.0

#     face_data = app.get(rgb_face)
#     if len(face_data) > 0:
#         return face_data[0].embedding

#     return None



def detect_faces(frame: np.ndarray, confidence_threshold: float = 0.7):
    """
    Détecte les visages sans modifier le frame original.
    Retourne :
        - frame_annotated : copie du frame avec rectangles + score
        - faces : liste de [ (x, y, w, h), confidence, face_crop ]
    """
    if frame is None or frame.size == 0:
        return frame, []

    frame_annotated = frame.copy()
    faces = []
    h, w = frame.shape[:2]

    # Inference YOLO (verbose=False = gain de performance)
    results = model(frame, verbose=False)[0]

    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < confidence_threshold:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

        # Petit padding pour un crop plus naturel (évite les visages trop serrés)
        pad = 20
        x1_p = max(0, x1 - pad)
        y1_p = max(0, y1 - pad)
        x2_p = min(w, x2 + pad)
        y2_p = min(h, y2 + pad)

        face_crop = frame[y1_p:y2_p, x1_p:x2_p]

        # On garde les coordonnées originales (sans padding) pour l'affichage
        faces.append(((x1, y1, x2 - x1, y2 - y1), conf, face_crop))

        # Dessin uniquement sur la copie
        cv2.rectangle(frame_annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame_annotated, f"{conf:.2f}", (x1, max(10, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return frame_annotated, faces

def generate_face_embeddings(face_crop: np.ndarray) -> Optional[np.ndarray]:
    """
    Entrée : un crop de visage en BGR (uint8, comme sorti de cv2.imread)
    Sortie : embedding 512D sous forme de np.ndarray, ou None si échec
    """
    if face_crop is None or face_crop.size == 0:
        return None

    # Pas de / 255, pas de float32 forcé → buffalo_l gère très bien le uint8 nativement
    # Donc on ne touche presque à rien → c'est plus rapide sur CPU
    try:
        faces = app.get(face_crop)
    except Exception as e:
        print(f"Erreur insightface : {e}")
        return None

    if not faces:
        return None

    # On prend le visage avec le meilleur score de détection
    best_face = max(faces, key=lambda x: x.det_score)
    
    # Normalisation L2 défensive — cohérent avec face_detection.py et embeddings_service.py
    # Garantit norme=1.0 pour IndexFlatIP même si InsightFace produit une légère déviation
    raw_emb = best_face.embedding.astype(np.float32)
    norm = np.linalg.norm(raw_emb)
    return raw_emb / norm if norm > 0 else raw_emb


# ----------------------
# Système de file d'attente pour inférences thread-safe
# ----------------------
class InferenceQueue:
    """
    Gère les inférences des modèles dans un thread dédié pour éviter les race conditions.
    Toutes les requêtes d'inférence passent par une queue et sont traitées séquentiellement.
    """
    def __init__(self):
        self.request_queue = queue.Queue(maxsize=50)
        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._inference_worker, daemon=True)
        self.worker_thread.start()
        print("[INFO] Thread d'inférence démarré")

    def _inference_worker(self):
        """Thread worker qui traite les requêtes d'inférence séquentiellement"""
        while not self.stop_event.is_set():
            try:
                request = self.request_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            request_type = request["type"]
            result_event = request["result_event"]
            result_container = request["result_container"]

            try:
                if request_type == "detect_faces":
                    frame = request["frame"]
                    confidence_threshold = request["confidence_threshold"]
                    result = detect_faces(frame, confidence_threshold)
                    result_container["result"] = result
                    
                elif request_type == "generate_embeddings":
                    face_crop = request["face_crop"]
                    result = generate_face_embeddings(face_crop)
                    result_container["result"] = result

            except Exception as e:
                print(f"[ERREUR] Inférence échouée : {e}")
                result_container["result"] = None
            
            finally:
                result_event.set()

    def detect_faces_async(self, frame: np.ndarray, confidence_threshold: float = 0.7, timeout: float = 5.0):
        """
        Demande une détection de visages de manière thread-safe.
        Bloque jusqu'à ce que le résultat soit prêt.
        """
        result_event = threading.Event()
        result_container = {}
        
        request = {
            "type": "detect_faces",
            "frame": frame,
            "confidence_threshold": confidence_threshold,
            "result_event": result_event,
            "result_container": result_container
        }
        
        try:
            self.request_queue.put(request, timeout=1.0)
        except queue.Full:
            print("[WARN] Queue d'inférence pleine, frame ignorée")
            return frame, []
        
        if result_event.wait(timeout=timeout):
            return result_container.get("result", (frame, []))
        else:
            print("[WARN] Timeout d'inférence détection")
            return frame, []

    def generate_embeddings_async(self, face_crop: np.ndarray, timeout: float = 5.0) -> Optional[np.ndarray]:
        """
        Demande la génération d'embeddings de manière thread-safe.
        Bloque jusqu'à ce que le résultat soit prêt.
        """
        result_event = threading.Event()
        result_container = {}
        
        request = {
            "type": "generate_embeddings",
            "face_crop": face_crop,
            "result_event": result_event,
            "result_container": result_container
        }
        
        try:
            self.request_queue.put(request, timeout=1.0)
        except queue.Full:
            print("[WARN] Queue d'inférence pleine, embedding ignoré")
            return None
        
        if result_event.wait(timeout=timeout):
            return result_container.get("result", None)
        else:
            print("[WARN] Timeout d'inférence embedding")
            return None

    def stop(self):
        """Arrête proprement le thread d'inférence"""
        self.stop_event.set()
        self.worker_thread.join(timeout=2.0)
        print("[INFO] Thread d'inférence arrêté")


# Instance globale du système d'inférence
inference_queue = InferenceQueue()
