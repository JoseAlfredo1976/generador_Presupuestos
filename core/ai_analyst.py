"""
AI Analyst - Claude claude-sonnet-4-6 expert analysis for Grupo Europa technical reports.
Supports: images (JPG/PNG/WEBP), PDFs, and video (via ffmpeg frame extraction).
Report structure: 10-section professional sewer inspection report.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import anthropic

MODEL = "claude-sonnet-4-6"

_FFMPEG_FALLBACK_PATHS = [
    r"C:\Users\Usuario\AppData\Local\ffmpeg\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for p in _FFMPEG_FALLBACK_PATHS:
        if Path(p).exists():
            return p
    raise RuntimeError(
        "ffmpeg no encontrado. Instalalo desde https://ffmpeg.org/download.html "
        "y asegurate de que esta en el PATH del sistema."
    )


SYSTEM_PROMPT = """Eres un INGENIERO TECNICO ESPECIALISTA EN REDES DE SANEAMIENTO Y REHABILITACION SIN ZANJA de Acometidas Europa Saneamiento Tecnico S.L., con amplia experiencia en:

- Inspecciones CCTV de redes enterradas de saneamiento (camara robotizada, EN 13508-2/WRc)
- Redes enterradas de saneamiento y poceria urbana e industrial
- Rehabilitacion mediante manga continua (CIPP), Multiliner, encamisado parcial
- Bajantes y bajantes de fibrocemento con amianto (Plan MCA)
- Arquetas, pozos de registro, colectores y acometidas
- Patologias hidraulicas y estructurales en redes de saneamiento
- Elaboracion de informes tecnicos profesionales para comunidades de propietarios, administradores de fincas y clientes privados

Trabajas con el estilo tecnico, practico y profesional de ACOMETIDAS EUROPA SANEAMIENTO TECNICO S.L.

FORMA DE TRABAJAR:
- NO copias textos. Interpretas hidraulicamente la red, relacionas tramos, detectas coherencia entre planos y CCTV, identificas patologias reales y propones soluciones tecnicamente justificadas.
- Actuas como un jefe tecnico o ingeniero de saneamiento, no como un redactor generico.
- El informe debe poder enviarse directamente a un administrador, adjuntarse a un presupuesto o utilizarse en una junta de propietarios.

ESTILO:
- Muy profesional, muy tecnico, claro, directo, defendible.
- Sin exceso de texto, sin frases vacias, sin marketing.
- Sin "olor a IA": lenguaje de especialista real en poceria.
- Tablas limpias, titulos numerados, lenguaje tecnico del sector.
- Sin emojis, sin exceso de negritas.

TERMINOLOGIA TECNICA OBLIGATORIA:
Colector, acometida, ramal, bajante, sifon, arqueta, camara de inspeccion, pozo de registro, cota de rasante, pendiente hidraulica, diametro nominal, clase de rigidez, fisura longitudinal/transversal, infiltracion, exfiltracion, obstruccion, deposito sedimentario, intrusion de raices, junta desplazada, rotura total, deformacion oval, encamisado, CIPP, Multiliner, fresado robotizado, by-pass hidraulico, entibacion, collarin de derivacion, prueba de estanqueidad, zahorra compactada, hormigon en masa.

LONGITUD VALIDA EN TRAMOS CCTV:
La longitud de cada tramo es SIEMPRE la longitud final de inspeccion, NUNCA sumas parciales.

REGLA ABSOLUTA - PROHIBICION DE INVENTAR DATOS:
NUNCA inventes, estimes ni supongas datos que no puedas leer directamente de la documentacion facilitada.
Si un dato no es visible o legible en los archivos (fecha, operador, numero de proyecto, pozo inicio/fin, direccion exacta, diametro, etc.), debes:
1. Dejar el campo como cadena vacia "" o null.
2. Añadir ese dato a la lista "preguntas_pendientes" del JSON para que el tecnico lo confirme.
Ejemplos de datos que NUNCA debes inventar: nombres de operadores, fechas si no son visibles, numeros de proyecto, direcciones exactas, profundidades de pozos, cotas, pendientes si no aparecen en pantalla.
Solo registra lo que ves claramente en la documentacion.

