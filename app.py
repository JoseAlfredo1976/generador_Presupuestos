#!/usr/bin/env python3
"""
Interfaz web del Generador de Presupuestos + Analisis IA - Grupo Europa
Uso: python app.py  -> abre http://localhost:5000
"""
import json
import os
import sys
import tempfile
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template,
                   request, send_file, url_for)

from core.ai_analyst import extract_partidas_from_subcontrata, extract_solicitud_data
from core.docx_generator import DocxGenerator
from core.excel_generator import ExcelGenerator
from core.html_generator import HtmlGenerator
from core.pdf_converter import PdfConverter
from utils.tarifa_loader import TarifaLoader
from utils.sheets_registro import siguiente_numero, registrar as sheets_registrar
from utils.output_saver import guardar_en_red, estado_disco as disco_estado

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
TARIFAS_DIR = BASE_DIR / "tarifas"
# Salidas y uploads fuera de Google Drive para evitar WinError 2 con rutas largas/acentos
SALIDAS_DIR = Path(tempfile.gettempdir()) / "acometidas_salidas"
UPLOADS_DIR = Path(tempfile.gettempdir()) / "acometidas_uploads_ia"
TARIFAS_FILE = TARIFAS_DIR / "TARIFAS.xlsx"

SALIDAS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

TEMPLATE_FILES = {
    "obra_1":              "MODELO_MAESTRO_1OPCION.docx",
    "obra_2":              "MODELO_MAESTRO_2OPCIONES.docx",
    "desatasco":           "MODELO_DESATASCO.docx",
    "cctv_bajante":        "MODELO_CCTV_BAJANTE.docx",
    "inspeccion_zum":      "MODELO_INSPECCION_ZUM.docx",
    "limpieza_aerea":      "MODELO_LIMPIEZA_AEREA.docx",
    "fresador":            "MODELO_FRESADOR.docx",
    "robot_limpieza":      "MODELO_ROBOT_LIMPIEZA.docx",
    "fuga_agua":           "MODELO_FUGA_AGUA.docx",
    "vaciado_fosa":        "MODELO_VACIADO_FOSA.docx",
    # Nuevos modelos
    "informe_desatasco":   "MODELO_INFORME_DESATASCO.docx",
    "bajantes_amianto":    "MODELO_BAJANTES_AMIANTO.docx",
    "certificado_obra":    "MODELO_CERTIFICADO_OBRA.docx",
    "plan_seguridad":      "MODELO_PLAN_SEGURIDAD.docx",
    "contrato_saneamiento": "MODELO_CONTRATO_SANEAMIENTO.docx",
    # Nuevos oficios
    "fontaneria":           "MODELO_FONTANERIA.docx",
    "albanileria":          "MODELO_ALBANILERIA.docx",
    # Contrato subcontratacion
    "contrato_subcontrata": "MODELO_CONTRATO_SUBCONTRATA.docx",
}

ALLOWED_IA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v",
    ".doc", ".docx", ".txt", ".md",
}

app = Flask(__name__, template_folder="web_templates")
app.secret_key = "grupo-europa-presupuestos"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

_tarifas: TarifaLoader | None = None


def get_tarifas() -> TarifaLoader:
    global _tarifas
    if _tarifas is None:
        _tarifas = TarifaLoader(TARIFAS_FILE)
    return _tarifas


def _safe_filename(s: str, maxlen: int = 60) -> str:
    """Remove accents, keep only safe ASCII chars for Windows paths."""
    # Normalize to NFD and drop combining marks (removes accents)
    nfd = unicodedata.normalize("NFD", s)
    ascii_str = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Replace characters not allowed in Windows filenames
    safe = ""
    for c in ascii_str:
        if c.isalnum() or c in (" ", "-", "_", ".", "(", ")"):
            safe += c
        else:
            safe += "-"
    return safe[:maxlen].strip(". -")


def fmt_euro(amount: float) -> str:
    s = f"{amount:,.2f} €"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_euro_plain(amount: float) -> str:
    s = f"{amount:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def numero_a_letras(n: float) -> str:
    """Convierte un numero entero (parte entera de euros) a palabras en castellano."""
    n = int(round(n))
    if n == 0:
        return "CERO"
    if n < 0:
        return "MENOS " + numero_a_letras(-n)

    unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE",
                "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE",
                "QUINCE", "DIECISEIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE",
                "VEINTE", "VEINTIUN", "VEINTIDOS", "VEINTITRES", "VEINTICUATRO",
                "VEINTICINCO", "VEINTISEIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE"]
    decenas = ["", "DIEZ", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA",
               "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    centenas = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
                "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]

    def _menos_mil(n: int) -> str:
        if n == 0:
            return ""
        if n == 100:
            return "CIEN"
        if n < 30:
            return unidades[n]
        if n < 100:
            d, u = divmod(n, 10)
            return decenas[d] + (" Y " + unidades[u] if u else "")
        c, resto = divmod(n, 100)
        return centenas[c] + (" " + _menos_mil(resto) if resto else "")

    if n < 1000:
        return _menos_mil(n)
    if n < 2000:
        resto = n - 1000
        return "MIL" + (" " + _menos_mil(resto) if resto else "")
    if n < 1_000_000:
        miles, resto = divmod(n, 1000)
        return _menos_mil(miles) + " MIL" + (" " + _menos_mil(resto) if resto else "")
    if n < 2_000_000:
        resto = n - 1_000_000
        return "UN MILLON" + (" " + numero_a_letras(resto) if resto else "")
    millones, resto = divmod(n, 1_000_000)
    return _menos_mil(millones) + " MILLONES" + (" " + numero_a_letras(resto) if resto else "")


def _parse_fecha(fecha_raw: str):
    try:
        dt = datetime.strptime(fecha_raw, "%Y-%m-%d")
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        fecha_larga = f"{dt.day} de {meses[dt.month - 1]} de {dt.year}"
        fecha_display = dt.strftime("%d/%m/%Y")
    except ValueError:
        fecha_larga = fecha_raw
        fecha_display = fecha_raw
    return fecha_larga, fecha_display


def _fval(f, name: str, default: float = 0.0) -> float:
    try:
        return float(f.get(name, str(default)).replace(",", "."))
    except ValueError:
        return default


def _parse_items(f, prefix: str = "item") -> list[dict]:
    items = []
    idx = 0
    while True:
        desc = f.get(f"{prefix}_desc_{idx}", "").strip()
        if not desc:
            break
        qty = _fval(f, f"{prefix}_qty_{idx}", 1.0)
        price = _fval(f, f"{prefix}_price_{idx}", 0.0)
        unit = f.get(f"{prefix}_unit_{idx}", "PA").strip() or "PA"
        items.append({
            "descripcion": desc,
            "unidad": unit,
            "cantidad": qty,
            "precio_unitario": price,
            "importe": round(qty * price, 2),
        })
        idx += 1
    return items


def _svc_line(f, prefix: str) -> tuple[dict, float]:
    uds = _fval(f, f"{prefix.lower()}_uds", 1.0)
    precio = _fval(f, f"{prefix.lower()}_precio", 0.0)
    importe = round(uds * precio, 2)
    data = {
        f"[[{prefix}_UDS]]":     _fmt_qty_str(uds),
        f"[[{prefix}_PRECIO]]":  fmt_euro_plain(precio),
        f"[[{prefix}_IMPORTE]]": fmt_euro_plain(importe),
    }
    return data, importe


def _fmt_qty_str(qty: float) -> str:
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.2f}".replace(".", ",")


