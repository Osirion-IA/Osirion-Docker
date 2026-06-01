#!/usr/bin/env python3
"""
Osirion — Construction des images Docker
=========================================
Lance les builds un par un avec logs en temps réel et suivi de progression.

Usage :
    python build_images.py           → build toutes les images
    python build_images.py --dry-run → affiche les commandes sans les exécuter

Pré-requis : Docker Desktop ou Docker Engine en cours d'exécution.
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

# =============================================================================
# Couleurs ANSI (désactivées automatiquement si le terminal ne les supporte pas)
# =============================================================================
def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

if _supports_color():
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
else:
    RESET = BOLD = DIM = RED = GREEN = YELLOW = BLUE = CYAN = WHITE = ""

# =============================================================================
# Configuration des étapes de build
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

STEPS = [
    {
        "label":   "Base de données (pull image)",
        "type":    "pull",
        "image":   "pgvector/pgvector:pg15",
        "note":    "~150 MB — téléchargement depuis Docker Hub",
        "est_min": 1,
    },
    {
        "label":   "Osirion Backend  [CPU]",
        "type":    "build",
        "image":   "osirion-backend:cpu",
        "context": os.path.join(SCRIPT_DIR, "Osirion-backend-main", "Osirion-backend-main"),
        "args":    {"GPU": "0"},
        "note":    "~4 GB — torch CPU + onnxruntime CPU (le backend n'utilise pas le GPU)",
        "est_min": 25,
    },
    {
        "label":   "Osirion Core     [GPU]",
        "type":    "build",
        "image":   "osirion-core:gpu",
        "context": os.path.join(SCRIPT_DIR, "Osirion-core-master", "Osirion-core-master"),
        "args":    {"GPU": "1"},
        "note":    "~6 GB — torch CUDA 12 (épinglé) + InsightFace + EasyOCR",
        "est_min": 35,
    },
    {
        "label":   "Osirion Frontend",
        "type":    "build",
        "image":   "osirion-frontend:latest",
        "context": os.path.join(SCRIPT_DIR, "Osirion-front-end-main", "Osirion-front-end-main"),
        "args":    {},
        "note":    "~200 MB — Next.js standalone",
        "est_min": 4,
    },
]

# =============================================================================
# Affichage
# =============================================================================

def bar(done: int, total: int, width: int = 30) -> str:
    filled = int(width * done / total)
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def header(total_steps: int, total_est: int) -> None:
    print()
    print(f"{BOLD}{CYAN}{'═' * 62}{RESET}")
    print(f"{BOLD}{CYAN}  Osirion — Construction des images Docker{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 62}{RESET}")
    print(f"  {DIM}Démarrage : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}{RESET}")
    print(f"  {DIM}{total_steps} étapes — durée estimée totale : ~{total_est} min{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 62}{RESET}")
    print()


def step_banner(idx: int, total: int, step: dict) -> None:
    pct = int(100 * (idx - 1) / total)
    print()
    print(f"{BOLD}{BLUE}{'─' * 62}{RESET}")
    print(
        f"{BOLD}{BLUE}  Étape {idx}/{total}  {bar(idx - 1, total)}  {pct}%{RESET}"
    )
    print(f"{BOLD}{WHITE}  {step['label']}{RESET}")
    print(f"  {DIM}Image : {step['image']}{RESET}")
    print(f"  {DIM}Note  : {step['note']}{RESET}")
    print(f"  {DIM}Durée estimée : ~{step['est_min']} min{RESET}")
    print(f"{BOLD}{BLUE}{'─' * 62}{RESET}")
    print()


def step_result(label: str, success: bool, elapsed: float) -> None:
    icon   = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
    status = f"{GREEN}OK{RESET}" if success else f"{RED}ÉCHEC{RESET}"
    print()
    print(f"  {icon}  {BOLD}{label}{RESET}  →  {status}  ({fmt_duration(elapsed)})")
    print()


def summary(results: list) -> None:
    total_time = sum(r["elapsed"] for r in results)
    all_ok     = all(r["success"] for r in results)

    print()
    print(f"{BOLD}{CYAN}{'═' * 62}{RESET}")
    print(f"{BOLD}{CYAN}  Résumé final{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 62}{RESET}")
    print()

    for r in results:
        icon   = f"{GREEN}✓{RESET}" if r["success"] else f"{RED}✗{RESET}"
        timing = fmt_duration(r["elapsed"])
        label  = r["label"].ljust(30)
        print(f"  {icon}  {label}  {DIM}{timing}{RESET}")

    print()
    print(f"  Temps total : {BOLD}{fmt_duration(total_time)}{RESET}")
    print()

    if all_ok and len(results) == len(STEPS):
        print(f"{GREEN}{BOLD}  Toutes les images sont prêtes !{RESET}")
        print()
        print(f"  {DIM}Prochaines étapes :{RESET}")
        print(f"  {DIM}  1. cp .env.example .env   (puis remplir les valeurs){RESET}")
        print(f"  {DIM}  2. docker compose up -d{RESET}")
        print(f"  {DIM}  3. docker compose logs -f{RESET}")
    else:
        built = [r["label"] for r in results if r["success"]]
        failed = [r["label"] for r in results if not r["success"]]
        if failed:
            print(f"{RED}  Images en échec :{RESET}")
            for name in failed:
                print(f"  {RED}  • {name}{RESET}")
        if built:
            print(f"{YELLOW}  Images construites : {len(built)}/{len(STEPS)}{RESET}")

    print()
    print(f"{BOLD}{CYAN}{'═' * 62}{RESET}")
    print()

# =============================================================================
# Exécution des commandes Docker
# =============================================================================

def run_pull(image: str, dry_run: bool) -> tuple[int, float]:
    cmd = ["docker", "pull", image]
    print(f"  {DIM}$ {' '.join(cmd)}{RESET}", flush=True)
    if dry_run:
        print(f"  {YELLOW}[dry-run] Commande non exécutée.{RESET}")
        return 0, 0.0

    start = time.time()
    proc  = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
    )
    for line in proc.stdout:
        print(f"  {DIM}{line.rstrip()}{RESET}", flush=True)
    proc.wait()
    return proc.returncode, time.time() - start


def run_build(image: str, context: str, args: dict, dry_run: bool) -> tuple[int, float]:
    cmd = ["docker", "build", "-t", image]
    for k, v in args.items():
        cmd += ["--build-arg", f"{k}={v}"]
    cmd.append(context)

    print(f"  {DIM}$ {' '.join(cmd)}{RESET}", flush=True)
    if dry_run:
        print(f"  {YELLOW}[dry-run] Commande non exécutée.{RESET}")
        return 0, 0.0

    if not os.path.isdir(context):
        print(f"  {RED}ERREUR : le dossier context est introuvable :{RESET}")
        print(f"  {RED}  {context}{RESET}")
        return 1, 0.0

    start = time.time()
    proc  = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
    )

    last_step = ""
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        # BuildKit affiche les étapes sous forme "#X [stage N/M] ..."
        if line.startswith("#"):
            if line != last_step:
                print(f"  {CYAN}{line}{RESET}", flush=True)
                last_step = line
        else:
            print(f"    {line}", flush=True)

    proc.wait()
    return proc.returncode, time.time() - start


def ask_continue(label: str) -> bool:
    try:
        answer = input(
            f"\n  {YELLOW}'{label}' a échoué. Continuer quand même ? (o/N) : {RESET}"
        ).strip().lower()
        return answer in ("o", "oui", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False

# =============================================================================
# Vérification Docker
# =============================================================================

def check_docker() -> None:
    try:
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"\n  {RED}ERREUR : Docker n'est pas accessible.{RESET}")
        print(f"  {DIM}Vérifiez que Docker Desktop est démarré.{RESET}\n")
        sys.exit(1)

# =============================================================================
# Point d'entrée
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Construit les images Docker Osirion.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les commandes sans les exécuter.",
    )
    args = parser.parse_args()

    check_docker()

    total_est = sum(s["est_min"] for s in STEPS)
    header(len(STEPS), total_est)

    results = []

    for idx, step in enumerate(STEPS, start=1):
        step_banner(idx, len(STEPS), step)

        if step["type"] == "pull":
            code, elapsed = run_pull(step["image"], args.dry_run)
        else:
            code, elapsed = run_build(
                step["image"], step["context"], step["args"], args.dry_run
            )

        success = code == 0
        step_result(step["label"], success, elapsed)
        results.append({"label": step["label"], "success": success, "elapsed": elapsed})

        if not success and not args.dry_run:
            if not ask_continue(step["label"]):
                print(f"\n  {RED}Arrêt du script.{RESET}")
                break

    summary(results)
    return 0 if all(r["success"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