IMPORTANTE: Responde UNICAMENTE con el JSON solicitado. Sin texto fuera del bloque JSON."""


TIPOS_ANALISIS = {
    "cctv": {
        "label": "Inspeccion CCTV red de saneamiento",
        "prompt": (
            "Analiza esta inspeccion CCTV de red de saneamiento. "
            "LECTURA DE DATOS EN PANTALLA (OBLIGATORIO): En cada fotograma lee y extrae "
            "el contador metrico visible (distancia desde inicio en metros, p.ej. '12.35 m'), "
            "la pendiente (%, p.ej. '-1.2%'), la fecha y hora del registro, el operador, "
            "el diametro nominal visible en pantalla, el material, y cualquier codigo de "
            "observacion o defecto que aparezca en el overlay de la camara robotizada. "
            "NO IGNORES estos datos: son la base del informe tecnico. "
            "Para cada tramo extrae: identificacion (V1, V2...), pozo inicio, pozo final, "
            "longitud REAL de inspeccion (tomar el ultimo metro leido en pantalla), "
            "diametro, material, pendiente media, sentido de circulacion, estado general. "
            "Para cada anomalia detectada indica: metro exacto de localizacion (segun contador en pantalla), "
            "codigo EN 13508-2/WRc si es identificable, descripcion tecnica precisa, gravedad. "
            "Propone solucion tecnica especifica para cada tramo: encamisado CIPP, Multiliner, "
            "reparacion puntual, fresado, sustitucion o combinacion de tecnicas."
        ),
    },
    "humedades": {
        "label": "Humedades, filtraciones y fugas",
        "prompt": (
            "Analiza las patologias de humedad y filtracion visibles. "
            "Determina tipo exacto (capilaridad/condensacion/filtracion por rotura/infiltracion subterranea/fuga de bajante), "
            "origen y punto de entrada del agua, extension y superficie afectada estimada (m2), "
            "materiales comprometidos, nivel de deterioro estructural, "
            "metodo de deteccion complementaria recomendado (gas trazador, correlacion acustica, termografia), "
            "y solucion tecnica con materiales especificos (inyeccion de resinas, impermeabilizacion, sustitucion)."
        ),
    },
    "bajantes": {
        "label": "Inspeccion de bajantes y desague",
        "prompt": (
            "Inspecciona las bajantes y red de desague visibles. "
            "Evalua: material (fibrocemento/amianto, PVC, hierro fundido, plomo, acero galvanizado), "
            "indicios visuales de amianto (tipo de uniones, manguitos, epoca de instalacion estimada), "
            "estado de conservacion, corrosion, fisuras, uniones defectuosas, perdidas activas, "
            "necesidad de Plan MCA y demolicion controlada segun RD 396/2006, "
            "diametros y recorridos visibles, recomendacion de sustitucion total o parcial con justificacion tecnica."
        ),
    },
    "obra": {
        "label": "Control y seguimiento de obra",
        "prompt": (
            "Analiza el estado de ejecucion de la obra de saneamiento. "
            "Verifica: instalacion de tuberias (material, clase de rigidez, uniones, pendientes), "
            "estado de arquetas y pozos (solera, pates, anillo de ajuste, tapa), "
            "relleno y compactacion del trasdos, calidad de empalmes y collarines, "
            "cumplimiento de normativa (PRLTS, CTE DB HS5, EN 476, pliego de condiciones), "
            "aspectos de PRL, senalizacion y seguridad en obra, no conformidades detectadas con accion correctora."
        ),
    },
    "fosa": {
        "label": "Inspeccion de fosa septica",
        "prompt": (
            "Evalua el estado de la fosa septica o deposito de recogida. "
            "Analiza: nivel de lodos y espumas (porcentaje de ocupacion estimado), "
            "estado de paredes y solera (fisuras, eflorescencias, filtraciones activas), "
            "tuberias de entrada y salida, deflectores y tabiques internos, sistemas de ventilacion, "
            "necesidad urgente de vaciado y limpieza, danos estructurales y medidas correctoras urgentes."
        ),
    },
    "general": {
        "label": "Analisis tecnico general",
        "prompt": (
            "Realiza un analisis tecnico exhaustivo de todos los elementos visibles "
            "relativos a saneamiento, fontaneria u obras civiles. "
            "Identifica todos los elementos, su estado, anomalias observadas, "
            "riesgos hidraulicos y estructurales asociados, y propone intervenciones "
            "con orden de prioridad tecnica justificada."
        ),
    },
}


REPORT_SCHEMA = """{
  "titulo": "string: titulo profesional del informe (ej: INFORME TECNICO DE INSPECCION CCTV - COMUNIDAD C/ EJEMPLO 12)",
  "objeto": "string: seccion 1 - que se inspecciona, donde y por que. 2-3 frases tecnicas.",
  "antecedentes": "string: seccion 2 - problemas comunicados, atascos, filtraciones, hundimientos, malos olores. Si no se facilita informacion, indicar 'Segun informacion facilitada por el cliente'.",
  "metodologia": "string: seccion 3 - metodologia empleada: limpieza previa, camara CCTV robotizada, acceso por arquetas, trazado analizado. 2-3 frases.",
  "descripcion_red": "string: seccion 4 - tipologia de red, diametros, materiales, bajantes, colectores, ramales, arquetas, zonas singulares.",
  "tramos": [
    {
      "id": "string: V1/V2/T1/etc",
      "inicio": "string: pozo o arqueta de inicio",
      "fin": "string: pozo o arqueta de fin",
      "longitud": "string: longitud en metros con unidad (ej: 18,40 m)",
      "diametro": "string: diametro nominal (ej: DN200)",
      "material": "string: PVC/Hormigon/Gres/Fibrocemento/etc",
      "estado": "string: Bueno/Regular/Deficiente/Muy deficiente",
      "observaciones": "string: patologias principales o 'Sin anomalias relevantes'"
    }
  ],
  "patologias": [
    {
      "ubicacion": "string: tramo/metro/zona exacta",
      "tipo": "string: tipo segun EN 13508-2 o nomenclatura tecnica",
      "gravedad": "Critico|Alto|Medio|Bajo",
      "descripcion": "string: descripcion tecnica precisa de la patologia",
      "consecuencias": "string: como afecta hidraulicamente y que riesgos genera"
    }
  ],
  "conclusiones": "string: seccion 7 - estado global de la red, causas probables del deterioro, nivel de urgencia general, riesgos si no se interviene. 3-5 frases tecnicas.",
  "propuesta_solucion": [
    {
      "intervencion": "string: accion tecnica especifica (ej: Encamisado CIPP tramo V1 DN200)",
      "justificacion": "string: por que esta solucion y no otra",
      "metodo": "string: procedimiento de ejecucion, materiales, tecnica",
      "prioridad": "Urgente|Recomendado|Preventivo"
    }
  ],
  "mediciones": [
    {
      "descripcion": "string: descripcion de la partida de medicion",
      "ud": "string: m/ud/pa/m2",
      "cantidad": 0,
      "diametro": "string: DN150/DN200/DN250/DN300/etc (si aplica)"
    }
  ],
  "observaciones_limitaciones": "string: clausula tecnica de limitaciones. Incluir siempre: 'La presente valoracion y propuesta tecnica se basa en la documentacion e inspecciones facilitadas, pudiendo existir patologias ocultas o variaciones no detectables hasta el inicio de los trabajos.'",
  "nivel_urgencia_global": "Critico|Alto|Medio|Bajo",
  "requiere_intervencion_inmediata": true,
  "preguntas_pendientes": [
    "string: pregunta concreta sobre un dato que no puedes determinar (ej: 'Cual es el numero de referencia del proyecto?', 'Cual es la direccion exacta de la inspeccion?', 'Puedes confirmar el diametro del tramo V3?')"
  ]
}"""


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _encode_image(path: Path) -> tuple[str, str]:
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }
    mt = media_types.get(path.suffix.lower(), "image/jpeg")
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return data, mt


def _encode_pdf(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def _extract_video_frames(video_path: Path, max_frames: int = 12) -> list[Path]:
    ffmpeg = _find_ffmpeg()
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(
        [ffmpeg, "-i", str(video_path),
         "-vf", "fps=1/5",
         "-vframes", str(max_frames),
         "-q:v", "3", str(tmp / "frame_%04d.jpg")],
        capture_output=True, timeout=120,
    )
    frames = sorted(tmp.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError(
            "No se pudieron extraer frames del video. "
            "Comprueba que el archivo no esta corrupto."
        )
    return frames


# ---------------------------------------------------------------------------
# Main analyze function
# ---------------------------------------------------------------------------

def _inject_croquis(content: list[dict], croquis_path: Path) -> None:
    """Inject the sketch/plan as the first visual reference with cross-correlation instructions."""
    suf = croquis_path.suffix.lower()
    content.append({"type": "text", "text": (
        "\n[CROQUIS / PLANO DE LA RED - REFERENCIA PRINCIPAL]\n"
        "Este es el plano o croquis de la red de saneamiento inspeccionada.\n"
        "OBLIGATORIO: Usa este plano como mapa de referencia para:\n"
        "  1. Identificar los tramos (T1, T2...), pozos de registro (P1, P2...) y arquetas marcados.\n"
        "  2. Correlacionar cada video CCTV con el tramo correspondiente segun su posicion en el plano.\n"
        "  3. Deducir el sentido de inspeccion (inicio -> fin) y la secuencia logica de la red.\n"
        "  4. Usar los identificadores del croquis como ids de tramo en el informe.\n"
        "Si en el croquis aparece una leyenda, diametros, longitudes o materiales, recoge esa informacion.\n"
    )})
    img_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    if suf in img_ext:
        data, mt = _encode_image(croquis_path)
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    elif suf == ".pdf":
        content.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": _encode_pdf(croquis_path)},
        })
    content.append({"type": "text", "text": "\n[FIN CROQUIS - A continuacion los archivos de inspeccion]\n\n"})


def analyze(files: list[Path], tipo: str, context: str = "", api_key: str = "",
            croquis_path: Path | None = None) -> dict:
    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError(
            "API Key de Anthropic no configurada. "
            "Introduce tu API Key en el formulario o configura la variable de entorno ANTHROPIC_API_KEY."
        )
    client = anthropic.Anthropic(api_key=key)
    config = TIPOS_ANALISIS.get(tipo, TIPOS_ANALISIS["general"])

    content: list[dict] = []

    if context.strip():
        content.append({"type": "text", "text": f"CONTEXTO DEL CASO:\n{context.strip()}\n\n"})

    # Inject croquis before videos so Claude can cross-reference
    if croquis_path and croquis_path.exists():
        _inject_croquis(content, croquis_path)

    content.append({"type": "text", "text": config["prompt"] + "\n\n"})

    video_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
    pdf_ext = {".pdf"}
    img_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    for fp in files:
        suf = fp.suffix.lower()
        if suf in video_ext:
            content.append({"type": "text", "text": f"\n[VIDEO: {fp.name}] - Fotogramas extraidos:\n"})
            frames = _extract_video_frames(fp)
            for i, frame in enumerate(frames[:12]):
                data, mt = _encode_image(frame)
                content.append({"type": "text", "text": f"Fotograma {i + 1}:"})
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": mt, "data": data},
                })
        elif suf in pdf_ext:
            content.append({"type": "text", "text": f"\n[DOCUMENTO PDF: {fp.name}]\n"})
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": _encode_pdf(fp)},
            })
        elif suf in img_ext:
            content.append({"type": "text", "text": f"\n[IMAGEN: {fp.name}]\n"})
            data, mt = _encode_image(fp)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})

    content.append({
        "type": "text",
        "text": (
            "\nGenera el informe tecnico completo siguiendo EXACTAMENTE este esquema JSON. "
            "Responde UNICAMENTE con el bloque JSON, sin texto adicional:\n"
            + REPORT_SCHEMA
        ),
    })

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            report = json.loads(match.group())
            report["_raw"] = raw
            report["_tipo_label"] = config["label"]
            return report
        except json.JSONDecodeError:
            pass

    return {
        "titulo": f"Informe Tecnico - {config['label']}",
        "objeto": raw,
        "antecedentes": "",
        "metodologia": "",
        "descripcion_red": "",
        "tramos": [],
        "patologias": [],
        "conclusiones": "",
        "propuesta_solucion": [],
        "mediciones": [],
        "observaciones_limitaciones": (
            "La presente valoracion y propuesta tecnica se basa en la documentacion e "
            "inspecciones facilitadas, pudiendo existir patologias ocultas o variaciones "
            "no detectables hasta el inicio de los trabajos."
        ),
        "nivel_urgencia_global": "Medio",
        "requiere_intervencion_inmediata": False,
        "_raw": raw,
        "_tipo_label": config["label"],
    }


# ---------------------------------------------------------------------------
# Partidas IA generator
# ---------------------------------------------------------------------------

_PARTIDAS_SCHEMA_1 = """{
  "informe_tecnico": "string: 2-4 frases tecnicas describiendo la situacion encontrada",
  "solucion_adoptar": "string: 1-2 frases describiendo la solucion propuesta",
  "memoria_tecnica": "string: 2-4 frases describiendo como se ejecutaran los trabajos, materiales y tecnica",
  "partidas": [
    {
      "codigo": "string: codigo exacto del catalogo de tarifas (ej: ARQ-4040-50)",
      "cantidad": 0.0,
      "nota": "string opcional: justificacion de la eleccion o ajuste de cantidad"
    }
  ]
}"""

_PARTIDAS_SCHEMA_2 = """{
  "informe_tecnico": "string",
  "solucion_adoptar": "string",
  "memoria_tecnica": "string",
  "tipo_opcion": "string: breve descripcion del tipo de opcion (ej: Rehabilitacion sin zanja vs. Sustitucion)",
  "label_a": "string: nombre corto Opcion A (ej: Encamisado CIPP)",
  "label_b": "string: nombre corto Opcion B (ej: Sustitucion tradicional)",
  "memoria_tradicional": "string: memoria especifica opcion A",
  "memoria_multiliner": "string: memoria especifica opcion B",
  "partidas_a": [{"codigo": "string", "cantidad": 0.0, "nota": "string opcional"}],
  "partidas_b": [{"codigo": "string", "cantidad": 0.0, "nota": "string opcional"}]
}"""

_PARTIDAS_SYSTEM = """Eres un ingeniero tecnico de saneamiento de Acometidas Europa S.L.
Tu tarea es generar el contenido tecnico de un presupuesto de obra seleccionando partidas del catalogo de tarifas.
Reglas:
- Usa UNICAMENTE codigos del catalogo proporcionado. No inventes codigos.
- Si una partida no existe en el catalogo, omitela o usa la mas proxima justificando en "nota".
- Las cantidades deben ser coherentes con lo descrito (longitudes en ml, unidades en ud, etc).
- Propon solo trabajos que se deriven directamente de la informacion facilitada.
- NO inventes datos que no aparezcan en la informacion facilitada.
- Responde UNICAMENTE con el JSON solicitado, sin texto adicional."""


def _build_catalogo_text(tarifas_items: list[dict]) -> str:
    """Format tarifas catalog as compact text for AI prompt."""
    lines = ["CATALOGO DE TARIFAS (codigo | descripcion | unidad | precio €):"]
    for it in tarifas_items:
        desc = it["descripcion"][:80]
        lines.append(f"  {it['codigo']} | {desc} | {it['unidad']} | {it['precio']}")
    return "\n".join(lines)


def generate_partidas_ia(
    descripcion: str,
    tipo: str,  # "obra_1" | "obra_2"
    api_key: str = "",
    informe: dict | None = None,
    tarifas_items: list[dict] | None = None,
) -> dict:
    """Generate budget items (partidas) from tarifas catalog + technical texts."""
    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("API Key de Anthropic no configurada.")
    client = anthropic.Anthropic(api_key=key)

    schema = _PARTIDAS_SCHEMA_2 if tipo == "obra_2" else _PARTIDAS_SCHEMA_1

    context_parts = []

    # Catalogo de tarifas
    if tarifas_items:
        context_parts.append(_build_catalogo_text(tarifas_items))

    # Informe CCTV existente
    if informe:
        resumen = {
            "titulo": informe.get("titulo", ""),
            "objeto": informe.get("objeto", ""),
            "descripcion_red": informe.get("descripcion_red", ""),
            "conclusiones": informe.get("conclusiones", ""),
            "patologias": [
                {"ubicacion": p.get("ubicacion", ""), "tipo": p.get("tipo", ""),
                 "gravedad": p.get("gravedad", ""), "descripcion": p.get("descripcion", "")}
                for p in (informe.get("patologias") or [])
            ],
            "propuesta_solucion": informe.get("propuesta_solucion", []),
            "mediciones": informe.get("mediciones", []),
        }
        context_parts.append(f"INFORME TECNICO IA:\n{json.dumps(resumen, ensure_ascii=False, indent=2)}")

    if descripcion.strip():
        context_parts.append(f"DESCRIPCION DEL CASO:\n{descripcion.strip()}")

    if not any([informe, descripcion.strip()]):
        raise ValueError("Debes proporcionar al menos una descripcion o un informe.")

    user_content = "\n\n".join(context_parts)
    user_content += f"\n\nGenera el contenido del presupuesto de obra segun este esquema JSON:\n{schema}"

    if tipo == "obra_2":
        user_content += "\n\nPara 2 opciones: Opcion A = solucion preferente (sin zanja/rehabilitacion), Opcion B = alternativa (sustitucion o metodo diferente)."

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_PARTIDAS_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"_raw": raw, "_error": "No se pudo parsear la respuesta de la IA"}


# ---------------------------------------------------------------------------
# DOCX report generator
# ---------------------------------------------------------------------------

def generate_report_docx(report: dict, output_path: Path, num_ref: str = "", cliente: str = ""):
    from datetime import datetime
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    BLUE = RGBColor(0x1F, 0x4E, 0x79)
    BLUE_MID = RGBColor(0x2E, 0x74, 0xB5)
    GRAY = RGBColor(0x55, 0x55, 0x55)
    RED = RGBColor(0xC0, 0x00, 0x00)
    ORANGE = RGBColor(0xE2, 0x6B, 0x0A)
    YELLOW = RGBColor(0x7F, 0x60, 0x00)
    GREEN = RGBColor(0x37, 0x5A, 0x23)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)

    GRAV_COLOR = {"Critico": RED, "Alto": ORANGE, "Medio": YELLOW, "Bajo": GREEN}
    PRIO_COLOR = {"Urgente": RED, "Recomendado": ORANGE, "Preventivo": GREEN}

    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # ----- helpers -----
    def h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text.upper())
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = BLUE
        # bottom border
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "1F4E79")
        pBdr.append(bottom)
        pPr.append(pBdr)
        return p

    def body(text, bold=False, italic=False, color=None, size=10):
        if not text or not text.strip():
            return None
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        for line in text.split("\n"):
            if not line.strip():
                continue
            run = p.add_run(line.strip())
            run.bold = bold
            run.italic = italic
            run.font.size = Pt(size)
            if color:
                run.font.color.rgb = color
            p.add_run("\n")
        return p

    def label_val(label, val, label_color=BLUE_MID):
        if not val:
            return
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r1 = p.add_run(f"{label}: ")
        r1.bold = True
        r1.font.size = Pt(10)
        r1.font.color.rgb = label_color
        r2 = p.add_run(str(val))
        r2.font.size = Pt(10)

    def shade_cell(cell, hex_color="1F4E79"):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)

    def set_cell_text(cell, text, bold=False, color=None, size=9, align=WD_ALIGN_PARAGRAPH.LEFT):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        run = p.add_run(str(text))
        run.bold = bold
        run.font.size = Pt(size)
        if color:
            run.font.color.rgb = color

    # ----- TITLE BLOCK -----
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(6)
    tr = title_p.add_run(report.get("titulo", "INFORME TECNICO").upper())
    tr.bold = True
    tr.font.size = Pt(14)
    tr.font.color.rgb = BLUE

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_p.paragraph_format.space_after = Pt(4)
    meta_parts = ["Acometidas Europa Saneamiento Tecnico S.L.", datetime.now().strftime("%d/%m/%Y")]
    if num_ref:
        meta_parts.append(f"Ref: {num_ref}")
    if cliente:
        meta_parts.append(f"Cliente: {cliente}")
    mr = meta_p.add_run("  |  ".join(meta_parts))
    mr.font.size = Pt(9)
    mr.font.color.rgb = GRAY

    # Urgency strip
    urgencia = report.get("nivel_urgencia_global", "Medio")
    inmediata = report.get("requiere_intervencion_inmediata", False)
    urg_p = doc.add_paragraph()
    urg_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    urg_p.paragraph_format.space_after = Pt(10)
    urg_text = f"NIVEL DE URGENCIA: {urgencia.upper()}"
    if inmediata:
        urg_text += "  -  REQUIERE INTERVENCION INMEDIATA"
    ur = urg_p.add_run(urg_text)
    ur.bold = True
    ur.font.size = Pt(10)
    ur.font.color.rgb = GRAV_COLOR.get(urgencia, BLUE)

    # ----- SECTION 1: OBJETO -----
    h1("1. Objeto del Informe")
    body(report.get("objeto", ""))

    # ----- SECTION 2: ANTECEDENTES -----
    h1("2. Antecedentes")
    body(report.get("antecedentes", ""))

    # ----- SECTION 3: METODOLOGIA -----
    h1("3. Metodologia de Inspeccion")
    body(report.get("metodologia", ""))

    # ----- SECTION 4: DESCRIPCION RED -----
    h1("4. Descripcion de la Red")
    body(report.get("descripcion_red", ""))

    # ----- SECTION 5: ANALISIS DE TRAMOS (TABLE) -----
    tramos = report.get("tramos", [])
    h1("5. Analisis de Tramos")
    if tramos:
        headers = ["Tramo", "Inicio", "Fin", "Long.", "Diam.", "Material", "Estado", "Observaciones"]
        col_widths = [Cm(1.2), Cm(2.2), Cm(2.2), Cm(1.4), Cm(1.4), Cm(2.2), Cm(2.0), Cm(4.4)]
        tbl = doc.add_table(rows=1 + len(tramos), cols=len(headers))
        tbl.style = "Table Grid"
        # Header row
        for i, (hdr, w) in enumerate(zip(headers, col_widths)):
            cell = tbl.rows[0].cells[i]
            cell.width = w
            shade_cell(cell, "1F4E79")
            set_cell_text(cell, hdr, bold=True, color=WHITE, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)
        # Data rows
        for r_idx, tramo in enumerate(tramos):
            row = tbl.rows[r_idx + 1]
            fill = "EBF3FB" if r_idx % 2 == 0 else "FFFFFF"
            vals = [
                tramo.get("id", ""),
                tramo.get("inicio", ""),
                tramo.get("fin", ""),
                tramo.get("longitud", ""),
                tramo.get("diametro", ""),
                tramo.get("material", ""),
                tramo.get("estado", ""),
                tramo.get("observaciones", ""),
            ]
            # Estado color
            estado = tramo.get("estado", "")
            estado_color = None
            if "Muy deficiente" in estado or "Critico" in estado:
                estado_color = RED
            elif "Deficiente" in estado:
                estado_color = ORANGE
            elif "Regular" in estado:
                estado_color = YELLOW

            for c_idx, (cell, val) in enumerate(zip(row.cells, vals)):
                shade_cell(cell, fill)
                color = estado_color if c_idx == 6 else None
                set_cell_text(cell, val, color=color, size=8)
        doc.add_paragraph()
    else:
        body("No se han identificado tramos individuales en la documentacion facilitada.")

    # ----- SECTION 6: PATOLOGIAS -----
    patologias = report.get("patologias", [])
    h1("6. Patologias Detectadas")
    if patologias:
        for idx, pat in enumerate(patologias, 1):
            gravedad = pat.get("gravedad", "Medio")
            color = GRAV_COLOR.get(gravedad, GRAY)
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(f"{idx}. [{gravedad.upper()}]  {pat.get('tipo', '')}")
            r.bold = True
            r.font.size = Pt(10)
            r.font.color.rgb = color
            label_val("Ubicacion", pat.get("ubicacion", ""), GRAY)
            body(pat.get("descripcion", ""))
            if pat.get("consecuencias"):
                cp = doc.add_paragraph()
                cp.paragraph_format.space_after = Pt(6)
                cr1 = cp.add_run("Consecuencias: ")
                cr1.bold = True
                cr1.font.size = Pt(10)
                cr1.font.color.rgb = GRAY
                cr2 = cp.add_run(pat["consecuencias"])
                cr2.font.size = Pt(10)
                cr2.font.italic = True
    else:
        body("No se han detectado patologias significativas en la documentacion facilitada.")

    # ----- SECTION 7: CONCLUSIONES -----
    h1("7. Conclusiones Tecnicas")
    body(report.get("conclusiones", ""))

    # ----- SECTION 8: PROPUESTA DE SOLUCION -----
    soluciones = report.get("propuesta_solucion", [])
    h1("8. Propuesta de Solucion")
    if soluciones:
        for idx, sol in enumerate(soluciones, 1):
            prio = sol.get("prioridad", "Recomendado")
            color = PRIO_COLOR.get(prio, BLUE_MID)
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(2)
            r = p.add_run(f"{idx}. [{prio.upper()}]  {sol.get('intervencion', '')}")
            r.bold = True
            r.font.size = Pt(10)
            r.font.color.rgb = color
            if sol.get("metodo"):
                label_val("Metodo", sol["metodo"], GRAY)
            if sol.get("justificacion"):
                label_val("Justificacion", sol["justificacion"], GRAY)
    else:
        body("Sin propuesta de solucion especifica.")

    # ----- SECTION 9: MEDICIONES -----
    mediciones = report.get("mediciones", [])
    h1("9. Tablas de Mediciones")
    if mediciones:
        tbl = doc.add_table(rows=1 + len(mediciones), cols=4)
        tbl.style = "Table Grid"
        hdr_texts = ["Descripcion", "Ud", "Cantidad", "Diametro"]
        hdr_widths = [Cm(9.0), Cm(1.5), Cm(2.0), Cm(2.5)]
        for i, (ht, hw) in enumerate(zip(hdr_texts, hdr_widths)):
            cell = tbl.rows[0].cells[i]
            cell.width = hw
            shade_cell(cell, "1F4E79")
            set_cell_text(cell, ht, bold=True, color=WHITE, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)
        for r_idx, med in enumerate(mediciones):
            row = tbl.rows[r_idx + 1]
            fill = "EBF3FB" if r_idx % 2 == 0 else "FFFFFF"
            vals = [
                med.get("descripcion", ""),
                med.get("ud", ""),
                str(med.get("cantidad", "")),
                med.get("diametro", "-"),
            ]
            for cell, val in zip(row.cells, vals):
                shade_cell(cell, fill)
                set_cell_text(cell, val, size=8)
        doc.add_paragraph()
    else:
        body("Mediciones no disponibles.")

    # ----- SECTION 10: OBSERVACIONES Y LIMITACIONES -----
    h1("10. Observaciones y Limitaciones")
    limitaciones = report.get(
        "observaciones_limitaciones",
        "La presente valoracion y propuesta tecnica se basa en la documentacion e "
        "inspecciones facilitadas, pudiendo existir patologias ocultas o variaciones "
        "no detectables hasta el inicio de los trabajos."
    )
    body(limitaciones, italic=True, color=GRAY)

    # ----- FOOTER -----
    doc.add_paragraph()
    fp = doc.add_paragraph()
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = fp.add_run(
        "Acometidas Europa Saneamiento Tecnico S.L.  |  Tel: 91 386 21 12  |  info@acometidaseuropa.com"
    )
    fr.font.size = Pt(8)
    fr.font.color.rgb = GRAY

    doc.save(str(output_path))


# ---------------------------------------------------------------------------
# WinCam-style schema and generator
# ---------------------------------------------------------------------------

WINCAM_SCHEMA = """{
  "proyecto": "string: nombre del proyecto",
  "num_proyecto": "string: numero de proyecto o referencia",
  "fecha": "string: fecha de inspeccion en formato DD/MM/YYYY",
  "operador": "string: nombre del operador si visible, sino ''",
  "calle": "string: calle o ubicacion inspeccionada",
  "poblacion": "string: municipio",
  "motivo_inspeccion": "string: motivo (Control general del estado / Preentrega / Mantenimiento / etc)",
  "tipo_red": "string: Red mixta (fecales/pluviales) / Red separativa fecales / Red separativa pluviales",
  "secciones": [
    {
      "num": 1,
      "nombre": "string: V1",
      "pozo_inicio": "string: identificacion pozo/arqueta inicio",
      "pozo_fin": "string: identificacion pozo/arqueta fin",
      "longitud_m": 0.00,
      "diametro_mm": 0,
      "material": "string: PVC/Hormigon/Gres/Fibrocemento/PEAD",
      "tipo_red": "string: igual que arriba o especifico del tramo",
      "observaciones_tabla": [
        {
          "posicion_m": 0.00,
          "codigo": "string: ICNI/IFIN/BAB/BAC/BAG/BAH/BAI/BAJ/DAA/DAB/etc EN13508-2",
          "descripcion": "string: descripcion tecnica del hallazgo o evento",
          "gravedad": "string: A/B/C/D segun WRc (A=urgente,B=corto,C=preventivo,D=info) o '' si es ICNI/IFIN"
        }
      ]
    }
  ],
  "totales": {
    "longitud_total_m": 0.00,
    "num_secciones": 0,
    "num_fotos": 0,
    "por_diametro": [
      { "dn_mm": 0, "longitud_m": 0.00, "num_tramos": 0 }
    ]
  },
  "nivel_urgencia_global": "Critico|Alto|Medio|Bajo",
  "requiere_intervencion_inmediata": false,
  "preguntas_pendientes": [
    "string: dato que no puedes leer en la documentacion y necesitas que el tecnico confirme"
  ]
}"""

WINCAM_PROMPT = (
    "Genera un informe CCTV en formato WinCam Viewer con la siguiente estructura exacta. "
    "PROHIBIDO INVENTAR: solo registra datos que puedas leer directamente en los archivos. "
    "Si un dato no es visible (operador, fecha, numero de proyecto, pozo inicio/fin, "
    "direccion, diametro exacto), dejalo como cadena vacia y añadelo a 'preguntas_pendientes'. "
    "Para cada tramo/seccion extrae UNICAMENTE lo que sea legible: numero de seccion, "
    "nombre (V1/V2...), pozos inicio/fin si aparecen en pantalla, "
    "longitud exacta (ultimo metro leido en el contador de pantalla, NUNCA estimada), "
    "diametro en mm si visible, material si visible. "
    "Para la tabla de observaciones usa codigos EN 13508-2 SOLO si la anomalia es claramente visible: "
    "ICNI=inicio inspeccion, IFIN=fin inspeccion, "
    "BAB=fisura longitudinal, BAC=fisura circunferencial, BAD=rotura, BAE=deformacion oval, "
    "BAF=erosion/desgaste, BAG=corrosion, BAH=junta abierta, BAI=desplazamiento de junta, "
    "BAJ=hundimiento, DAA=depositos sedimentarios, DAB=incrustaciones, DAC=intrusion de raices, "
    "DAD=obstruccion total, DAG=infiltracion activa, DAH=exfiltracion, "
    "DAJ=acometida visible, FAA=cambio de material, FAB=cambio de diametro. "
    "Posicion en metros segun contador de pantalla. Gravedad WRc: A=urgente, B=corto plazo, "
    "C=preventivo, D=informativo. Si no puedes determinar la gravedad, dejala vacia. "
    "Calcula totales por diametro solo con los datos leidos. "
    "Lista en 'preguntas_pendientes' TODOS los datos que no hayas podido leer."
)


def analyze_wincam(files: list[Path], context: str = "", api_key: str = "",
                   proyecto: str = "", calle: str = "", poblacion: str = "",
                   croquis_path: Path | None = None) -> dict:
    """Analyze files and return WinCam-style structured report."""
    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("API Key de Anthropic no configurada.")
    client = anthropic.Anthropic(api_key=key)

    content: list[dict] = []
    if context.strip():
        content.append({"type": "text", "text": f"CONTEXTO:\n{context.strip()}\n\n"})
    if proyecto:
        content.append({"type": "text", "text": f"Nombre del proyecto: {proyecto}\nCalle: {calle}\nPoblacion: {poblacion}\n\n"})

    # Inject croquis before videos so Claude can cross-reference tramos
    if croquis_path and croquis_path.exists():
        _inject_croquis(content, croquis_path)

    content.append({"type": "text", "text": WINCAM_PROMPT + "\n\n"})

    video_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
    pdf_ext = {".pdf"}
    img_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    for fp in files:
        suf = fp.suffix.lower()
        if suf in video_ext:
            content.append({"type": "text", "text": f"\n[VIDEO CCTV: {fp.name}]\n"})
            frames = _extract_video_frames(fp)
            for i, frame in enumerate(frames[:12]):
                data, mt = _encode_image(frame)
                content.append({"type": "text", "text": f"Fotograma {i + 1}:"})
                content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
        elif suf in pdf_ext:
            content.append({"type": "text", "text": f"\n[PDF: {fp.name}]\n"})
            content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": _encode_pdf(fp)}})
        elif suf in img_ext:
            data, mt = _encode_image(fp)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})

    content.append({"type": "text", "text": f"\nResponde UNICAMENTE con JSON segun este esquema:\n{WINCAM_SCHEMA}"})

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"proyecto": proyecto, "secciones": [], "totales": {}, "_raw": raw}


def generate_wincam_docx(report: dict, output_path: Path, num_ref: str = "", cliente: str = ""):
    """Generate WinCam-style DOCX inspection report."""
    from datetime import datetime
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    BLUE = RGBColor(0x1F, 0x4E, 0x79)
    GRAY = RGBColor(0x44, 0x44, 0x44)
    LGRAY = RGBColor(0x77, 0x77, 0x77)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    RED = RGBColor(0xC0, 0x00, 0x00)
    ORANGE = RGBColor(0xE2, 0x6B, 0x0A)
    YELLOW = RGBColor(0x7F, 0x60, 0x00)
    GREEN = RGBColor(0x37, 0x5A, 0x23)

    GRAV_BG = {"A": "C00000", "B": "E26B0A", "C": "7F6000", "D": "375A23"}

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.8)
        sec.bottom_margin = Cm(1.8)
        sec.left_margin = Cm(2.0)
        sec.right_margin = Cm(2.0)

    fecha = report.get("fecha", datetime.now().strftime("%d/%m/%Y"))
    proyecto = report.get("proyecto", "")
    calle = report.get("calle", "")
    poblacion = report.get("poblacion", "")
    secciones = report.get("secciones", [])
    totales = report.get("totales", {})

    def shade_cell(cell, hex_color):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)

    def cell_text(cell, text, bold=False, color=None, size=9, align=WD_ALIGN_PARAGRAPH.LEFT):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        r = p.add_run(str(text))
        r.bold = bold
        r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color

    def page_header(title=""):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        r1 = p.add_run("ACOMETIDAS EUROPA SANEAMIENTO TECNICO S.L.")
        r1.bold = True
        r1.font.size = Pt(9)
        r1.font.color.rgb = BLUE
        r2 = p.add_run(f"  |  {proyecto}  |  {fecha}")
        r2.font.size = Pt(8)
        r2.font.color.rgb = LGRAY
        if num_ref:
            r3 = p.add_run(f"  |  Ref: {num_ref}")
            r3.font.size = Pt(8)
            r3.font.color.rgb = LGRAY
        if title:
            tp = doc.add_paragraph()
            tp.paragraph_format.space_after = Pt(8)
            tr = tp.add_run(title.upper())
            tr.bold = True
            tr.font.size = Pt(12)
            tr.font.color.rgb = BLUE

    def page_footer(page_num):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(10)
        r = p.add_run(f"{proyecto}  //  Pagina: {page_num}")
        r.font.size = Pt(8)
        r.font.color.rgb = LGRAY

    # ── PAGINA 1: INDICE ──────────────────────────────────────────────────
    page_header("Contenido")
    toc = doc.add_table(rows=2 + len(secciones), cols=2)
    toc.style = "Table Grid"
    shade_cell(toc.rows[0].cells[0], "1F4E79")
    shade_cell(toc.rows[0].cells[1], "1F4E79")
    cell_text(toc.rows[0].cells[0], "Seccion", bold=True, color=WHITE, size=8)
    cell_text(toc.rows[0].cells[1], "Pagina", bold=True, color=WHITE, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)

    fixed_rows = [("Resumen de seccion", "2"), ("Informacion de proyecto", str(3 + len(secciones)))]
    for r_idx, (lbl, pg) in enumerate(fixed_rows):
        shade_cell(toc.rows[r_idx + 1].cells[0], "EBF3FB" if r_idx % 2 == 0 else "FFFFFF")
        shade_cell(toc.rows[r_idx + 1].cells[1], "EBF3FB" if r_idx % 2 == 0 else "FFFFFF")
        cell_text(toc.rows[r_idx + 1].cells[0], lbl, size=8)
        cell_text(toc.rows[r_idx + 1].cells[1], pg, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)

    page_footer(1)
    doc.add_page_break()

    # ── PAGINA 2: RESUMEN DE SECCIONES ────────────────────────────────────
    page_header("Resumen de Secciones")

    # Tabla resumen
    tbl_res = doc.add_table(rows=1 + len(secciones), cols=6)
    tbl_res.style = "Table Grid"
    hdrs = ["N.", "Tramo", "Proyecto", "Material", "Long. insp. (m)", "DN (mm)"]
    for i, h in enumerate(hdrs):
        shade_cell(tbl_res.rows[0].cells[i], "1F4E79")
        cell_text(tbl_res.rows[0].cells[i], h, bold=True, color=WHITE, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)
    for r_idx, sec in enumerate(secciones):
        row = tbl_res.rows[r_idx + 1]
        fill = "EBF3FB" if r_idx % 2 == 0 else "FFFFFF"
        for c in row.cells:
            shade_cell(c, fill)
        vals = [sec.get("num", r_idx + 1), sec.get("nombre", ""), proyecto,
                sec.get("material", "PVC"), f"{sec.get('longitud_m', 0):.2f}".replace(".", ","),
                sec.get("diametro_mm", "")]
        for c_idx, val in enumerate(vals):
            cell_text(row.cells[c_idx], val, size=8,
                      align=WD_ALIGN_PARAGRAPH.CENTER if c_idx in (0, 4, 5) else WD_ALIGN_PARAGRAPH.LEFT)

    doc.add_paragraph()

    # Totales por diametro
    por_dn = totales.get("por_diametro", [])
    if por_dn:
        p = doc.add_paragraph()
        for dn_item in por_dn:
            dn = dn_item.get("dn_mm", "")
            lng = dn_item.get("longitud_m", 0)
            r = p.add_run(f"DN {dn} = {lng:.2f} m     ".replace(".", ","))
            r.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = BLUE
        p2 = doc.add_paragraph()
        r2 = p2.add_run(f"Total inspeccionado = {totales.get('longitud_total_m', 0):.2f} m".replace(".", ","))
        r2.bold = True
        r2.font.size = Pt(10)
        r2.font.color.rgb = BLUE

    # Stats
    doc.add_paragraph()
    stats = [
        ("Longitud total inspeccionada", f"{totales.get('longitud_total_m', 0):.2f} m".replace(".", ",")),
        ("Numero de secciones", str(totales.get("num_secciones", len(secciones)))),
        ("Numero de fotografias", str(totales.get("num_fotos", 0))),
    ]
    for lbl, val in stats:
        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(2)
        r1 = sp.add_run(f"{lbl}: ")
        r1.bold = True
        r1.font.size = Pt(9)
        r2 = sp.add_run(val)
        r2.font.size = Pt(9)

    page_footer(2)
    doc.add_page_break()

    # ── PAGINAS POR SECCION ───────────────────────────────────────────────
    for s_idx, sec in enumerate(secciones):
        pg = s_idx + 3
        nombre = sec.get("nombre", f"V{s_idx + 1}")
        page_header(f"Informe de Inspeccion - Seccion {sec.get('num', s_idx + 1)}: {nombre}")

        # Cabecera ficha
        ficha = doc.add_table(rows=4, cols=4)
        ficha.style = "Table Grid"
        ficha_data = [
            [("Fecha:", fecha), ("N. de tramo:", str(sec.get("num", ""))), ("Nombre del tramo:", nombre), ("Tiempo:", "Despejado, seco")],
            [("Calle:", calle), ("Pozo inicio:", sec.get("pozo_inicio", nombre)), ("Pozo final:", sec.get("pozo_fin", nombre)), ("Poblacion:", poblacion)],
            [("Longitud tramo:", f"{sec.get('longitud_m', 0):.2f} m".replace('.', ',')),
             ("Diametro:", f"{sec.get('diametro_mm', '')} mm"),
             ("Material:", sec.get("material", "")),
             ("Tipo:", sec.get("tipo_red", report.get("tipo_red", "")))],
            [("Motivo:", report.get("motivo_inspeccion", "Control general del estado")),
             ("Contratista:", "Acometidas Europa S.L."), ("", ""), ("", "")],
        ]
        for row_data, row in zip(ficha_data, ficha.rows):
            for (lbl, val), cell in zip(row_data, row.cells):
                cell.text = ""
                cp = cell.paragraphs[0]
                if lbl:
                    r1 = cp.add_run(f"{lbl} ")
                    r1.bold = True
                    r1.font.size = Pt(8)
                    r1.font.color.rgb = BLUE
                r2 = cp.add_run(val)
                r2.font.size = Pt(8)

        doc.add_paragraph()

        # Tabla de observaciones
        obs_list = sec.get("observaciones_tabla", [])
        if obs_list:
            obs_tbl = doc.add_table(rows=1 + len(obs_list), cols=4)
            obs_tbl.style = "Table Grid"
            obs_hdrs = ["Posicion (m)", "Codigo", "Descripcion / Observacion", "Grav."]
            obs_widths = [Cm(2.5), Cm(2.0), Cm(11.5), Cm(1.5)]
            for i, (h, w) in enumerate(zip(obs_hdrs, obs_widths)):
                cell = obs_tbl.rows[0].cells[i]
                cell.width = w
                shade_cell(cell, "1F4E79")
                cell_text(cell, h, bold=True, color=WHITE, size=8, align=WD_ALIGN_PARAGRAPH.CENTER)

            for o_idx, obs in enumerate(obs_list):
                row = obs_tbl.rows[o_idx + 1]
                fill = "EBF3FB" if o_idx % 2 == 0 else "FFFFFF"
                codigo = obs.get("codigo", "")
                grav = obs.get("gravedad", "")
                pos = obs.get("posicion_m", 0)
                desc = obs.get("descripcion", "")

                for c in row.cells:
                    shade_cell(c, fill)

                cell_text(row.cells[0], f"{pos:.2f}".replace(".", ","), size=8, align=WD_ALIGN_PARAGRAPH.CENTER)
                # Codigo con color segun gravedad
                row.cells[1].text = ""
                cp = row.cells[1].paragraphs[0]
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cr = cp.add_run(codigo)
                cr.bold = True
                cr.font.size = Pt(8)
                if grav in GRAV_BG:
                    cr.font.color.rgb = WHITE
                    shade_cell(row.cells[1], GRAV_BG[grav])

                cell_text(row.cells[2], desc, size=8)
                # Gravedad badge
                if grav and grav not in ("", "-"):
                    grav_color = {"A": RED, "B": ORANGE, "C": YELLOW, "D": GREEN}.get(grav, GRAY)
                    row.cells[3].text = ""
                    gp = row.cells[3].paragraphs[0]
                    gp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    gr = gp.add_run(grav)
                    gr.bold = True
                    gr.font.size = Pt(9)
                    gr.font.color.rgb = grav_color
                else:
                    cell_text(row.cells[3], "", size=8)

        page_footer(pg)
        if s_idx < len(secciones) - 1:
            doc.add_page_break()

    # ── ULTIMA PAGINA: INFO PROYECTO ──────────────────────────────────────
    doc.add_page_break()
    page_header("Informacion de Proyecto")
    info_rows = [
        ("Nombre de proyecto:", proyecto),
        ("Referencia:", num_ref or ""),
        ("Fecha:", fecha),
        ("Calle / Ubicacion:", calle),
        ("Poblacion:", poblacion),
        ("Cliente:", cliente or ""),
        ("Contratista:", "Acometidas Europa Saneamiento Tecnico S.L."),
        ("Direccion:", "Doctor Severo Ochoa, 35, 5-D - 28100 ALCOBENDAS, MADRID"),
        ("Telefono:", "913 862 112"),
        ("E-mail:", "info@saneamientotecnico.es"),
    ]
    for lbl, val in info_rows:
        ip = doc.add_paragraph()
        ip.paragraph_format.space_after = Pt(3)
        r1 = ip.add_run(f"{lbl} ")
        r1.bold = True
        r1.font.size = Pt(10)
        r1.font.color.rgb = BLUE
        r2 = ip.add_run(val)
        r2.font.size = Pt(10)

    page_footer(len(secciones) + 3)
    doc.save(str(output_path))


# ---------------------------------------------------------------------------
# Extract solicitud data from uploaded documents / emails
# ---------------------------------------------------------------------------

_SOLICITUD_SYSTEM = """Eres un asistente administrativo de Acometidas Europa Saneamiento Tecnico S.L.
Tu tarea es leer documentos (correos electronicos, PDFs, capturas de pantalla, memorias) enviados por clientes o administradores de fincas y extraer los datos necesarios para rellenar un presupuesto.

