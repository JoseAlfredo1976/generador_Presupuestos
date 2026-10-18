"""
utils/erp.py - Conexion con el ERP de Grupo Europa.

- El ERP abre el generador con ?erp=<token> para pre-rellenar el cliente. El
  token es base64url(JSON) + "." + HMAC-SHA256(ERP_SECRET) y caduca (campo exp).
- Al generar un presupuesto se registra en el ERP (POST /api/internal/presupuestos,
  accion "registrar") con el numero que da el generador: la numeracion la lleva
  el generador (Google Sheets) y el ERP solo la recoge.

Variables de entorno: ERP_URL, ERP_SECRET (= INTEGRACION_SECRET del ERP) y
ERP_EMPRESA_NIF (sociedad por defecto si el presupuesto no viene del ERP).
Sin ERP_URL o ERP_SECRET no se hace nada: el generador funciona igual que antes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


def _secret() -> bytes:
    return os.environ.get("ERP_SECRET", "").strip().encode()


def leer_token(token: str) -> dict | None:
    """Datos del token del ERP si la firma es valida y no ha caducado."""
    secret = _secret()
    if not secret or not token or "." not in token:
        return None
    cuerpo, firma = token.rsplit(".", 1)
    esperada = base64.urlsafe_b64encode(hmac.new(secret, cuerpo.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    if not hmac.compare_digest(firma, esperada):
        return None
    try:
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    except ValueError:
        return None
    if not isinstance(datos, dict) or float(datos.get("exp", 0)) < time.time():
        return None
    return datos


def registrar(datos: dict) -> None:
    """Registra el presupuesto en el ERP. Los fallos solo se anotan en el log."""
    url = os.environ.get("ERP_URL", "").strip().rstrip("/")
    secret = _secret()
    if not url or not secret:
        return
    if not datos.get("empresa_nif"):
        datos["empresa_nif"] = os.environ.get("ERP_EMPRESA_NIF", "").strip()
    if not datos["empresa_nif"]:
        log.warning("ERP: sin empresa_nif, no se registra %s", datos.get("numero"))
        return
    req = urllib.request.Request(
        f"{url}/api/internal/presupuestos",
        data=json.dumps({"accion": "registrar", **datos}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {secret.decode()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            log.info("ERP: presupuesto %s registrado (%s)", datos.get("numero"), r.status)
    except urllib.error.HTTPError as e:
        log.warning("ERP: error %s al registrar %s: %s", e.code, datos.get("numero"), e.read()[:300])
    except Exception as e:
        log.warning("ERP: no se pudo registrar %s: %s", datos.get("numero"), e)
