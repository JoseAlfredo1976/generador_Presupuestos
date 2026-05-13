"""
Registro de presupuestos en Google Sheets.

Estructura esperada en cada pestaña:
  Col A: Nº Presupuesto   (ej: 4353/26)
  Col B: Fecha            (ej: 13/05/2026)
  Col C: Cliente
  Col D: Obra / Servicio
  Col E: Importe sin IVA  (ej: 3.500,00)
  Col F: Tipo documento
  Col G: Archivo generado (nombre de carpeta)

Si la hoja tiene columnas distintas, ajustar COL_* abajo.

Credenciales: colocar el archivo JSON de cuenta de servicio en
  budget_generator/config/google_credentials.json
y compartir la hoja con el email de la cuenta de servicio.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# ── Configuracion ─────────────────────────────────────────────────────────────

SHEET_ID = "1tj9jsgCdmOm-lsrfZO0ocGCjlzdUkHTP"

CREDS_PATH = Path(__file__).parent.parent / "config" / "google_credentials.json"

# Pestaña de Google Sheets para cada tipo de documento
TIPO_A_PESTAÑA: dict[str, str] = {
    "obra_1":               "POCERIA",
    "obra_2":               "POCERIA",
    "desatasco":            "POCERIA",
    "fuga_agua":            "POCERIA",
    "cctv_bajante":         "CCTV-LIMPIEZAS",
    "inspeccion_zum":       "CCTV-LIMPIEZAS",
    "limpieza_aerea":       "LIMPIEZAS",
    "fresador":             "LIMPIEZAS",
    "robot_limpieza":       "LIMPIEZAS",
    "vaciado_fosa":         "LIMPIEZAS",
    "informe_desatasco":    "CCTV-LIMPIEZAS",
    "bajantes_amianto":     "CCTV-LIMPIEZAS",
    "certificado_obra":     "POCERIA",
    "plan_seguridad":       "PLAN SEGURIDAD",
    "contrato_saneamiento": "CONTRATOS",
    "fontaneria":           "FONTANERIA",
    "albanileria":          "ALBANILERIA",
    "contrato_subcontrata": "SUBCONTRATAS",
}

# ── Conexion lazy ──────────────────────────────────────────────────────────────

_gc = None  # gspread client


def _client():
    global _gc
    if _gc is not None:
        return _gc
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    # Primero: archivo local (uso en oficina)
    if CREDS_PATH.exists():
        creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=scopes)
    else:
        # Segundo: variable de entorno (uso en nube / Railway)
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
        if not creds_json:
            raise FileNotFoundError(
                f"Credenciales Google no encontradas en {CREDS_PATH} "
                "ni en la variable de entorno GOOGLE_CREDENTIALS_JSON."
            )
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)

    _gc = gspread.authorize(creds)
    return _gc


def _get_worksheet(tab_name: str):
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        return sh.worksheet(tab_name)
    except Exception:
        # Crear la pestaña si no existe
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=10)
        ws.append_row(
            ["Nº Presupuesto", "Fecha", "Cliente", "Obra / Servicio",
             "Importe sin IVA", "Tipo", "Carpeta"],
            value_input_option="USER_ENTERED",
        )
        return ws


# ── Numeracion ────────────────────────────────────────────────────────────────

def _año_corto() -> str:
    return datetime.now().strftime("%y")


def siguiente_numero(tipo: str, num_base: int | None = None) -> str:
    """
    Devuelve el siguiente numero de presupuesto para el tipo dado.

    Si num_base es None -> numero nuevo correlativo: '4353/26'
    Si num_base existe  -> busca si ya hay entradas con ese numero base
                          y añade sufijo revision: '4353A/26', '4353B/26'...

    Devuelve la cadena formateada lista para mostrar en el formulario.
    Si el tipo no tiene contador propio devuelve '' (el usuario introduce manual).
    Si no hay conexion con Sheets devuelve '' (el usuario introduce manual).
    """
    # Tipos sin contador propio: el usuario introduce el numero manualmente
    from utils.base_datos import TIPOS_SIN_CONTADOR
    if tipo in TIPOS_SIN_CONTADOR:
        return ""

    try:
        tab = TIPO_A_PESTAÑA.get(tipo, "VARIOS")
        ws = _get_worksheet(tab)
        year = _año_corto()

        col_a = ws.col_values(1)  # Nº Presupuesto
        # Filtrar solo entradas del año en curso
        pattern_year = re.compile(rf"^(\d+)([A-Z]*)/{re.escape(year)}$")
        numeros_año: list[tuple[int, str]] = []
        for cell in col_a[1:]:  # saltar cabecera
            m = pattern_year.match(str(cell).strip())
            if m:
                numeros_año.append((int(m.group(1)), m.group(2)))

        if num_base is None:
            # Siguiente correlativo
            maximo = max((n for n, _ in numeros_año), default=0)
            return f"{maximo + 1}/{year}"
        else:
            # Revision: buscar letras ya usadas para ese num_base
            letras_usadas = [suf for n, suf in numeros_año if n == num_base and suf]
            if not letras_usadas:
                # Primera revision
                return f"{num_base}A/{year}"
            ultimo = sorted(letras_usadas)[-1]
            siguiente_letra = chr(ord(ultimo[-1]) + 1)
            return f"{num_base}{siguiente_letra}/{year}"

    except FileNotFoundError:
        # Sin credenciales: usar base local como fallback
        return _siguiente_numero_local(tipo, num_base)
    except Exception as e:
        log.warning("Sheets.siguiente_numero error: %s - usando base local", e)
        return _siguiente_numero_local(tipo, num_base)


def _siguiente_numero_local(tipo: str, num_base: int | None = None) -> str:
    """Fallback: numeracion desde BASE_DATOS.xlsx cuando Sheets no esta disponible."""
    try:
        from utils.base_datos import siguiente_numero_local
        year = _año_corto()
        n = siguiente_numero_local(tipo)
        if n is None:
            return ""
        if num_base is None:
            return f"{n}/{year}"
        else:
            return f"{num_base}A/{year}"
    except Exception:
        return ""


def registrar(
    tipo: str,
    num_contrato: str,
    fecha: str,
    cliente: str,
    obra: str,
    importe: float,
    carpeta: str,
) -> bool:
    """
    Anota el presupuesto generado en la pestaña correspondiente.
    Devuelve True si se registro correctamente, False si fallo (no es critico).
    """
    try:
        tab = TIPO_A_PESTAÑA.get(tipo, "VARIOS")
        ws = _get_worksheet(tab)
        importe_str = f"{importe:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ws.append_row(
            [num_contrato, fecha, cliente, obra, importe_str, tipo, carpeta],
            value_input_option="USER_ENTERED",
        )
        log.info("Registrado en Sheets: %s - %s", tab, num_contrato)
        return True
    except FileNotFoundError:
        log.info("Sheets offline: presupuesto no registrado (sin credenciales)")
        return False
    except Exception as e:
        log.warning("Sheets.registrar error: %s", e)
        return False
