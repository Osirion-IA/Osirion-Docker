# =============================================================================
# Osirion-Backend — Dockerfile multi-stage
# =============================================================================
# Build args :
#   GPU=0  (défaut) — torch CPU  + onnxruntime      (~3 GB image finale)
#   GPU=1           — torch CUDA + onnxruntime-gpu  (~7 GB image finale)
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

COPY yolov11n-face.pt .

# Pré-télécharger le pack InsightFace d'enrôlement (PARITÉ avec le Core :
# antelopev2 = SCRFD-10G + glintr100 ResNet-100). Évite un téléchargement au
# premier enrôlement. Doit rester ALIGNÉ sur le Core (même INSIGHTFACE_MODEL_PACK).
#
# BUG antelopev2 : son .zip contient un dossier `antelopev2/`, donc l'auto-download
# d'insightface l'extrait en DOUBLE (models/antelopev2/antelopev2/*.onnx) →
# FaceAnalysis ne trouve aucun modèle (AssertionError: 'detection' in self.models).
# On télécharge donc le zip et on l'extrait NOUS-MÊMES au bon niveau (models/), avec
# repli de mise à plat si un dossier imbriqué subsiste. Les autres packs (buffalo_l)
# passent par l'auto-download normal (verify ci-dessous).
ARG INSIGHTFACE_MODEL_PACK=antelopev2
ENV INSIGHTFACE_MODEL_PACK=${INSIGHTFACE_MODEL_PACK}
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
print('InsightFace', pack, 'OK (backend) —', list(app.models.keys()))"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["python", "/app/scripts/entrypoint.py"]