def _build_common_data(f) -> tuple[dict, str, str, str, str]:
    fecha_raw = f.get("fecha_contrato", datetime.now().strftime("%Y-%m-%d"))
    fecha_larga, fecha_display = _parse_fecha(fecha_raw)
    num_contrato = f.get("num_contrato", "").strip()
    obra = f.get("obra", "").strip()
    servicio = f.get("servicio", "").strip()
    current_year = str(datetime.now().year)
    data = {
        "[[CONTRATO_NUM]]":          num_contrato,
        "[[NUMERO_PRESUPUESTO]]":    num_contrato,
        "[[INFORME_NUM]]":           num_contrato,
        "[[FECHA_CONTRATO]]":        fecha_display,
        "[[FECHA_INFORME]]":         fecha_display,
        "[[FECHA_LARGA]]":           fecha_larga,
        "[[OBRA_COMUNIDAD]]":        obra,
        "[[NOMBRE_OBRA]]":           obra,
        "[[DIRECCION_OBRA]]":        obra,
        "[[SERVICIO_COMUNIDAD]]":    obra,   # siempre la direccion de ejecucion
        "[[TIPO_SERVICIO]]":         servicio,
        "[[CLIENTE_NOMBRE]]":        f.get("cliente_nombre", "").strip(),
        "[[CLIENTE_DIRECCION]]":     f.get("cliente_dir", "").strip(),
        "[[CLIENTE_TELEFONO]]":      f.get("cliente_tel", "").strip(),
        "[[CLIENTE_EMAIL]]":         f.get("cliente_email", "").strip(),
        "[[CLIENTE_CORREO ELECTRONICO]]": f.get("cliente_email", "").strip(),
        "[[CLIENTE_CORREOELECTRONICO]]":  f.get("cliente_email", "").strip(),
        "[[PROVINCIA]]":             f.get("provincia", "Madrid").strip(),
        "[[ADMINISTRACION]]":        f.get("administracion", "").strip() or "—",
        "[[ADMINISTRACION_TELEFONO]]":           f.get("admin_tel", "").strip(),
        "[[ADMINISTRACION_CORREO ELECTRONICO]]": f.get("admin_email", "").strip(),
        "[[ADMINISTRACION_CORREOELECTRONICO]]":  f.get("admin_email", "").strip(),
        # Correccion de años hardcodeados en plantillas antiguas
        "de 2024": f"de {current_year}",
        "de 2025": f"de {current_year}",
    }
    return data, num_contrato, fecha_larga, obra, servicio


def _build_obra_data(f, total_sin_iva: float, fecha_larga: str) -> dict:
    return {
        "[[INFORME_TECNICO]]":         f.get("informe", "").strip(),
        "[[SOLUCION_ADOPTAR]]":        f.get("solucion", "").strip(),
        "[[MEMORIA_TECNICA]]":         f.get("memoria", "").strip(),
        "[[TOTAL_PRESUPUESTO]]":       fmt_euro_plain(total_sin_iva),
        "[[RESUMEN_VALORACION]]":      fmt_euro_plain(total_sin_iva),
        "[[FORMA_PAGO]]":              f.get("forma_pago", "50% inicio, 50% finalizacion").strip(),
        "[[PLAZO_EJECUCION]]":         f.get("plazo", "30").strip(),
        "[[FECHA_INICIO_OBRA_LARGA]]": fecha_larga,
        "[[FECHA_FIN_OBRA]]":          f.get("fecha_fin_obra", "").strip(),
    }


def _build_obra_2_extra(f, total_a: float, total_b: float) -> dict:
    return {
        "[[TIPO_OPCION]]":            f.get("tipo_opcion", "").strip(),
        "[[MEMORIA_TRADICIONAL]]":    f.get("memoria_tradicional", "").strip(),
        "[[MEMORIA_MULTILINER]]":     f.get("memoria_multiliner", "").strip(),
        "[[IMPORTE_TOTAL_OPCION_A]]": fmt_euro_plain(total_a),
        "[[IMPORTE_TOTAL_OPCION_B]]": fmt_euro_plain(total_b),
        "[[FIRMANTE_NOMBRE]]":        f.get("firmante_nombre", "").strip(),
        "[[FIRMANTE_CARGO]]":         f.get("firmante_cargo", "").strip(),
        "[[FIRMANTE_DNI]]":           f.get("firmante_dni", "").strip(),
        "[[FIRMANTE_FECHA]]":         f.get("firmante_fecha", "").strip(),
    }


