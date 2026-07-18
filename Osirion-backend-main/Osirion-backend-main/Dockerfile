# =============================================================================
# Osirion-Backend — Dockerfile multi-stage
# =============================================================================
# Build args :
#   GPU=0  (défaut) — torch CPU   (détection de visage YOLO via ultralytics)
#   GPU=1           — torch CUDA
#
# Usage :
#   CPU : docker build .
#   GPU : docker build --build-arg GPU=1 .
#
# Via docker compose :
#   CPU : docker compose up
#   GPU : docker compose --profile gpu up
# =============================================================================

ARG GPU=1

# -----------
# Stage 1 : builder — installation des dépendances Python
# -----------
FROM python:3.12-slim AS builder

ARG GPU
ENV DEBIAN_FRONTEND=noninteractive
# PIP_NO_CACHE_DIR retiré : cache pip BuildKit (RUN --mount=type=cache) pour
# reprendre après une coupure réseau sans tout re-télécharger.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements-cpu.txt requirements-gpu.txt ./

# pip récent (≥25.1) pour --resume-retries : REPREND un téléchargement coupé en
# plein milieu (indispensable sur connexion lente/instable). Couche cachée.
RUN --mount=type=cache,target=/root/.cache/pip pip install --retries 10 --timeout 120 --upgrade pip

# Options réseau robustes (connexion lente) :
#   --resume-retries 10 → reprend un fichier interrompu sans tout refaire
#   --retries 10        → réessaie sur erreur de connexion
#   --timeout 120       → échoue vite sur stall puis reprend (vs attendre 300s)
# PyTorch épinglé CUDA 12 (GPU) / CPU (GPU=0).
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
#   GPU=1 → requirements-gpu.txt (onnxruntime-gpu ~700 MB)
#   GPU=0 → requirements-cpu.txt (onnxruntime CPU  ~50 MB)
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$GPU" = "1" ]; then \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 -r requirements-gpu.txt; \
    else \
        pip install --user --retries 10 --timeout 120 --resume-retries 10 -r requirements-cpu.txt; \
    fi

# -----------
# Stage 2 : runtime — image finale, sans outils de compilation
# -----------
FROM python:3.12-slim AS runtime

ARG GPU
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

LABEL org.opencontainers.image.title="Osirion-Backend" \
      org.opencontainers.image.description="API FastAPI + PostgreSQL/pgvector pour la surveillance Osirion"

# Dépendances runtime uniquement (pas d'outils de build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier les paquets Python compilés depuis le builder
COPY --from=builder /root/.local /root/.local

WORKDIR /app

# Code source uniquement
COPY alembic/         ./alembic/
COPY alembic.ini      .
COPY app/             ./app/
COPY scripts/         ./scripts/

# Modèle de détection de visage (YOLO via ultralytics) utilisé par
# app/services/detection_service.py. La reconnaissance faciale InsightFace
# (onnxruntime + pack antelopev2 ~1 GB) a été retirée — plus rien à pré-télécharger.
COPY yolov11n-face.pt .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["python", "/app/scripts/entrypoint.py"]
