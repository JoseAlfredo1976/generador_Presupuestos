# -*- coding: utf-8 -*-
"""Enlaces publicos de solo-video para compartir un informe CCTV con el cliente
final (ver /ver/<token> en app.py).

Esta app no tiene sistema de cuentas: un token = un informe (session_id).
Quien tenga el enlace puede ver el video comprimido y la tabla de anomalias
de ESE informe.
"""
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_DB_PATH = _CONFIG_DIR / "enlaces.db"


def _conn() -> sqlite3.Connection:
    _CONFIG_DIR.mkdir(exist_ok=True)
    return sqlite3.connect(_DB_PATH)


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS enlaces_compartidos (
                token TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                creado_en TEXT NOT NULL
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_enlaces_session "
            "ON enlaces_compartidos (session_id)"
        )


def crear_o_reusar(session_id: str) -> str:
    """Devuelve el token existente para session_id, o crea uno nuevo."""
    with _conn() as c:
        row = c.execute(
            "SELECT token FROM enlaces_compartidos WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row:
            return row[0]
        token = secrets.token_urlsafe(24)
        c.execute(
            "INSERT INTO enlaces_compartidos (token, session_id, creado_en) VALUES (?, ?, ?)",
            (token, session_id, datetime.now().isoformat()),
        )
        return token


def resolver(token: str) -> str | None:
    """Devuelve el session_id para un token valido, o None."""
    with _conn() as c:
        row = c.execute(
            "SELECT session_id FROM enlaces_compartidos WHERE token = ?",
            (token,),
        ).fetchone()
    return row[0] if row else None
