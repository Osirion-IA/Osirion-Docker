# =============================================================================
# Osirion-Core — Dockerfile multi-stage
# =============================================================================
# Build args :
#   GPU=1  (défaut) — torch CUDA + onnxruntime-gpu  (~6 GB image finale)
#   GPU=0           — torch CPU  + onnxruntime      (~3 GB image finale)
#
# Usage :
#   GPU  : docker build .
#   CPU  : docker build --build-arg GPU=0 .
#
# Via docker compose :
#   GPU  : docker compose --profile gpu up
#   CPU  : docker compose up
# =============================================================================

ARG GPU=1

# -----------------------------------------------------------------------------
# Stage 1 : builder — compilation Cython + installation des dépendances Python
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ARG GPU
ENV DEBIAN_FRONTEND=noninteractive
# PIP_NO_CACHE_DIR retiré : on utilise un cache pip BuildKit (RUN --mount=type=cache)
# pour reprendre les téléchargements après une coupure réseau sans tout refaire.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt requirements-cpu.txt ./

# pip récent (≥25.1) pour --resume-retries : REPREND un téléchargement coupé en
# plein milieu (indispensable sur connexion lente/instable). Couche cachée.
RUN --mount=type=cache,target=/root/.cache/pip pip install --retries 10 --timeout 120 --upgrade pip

# PyTorch — versions ÉPINGLÉES en CUDA 12 (torch 2.9.1 / torchvision 0.24.1).
#   Sans épinglage, "torch>=2.0.0" tirait torch 2.12 + CUDA 13 (énorme + incompatible
#   avec les nvidia-*-cu12 du projet et le driver). 2.9.1 = même base que le backend.
# Options réseau robustes : --resume-retries 10 reprend un fichier interrompu.
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$GPU" = "1" ]; then \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 \
            "torch==2.9.1" "torchvision==0.24.1"; \
    else \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 \
            --index-url https://download.pytorch.org/whl/cpu \
            "torch==2.9.1" "torchvision==0.24.1"; \
    fi

# Dépendances applicatives :
#   GPU=1 → requirements.txt     (onnxruntime-gpu ≥1.17, bundle CUDA ~700 MB)
#   GPU=0 → requirements-cpu.txt (onnxruntime CPU  ≥1.17,         ~50 MB)
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$GPU" = "1" ]; then \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 -r requirements.txt && \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 \
            "nvidia-cuda-runtime-cu12" \
            "nvidia-cufft-cu12" \
            "nvidia-cublas-cu12>=12.2" \
            "nvidia-cudnn-cu12>=8.9" && \
        # ── Conflit onnxruntime : insightface tire `onnxruntime` (CPU) en
        # dépendance transitive, dont le pybind (onnxruntime_pybind11_state.so)
        # ÉCRASE celui d'onnxruntime-gpu → CUDAExecutionProvider disparaît et
        # InsightFace retombe sur CPU. On purge les DEUX distributions puis on
        # réinstalle UNIQUEMENT onnxruntime-gpu EN DERNIER (son pybind l'emporte).
        pip uninstall -y onnxruntime onnxruntime-gpu && \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 --no-deps \
            "onnxruntime-gpu>=1.22.0,<1.23" && \
        # Garde-fou : échoue le build si le pybind embarqué est un build CPU
        # (sans symbole CUDAExecutionProvider) — empêche toute régression future.
        grep -aq CUDAExecutionProvider \
            /root/.local/lib/python3.11/site-packages/onnxruntime/capi/onnxruntime_pybind11_state*.so \
        || { echo "ERREUR build : pybind onnxruntime sans CUDA (build CPU détecté)"; exit 1; }; \
    else \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 -r requirements-cpu.txt; \
    fi

# -----------------------------------------------------------------------------
# Stage 2 : runtime — image finale, sans outils de compilation
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ARG GPU
# Pack de modèles InsightFace pré-téléchargé ET utilisé au runtime. antelopev2 =
# SCRFD-10G + glintr100 (ResNet-100) → précision « entreprise ». Le backend
# d'enrôlement DOIT utiliser le même pack (même variable d'env).
ARG INSIGHTFACE_MODEL_PACK=antelopev2
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin:$PATH"
# Propagé à l'application (face_detection.py lit INSIGHTFACE_MODEL_PACK).
ENV INSIGHTFACE_MODEL_PACK=${INSIGHTFACE_MODEL_PACK}
# /app : racine des packages applicatifs (config, core, services, utils, ...)
ENV PYTHONPATH=/app