def _build_service_data(f, tipo: str, base_data: dict) -> tuple[dict, float]:
    data = dict(base_data)
    total = 0.0

    if tipo == "desatasco":
        for prefix in ["CAMION", "CAMION_DESP", "TAPA", "INODORO", "CATA"]:
            d, imp = _svc_line(f, prefix)
            data.update(d)
            total += imp

    elif tipo == "cctv_bajante":
        for prefix in ["CCTV", "CCTV_DESP", "TAPA", "INODORO", "CATA"]:
            d, imp = _svc_line(f, prefix)
            data.update(d)
            total += imp

    elif tipo == "inspeccion_zum":
        for prefix in ["CCTV", "CCTV_DESP"]:
            d, imp = _svc_line(f, prefix)
            data.update(d)
            total += imp

    elif tipo == "limpieza_aerea":
        for prefix in ["CAMION", "CAMION_DESP", "OCUPACION", "MEDIOS", "TAPA"]:
            d, imp = _svc_line(f, prefix)
            data.update(d)
            total += imp
        data["[[HORAS_ESTIMADAS]]"] = f.get("horas_estimadas", "").strip()
        data["[[TIEMPO_ESTIMADO]]"] = f.get("tiempo_estimado", "").strip()

    elif tipo == "fresador":
        for prefix in ["FRESADOR", "FRESADOR_DESP", "CAMION", "CAMION_DESP", "MEDIOS"]:
            d, imp = _svc_line(f, prefix)
            data.update(d)
            total += imp
        data["[[HORAS_ESTIMADAS]]"] = f.get("horas_estimadas", "").strip()

    elif tipo == "robot_limpieza":
        for prefix in ["CCTV", "CCTV_DESP", "CAMION", "CAMION_DESP",
                        "OCUPACION", "MEDIOS", "LOCALIZACION"]:
            d, imp = _svc_line(f, prefix)
            data.update(d)
            total += imp
        data["[[HORAS_ESTIMADAS]]"] = f.get("horas_estimadas", "").strip()
        data["[[TIEMPO_ESTIMADO]]"] = f.get("tiempo_estimado", "").strip()

    elif tipo == "fuga_agua":
        data["[[LOCALIZACION_SERVICIO]]"] = f.get("localizacion_servicio", "").strip()
        p1 = _fval(f, "precio_localizacion", 0.0)
        p2 = _fval(f, "precio_hora_adicional", 0.0)
        p3 = _fval(f, "precio_bombona", 0.0)
        data["[[PRECIO_LOCALIZACION_FUGA]]"] = fmt_euro_plain(p1)
        data["[[PRECIO_HORA_ADICIONAL]]"]    = fmt_euro_plain(p2)
        data["[[PRECIO_BOMBONA_GAS]]"]       = fmt_euro_plain(p3)
        total = p1

    elif tipo == "vaciado_fosa":
        data["[[VALIDEZ_OFERTA]]"] = f.get("validez_oferta", "30 dias").strip()
        for field in ["UD_DESPLAZAMIENTO", "UD_SUCCION", "UD_LIMPIEZA", "UD_DESCARGA", "UD_RESIDUO"]:
            data[f"[[{field}]]"] = f.get(field.lower(), "").strip()

    # --- Nuevos modelos ---

    elif tipo == "informe_desatasco":
        data["[[INFORME_TECNICO]]"] = f.get("informe_tecnico", "").strip()

    elif tipo == "bajantes_amianto":
        ba_lines = [
            "MOVILIZACION", "PLAN_TRABAJO_MCA", "MUESTREO_AMIANTO",
            "SUSTITUCION_BAJANTE", "SUSTITUCION_INJERTO",
            "APERTURA_CIERRE", "GESTION_RESIDUOS",
        ]
        for name in ba_lines:
            key = name.lower()
            ud = _fval(f, f"ba_{key}_ud", 0.0)
            precio = _fval(f, f"ba_{key}_precio", 0.0)
            importe = round(ud * precio, 2)
            data[f"[[UD_{name}]]"]     = _fmt_qty_str(ud)
            data[f"[[PRECIO_{name}]]"] = fmt_euro_plain(precio)
            data[f"[[IMPORTE_{name}]]"] = fmt_euro_plain(importe)
            total += importe
        data["[[PRECIO_MUESTREO_CONTROL]]"]      = fmt_euro_plain(_fval(f, "ba_muestreo_control_precio", 0.0))
        data["[[PRECIO_MUESTREO_FINALIZACION]]"] = fmt_euro_plain(_fval(f, "ba_muestreo_fin_precio", 0.0))
        data["[[VALIDEZ_OFERTA]]"]  = f.get("validez_oferta", "30 dias").strip()
        data["[[IMPORTE_TOTAL]]"]   = fmt_euro_plain(total)
        data["[[FORMA_PAGO]]"]      = f.get("forma_pago_ba", "50% al inicio de los trabajos, 50% a la finalizacion").strip()

    elif tipo == "certificado_obra":
        # CONTRATO_NUM, FECHA_LARGA, OBRA_COMUNIDAD already in base_data
        for field_key, placeholder in [
            ("fecha_inicio_obra", "[[FECHA_INICIO_LARGA]]"),
            ("fecha_fin_obra",    "[[FECHA_FINAL_LARGA]]"),
        ]:
            raw = f.get(field_key, "").strip()
            if raw:
                larga, _ = _parse_fecha(raw)
                data[placeholder] = larga
            else:
                data[placeholder] = ""

    elif tipo == "plan_seguridad":
        ps_fields = [
            "empresa_contratista", "cif_empresa", "direccion_empresa", "telefono_empresa",
            "autor_plan", "dni_autor_plan", "jefe_obra", "coordinador_seguridad",
            "recurso_preventivo", "acceso_obra", "descripcion_tecnica_obra",
            "promotor_nombre", "promotor_cif", "promotor_direccion", "promotor_telefono",
            "numero_max_trabajadores", "presupuesto_ejecucion_material",
            "centro_asistencial", "direccion_centro_medico", "telefono_centro_medico",
            "mes_plan", "plano_centro_medico", "tabla_presupuesto",
        ]
        for field in ps_fields:
            data[f"[[{field.upper()}]]"] = f.get(field, "").strip()
        data["[[PLAZO_EJECUCION]]"] = f.get("plazo", "30").strip()
        # Derivar AÑO_PLAN y FECHA_PLAN de fecha_contrato
        try:
            dt_plan = datetime.strptime(f.get("fecha_contrato", ""), "%Y-%m-%d")
            meses_ps = ["enero","febrero","marzo","abril","mayo","junio",
                        "julio","agosto","septiembre","octubre","noviembre","diciembre"]
            data["[[AÑO_PLAN]]"]  = str(dt_plan.year)
            data["[[FECHA_PLAN]]"] = f"{dt_plan.day} de {meses_ps[dt_plan.month-1]} de {dt_plan.year}"
        except ValueError:
            data["[[AÑO_PLAN]]"]  = str(datetime.now().year)
            data["[[FECHA_PLAN]]"] = ""

    elif tipo == "contrato_saneamiento":
        data["[[IMPORTE_ANUAL]]"] = fmt_euro_plain(_fval(f, "importe_anual", 0.0))
        total = _fval(f, "importe_anual", 0.0)

    data["[[IMPORTE_TOTAL_ESTIMADO]]"] = fmt_euro_plain(total)
    return data, total


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    today = datetime.now().strftime("%Y-%m-%d")
    missing = [name for name in TEMPLATE_FILES.values()
               if not (TEMPLATES_DIR / name).exists()]
    return render_template("index.html", today=today, missing_templates=missing)


