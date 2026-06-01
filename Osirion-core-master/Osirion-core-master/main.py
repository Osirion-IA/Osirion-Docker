
# main.py
import cv2
import threading
import queue
import numpy as np
import time
import math
import sys
import lap  # Requis par ByteTrack
import os
import asyncio
import aiohttp
sys.path.append(os.getcwd())

from face_detection import detect_faces, generate_face_embeddings
from services.embeddings_search_service import search_similar_embeddings, search_embedding_async
from services.event_services import send_event_async
from services.camera_fetching_service import fetch_camera_list
from utils.auth_utils import API_URL


# Ajouter le chemin du dossier YOLOX/yolox pour que Python trouve le module
from ByteTrack.yolox.tracker.byte_tracker import BYTETracker


# ----------------------
# Configuration
# ----------------------
cameras = fetch_camera_list()
print(f"Caméras trouvées au total : {len(cameras)}")

# Filtrer uniquement les caméras actives
active_cameras = [cam for cam in cameras if cam.get("is_active", False)]
if not active_cameras:
    print("Aucune caméra active trouvée !")
    exit(1)

num_cams = len(active_cameras)
active_cam_strs = [f"{cam['cam_name']} (id={cam['id']}, {cam['location']})" for cam in active_cameras]
print(f"Caméras actives : {active_cam_strs}")

FRAME_SIZE = (640, 480)           # Taille de chaque flux individuel
PROCESS_EVERY_N_FRAME = 10         # Traiter 1 frame sur 3 pour gagner en performance

# ----------------------
# Configuration du ByteTrack
# ----------------------
BYTE_TRACK_ARGS = {
    "track_thresh": 0.5,     # Seuil pour créer un nouveau track
    "track_buffer": 30,      # Frames à garder un track perdu (~1s à 30fps)
    "match_thresh": 0.8,     # Seuil pour associer détection → track existant
    "frame_rate": 30         # Approximation du framerate
}

# ----------------------
# Configuration de la reconnaissance faciale
# ----------------------
FACE_DETECTION_CONFIDENCE = 0.7   # Seuil de confiance pour la détection de visages
RECOGNITION_THRESHOLD = 0.70      # Seuil de score pour accepter une reconnaissance
REIDENTIFICATION_INTERVAL = 200   # Frames avant de ré-identifier un track existant
CACHE_TTL_FRAMES = 600            # Durée de vie des tracks en cache (en frames)
FRAME_QUEUE_TIMEOUT = 0.1         # Timeout pour récupérer une frame de la queue (secondes)
RECONNECTION_SLEEP = 0.1          # Délai avant tentative de reconnexion RTSP (secondes)
MAX_RECONNECTION_ATTEMPTS = 5     # Nombre maximum de tentatives de reconnexion avant abandon
RECONNECTION_BASE_DELAY = 1.0     # Délai de base pour le backoff exponentiel (secondes)
MAX_RECONNECTION_DELAY = 30.0     # Délai maximum entre les tentatives de reconnexion (secondes)
FRAME_FAILURE_THRESHOLD = 10      # Nombre d'échecs consécutifs avant de déclencher une reconnexion

# Structures globales
trackers = {}              # {cam_id: BYTETracker}
track_id_to_person = {}    # {cam_id: {track_id: {"name", "score", "last_updated"}}}
current_frame_idx = {}     # {cam_id: int}

frame_queues = {}          # {cam_id: queue.Queue(maxsize=2)}
result_frames = {}         # {cam_id: frame annoté}
result_lock = threading.Lock()
stop_event = threading.Event()


# ----------------------
# Initialisation des structures par caméra
# ----------------------
for cam in active_cameras:
    cam_id = cam["id"]
    frame_queues[cam_id] = queue.Queue(maxsize=2)
    result_frames[cam_id] = None

    trackers[cam_id] = BYTETracker(**BYTE_TRACK_ARGS)
    track_id_to_person[cam_id] = {}
    current_frame_idx[cam_id] = 0


# Mode headless : pas d'affichage graphique


