"""
Base de datos local: clientes y contadores de numeracion.
Fuente: tarifas/BASE_DATOS.xlsx
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

BASE_PATH = Path(__file__).parent.parent / "tarifas" / "BASE_DATOS.xlsx"

# Mapeo tipo -> CATEGORIA en hoja CONTROL del Excel
TIPO_A_CATEGORIA: dict[str, str] = {
    "obra_1":               "POCERIA",
    "obra_2":               "POCERIA",
    "desatasco":            "POCERIA",
    "fuga_agua":            "POCERIA",
    "certificado_obra":     "POCERIA",
    "contrato_subcontrata": "POCERIA",
    "plan_seguridad":       "POCERIA",
    "cctv_bajante":         "INFORMES CCTV-LIMPIEZAS",
    "inspeccion_zum":       "INFORMES CCTV-LIMPIEZAS",
    "informe_desatasco":    "INFORMES CCTV-LIMPIEZAS",
    "bajantes_amianto":     "INFORMES CCTV-LIMPIEZAS",
    "limpieza_aerea":       "LIMPIEZAS",
    "fresador":             "LIMPIEZAS",
    "robot_limpieza":       "LIMPIEZAS",
    "vaciado_fosa":         "LIMPIEZAS",
    "contrato_saneamiento": "CONTRATOS DE MANTENIMIENTO",
    "fontaneria":           "FONTANERIA",
    "albanileria":          "ALBANILERIA Y OTROS TRABAJOS",
}

_clientes: list[str] | None = None
_contadores: dict[str, int] | None = None


def _load():
    global _clientes, _contadores
    if _clientes is not None:
        return
    if not BASE_PATH.exists():
        log.warning("BASE_DATOS.xlsx no encontrado en %s", BASE_PATH)
        _clientes = []
        _contadores = {}
        return

    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(BASE_PATH), read_only=True, data_only=True)

        # Clientes
        ws_cli = wb["CLIENTES"]
        nombres = []
        for i, row in enumerate(ws_cli.iter_rows(values_only=True)):
            if i == 0:
                continue  # cabecera
            nombre = row[0]
            if nombre and str(nombre).strip():
                nombres.append(str(nombre).strip())
        _clientes = sorted(set(nombres))

        # Contadores desde hoja CONTROL
        ws_ctrl = wb["CONTROL"]
        contadores = {}
        for i, row in enumerate(ws_ctrl.iter_rows(values_only=True)):
            if i == 0:
                continue
            categoria, _, _, _, _, siguiente = row[:6]
            if categoria and siguiente:
                try:
                    contadores[str(categoria).strip()] = int(siguiente)
                except (ValueError, TypeError):
                    pass
        _contadores = contadores

        log.info("BASE_DATOS cargada: %d clientes, %d categorias", len(_clientes), len(_contadores))
    except Exception as e:
        log.warning("Error cargando BASE_DATOS: %s", e)
        _clientes = []
        _contadores = {}


def buscar_clientes(q: str, limit: int = 20) -> list[str]:
    """Devuelve clientes cuyo nombre contiene q (case-insensitive)."""
    _load()
    if not q or not _clientes:
        return []
    q_lower = q.lower()
    return [c for c in _clientes if q_lower in c.lower()][:limit]


def siguiente_numero_local(tipo: str) -> int | None:
    """
    Devuelve el siguiente numero para el tipo dado segun la base local.
    Retorna None si no hay datos.
    """
    _load()
    if not _contadores:
        return None
    cat = TIPO_A_CATEGORIA.get(tipo)
    if not cat:
        return None
    return _contadores.get(cat)
