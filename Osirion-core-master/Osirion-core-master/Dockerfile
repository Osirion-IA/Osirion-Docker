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
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt requirements-cpu.txt ./

# PyTorch :
#   GPU=0 → wheel CPU-only (index pytorch/whl/cpu)  ~500 MB
#   GPU=1 → wheel CUDA 12.x (index PyPI par défaut) ~2.5 GB
RUN if [ "$GPU" = "1" ]; then \
        pip install --user --no-cache-dir --retries 5 --timeout 180 \
            "torch>=2.0.0" "torchvision>=0.15.0"; \
    else \
        pip install --user --no-cache-dir --retries 5 --timeout 180 \
            --index-url https://download.pytorch.org/whl/cpu \
            "torch>=2.0.0" "torchvision>=0.15.0"; \
    fi

# Dépendances applicatives :
#   GPU=1 → requirements.txt     (onnxruntime-gpu ≥1.17, bundle CUDA ~700 MB)
#   GPU=0 → requirements-cpu.txt (onnxruntime CPU  ≥1.17,         ~50 MB)
RUN if [ "$GPU" = "1" ]; then \
        pip install --user --no-cache-dir --retries 5 --timeout 120 -r requirements.txt && \
        pip install --user --no-cache-dir \
            "nvidia-cuda-runtime-cu12" \
            "nvidia-cufft-cu12" \
            "nvidia-cublas-cu12>=12.2" \
            "nvidia-cudnn-cu12>=8.9"; \
    else \
        pip install --user --no-cache-dir --retries 5 --timeout 120 -r requirements-cpu.txt; \
    fi

# ByteTrack cloné comme package local — import via PYTHONPATH=/app
# from ByteTrack.yolox.tracker.byte_tracker import BYTETracker
RUN git clone --depth 1 https://github.com/ifzhang/ByteTrack.git /build/ByteTrack

# -----------------------------------------------------------------------------
# Stage 2 : runtime — image finale, sans outils de compilation
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ARG GPU
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/root/.local/bin:$PATH"
# /app pour "from ByteTrack.yolox..." et /app/ByteTrack pour les imports internes yolox
ENV PYTHONPATH=/app:/app/ByteTrack

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

# ByteTrack comme package local (doit être dans PYTHONPATH=/app)
COPY --from=builder /build/ByteTrack ./ByteTrack

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
# Modèle YOLO de détection de plaque (LPR/ANPR) — optionnel.
# Placez 'license_plate_detector.pt' à la racine du Core pour l'embarquer dans
# l'image ; sinon montez-le via docker-compose ou définissez PLATE_MODEL_PATH.
# Le module plaques se désactive proprement si le modèle est absent.
# COPY license_plate_detector.pt .

# Pré-télécharger le modèle InsightFace buffalo_l (~183 MB) pour éviter un
# téléchargement au premier démarrage du conteneur.
# Note : CPUExecutionProvider utilisé ici car le builder n'a pas de GPU ;
#        en production GPU, face_detection.py sélectionne CUDAExecutionProvider.
RUN python -c "\
from insightface.app import FaceAnalysis; \
app = FaceAnalysis( \
    name='buffalo_l', \
    providers=['CPUExecutionProvider'], \
    allowed_modules=['detection', 'recognition'] \
); \
app.prepare(ctx_id=-1, det_size=(320, 320)); \
print('InsightFace buffalo_l prêt')"

RUN mkdir -p logs

EXPOSE 5000

# start_period=90s laisse le temps à InsightFace de s'initialiser au démarrage
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -sf http://localhost:5000/api/cameras || exit 1

CMD ["python", "-u", "main_refactored.py"]
