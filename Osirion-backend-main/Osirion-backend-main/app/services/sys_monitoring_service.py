import psutil
import platform
from datetime import datetime
from typing import Dict, List, Any

def get_size(bytes_val: int, suffix: str = "B") -> str:
    """Convertit les octets en unité lisible (KB, MB, GB, etc.)."""
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes_val < factor:
            return f"{bytes_val:.2f} {unit}{suffix}"
        bytes_val /= factor
    return f"{bytes_val:.2f} E{suffix}"  # Cas extrême


def get_system_info() -> Dict[str, Any]:
    """
    Retourne un dictionnaire complet avec toutes les informations système.
    """
    info: Dict[str, Any] = {}

    # === Informations générales ===
    uname = platform.uname()
    info["general"] = {
        "system": uname.system,
        "hostname": uname.node,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "architecture": platform.architecture()[0],
    }

    # Temps de démarrage
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    info["boot_time"] = boot_time.strftime("%Y-%m-%d %H:%M:%S")

    # === CPU ===
    cpu_freq = psutil.cpu_freq()
    info["cpu"] = {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "total_usage_percent": psutil.cpu_percent(interval=1),
        "per_core_usage_percent": psutil.cpu_percent(interval=1, percpu=True),
        "current_frequency_mhz": cpu_freq.current if cpu_freq else None,
        "min_frequency_mhz": cpu_freq.min if cpu_freq else None,
        "max_frequency_mhz": cpu_freq.max if cpu_freq else None,
    }

    # === Mémoire RAM ===
    svmem = psutil.virtual_memory()
    info["ram"] = {
        "total": get_size(svmem.total),
        "available": get_size(svmem.available),
        "used": get_size(svmem.used),
        "percent": svmem.percent,
        "raw_bytes": {
            "total": svmem.total,
            "available": svmem.available,
            "used": svmem.used,
        }
    }

    # === Swap ===
    swap = psutil.swap_memory()
    info["swap"] = {
        "total": get_size(swap.total),
        "used": get_size(swap.used),
        "free": get_size(swap.free),
        "percent": swap.percent,
        "raw_bytes": {
            "total": swap.total,
            "used": swap.used,
        }
    }

    # === Disques ===
    info["disks"] = []
    for partition in psutil.disk_partitions(all=False):  # all=False pour éviter les systèmes de fichiers virtuels
        partition_info: Dict[str, Any] = {
            "device": partition.device,
            "mountpoint": partition.mountpoint,
            "fstype": partition.fstype,
            "opts": partition.opts,
        }
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            partition_info.update({
                "total": get_size(usage.total),
                "used": get_size(usage.used),
                "free": get_size(usage.free),
                "percent": usage.percent,
                "raw_bytes": {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                }
            })
        except PermissionError:
            partition_info["error"] = "Accès refusé"
        info["disks"].append(partition_info)

    # === Réseau ===
    net_io = psutil.net_io_counters()
    info["network"] = {
        "total_bytes_sent": get_size(net_io.bytes_sent),
        "total_bytes_recv": get_size(net_io.bytes_recv),
        "total_packets_sent": net_io.packets_sent,
        "total_packets_recv": net_io.packets_recv,
        "raw_bytes": {
            "sent": net_io.bytes_sent,
            "recv": net_io.bytes_recv,
        }
    }

    # Interfaces réseau (IPv4 uniquement pour simplifier)
    info["network_interfaces"] = {}
    for interface, addrs in psutil.net_if_addrs().items():
        ipv4_info = None
        for addr in addrs:
            if addr.family.name == "AF_INET":
                ipv4_info = {
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast,
                }
                break
        if ipv4_info:
            info["network_interfaces"][interface] = ipv4_info

    return info