# ----------------------
# Thread 1 : Capture RTSP
# ----------------------
def capture_thread(cam):
    cam_id = cam["id"]
    cam_name = cam["cam_name"]
    rtsp_url = cam["rtsp_url"]
    cam_queue = frame_queues[cam_id]

    cap = None
    reconnection_attempts = 0
    frame_failures = 0

    def connect_camera():
        """Tente de se connecter à la caméra"""
        new_cap = cv2.VideoCapture(rtsp_url)
        new_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if new_cap.isOpened():
            return new_cap
        new_cap.release()
        return None

    # Connexion initiale
    print(f"[INFO] Connexion à la caméra {cam_id} ({cam_name})...")
    cap = connect_camera()
    if not cap:
        print(f"[ERREUR] Caméra {cam_id} ({cam_name}) : impossible d'ouvrir le flux RTSP")
        return

    print(f"[OK] Caméra {cam_id} ({cam_name}) connectée")
    reconnection_attempts = 0
    frame_failures = 0

    while not stop_event.is_set():
        ret, frame = cap.read()
        
        if not ret:
            frame_failures += 1
            
            # Déclencher une reconnexion après plusieurs échecs consécutifs
            if frame_failures >= FRAME_FAILURE_THRESHOLD:
                print(f"[WARN] Caméra {cam_id} : {frame_failures} échecs consécutifs, reconnexion...")
                
                # Libérer la connexion actuelle
                cap.release()
                
                # Calculer le délai avec backoff exponentiel
                delay = min(RECONNECTION_BASE_DELAY * (2 ** reconnection_attempts), MAX_RECONNECTION_DELAY)
                print(f"[INFO] Caméra {cam_id} : attente de {delay:.1f}s avant reconnexion (tentative {reconnection_attempts + 1}/{MAX_RECONNECTION_ATTEMPTS})")
                time.sleep(delay)
                
                # Tenter la reconnexion
                cap = connect_camera()
                
                if cap:
                    print(f"[OK] Caméra {cam_id} ({cam_name}) reconnectée")
                    reconnection_attempts = 0
                    frame_failures = 0
                else:
                    reconnection_attempts += 1
                    if reconnection_attempts >= MAX_RECONNECTION_ATTEMPTS:
                        print(f"[ERREUR] Caméra {cam_id} : échec après {MAX_RECONNECTION_ATTEMPTS} tentatives, abandon")
                        return
            else:
                # Échec ponctuel, attente courte
                time.sleep(RECONNECTION_SLEEP)
            continue

        # Frame lue avec succès, réinitialiser les compteurs
        frame_failures = 0
        reconnection_attempts = 0

        frame = cv2.resize(frame, FRAME_SIZE)

        if cam_queue.full():
            try:
                cam_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            cam_queue.put_nowait(frame)
        except queue.Full:
            pass

    if cap:
        cap.release()
    print(f"Capture thread caméra {cam_id} arrêtée.")