@app.route("/analizar")
def analizar():
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    return render_template("analizar.html", api_key_set=api_key_set)


@app.route("/api/analizar", methods=["POST"])
def api_analizar():
    import traceback as _tb_mod
    _log = Path("C:/debug_analizar.log")

    def _write_log(msg: str):
        try:
            with open(_log, "a", encoding="utf-8") as _f:
                _f.write(msg + "\n")
        except Exception:
            pass

    _write_log("=== NUEVA PETICION /api/analizar ===")

    try:
        from core.ai_analyst import (analyze, generate_report_docx,
                                      analyze_wincam, generate_wincam_docx)
    except Exception as e:
        tb = _tb_mod.format_exc()
        _write_log("ERROR IMPORTANDO ai_analyst:\n" + tb)
        return jsonify({"error": str(e), "traceback": tb}), 500

    try:
        tipo = request.form.get("tipo_analisis", "general")
        formato = request.form.get("formato", "descriptivo")  # descriptivo | wincam | ambos
        context = request.form.get("contexto", "")
        api_key = request.form.get("api_key", "").strip()
        num_ref = request.form.get("num_ref", "").strip()
        cliente = request.form.get("cliente", "").strip()
        proyecto = request.form.get("proyecto", num_ref).strip()
        calle = request.form.get("calle", "").strip()
        poblacion = request.form.get("poblacion", "").strip()

        _write_log(f"tipo={tipo} formato={formato} api_key={'SET' if api_key else 'ENV'}")

        # Save uploaded files
        session_id = uuid.uuid4().hex[:8]
        session_dir = UPLOADS_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        _write_log(f"session_dir={session_dir}")

        saved_files: list[Path] = []
        for uploaded in request.files.getlist("archivos"):
            if not uploaded.filename:
                continue
            suffix = Path(uploaded.filename).suffix.lower()
            if suffix not in ALLOWED_IA_EXTENSIONS:
                _write_log(f"Extension no permitida: {suffix}")
                continue
            dest = session_dir / f"{uuid.uuid4().hex[:6]}{suffix}"
            _write_log(f"Guardando {uploaded.filename} -> {dest}")
            uploaded.save(str(dest))
            if dest.exists():
                saved_files.append(dest)
                _write_log(f"OK: {dest.stat().st_size} bytes")
            else:
                _write_log(f"WARN: no existe tras save: {dest}")

        # Croquis (optional - single file: image or PDF)
        croquis_path = None
        croquis_file = request.files.get("croquis")
        if croquis_file and croquis_file.filename:
            suf_c = Path(croquis_file.filename).suffix.lower()
            if suf_c in ALLOWED_IA_EXTENSIONS:
                dest_c = session_dir / f"croquis{suf_c}"
                croquis_file.save(str(dest_c))
                if dest_c.exists():
                    croquis_path = dest_c
                    _write_log(f"Croquis guardado: {dest_c} ({dest_c.stat().st_size} bytes)")

        _write_log(f"saved_files={len(saved_files)} croquis={'si' if croquis_path else 'no'}")
        if not saved_files:
            return jsonify({"error": "No se recibieron archivos validos o no se pudieron guardar."}), 400

        result = {"_formato": formato}

        # Formato descriptivo (o ambos)
        if formato in ("descriptivo", "ambos"):
            _write_log("Llamando a analyze() descriptivo...")
            report = analyze(saved_files, tipo, context, api_key, croquis_path=croquis_path)
            _write_log("analyze() OK")
            result.update(report)
            docx_name = f"Informe_IA_{session_id}.docx"
            docx_path = SALIDAS_DIR / docx_name
            try:
                generate_report_docx(report, docx_path, num_ref=num_ref, cliente=cliente)
                result["_docx"] = docx_name
            except Exception as e:
                result["_docx_error"] = str(e)
                _write_log(f"DOCX descriptivo error: {e}")
            try:
                pdf_path = PdfConverter().convert(docx_path, SALIDAS_DIR)
                if pdf_path:
                    result["_pdf"] = pdf_path.name
            except Exception:
                pass

        # Formato WinCam (o ambos)
        if formato in ("wincam", "ambos"):
            _write_log("Llamando a analyze_wincam()...")
            wc_report = analyze_wincam(saved_files, context, api_key,
                                       proyecto=proyecto or num_ref,
                                       calle=calle, poblacion=poblacion,
                                       croquis_path=croquis_path)
            _write_log("analyze_wincam() OK")
            result["_wincam"] = wc_report
            wc_name = f"Informe_WinCam_{session_id}.docx"
            wc_path = SALIDAS_DIR / wc_name
            try:
                generate_wincam_docx(wc_report, wc_path, num_ref=num_ref, cliente=cliente)
                result["_docx_wincam"] = wc_name
            except Exception as e:
                result["_wincam_docx_error"] = str(e)
                _write_log(f"DOCX WinCam error: {e}")

        return jsonify(result)

    except Exception as e:
        tb = _tb_mod.format_exc()
        _write_log("=== EXCEPCION ===\n" + tb)
        return jsonify({"error": f"{str(e)}\n\n--- TRACEBACK ---\n{tb}", "traceback": tb}), 500


