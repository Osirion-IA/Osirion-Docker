from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
import os

from app.database import engine
from app.routes.people_routes import router as people_router
from app.routes.cameras_routes import router as camera_router
from app.routes.monitoring_routes import router as monitoring_router
from app.routes.events_routes import router as events_router
from app.routes.auth_routes import router as auth_router
from app.routes.users_routes import router as users_router
from app.routes.plates_routes import router as plates_router
from app.routes.alerts_routes import router as alerts_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.audit_routes import router as audit_router
from app.routes.maintenance_routes import router as maintenance_router
from app.services.Faiss_search_service import build_or_reload_faiss_index
from app.middleware.rate_limit import limiter
from app.config import settings

app = FastAPI(
    title="Osirion API",
    version="2.0.0",
    description="Backend FastAPI sécurisé pour l'IA de surveillance Osirion",
)

# ─────────────────────────────────────────────
# RATE LIMITING
# ─────────────────────────────────────────────
app.state.limiter = limiter

# ─────────────────────────────────────────────
# Initialisation BDD à startup
# ─────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    # Les migrations sont appliquées par scripts/entrypoint.py (alembic upgrade head)
    # avant le démarrage d'uvicorn — create_all n'est pas appelé ici pour éviter
    # les conflits avec Alembic sur les tables déjà créées.
    build_or_reload_faiss_index()


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "Trop de requêtes",
            "detail": "Vous avez dépassé la limite de requêtes autorisées. Veuillez réessayer plus tard."
        }
    )

# ─────────────────────────────────────────────
# CORS (autoriser le frontend)
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ─────────────────────────────────────────────
# Fichiers statiques (images uploadées)
# ─────────────────────────────────────────────
for _dir in ("uploads", "cropped", "snapshots"):
    os.makedirs(_dir, exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/cropped", StaticFiles(directory="cropped"), name="cropped")
app.mount("/snapshots", StaticFiles(directory="snapshots"), name="snapshots")

# ─────────────────────────────────────────────
# Enregistrement des routes
# ─────────────────────────────────────────────
app.include_router(auth_router, prefix="/auth", tags=["🔐 Authentication"])
app.include_router(events_router, prefix="/events", tags=[" Events"])
app.include_router(users_router, prefix="/users", tags=["👥 Users Management"])
app.include_router(people_router, prefix="/people", tags=["👤 People"])
app.include_router(plates_router, prefix="/plates", tags=["🚗 License Plates"])
app.include_router(alerts_router, prefix="/alerts", tags=["🚨 Alerts"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["📊 Dashboard"])
app.include_router(audit_router, prefix="/audit", tags=["📝 Audit"])
app.include_router(maintenance_router, prefix="/maintenance", tags=["🧹 Maintenance"])
app.include_router(camera_router, prefix="/cameras", tags=["📹 Cameras"])
app.include_router(monitoring_router,prefix="/sysInfo", tags=["Syetem Informations"])

# ─────────────────────────────────────────────
# Route de test (Non protégée)
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "Osirion API is running 🚀",
        "version": "2.0.0",
        "status": "protected",
        "docs": "/docs"
    }

# ─────────────────────────────────────────────
# Route de santé (Non protégée)
# ─────────────────────────────────────────────
@app.get("/health")
def health_check():
    db_status = "connected"
    try:
        from sqlmodel import Session, text
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    from app.services.Faiss_search_service import index
    faiss_status = f"{index.ntotal} vecteurs" if index is not None else "vide (aucune personne enregistrée)"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "faiss_index": faiss_status,
        "authentication": "enabled"
    }