# ----------------------
# Thread 2 : Détection + Tracking + Reconnaissance (avec async)
# ----------------------
def processing_thread(cam):
    cam_id = cam["id"]
    cam_name = cam["cam_name"]
    location = cam["location"]
    cam_queue = frame_queues[cam_id]

    tracker = trackers[cam_id]
    person_db = track_id_to_person[cam_id]

    frame_counter = 0

    # Créer une event loop pour ce thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while not stop_event.is_set():
        try:
            frame = cam_queue.get(timeout=FRAME_QUEUE_TIMEOUT)
        except queue.Empty:
            continue

        frame_counter += 1
        frame_to_display = frame.copy()
        frame_annotated = frame.copy()

        current_frame_idx[cam_id] += 1
        frame_idx = current_frame_idx[cam_id]

        if frame_counter % PROCESS_EVERY_N_FRAME == 0:
            frame_annotated, faces_data = detect_faces(frame, confidence_threshold=FACE_DETECTION_CONFIDENCE)

            # Préparation des détections pour ByteTrack
            detections = []
            crops = []
            for (x, y, w, h), conf, face_crop in faces_data:
                if face_crop.size == 0:
                    continue
                x1, y1, x2, y2 = x, y, x + w, y + h
                detections.append([x1, y1, x2, y2, conf])
                crops.append((face_crop, (x, y, w, h), conf))

            # Mise à jour du tracker
            output_results = np.array(detections) if detections else np.empty((0, 5))
            img_info = [frame.shape[0], frame.shape[1]]
            img_size = [frame.shape[0], frame.shape[1]]

            tracks = tracker.update(output_results, img_info, img_size)

            # Collecter les tracks nécessitant reconnaissance
            recognition_tasks = []
            track_info = []

            for track in tracks:
                tlwh = track.tlwh
                track_id = track.track_id

                x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
                center_x = x + w // 2
                center_y = y + h // 2

                # Reconnaissance seulement si nouveau track ou ré-identification périodique
                if track_id not in person_db or person_db[track_id].get("last_updated", -1000) < frame_idx - REIDENTIFICATION_INTERVAL:
                    # Trouver le crop le plus proche du centre du track
                    best_crop = None
                    best_dist = float('inf')
                    for face_crop, bbox, _ in crops:
                        bx, by, bw, bh = bbox
                        bc_x, bc_y = bx + bw // 2, by + bh // 2
                        dist = (bc_x - center_x)**2 + (bc_y - center_y)**2
                        if dist < best_dist:
                            best_dist = dist
                            best_crop = face_crop

                    if best_crop is not None and best_crop.size > 0:
                        embeddings = generate_face_embeddings(best_crop)
                        if len(embeddings) > 0:
                            recognition_tasks.append(embeddings)
                            track_info.append({"track_id": track_id, "x": x, "y": y, "w": w, "h": h})

            # Exécuter toutes les reconnaissances en parallèle
            if recognition_tasks:
                async def process_all_recognitions():
                    async with aiohttp.ClientSession() as session:
                        # Étape 1 : recherche par similarité en parallèle
                        search_tasks = [search_embedding_async(session, emb, top_k=1) for emb in recognition_tasks]
                        all_results = await asyncio.gather(*search_tasks)

                        # Étape 2 : envoyer les événements pour les personnes nouvellement reconnues
                        event_tasks = []
                        for info, results in zip(track_info, all_results):
                            track_id = info["track_id"]
                            if results and results[0]["score"] > RECOGNITION_THRESHOLD:
                                prev = person_db.get(track_id, {})
                                prev_name = prev.get("name", "Inconnu")
                                prev_sent = prev.get("event_sent", False)
                                new_name = results[0].get("name", "Inconnu")
                                # Envoyer si première reconnaissance ou si la personne a changé
                                if not prev_sent or prev_name != new_name:
                                    event_tasks.append(
                                        send_event_async(
                                            session,
                                            frame_annotated,
                                            cam_id,
                                            results[0]["id"],
                                            "recognition",
                                            results[0]["score"]
                                        )
                                    )

                        if event_tasks:
                            await asyncio.gather(*event_tasks, return_exceptions=True)

                        return all_results

                results_list = loop.run_until_complete(process_all_recognitions())

                # Mettre à jour person_db avec les résultats
                for info, results in zip(track_info, results_list):
                    track_id = info["track_id"]
                    x, y, w, h = info["x"], info["y"], info["w"], info["h"]
                    
                    name = "Inconnu"
                    recognition_score = 0.0
                    color = (0, 0, 255)

                    if results and len(results) > 0 and results[0]["score"] > RECOGNITION_THRESHOLD:
                        name = results[0].get("name", "Inconnu")
                        recognition_score = results[0]["score"]
                        color = (0, 255, 0)
                        print(f"[RECONNU] Caméra {cam_id} ({cam_name}, {location}) : {name} "
                              f"(score {recognition_score:.2f}, track_id={track_id})")

                    person_db[track_id] = {
                        "name": name,
                        "score": recognition_score,
                        "last_updated": frame_idx,
                        "event_sent": name != "Inconnu"
                    }

                    # Annotation sur la frame
                    label = f"{name} (ID:{track_id})"
                    if recognition_score > 0:
                        label += f" {recognition_score:.2f}"
                    cv2.rectangle(frame_annotated, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(frame_annotated, label, (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            # Annoter les tracks déjà en cache
            processed_track_ids = {t["track_id"] for t in track_info}
            for track in tracks:
                track_id = track.track_id
                if track_id in person_db and track_id not in processed_track_ids:
                    tlwh = track.tlwh
                    x, y, w, h = int(tlwh[0]), int(tlwh[1]), int(tlwh[2]), int(tlwh[3])
                    
                    cached = person_db[track_id]
                    name = cached["name"]
                    recognition_score = cached["score"]
                    color = (0, 255, 0) if name != "Inconnu" else (0, 0, 255)

                    label = f"{name} (ID:{track_id})"
                    if recognition_score > 0:
                        label += f" {recognition_score:.2f}"

                    cv2.rectangle(frame_annotated, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(frame_annotated, label, (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            frame_to_display = frame_annotated

            # Nettoyage périodique du cache
            if frame_idx % REIDENTIFICATION_INTERVAL == 0:
                expired = [tid for tid, data in person_db.items() if frame_idx - data["last_updated"] > CACHE_TTL_FRAMES]
                for tid in expired:
                    del person_db[tid]

        # Titre de la caméra
        overlay = f"{cam_name} (ID: {cam_id}) - {location}"
        cv2.putText(frame_to_display, overlay, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame_to_display, overlay, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

        with result_lock:
            result_frames[cam_id] = frame_to_display

    loop.close()


# ----------------------
# Démarrage des threads
# ----------------------
for cam in active_cameras:
    threading.Thread(target=capture_thread, args=(cam,), daemon=True).start()
    threading.Thread(target=processing_thread, args=(cam,), daemon=True).start()

time.sleep(3)
print(f"Système multi-caméras prêt en mode headless (sans affichage).")
print("Le traitement de reconnaissance faciale est actif en arrière-plan.")
print("Appuyez sur Ctrl+C pour quitter.")


# ----------------------
# Boucle principale : Mode headless (pas d'affichage)
# ----------------------
try:
    while True:
        time.sleep(1)  # Attente passive, le traitement se fait dans les threads

except KeyboardInterrupt:
    print("\nArrêt demandé par l'utilisateur (Ctrl+C)")

finally:
    stop_event.set()
    time.sleep(0.5)
    print("Application multi-caméras fermée proprement.")