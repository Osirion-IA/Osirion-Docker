# utils/logger.py
"""
Configuration centralisée du logging pour Osirion-Core
Support des logs structurés avec rotation automatique
"""
import logging
import logging.handlers
import os
import sys
import json
from datetime import datetime
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """
    Formateur de logs structurés en JSON
    Facilite l'indexation dans ELK, Loki, etc.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Ajouter l'exception si présente
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Ajouter les champs personnalisés (camera_id, track_id, etc.)
        if hasattr(record, 'camera_id'):
            log_data["camera_id"] = record.camera_id
        if hasattr(record, 'track_id'):
            log_data["track_id"] = record.track_id
        if hasattr(record, 'fps'):
            log_data["fps"] = record.fps
        if hasattr(record, 'latency_ms'):
            log_data["latency_ms"] = record.latency_ms
        
        return json.dumps(log_data, ensure_ascii=False)


class ColoredConsoleFormatter(logging.Formatter):
    """
    Formateur pour affichage console avec couleurs
    Améliore la lisibilité en développement
    """
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Vert
        'WARNING': '\033[33m',    # Jaune
        'ERROR': '\033[31m',      # Rouge
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Format : [2026-02-03 14:30:15] INFO [camera_manager] Message
        log_format = (
            f"{color}[%(asctime)s] %(levelname)-8s{reset} "
            f"[%(name)s] %(message)s"
        )
        
        formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_json: bool = False,
    enable_console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Configure le système de logging pour l'application
    
    Args:
        log_level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Répertoire pour stocker les logs
        enable_json: Activer les logs JSON structurés (pour production)
        enable_console: Activer l'affichage console
        max_bytes: Taille max d'un fichier de log avant rotation
        backup_count: Nombre de fichiers de backup à conserver
    
    Returns:
        Logger racine configuré
    """
    
    # Créer le répertoire de logs s'il n'existe pas
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Configurer le logger racine
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Supprimer les handlers existants pour éviter les doublons
    root_logger.handlers.clear()
    
    # Handler 1 : Fichier de logs standard (texte lisible)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path / "osirion.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Handler 2 : Fichier de logs JSON (pour parsing automatique)
    if enable_json:
        json_handler = logging.handlers.RotatingFileHandler(
            filename=log_path / "osirion.json.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        json_handler.setLevel(logging.INFO)
        json_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(json_handler)
    
    # Handler 3 : Console avec couleurs
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ColoredConsoleFormatter())
        root_logger.addHandler(console_handler)
    
    # Handler 4 : Fichier séparé pour les erreurs uniquement
    error_handler = logging.handlers.RotatingFileHandler(
        filename=log_path / "osirion.error.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    root_logger.addHandler(error_handler)
    
    # Réduire le verbosity des bibliothèques tierces
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('socketio').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    
    root_logger.info(f"Système de logging initialisé (niveau={log_level}, dir={log_dir})")
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtenir un logger nommé pour un module spécifique
    
    Usage:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Message", extra={'camera_id': 1})
    
    Args:
        name: Nom du module (utiliser __name__)
    
    Returns:
        Logger configuré pour ce module
    """
    return logging.getLogger(name)


# Fonction d'aide pour logger avec contexte
def log_with_context(logger: logging.Logger, level: str, message: str, **context):
    """
    Logger un message avec contexte structuré
    
    Usage:
        log_with_context(logger, 'info', 'Frame processed', 
                        camera_id=1, fps=30, latency_ms=45)
    """
    log_func = getattr(logger, level.lower())
    log_func(message, extra=context)