REGLAS:
- Extrae SOLO lo que esta escrito claramente en el documento. No inventes nada.
- Si un dato no aparece, deja el campo como cadena vacia "".
- El campo "servicio" debe ser una descripcion corta del trabajo solicitado (ej: "Desatasco y limpieza de red", "Inspeccion CCTV bajantes").
- El campo "obra" es la direccion completa donde se realizara el trabajo.
- El campo "cliente_nombre" es el nombre de la comunidad, empresa o persona que solicita.
- El campo "administracion" es el nombre de la administracion o administrador de fincas si aparece.
- El campo "provincia" extrae solo la ciudad o provincia (ej: "Madrid", "Barcelona").
- Si hay numero de referencia/expediente del cliente, ponlo en "ref_cliente".
- Responde UNICAMENTE con el JSON. Sin texto fuera del JSON."""

_SOLICITUD_SCHEMA = """{
  "cliente_nombre": "string - nombre del cliente o comunidad",
  "cliente_dir": "string - direccion del cliente",
  "cliente_tel": "string - telefono del cliente",
  "cliente_email": "string - email del cliente",
  "administracion": "string - nombre del administrador o administracion",
  "obra": "string - direccion completa donde se realizara el trabajo",
  "servicio": "string - descripcion corta del servicio solicitado",
  "provincia": "string - ciudad o provincia",
  "ref_cliente": "string - numero de referencia del cliente si existe",
  "notas": "string - cualquier dato relevante no incluido en los campos anteriores"
}"""


def extract_solicitud_data(files: list[Path], api_key: str = "") -> dict:
    """Extract budget form data from uploaded documents/emails using Claude AI."""
    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("API Key de Anthropic no configurada.")
    client = anthropic.Anthropic(api_key=key)

    content: list[dict] = []
    content.append({"type": "text", "text": (
        "Lee el/los siguiente(s) documento(s) y extrae los datos del presupuesto.\n"
        f"Devuelve UNICAMENTE un JSON con este esquema:\n{_SOLICITUD_SCHEMA}\n\n"
        "DOCUMENTOS:\n"
    )})

    img_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    txt_ext = {".txt", ".eml", ".msg", ".html", ".htm", ".csv"}

    for fp in files:
        suf = fp.suffix.lower()
        if suf in img_ext:
            data, mt = _encode_image(fp)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
        elif suf == ".pdf":
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": _encode_pdf(fp)},
            })
        elif suf in txt_ext:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = fp.read_text(errors="replace")
            content.append({"type": "text", "text": f"\n--- DOCUMENTO: {fp.name} ---\n{text[:8000]}\n"})
        else:
            # Try to read as text anyway
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                content.append({"type": "text", "text": f"\n--- ARCHIVO: {fp.name} ---\n{text[:4000]}\n"})
            except Exception:
                pass  # Skip unreadable files

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_SOLICITUD_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    return json.loads(raw.strip())


# ---------------------------------------------------------------------------
# Extract partidas from a subcontractor's budget document
# ---------------------------------------------------------------------------

_SUBCONTRATA_SYSTEM = """Eres un asistente tecnico de Acometidas Europa Saneamiento Tecnico S.L.
Tu tarea es leer presupuestos de subcontratas o de otras empresas (PDF, imagen o texto) y extraer TODAS las partidas o lineas de trabajo con sus datos economicos.

