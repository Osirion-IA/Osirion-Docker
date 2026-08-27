from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
import os

from app.database import engine
from app.routes.cameras_routes import router as camera_router
from app.routes.monitoring_routes import router as monitoring_router
from app.routes.events_routes import router as events_router
from app.routes.auth_routes import router as auth_router
from app.routes.users_routes import router as users_router
from app.routes.alerts_routes import router as alerts_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.audit_routes import router as audit_router
from app.routes.maintenance_routes import router as maintenance_router
from app.routes.groups_routes import router as groups_router
from app.routes.zones_routes import router as zones_router
from app.routes.analytics_routes import router as analytics_router
from app.routes.rules_routes import router as rules_router
from app.routes.hikcentral_routes import router as hikcentral_router
from app.routes.camera_status_routes import router as camera_status_router
from app.routes.notifications_routes import router as notifications_router
from app.routes.work_schedules_routes import router as work_schedules_router
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
    # Migrations appliquées par scripts/entrypoint.py (alembic upgrade head) avant uvicorn.
    # Synchro périodique du catalogue HikCentral (no-op si non configuré / intervalle 0).
    from app.services.hikcentral_scheduler import start_periodic_sync
    start_periodic_sync()
    # Enregistreur d'historique de connectivité caméra (poll santé Core → transitions).
    from app.services.camera_status_recorder import start as start_camera_status_recorder
    start_camera_status_recorder()


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
app.include_router(alerts_router, prefix="/alerts", tags=["🚨 Alerts"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["📊 Dashboard"])
app.include_router(audit_router, prefix="/audit", tags=["📝 Audit"])
app.include_router(maintenance_router, prefix="/maintenance", tags=["🧹 Maintenance"])
app.include_router(camera_router, prefix="/cameras", tags=["📹 Cameras"])
app.include_router(groups_router, prefix="/groups", tags=["🗂️ Camera Groups"])
app.include_router(zones_router, prefix="/zones", tags=["📐 Zones & Comptage"])
app.include_router(analytics_router, prefix="/analytics", tags=["📈 Analytics"])
app.include_router(rules_router, prefix="/rules", tags=["⚙️ Rules"])
app.include_router(hikcentral_router, prefix="/hikcentral", tags=["🎥 HikCentral"])
app.include_router(camera_status_router, prefix="/camera-status", tags=["📡 Camera Status"])
app.include_router(notifications_router, prefix="/notifications", tags=["✉️ Notifications"])
app.include_router(work_schedules_router, prefix="/work-schedules", tags=["🕗 Régimes horaires"])
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

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "authentication": "enabled"
    }