@app.route("/api/generar_partidas_ia", methods=["POST"])
def api_generar_partidas_ia():
    """Generate budget items + technical texts using Claude, then enrich with tarifas prices."""
    import traceback as _tb
    try:
        from core.ai_analyst import generate_partidas_ia
        # Aceptar tanto JSON como FormData (cuando hay archivos adjuntos)
        ct = request.content_type or ""
        if "multipart/form-data" in ct:
            descripcion = request.form.get("descripcion", "").strip()
            tipo        = request.form.get("tipo", "obra_1")
            api_key     = request.form.get("api_key", "").strip()
            informe_raw = request.form.get("informe", "")
            try:
                informe = json.loads(informe_raw) if informe_raw else None
            except Exception:
                informe = None
            # Guardar archivos subidos temporalmente
            _ia_tmp = Path(tempfile.mkdtemp(prefix="ia_gen_"))
            saved_files: list[Path] = []
            for fobj in request.files.getlist("archivos_ia"):
                suf = Path(fobj.filename or "").suffix.lower()
                if suf in {".pdf", ".docx", ".doc", ".txt", ".md"}:
                    dest = _ia_tmp / (uuid.uuid4().hex[:6] + suf)
                    fobj.save(dest)
                    saved_files.append(dest)
        else:
            data = request.get_json(force=True)
            descripcion = data.get("descripcion", "").strip()
            tipo        = data.get("tipo", "obra_1")
            api_key     = data.get("api_key", "").strip()
            informe     = data.get("informe") or None  # existing IA report or null
            saved_files = []
            _ia_tmp = None

        tarifas = get_tarifas()
        result = generate_partidas_ia(
            descripcion, tipo, api_key, informe,
            tarifas_items=tarifas.all_items(),
            files=saved_files or None,
        )

        if "_error" in result:
            return jsonify({"error": result["_error"], "raw": result.get("_raw", "")}), 500

        # Enrich partidas: lookup by exact code, fallback fuzzy by nota/codigo text
        def _enrich(partidas: list) -> list:
            enriched = []
            for p in (partidas or []):
                codigo = p.get("codigo", "").strip()
                found = tarifas.lookup(codigo) if codigo else None
                if not found:
                    # Fallback: fuzzy search on the code string itself
                    found = tarifas.search(codigo)
                enriched.append({
                    "codigo":          found["codigo"]      if found else codigo,
                    "descripcion":     found["descripcion"] if found else codigo,
                    "unidad":          found["unidad"]      if found else "ud",
                    "cantidad":        float(p.get("cantidad", 1)),
                    "precio_unitario": found["precio"]      if found else 0.0,
                    "tarifa_encontrada": bool(found),
                    "nota":            p.get("nota", ""),
                })
            return enriched

        if tipo == "obra_2":
            result["partidas_a"] = _enrich(result.get("partidas_a", []))
            result["partidas_b"] = _enrich(result.get("partidas_b", []))
        else:
            result["partidas"] = _enrich(result.get("partidas", []))

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e), "traceback": _tb.format_exc()}), 500
    finally:
        if '_ia_tmp' in dir() and _ia_tmp and _ia_tmp.exists():
            import shutil as _sh
            _sh.rmtree(_ia_tmp, ignore_errors=True)


@app.route("/api/chat_informe", methods=["POST"])
def api_chat_informe():
    """Chat con el perito IA para modificar o ampliar un informe generado."""
    import traceback as _tb
    try:
        from core.ai_analyst import SYSTEM_PROMPT, REPORT_SCHEMA, generate_report_docx
        data = request.get_json(force=True)
        report_actual = data.get("report", {})
        historial = data.get("historial", [])  # [{role, content}]
        mensaje = data.get("mensaje", "").strip()
        api_key = data.get("api_key", "").strip()
        num_ref = data.get("num_ref", "")
        cliente = data.get("cliente", "")

        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return jsonify({"error": "API Key no configurada."}), 400

        import anthropic as _ant
        client = _ant.Anthropic(api_key=key)

        # Construir historial de conversacion
        messages = []
        for h in historial:
            messages.append({"role": h["role"], "content": h["content"]})

        # Mensaje actual del usuario
        user_content = (
            f"INFORME ACTUAL EN JSON:\n{json.dumps(report_actual, ensure_ascii=False, indent=2)}\n\n"
            f"INSTRUCCION DEL TECNICO:\n{mensaje}\n\n"
            f"Aplica la modificacion solicitada y devuelve el informe completo actualizado "
            f"en el mismo formato JSON. Si la instruccion es una pregunta tecnica, "
            f"responde como texto en el campo 'respuesta_chat' y mantén el informe sin cambios. "
            f"Responde UNICAMENTE con JSON segun el esquema:\n{REPORT_SCHEMA}"
        )
        messages.append({"role": "user", "content": user_content})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        raw = response.content[0].text.strip()

        import re
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                updated = json.loads(match.group())
                # Regenerar DOCX con el informe actualizado
                session_id = uuid.uuid4().hex[:8]
                docx_name = f"Informe_IA_{session_id}.docx"
                docx_path = SALIDAS_DIR / docx_name
                try:
                    generate_report_docx(updated, docx_path, num_ref=num_ref, cliente=cliente)
                    updated["_docx"] = docx_name
                except Exception:
                    pass
                updated["_assistant_msg"] = updated.get("respuesta_chat", "Informe actualizado.")
                return jsonify({"report": updated, "raw": raw})
            except json.JSONDecodeError:
                pass

        # Si no hay JSON valido, es una respuesta conversacional
        return jsonify({"report": report_actual, "raw": raw, "assistant_msg": raw})

    except Exception as e:
        tb = _tb.format_exc()
        return jsonify({"error": str(e), "traceback": tb}), 500


