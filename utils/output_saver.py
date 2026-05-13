"""
Copia los archivos generados al disco externo configurado, con estructura:
  {output_base_path}/{output_subfolder}/{CATEGORIA}/{num}-{obra}/

Si el disco no esta conectado o no hay ruta configurada, falla silenciosamente.
"""
from __future__ import annotations

import logging
import shutil
import unicodedata
from pathlib import Path

from utils.app_config import load as load_cfg

log = logging.getLogger(__name__)

# ── Mapeo tipo -> subcarpeta ──────────────────────────────────────────────────

TIPO_A_CARPETA: dict[str, str] = {
    "obra_1":               "POCERIA",
    "obra_2":               "POCERIA",
    "desatasco":            "POCERIA",
    "fuga_agua":            "POCERIA",
    "cctv_bajante":         "INFORMES CCTV-LIMPIEZAS",
    "inspeccion_zum":       "INFORMES CCTV-LIMPIEZAS",
    "limpieza_aerea":       "LIMPIEZAS",
    "fresador":             "LIMPIEZAS",
    "robot_limpieza":       "LIMPIEZAS",
    "vaciado_fosa":         "LIMPIEZAS",
    "informe_desatasco":    "INFORMES CCTV-LIMPIEZAS",
    "bajantes_amianto":     "INFORMES CCTV-LIMPIEZAS",
    "certificado_obra":     "POCERIA",
    "plan_seguridad":       "PLAN DE SEGURIDAD Y SALUD",
    "contrato_saneamiento": "CONTRATOS DE MANTENIMIENTO",
    "fontaneria":           "FONTANERIA",
    "albanileria":          "ALBANILERIA Y OTROS TRABAJOS",
    "contrato_subcontrata": "POCERIA",
}


def _safe(s: str, maxlen: int = 50) -> str:
    nfd = unicodedata.normalize("NFD", s)
    clean = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    safe = ""
    for c in clean:
        if c.isalnum() or c in (" ", "-", "_", ".", "N", "/"):
            safe += c
        elif c in ("\\", ":", "*", "?", '"', "<", ">", "|"):
            safe += "-"
        else:
            safe += c
    return safe[:maxlen].strip(". -")


def _get_base() -> Path | None:
    """Resuelve la ruta base desde la configuracion."""
    cfg = load_cfg()
    raw = (cfg.get("output_base_path") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    subfolder = (cfg.get("output_subfolder") or "PRESUPUESTOS GRUPO EUROPA").strip()
    base = p / subfolder if subfolder else p
    if not p.exists():
        log.warning("Disco externo no encontrado: %s", raw)
        return None
    return base


def guardar_en_red(
    tipo: str,
    num_contrato: str,
    obra: str,
    archivos: list[Path],
) -> Path | None:
    """
    Copia los archivos al disco externo configurado.
    Devuelve la carpeta destino o None si el disco no esta disponible.
    """
    base = _get_base()
    if base is None:
        return None

    categoria = TIPO_A_CARPETA.get(tipo, "VARIOS")
    cat_dir = base / categoria
    cat_dir.mkdir(parents=True, exist_ok=True)

    num_base = num_contrato.split("/")[0]
    obra_safe = _safe(obra.upper(), maxlen=50)
    folder_name = f"{num_base}-{obra_safe}"
    dest_dir = cat_dir / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    copiados = 0
    for src in archivos:
        if src and src.exists():
            try:
                shutil.copy2(src, dest_dir / src.name)
                copiados += 1
            except Exception as e:
                log.warning("No se pudo copiar %s: %s", src.name, e)

    if copiados:
        log.info("Guardados %d archivo(s) en %s", copiados, dest_dir)
        return dest_dir
    return None


def estado_disco() -> dict:
    """Devuelve el estado actual del disco para mostrar en la UI."""
    cfg = load_cfg()
    raw = (cfg.get("output_base_path") or "").strip()
    subfolder = (cfg.get("output_subfolder") or "").strip()

    if not raw:
        return {"configurado": False, "conectado": False, "ruta": "", "ruta_completa": ""}

    p = Path(raw)
    conectado = p.exists()
    ruta_completa = str(p / subfolder) if subfolder else str(p)
    return {
        "configurado": True,
        "conectado": conectado,
        "ruta": raw,
        "subfolder": subfolder,
        "ruta_completa": ruta_completa,
    }
