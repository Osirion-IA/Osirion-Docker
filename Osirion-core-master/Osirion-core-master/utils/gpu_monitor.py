# utils/gpu_monitor.py
"""
Métriques GPU NVIDIA via `nvidia-smi` (présent dans l'image CUDA du Core).

Best-effort et défensif : si nvidia-smi est absent (Core en CPU) ou échoue,
on renvoie {"available": False, "gpus": []} — jamais d'exception propagée.
Aucune dépendance Python (pas de pynvml) : on parse la sortie CSV de nvidia-smi.
"""
import shutil
import subprocess

_QUERY = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu"


def get_gpu_stats() -> dict:
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "gpus": []}
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return {"available": False, "gpus": []}

    if out.returncode != 0:
        return {"available": False, "gpus": []}

    gpus = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            idx, name, util, mem_used, mem_total, temp = parts[:6]
            mem_used_f = float(mem_used)
            mem_total_f = float(mem_total)
            gpus.append({
                "index": int(idx),
                "name": name,
                "utilization_percent": float(util),
                "memory_used_mb": mem_used_f,
                "memory_total_mb": mem_total_f,
                "memory_percent": round(mem_used_f / mem_total_f * 100, 1) if mem_total_f > 0 else 0.0,
                "temperature_c": float(temp),
            })
        except (ValueError, IndexError):
            continue

    return {"available": len(gpus) > 0, "gpus": gpus}