@app.route("/api/importar_informe", methods=["POST"])
def api_importar_informe():
    """Importa un informe existente (DOCX/PDF/TXT) y lo convierte al schema JSON para edicion via chat."""
    import traceback as _tb
    import base64
    import re
    tmp_dir = None
    try:
        from core.ai_analyst import SYSTEM_PROMPT, REPORT_SCHEMA
        import anthropic as _ant

        archivo = request.files.get("archivo")
        api_key = request.form.get("api_key", "").strip()

        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return jsonify({"error": "API Key no configurada."}), 400
        if not archivo or not archivo.filename:
            return jsonify({"error": "No se recibio ningun archivo."}), 400

        suffix = Path(archivo.filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".doc", ".txt", ".md"}:
            return jsonify({"error": "Formato no soportado. Usa PDF, DOCX o TXT."}), 400

        tmp_dir = Path(tempfile.mkdtemp(prefix="importar_"))
        dest = tmp_dir / f"informe{suffix}"
        archivo.save(str(dest))

        client = _ant.Anthropic(api_key=key)
        instruccion = (
            "Extrae toda la informacion de este informe tecnico y estructurala en el siguiente "
            "esquema JSON. Si algun campo no aparece en el documento usa null o [] segun el tipo. "
            "Devuelve UNICAMENTE el JSON sin ningun texto adicional.\n\n"
            f"Esquema requerido:\n{REPORT_SCHEMA}"
        )

        if suffix == ".pdf":
            pdf_data = dest.read_bytes()
            messages = [{
                "role": "user",
                "content": [
                    {"type": "document", "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(pdf_data).decode(),
                    }},
                    {"type": "text", "text": instruccion},
                ],
            }]
        else:
            if suffix in (".docx", ".doc"):
                try:
                    from docx import Document as _DocxDoc
                    doc = _DocxDoc(str(dest))
                    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                except Exception:
                    text = dest.read_text(encoding="utf-8", errors="replace")
            else:
                text = dest.read_text(encoding="utf-8", errors="replace")
            messages = [{"role": "user", "content": f"INFORME:\n{text}\n\n{instruccion}"}]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                report = json.loads(match.group())
                return jsonify(report)
            except json.JSONDecodeError:
                pass
        return jsonify({"error": "No se pudo extraer JSON del informe.", "_raw": raw[:2000]}), 500

    except Exception as e:
        return jsonify({"error": str(e), "traceback": _tb.format_exc()}), 500
    finally:
        if tmp_dir and tmp_dir.exists():
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route("/api/tarifa/<code>")
def api_tarifa(code: str):
    item = get_tarifas().lookup(code)
    if not item:
        return jsonify({}), 404
    return jsonify(item)


@app.route("/api/siguiente_numero")
def api_siguiente_numero():
    """Devuelve el siguiente numero de presupuesto para un tipo dado.
    Parametros GET: tipo, num_base (opcional, para revision)
    Responde: {numero, sin_contador} donde sin_contador=True indica que el usuario
    debe introducir el mismo numero que el presupuesto asociado.
    """
    from utils.base_datos import TIPOS_SIN_CONTADOR
    tipo = request.args.get("tipo", "")
    num_base_str = request.args.get("num_base", "")
    num_base = int(num_base_str) if num_base_str.isdigit() else None
    sin_contador = tipo in TIPOS_SIN_CONTADOR
    try:
        numero = siguiente_numero(tipo, num_base)
    except Exception as e:
        return jsonify({"numero": "", "sin_contador": sin_contador, "error": str(e)})
    return jsonify({"numero": numero, "sin_contador": sin_contador})


@app.route("/api/clientes")
def api_clientes():
    """Autocomplete de clientes. Param GET: q (texto a buscar)"""
    from utils.base_datos import buscar_clientes
    q = request.args.get("q", "").strip()
    return jsonify(buscar_clientes(q, limit=15))


@app.route("/api/tarifas")
def api_tarifas_list():
    return jsonify(get_tarifas().all_codes())


@app.route("/api/tarifas_full")
def api_tarifas_full():
    return jsonify(get_tarifas().all_items())


