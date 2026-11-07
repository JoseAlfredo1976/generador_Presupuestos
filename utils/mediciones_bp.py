"""
utils/mediciones_bp.py - Rutas de "Croquis · Red de saneamiento".

Pantalla:  GET  /croquis/red
API:       GET  /api/red/obras                      lista de obras guardadas
           POST /api/red/nueva                      crea obra (nombre, ref, plano PDF/imagen)
           GET  /api/red/obra/<id>                  obra.json
           POST /api/red/obra/<id>                  guarda obra.json (JSON en el cuerpo)
           GET  /api/red/obra/<id>/plano            imagen del plano
           GET  /api/red/obra/<id>/resumen          totales por DN, arquetas y pozos
           GET  /api/red/obra/<id>/partidas         partidas valoradas con TARIFAS.xlsx
           GET  /api/red/obra/<id>/excel            Excel de mediciones y partidas

Las obras se guardan en <BASE_DIR>/obras_red/<id>/ (obra.json + plano.jpg). Esa carpeta
está en .gitignore porque contiene planos de clientes. En Railway el disco es efímero:
para producción conviene un volumen persistente o mover las obras al ERP.

Se registra desde app.py con:
    from utils.mediciones_bp import crear_blueprint
    app.register_blueprint(crear_blueprint(BASE_DIR, get_tarifas))
"""
from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from core import mediciones


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s[:60] or "obra"


def crear_blueprint(base_dir: Path, get_tarifas) -> Blueprint:
    bp = Blueprint("mediciones_red", __name__)
    raiz = Path(base_dir) / "obras_red"
    raiz.mkdir(exist_ok=True)
    pagina = Path(base_dir) / "web_templates" / "red_saneamiento.html"

    def carpeta(oid: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", oid or ""):
            abort(400, "Identificador de obra no válido")
        return raiz / oid

    def leer(oid: str) -> dict:
        f = carpeta(oid) / "obra.json"
        if not f.exists():
            abort(404, "Obra no encontrada")
        return json.loads(f.read_text(encoding="utf-8"))

    def guardar(obra: dict) -> None:
        d = carpeta(obra["id"])
        d.mkdir(exist_ok=True)
        obra["modificado"] = datetime.now().isoformat(timespec="seconds")
        tmp = d / "obra.json.tmp"
        tmp.write_text(json.dumps(obra, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "obra.json")

    @bp.route("/croquis/red")
    def pantalla():
        return send_file(pagina, mimetype="text/html")

    @bp.route("/api/red/obras")
    def obras():
        out = []
        for f in sorted(raiz.glob("*/obra.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                o = json.loads(f.read_text(encoding="utf-8"))
                r = mediciones.resumen(o)
                out.append({"id": o["id"], "nombre": o.get("nombre", ""), "ref": o.get("ref", ""),
                            "modificado": o.get("modificado", o.get("creado", "")),
                            "ml": r["total_alza"], "arquetas": r["total_arquetas"],
                            "pozos": r["pozos"]["total"]})
            except Exception:
                continue
        return jsonify(out)

    @bp.route("/api/red/nueva", methods=["POST"])
    def nueva():
        nombre = (request.form.get("nombre") or "").strip()
        ref = (request.form.get("ref") or "").strip()
        f = request.files.get("plano")
        if not nombre or not f:
            return jsonify({"error": "Indica el nombre de la obra y sube el plano (PDF o imagen)."}), 400
        oid = _slug(f"{ref}_{nombre}" if ref else nombre)
        base, i = oid, 2
        while (raiz / oid).exists():
            oid = f"{base}_{i}"
            i += 1
        d = raiz / oid
        d.mkdir()
        try:
            w, h = _guardar_plano(f, d / "plano.jpg")
        except Exception as e:
            shutil.rmtree(d, ignore_errors=True)
            return jsonify({"error": f"No se pudo leer el plano: {e}"}), 400
        obra = mediciones.obra_vacia(oid, nombre, ref, w, h, "plano.jpg")
        guardar(obra)
        return jsonify(obra)

    @bp.route("/api/red/obra/<oid>", methods=["GET"])
    def obra_get(oid):
        return jsonify(leer(oid))

    @bp.route("/api/red/obra/<oid>", methods=["POST"])
    def obra_post(oid):
        actual = leer(oid)
        nueva_obra = request.get_json(silent=True)
        if not isinstance(nueva_obra, dict):
            return jsonify({"error": "Datos no válidos"}), 400
        for k in ("tramos", "arquetas", "pozos"):
            if not isinstance(nueva_obra.get(k, []), list):
                return jsonify({"error": f"'{k}' debe ser una lista"}), 400
        nueva_obra["id"] = actual["id"]
        nueva_obra["plano"] = actual["plano"]
        nueva_obra.setdefault("creado", actual.get("creado"))
        guardar(nueva_obra)
        return jsonify({"ok": True, "modificado": nueva_obra["modificado"],
                        "resumen": mediciones.resumen(nueva_obra)})

    @bp.route("/api/red/obra/<oid>/plano")
    def plano(oid):
        o = leer(oid)
        f = carpeta(oid) / o["plano"]["archivo"]
        if not f.exists():
            abort(404)
        return send_file(f, mimetype="image/jpeg", max_age=3600)

    @bp.route("/api/red/obra/<oid>/resumen")
    def resumen(oid):
        return jsonify(mediciones.resumen(leer(oid)))

    @bp.route("/api/red/obra/<oid>/partidas")
    def partidas(oid):
        return jsonify(mediciones.partidas(leer(oid), get_tarifas()))

    @bp.route("/api/red/obra/<oid>/excel")
    def excel(oid):
        o = leer(oid)
        tmp = Path(tempfile.gettempdir()) / f"mediciones_{oid}.xlsx"
        mediciones.excel(o, get_tarifas(), tmp)
        nombre = f"{datetime.now():%Y-%m-%d}_Mediciones_{_slug(o.get('nombre', oid))}.xlsx"
        return send_file(tmp, as_attachment=True, download_name=nombre)

    return bp


def _guardar_plano(fstorage, destino: Path) -> tuple[int, int]:
    """Guarda el plano como JPEG (máx. 3200 px de ancho). PDF: primera página."""
    from PIL import Image
    data = fstorage.read()
    name = (fstorage.filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        import fitz  # PyMuPDF
        doc = fitz.open(stream=data, filetype="pdf")
        page = doc[0]
        zoom = min(4.0, 3200 / max(page.rect.width, 1))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    if img.width < img.height and request.form.get("girar") == "1":
        img = img.rotate(90, expand=True)
    if img.width > 3200:
        img = img.resize((3200, round(3200 * img.height / img.width)))
    # el lienzo de dibujo usa un ancho fijo de 2000 unidades
    w, h = 2000, round(2000 * img.height / img.width)
    img.save(destino, "JPEG", quality=78, optimize=True)
    return w, h