LABEL org.opencontainers.image.title="Osirion-Core" \
      org.opencontainers.image.description="Système de surveillance multi-caméras avec détection et reconnaissance faciale"

# Dépendances runtime uniquement (pas d'outils de build)
# curl est requis par le HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier les paquets Python compilés depuis le builder
COPY --from=builder /root/.local /root/.local

# Enregistrer les libs nvidia (cublas, cudnn) auprès du linker dynamique
RUN if [ "$GPU" = "1" ]; then \
        find /root/.local/lib/python3.11/site-packages/nvidia \
            -mindepth 2 -maxdepth 2 -name lib -type d \
            > /etc/ld.so.conf.d/nvidia-pypi.conf 2>/dev/null || true && \
        ldconfig; \
    fi

WORKDIR /app

# Code source de l'application uniquement
COPY config/            ./config/
COPY core/              ./core/
COPY services/          ./services/
COPY utils/             ./utils/
COPY templates/         ./templates/
COPY face_detection.py  .
COPY plate_detection.py .
COPY main_refactored.py .
COPY yolov11n-face.pt   .
# Modèle YOLO de détection de plaque (LPR/ANPR).
# Le module plaques se désactive proprement si le modèle est absent.
COPY license_plate_detector.pt .

# Pré-télécharger le pack InsightFace (antelopev2 ≈ 360 MB : SCRFD-10G + glintr100
# ResNet-100) pour éviter un téléchargement au premier démarrage du conteneur.
# Note : CPUExecutionProvider utilisé ici car le builder n'a pas de GPU ;
#        en production GPU, face_detection.py sélectionne CUDAExecutionProvider.
#
# BUG antelopev2 : son .zip contient un dossier `antelopev2/`, donc l'auto-download
# d'insightface l'extrait en DOUBLE (models/antelopev2/antelopev2/*.onnx) →
# FaceAnalysis ne trouve aucun modèle (AssertionError: 'detection' in self.models).
# On télécharge donc le zip et on l'extrait NOUS-MÊMES au bon niveau (models/), avec
# repli de mise à plat si un dossier imbriqué subsiste. Les autres packs (buffalo_l)
# passent par l'auto-download normal (verify ci-dessous).
RUN if [ "$INSIGHTFACE_MODEL_PACK" = "antelopev2" ]; then \
        python -c "import os,glob,zipfile,shutil,urllib.request; \
root=os.path.expanduser('~/.insightface/models'); os.makedirs(root,exist_ok=True); \
z='/tmp/antelopev2.zip'; \
urllib.request.urlretrieve('https://github.com/deepinsight/insightface/releases/download/v0.7/antelopev2.zip', z); \
zipfile.ZipFile(z).extractall(root); \
n=os.path.join(root,'antelopev2','antelopev2'); \
([shutil.move(f, os.path.join(root,'antelopev2')) for f in glob.glob(n+'/*')] if os.path.isdir(n) else None); \
(os.rmdir(n) if os.path.isdir(n) else None); \
os.remove(z); print('antelopev2 extrait dans', root)"; \
    fi && \
    python -c "import os; from insightface.app import FaceAnalysis; \
pack=os.getenv('INSIGHTFACE_MODEL_PACK','antelopev2'); \
app=FaceAnalysis(name=pack, providers=['CPUExecutionProvider'], allowed_modules=['detection','recognition']); \
app.prepare(ctx_id=-1, det_size=(320,320)); \
print('InsightFace', pack, 'OK —', list(app.models.keys()))"

# Pré-télécharger les modèles EasyOCR (détecteur CRAFT + recognizer 'en', ~100 MB)
# pour le module LPR — évite un téléchargement (et un blocage potentiel sans réseau)
# au premier chargement du pipeline plaques. gpu=False suffit ici (builder sans GPU).
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False); print('EasyOCR prêt')"

RUN mkdir -p logs

EXPOSE 5000

# start_period=90s laisse le temps à InsightFace de s'initialiser au démarrage
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -sf http://localhost:5000/api/cameras || exit 1

CMD ["python", "-u", "main_refactored.py"]