@app.route("/api/analizar_solicitud", methods=["POST"])
def api_analizar_solicitud():
    """Extract budget form data from uploaded documents using AI."""
    files_in = request.files.getlist("archivos")
    if not files_in:
        return jsonify({"error": "No se recibieron archivos."}), 400

    api_key = request.form.get("api_key", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "API Key de Anthropic no configurada."}), 400

    ALLOWED = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".pdf", ".txt", ".eml", ".msg", ".html", ".htm",
    }
    tmp_dir = Path(tempfile.mkdtemp(prefix="solicitud_"))
    saved: list[Path] = []
    for fobj in files_in:
        suf = Path(fobj.filename or "").suffix.lower()
        if suf not in ALLOWED:
            continue
        dest = tmp_dir / f"{uuid.uuid4().hex}{suf}"
        fobj.save(dest)
        saved.append(dest)

    if not saved:
        return jsonify({"error": "Ningun archivo tiene formato valido (jpg, png, pdf, txt, eml)."}), 400

    try:
        result = extract_solicitud_data(saved, api_key=api_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route("/api/importar_subcontrata", methods=["POST"])
def api_importar_subcontrata():
    """Extract all partidas from a subcontractor budget document using AI."""
    files_in = request.files.getlist("archivos")
    if not files_in:
        return jsonify({"error": "No se recibieron archivos."}), 400

    api_key = request.form.get("api_key", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "API Key de Anthropic no configurada."}), 400

    ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".txt", ".html", ".htm", ".csv"}
    tmp_dir = Path(tempfile.mkdtemp(prefix="subcontrata_"))
    saved: list[Path] = []
    for fobj in files_in:
        suf = Path(fobj.filename or "").suffix.lower()
        if suf not in ALLOWED:
            continue
        dest = tmp_dir / f"{uuid.uuid4().hex}{suf}"
        fobj.save(dest)
        saved.append(dest)

    if not saved:
        return jsonify({"error": "Formato no valido. Sube PDF, imagen o texto."}), 400

    try:
        result = extract_partidas_from_subcontrata(saved, api_key=api_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route("/generar", methods=["POST"])
def generar():
    f = request.form
    tipo = f.get("tipo_modelo", "obra_1")

    common_data, num_contrato, fecha_larga, obra, servicio = _build_common_data(f)

    items = items_a = items_b = subc_items = None
    total_sin_iva = total_a = total_b = total_estimado = 0.0

    if tipo == "contrato_subcontrata":
        subc_items = _parse_items(f, "item")
        total_sin_iva = sum(i["importe"] for i in (subc_items or []))
        # Fechas contrato
        fecha_contrato_raw = f.get("fecha_contrato", datetime.now().strftime("%Y-%m-%d"))
        meses_esp = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                     "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        try:
            dt = datetime.strptime(fecha_contrato_raw, "%Y-%m-%d")
            dia_semana = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"][dt.weekday()]
            fecha_contrato_larga = f"{dia_semana}, {dt.day} de {meses_esp[dt.month-1]} de {dt.year}"
            fecha_aceptacion = f"{dt.day} de {meses_esp[dt.month-1]} de {dt.year}"
        except ValueError:
            fecha_contrato_larga = fecha_contrato_raw
            fecha_aceptacion = fecha_contrato_raw
        # Fecha inicio trabajos
        fecha_inicio_raw = f.get("fecha_inicio_trabajos", "")
        if fecha_inicio_raw:
            try:
                dt2 = datetime.strptime(fecha_inicio_raw, "%Y-%m-%d")
                fecha_inicio_str = f"{dt2.day} de {meses_esp[dt2.month-1].upper()} de {dt2.year}"
            except ValueError:
                fecha_inicio_str = fecha_inicio_raw
        else:
            fecha_inicio_str = ""
        # Importe en letra
        letra = numero_a_letras(total_sin_iva) + " EUROS"
        # Build data dict
        data = {
            **common_data,
            "[[FECHA_CONTRATO]]":          fecha_contrato_larga,
            "[[FECHA_ACEPTACION]]":        fecha_aceptacion,
            "[[PRESUPUESTO_NUM]]":         f.get("num_contrato", "").strip(),
            "[[OBRA_DIRECCION]]":          obra,
            "[[IMPORTE_TOTAL]]":           fmt_euro_plain(total_sin_iva),
            "[[IMPORTE_LETRA]]":           letra,
            "[[FORMA_PAGO]]":              f.get("forma_pago", "100% a la finalizacion de los trabajos mediante pagare a 90 dias").strip(),
            "[[PLAZO_EJECUCION]]":         f.get("plazo", "30").strip(),
            "[[FECHA_INICIO_TRABAJOS]]":   fecha_inicio_str,
            # Subcontratista
            "[[SUBC_EMPRESA]]":            f.get("subc_empresa", "").strip(),
            "[[SUBC_CIF]]":               f.get("subc_cif", "").strip(),
            "[[SUBC_DOMICILIO]]":          f.get("subc_domicilio", "").strip(),
            "[[SUBC_REP_NOMBRE]]":         f.get("subc_rep_nombre", "").strip(),
            "[[SUBC_REP_DNI]]":           f.get("subc_rep_dni", "").strip(),
            "[[SUBC_REP_DOMICILIO]]":      f.get("subc_rep_domicilio", "").strip(),
            "[[SUBC_NOTARIO]]":           f.get("subc_notario", "").strip(),
            "[[SUBC_NOTARIO_LOC]]":        f.get("subc_notario_loc", "").strip(),
            "[[SUBC_FECHA_ESCRITURA]]":    f.get("subc_fecha_escritura", "").strip(),
            "[[SUBC_PROTOCOLO]]":         f.get("subc_protocolo", "").strip(),
            "[[SUBC_REGISTRO]]":          f.get("subc_registro", "").strip(),
            "[[SUBC_TELEFONO]]":          f.get("subc_telefono", "").strip(),
            "[[SUBC_EMAIL]]":             f.get("subc_email", "").strip(),
        }

    elif tipo in ("obra_1", "fontaneria", "albanileria"):
        items = _parse_items(f, "item")
        if not items:
            return redirect(url_for("index"))
        total_sin_iva = sum(i["importe"] for i in items)
        data = {**common_data, **_build_obra_data(f, total_sin_iva, fecha_larga)}

    elif tipo == "obra_2":
        items_a = _parse_items(f, "item_a")
        items_b = _parse_items(f, "item_b")
        if not items_a and not items_b:
            return redirect(url_for("index"))
        total_a = sum(i["importe"] for i in (items_a or []))
        total_b = sum(i["importe"] for i in (items_b or []))
        total_sin_iva = max(total_a, total_b)
        data = {
            **common_data,
            **_build_obra_data(f, total_sin_iva, fecha_larga),
            **_build_obra_2_extra(f, total_a, total_b),
        }

    else:
        data, total_estimado = _build_service_data(f, tipo, common_data)
        # Partidas adicionales opcionales en modelos de servicio
        extra_items = _parse_items(f, "item")
        if extra_items:
            items = extra_items
            extra_total = sum(i["importe"] for i in extra_items)
            total_estimado += extra_total
            data["[[TOTAL_PARTIDAS_ADICIONALES]]"] = fmt_euro_plain(extra_total)

    # File naming - sanitized to avoid Windows path length / accent issues
    num_safe = _safe_filename(num_contrato.replace("/", "-"), maxlen=20)
    label = _safe_filename((servicio or obra).upper(), maxlen=40)
    stem = f"{num_safe}- {label} - PRESUPUESTO"
    folder_name = stem
    output_dir = SALIDAS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = {}
    errors = []

    # DOCX
    template_file = TEMPLATES_DIR / TEMPLATE_FILES.get(tipo, "MODELO_MAESTRO_1OPCION.docx")
    if template_file.exists():
        try:
            docx_path = output_dir / f"{stem}.docx"
            DocxGenerator(template_file).generate(
                docx_path, data,
                items=items, items_a=items_a, items_b=items_b,
                subc_items=subc_items,
            )
            generated["docx"] = docx_path.relative_to(SALIDAS_DIR).as_posix()
        except Exception as e:
            errors.append(f"DOCX: {e}")
    else:
        errors.append(f"Plantilla no encontrada: {template_file.name}")

    # Excel + HTML for obra types and new trades
    if tipo in ("obra_1", "obra_2", "fontaneria", "albanileria"):
        items_for_excel = items or items_a or []
        try:
            xlsx_path = output_dir / f"{stem}.xlsx"
            ExcelGenerator().generate(xlsx_path, data, items_for_excel)
            generated["xlsx"] = xlsx_path.relative_to(SALIDAS_DIR).as_posix()
        except Exception as e:
            errors.append(f"Excel: {e}")

        try:
            html_path = output_dir / f"{stem}_Visor.html"
            HtmlGenerator().generate(html_path, data, items_for_excel)
            generated["html"] = html_path.relative_to(SALIDAS_DIR).as_posix()
        except Exception as e:
            errors.append(f"HTML: {e}")

    # PDF
    try:
        docx_for_pdf = SALIDAS_DIR / generated["docx"] if "docx" in generated else None
        html_for_pdf = SALIDAS_DIR / generated["html"] if "html" in generated else None
        pdf_path = PdfConverter().convert(
            docx_for_pdf or output_dir / f"{stem}.docx",
            output_dir,
            html_fallback_path=html_for_pdf,
        )
        if pdf_path:
            generated["pdf"] = pdf_path.relative_to(SALIDAS_DIR).as_posix()
    except Exception as e:
        errors.append(f"PDF: {e}")

    # ── Guardar en disco externo y registrar en Sheets (background, no bloquea) ─
    import threading
    archivos_generados = [
        SALIDAS_DIR / v for v in generated.values()
        if isinstance(v, str) and (SALIDAS_DIR / v).exists()
    ]
    _registro_kwargs = dict(
        tipo=tipo, num_contrato=num_contrato,
        fecha=datetime.now().strftime("%d/%m/%Y"),
        cliente=data.get("[[CLIENTE_NOMBRE]]", ""),
        obra=obra or servicio, importe=total_sin_iva,
        carpeta=folder_name,
    )

    def _background_save():
        try:
            carpeta_red = guardar_en_red(tipo, num_contrato, obra or servicio, archivos_generados)
            if carpeta_red:
                _registro_kwargs["carpeta"] = carpeta_red.name
            sheets_registrar(**_registro_kwargs)
        except Exception as ex:
            import logging
            logging.getLogger(__name__).warning("Background save error: %s", ex)

    threading.Thread(target=_background_save, daemon=True).start()

    return render_template(
        "resultado.html",
        tipo_modelo=tipo,
        num_contrato=num_contrato,
        obra=obra,
        servicio=servicio,
        cliente=data.get("[[CLIENTE_NOMBRE]]", ""),
        fecha=fecha_larga,
        items=items or [],
        items_a=items_a or [],
        items_b=items_b or [],
        total_sin_iva=fmt_euro(total_sin_iva),
        total_con_iva=fmt_euro(total_sin_iva * 1.21),
        total_a=fmt_euro(total_a),
        total_b=fmt_euro(total_b),
        total_estimado=fmt_euro(total_estimado),
        generated=generated,
        errors=errors,
        folder_name=folder_name,
    )


@app.route("/api/estado_disco")
def api_estado_disco():
    return jsonify(disco_estado())


@app.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    from utils.app_config import load as cfg_load, save as cfg_save
    from utils.output_saver import estado_disco

    msg = ""
    if request.method == "POST":
        cfg = cfg_load()
        cfg["output_base_path"] = request.form.get("output_base_path", "").strip()
        cfg["output_subfolder"] = request.form.get("output_subfolder", "").strip()
        cfg_save(cfg)
        msg = "Configuracion guardada."

    cfg = cfg_load()
    disco = estado_disco()
    return render_template("configuracion.html", cfg=cfg, disco=disco, msg=msg)


@app.route("/descargar/<path:rel_path>")
def descargar(rel_path: str):
    full = SALIDAS_DIR / rel_path
    if not full.exists() or not full.is_file():
        abort(404)
    try:
        full.resolve().relative_to(SALIDAS_DIR.resolve())
    except ValueError:
        abort(403)
    return send_file(full, as_attachment=True, download_name=full.name)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser, threading, time

    def open_browser():
        time.sleep(1.2)
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=open_browser, daemon=True).start()
    print("\n  Generador de Presupuestos + Analisis IA - Grupo Europa")
    print("  Abriendo en el navegador: http://localhost:5000")
    print("  (Para parar: pulsa Ctrl+C)\n")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
