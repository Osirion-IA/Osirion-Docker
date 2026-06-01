#!/usr/bin/env python3
"""
Point d'entrée du container Osirion-Backend.
Séquence : attente PostgreSQL → migrations Alembic → démarrage Uvicorn.
"""
import os
import sys
import time
import subprocess
from urllib.parse import urlparse

import psycopg2


def wait_for_db(max_retries: int = 30, delay: int = 2) -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[entrypoint] ERROR: DATABASE_URL is not set.", flush=True)
        sys.exit(1)

    parsed = urlparse(db_url)
    host = parsed.hostname
    port = parsed.port or 5432
    user = parsed.username
    password = parsed.password
    dbname = parsed.path.lstrip("/")

    print(f"[entrypoint] Waiting for PostgreSQL at {host}:{port} ...", flush=True)

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                connect_timeout=3,
            )
            conn.close()
            print(f"[entrypoint] PostgreSQL ready (attempt {attempt}).", flush=True)
            return
        except psycopg2.OperationalError as exc:
            print(
                f"[entrypoint] Attempt {attempt}/{max_retries}: {exc}",
                flush=True,
            )
            time.sleep(delay)

    print("[entrypoint] PostgreSQL did not become ready in time. Exiting.", flush=True)
    sys.exit(1)


def run_migrations() -> None:
    print("[entrypoint] Running Alembic migrations ...", flush=True)
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd="/app",
    )
    if result.returncode != 0:
        print("[entrypoint] Migration failed. Exiting.", flush=True)
        sys.exit(1)
    print("[entrypoint] Migrations applied.", flush=True)


def init_default_admin() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@osirion.app")
    admin_password = os.getenv("ADMIN_PASSWORD", "adminadminadmin")

    try:
        import psycopg2
        from urllib.parse import urlparse

        db_url = os.getenv("DATABASE_URL", "")
        parsed = urlparse(db_url)
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            dbname=parsed.path.lstrip("/"),
        )
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM \"user\" WHERE role = 'admin'")
        (count,) = cur.fetchone()

        if count == 0:
            import bcrypt
            hashed = bcrypt.hashpw(admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                """INSERT INTO "user" ("fullName", email, usr_password, role, is_active, is_verified, created_at, updated_at)
                   VALUES (%s, %s, %s, 'admin', TRUE, TRUE, NOW(), NOW())""",
                ("Admin", admin_email, hashed),
            )
            conn.commit()
            print(f"[entrypoint] Admin account created: {admin_email}", flush=True)
        else:
            print(f"[entrypoint] Admin account already exists, skipping.", flush=True)

        cur.close()
        conn.close()
    except Exception as exc:
        print(f"[entrypoint] WARNING: could not init admin: {exc}", flush=True)


def start_server() -> None:
    print("[entrypoint] Starting Uvicorn ...", flush=True)
    cmd = [
        "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
    ]
    # --reload activé si UVICORN_RELOAD=true (défaut: true quand bind mount actif)
    if os.getenv("UVICORN_RELOAD", "true").lower() == "true":
        cmd += ["--reload", "--reload-dir", "/app/app", "--reload-delay", "0.25"]
        print("[entrypoint] Hot-reload activé (UVICORN_RELOAD=true).", flush=True)
    # os.execvp remplace le processus courant — uvicorn hérite du PID 1
    os.execvp("uvicorn", cmd)


if __name__ == "__main__":
    wait_for_db()
    run_migrations()
    init_default_admin()
    start_server()