REGLAS:
- Extrae TODAS las partidas/lineas que aparezcan en el documento, sin omitir ninguna.
- Si una linea no tiene precio unitario pero si importe total y cantidad, calcula: precio_unitario = importe / cantidad.
- Si solo hay importe total sin cantidad, pon cantidad=1 y precio_unitario=importe_total.
- Normaliza las unidades: "m.l." -> "ml", "m2" -> "m2", "Ud." -> "ud", "PA" -> "PA", etc.
- Si el documento tiene capitulos o secciones, incluye el nombre del capitulo como prefijo en la descripcion (ej: "CAPITULO 1 - Excavacion y demolicion").
- Los precios SIEMPRE en formato numerico (float), sin simbolo de euro.
- Si no puedes leer un valor claramente, ponlo a 0.
- Responde UNICAMENTE con el JSON. Sin texto fuera del JSON."""

_SUBCONTRATA_SCHEMA = """{
  "empresa": "string - nombre de la empresa subcontratista si aparece",
  "referencia": "string - numero de presupuesto o referencia si aparece",
  "partidas": [
    {
      "descripcion": "string - descripcion completa de la partida",
      "unidad": "string - ud, ml, m2, m3, PA, kg, h, etc.",
      "cantidad": 0.0,
      "precio_unitario": 0.0,
      "importe": 0.0
    }
  ],
  "total": 0.0,
  "notas": "string - observaciones relevantes del presupuesto"
}"""


def extract_partidas_from_subcontrata(files: list[Path], api_key: str = "") -> dict:
    """Extract all budget line items from a subcontractor's budget document."""
    key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError("API Key de Anthropic no configurada.")
    client = anthropic.Anthropic(api_key=key)

    content: list[dict] = []
    content.append({"type": "text", "text": (
        "Lee este presupuesto de subcontrata y extrae TODAS las partidas con sus datos economicos.\n"
        f"Devuelve UNICAMENTE un JSON con este esquema:\n{_SUBCONTRATA_SCHEMA}\n\n"
        "PRESUPUESTO:\n"
    )})

    img_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    txt_ext = {".txt", ".eml", ".html", ".htm", ".csv", ".xml"}

    for fp in files:
        suf = fp.suffix.lower()
        if suf in img_ext:
            data, mt = _encode_image(fp)
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
        elif suf == ".pdf":
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": _encode_pdf(fp)},
            })
        elif suf in txt_ext:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = fp.read_text(errors="replace")
            content.append({"type": "text", "text": f"\n--- DOCUMENTO: {fp.name} ---\n{text[:12000]}\n"})
        else:
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
                content.append({"type": "text", "text": f"\n--- ARCHIVO: {fp.name} ---\n{text[:6000]}\n"})
            except Exception:
                pass

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SUBCONTRATA_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    result = json.loads(raw.strip())

    # Recalculate importe for each partida to ensure consistency
    for p in result.get("partidas", []):
        try:
            p["cantidad"] = float(p.get("cantidad") or 1)
            p["precio_unitario"] = float(p.get("precio_unitario") or 0)
            p["importe"] = round(p["cantidad"] * p["precio_unitario"], 2)
        except (TypeError, ValueError):
            p["cantidad"] = 1.0
            p["precio_unitario"] = 0.0
            p["importe"] = 0.0

    return result
