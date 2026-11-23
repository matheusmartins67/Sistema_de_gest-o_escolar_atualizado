"""Configuração centralizada e caminhos da aplicação."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_env() -> None:
    """Carrega variáveis simples de um arquivo .env sem sobrescrever o ambiente."""
    env_file = PROJECT_ROOT / '.env'
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_project_env()
DATA_DIR = Path(os.environ.get("SCHOOL_DATA_DIR", PROJECT_ROOT / "data"))
DATABASE_FILE = Path(os.environ.get("SCHOOL_DATABASE_PATH", DATA_DIR / "escola.db"))
UPLOADS_DIR = Path(os.environ.get("SCHOOL_UPLOADS_DIR", DATA_DIR / "uploads"))
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"


def database_path() -> str:
    """Retorna o caminho do SQLite, criando o diretório de dados quando preciso."""
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    return str(DATABASE_FILE)


def ensure_runtime_directories() -> None:
    """Cria diretórios locais que não devem ser versionados."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    """Valores de execução, todos ajustáveis por variáveis de ambiente."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    UPLOAD_FOLDER = str(UPLOADS_DIR)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
