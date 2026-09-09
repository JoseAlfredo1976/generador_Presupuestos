"""
Auditoria diaria: compara la numeracion real de la carpeta de red
\\Srveuropa\grupo_europa\GRUPO EUROPA\PRODUCCION\PRESUPUESTOS
contra el Google Sheet de numeracion, y deja el resultado en la
pestana AUDITORIA_RESUMEN para que el workflow n8n solo tenga que
leerla y avisar si hay ALERTA = SI.

Pensado para ejecutarse a diario via Tarea Programada de Windows,
en una maquina con acceso a la carpeta de red \\Srveuropa\...

Uso:
    py -3.12 scripts\auditar_numeracion.py
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

RUTA_PRESUPUESTOS = Path(r"\\Srveuropa\grupo_europa\GRUPO EUROPA\PRODUCCION\PRESUPUESTOS")

# Nombre de la subcarpeta real en disco para cada pestana del Sheet de numeracion.
# Verificado el 2026-09-08 listando \\Srveuropa\...\PRESUPUESTOS. SUBCONTRATAS y VARIOS
# no tienen carpeta fisica propia -> se marcan None y se excluyen del escaneo.
CATEGORIAS = {
    "POCERIA": "POCERIA",
    "CCTV-LIMPIEZAS": "INFORMES CCTV-LIMPIEZAS",
    "LIMPIEZAS": "LIMPIEZAS",
    "PLAN SEGURIDAD": "PLAN DE SEGURIDAD Y SALUD",
    "CONTRATOS": "CONTRATOS DE MANTENIMIENTO",
    "FONTANERIA": "FONTANERIA",
    "ALBANILERIA": "ALBAÑILERIA Y OTROS TRABAJOS",
    "SUBCONTRATAS": None,
    "VARIOS": None,
}

RE_NUMERO_INICIAL = re.compile(r"^(\d+)([A-Z]?)")
RE_NUMERO_ANIO = re.compile(r"^(\d+)[A-Z]*/(\d{2})$")

SHEET_ID = "1CzmpibqBUsvc0ZK4IlRheNto23kJkMLgBw3akT5pmQg"
TAB_RESUMEN = "AUDITORIA_RESUMEN"


def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = Path(__file__).parent.parent / "config" / "google_credentials.json"
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    if not creds_path.exists():
        raise FileNotFoundError(f"Credenciales Google no encontradas en {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
    return gspread.authorize(creds)


def escanear_carpeta(carpeta: Path, anio_actual: int) -> tuple[int | None, dict[int, list[str]]]:
    """Escanea subcarpetas de primer nivel y devuelve (numero_maximo, duplicados),
    restringido a carpetas CREADAS este anio (la numeracion se reinicia cada anio,
    asi que el mismo numero en anios distintos es normal, no un duplicado)."""
    if not carpeta.exists():
        log.warning("Carpeta no encontrada: %s", carpeta)
        return None, {}

    # Clave (numero, letra) para no confundir revisiones (4685A, 4685B) con duplicados reales.
    entradas: dict[tuple[int, str], list[str]] = {}
    for item in carpeta.iterdir():
        if not item.is_dir():
            continue
        m = RE_NUMERO_INICIAL.match(item.name)
        if not m:
            continue
        try:
            anio_creacion = datetime.fromtimestamp(item.stat().st_ctime).year
        except OSError:
            continue
        if anio_creacion != anio_actual:
            continue
        n = int(m.group(1))
        letra = m.group(2)
        entradas.setdefault((n, letra), []).append(item.name)

    if not entradas:
        return None, {}
    duplicados = {clave: nombres for clave, nombres in entradas.items() if len(nombres) > 1}
    max_numero = max(n for (n, _letra) in entradas.keys())
    return max_numero, duplicados


def max_numero_sheet(ws, anio_corto: str) -> int | None:
    col_a = ws.col_values(1)
    maximos = []
    for valor in col_a:
        m = RE_NUMERO_ANIO.match(valor.strip())
        if m and m.group(2) == anio_corto:
            maximos.append(int(m.group(1)))
    if not maximos:
        return None
    return max(maximos)


def main() -> None:
    gc = _client()
    sh = gc.open_by_key(SHEET_ID)
    anio_corto = datetime.now().strftime("%y")
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    filas = [["FECHA", "CATEGORIA", "MAX_CARPETA_RED", "MAX_SHEET", "DIFERENCIA",
              "DUPLICADOS_DETECTADOS", "DETALLE_DUPLICADOS", "ALERTA"]]

    anio_actual = datetime.now().year

    for pestana, subcarpeta in CATEGORIAS.items():
        try:
            ws = sh.worksheet(pestana)
            max_sheet = max_numero_sheet(ws, anio_corto)
        except Exception as e:
            log.warning("No se pudo leer pestana %s: %s", pestana, e)
            max_sheet = None

        if subcarpeta is None:
            filas.append([fecha, pestana, "SIN CARPETA", max_sheet if max_sheet is not None else "N/D",
                          "N/D", 0, "", "NO"])
            log.info("%s: sin carpeta fisica asociada, se omite comparacion", pestana)
            continue

        carpeta = RUTA_PRESUPUESTOS / subcarpeta
        max_red, duplicados = escanear_carpeta(carpeta, anio_actual)
        detalle_dup = "; ".join(f"{n}{letra}: {', '.join(v)}" for (n, letra), v in duplicados.items())

        if max_red is None or max_sheet is None:
            diferencia = "N/D"
            alerta = "SI" if (max_red is None) != (max_sheet is None) else "N/D"
        else:
            diferencia = max_red - max_sheet
            alerta = "SI" if (diferencia != 0 or duplicados) else "NO"

        if duplicados and alerta != "SI":
            alerta = "SI"

        filas.append([
            fecha, pestana,
            max_red if max_red is not None else "N/D",
            max_sheet if max_sheet is not None else "N/D",
            diferencia,
            len(duplicados),
            detalle_dup,
            alerta,
        ])
        log.info("%s: carpeta=%s sheet=%s dif=%s dup=%s",
                  pestana, max_red, max_sheet, diferencia, len(duplicados))

    try:
        ws_resumen = sh.worksheet(TAB_RESUMEN)
        ws_resumen.clear()
    except Exception:
        ws_resumen = sh.add_worksheet(title=TAB_RESUMEN, rows=len(filas) + 10, cols=len(filas[0]))

    ws_resumen.update(filas, value_input_option="USER_ENTERED")
    log.info("Auditoria escrita en pestana %s (%d filas)", TAB_RESUMEN, len(filas) - 1)


if __name__ == "__main__":
    main()
