"""
core/mediciones.py - Mediciones de redes de saneamiento sobre plano.

Una "obra" es un dict (se guarda como obra.json) con la red dibujada sobre el plano:

    {
      "id": "2141-26_gavilanes", "nombre": "...", "ref": "2141/26",
      "plano": {"archivo": "plano.jpg", "w": 2000, "h": 1415},
      "escala_px_m": null,
      "tramos":   [{"id": "V1", "pts": [[x, y], ...] | null, "dn": "250", "long": 8.5,
                    "estado": "" | "ajuste" | "revisar", "nota": ""}],
      "arquetas": [{"id": "A1", "x": 0, "y": 0, "medida": "90x90", "prof": 0.6, "nota": ""}],
      "pozos":    [{"id": "P1", "x": 0, "y": 0, "prof": 2.6, "tipo": "reconstruir" | "nuevo",
                    "diam": 100, "nota": ""}],
      "arquetas_sin_localizar": {"n": 0, "medida": "40x40"},
      "verificacion": {"T:V1": "ok" | "duda"}
    }

dn de un tramo: "160", "200", "250", "300", "400", "500", "GAL" (galería visitable)
o "RAM" (ramal no grabado, se asume <= DN200).

Reglas de partidas (fijadas con J.A. en la obra Gavilanes n.º 1, nov. 2026):
- Cada tramo se redondea al metro superior y se suma por diámetro.
- Manga continua: REB-200 para DN160, DN200 y ramales (no existe REB-160);
  REB-250/300/400/500 para el resto. Galería visitable: GAL-RECON-PVC.
- Todas las arquetas llevan reconstrucción + tapa de su medida (ARQ-RECON-xxxx + TAPA-xxxx).
- Pozos: reconstrucción RECON-<prof. redondeada a metro> o construcción POZ-<diam>-<prof>;
  todos llevan tapa (la tarifa no tiene tapa circular: se aplica TAPA-6060).
- Solo se usan códigos de la tarifa; si falta alguno se devuelve en "faltan".
"""
from __future__ import annotations

import math
import re
from datetime import datetime

DN_ORDEN = ["160", "200", "RAM", "250", "300", "400", "500", "GAL"]
DN_NOMBRE = {"160": "DN160", "200": "DN200", "RAM": "Ramales sin grabar (<=DN200)", "250": "DN250",
             "300": "DN300", "400": "DN400", "500": "DN500", "GAL": "Galería visitable"}
MEDIDAS = ["100x100", "90x90", "80x80", "70x70", "60x60", "50x50", "40x40", "30x30"]


def alza(v) -> int:
    """Redondeo al metro superior (8,01 -> 9; 8,00 -> 8)."""
    if v is None:
        return 0
    return int(math.ceil(float(v) - 1e-9))


def codigo_manga(dn: str) -> str:
    if dn in ("160", "200", "RAM"):
        return "REB-200"
    if dn == "GAL":
        return "GAL-RECON-PVC"
    return f"REB-{dn}"


def _mm(medida: str) -> str:
    a, b = re.findall(r"\d+", medida)[:2]
    return f"{a}{b}"


def resumen(obra: dict) -> dict:
    """Totales por diámetro, arquetas por medida y pozos."""
    por_dn: dict[str, dict] = {}
    for t in obra.get("tramos", []):
        dn = str(t.get("dn", "")).upper()
        g = por_dn.setdefault(dn, {"dn": dn, "nombre": DN_NOMBRE.get(dn, dn), "n": 0,
                                   "exacto": 0.0, "alza": 0, "sin_cota": [], "tramos": []})
        g["n"] += 1
        g["tramos"].append(t.get("id"))
        if t.get("long") in (None, ""):
            g["sin_cota"].append(t.get("id"))
        else:
            g["exacto"] += float(t["long"])
            g["alza"] += alza(t["long"])
    tuberias = [por_dn[k] for k in DN_ORDEN if k in por_dn] + \
               [v for k, v in por_dn.items() if k not in DN_ORDEN]
    for g in tuberias:
        g["exacto"] = round(g["exacto"], 2)

    arq: dict[str, int] = {}
    for a in obra.get("arquetas", []):
        arq[a.get("medida", "40x40")] = arq.get(a.get("medida", "40x40"), 0) + 1
    sl = obra.get("arquetas_sin_localizar") or {}
    n_sl = int(sl.get("n") or 0)
    arquetas = [{"medida": m, "n": arq[m]} for m in sorted(arq, key=lambda m: -int(_mm(m)))]

    pozos = obra.get("pozos", [])
    return {
        "tuberias": tuberias,
        "total_exacto": round(sum(g["exacto"] for g in tuberias), 2),
        "total_alza": sum(g["alza"] for g in tuberias),
        "arquetas": arquetas,
        "arquetas_sin_localizar": {"n": n_sl, "medida": sl.get("medida", "40x40")},
        "total_arquetas": sum(arq.values()) + n_sl,
        "pozos": {"total": len(pozos),
                  "reconstruir": sum(1 for p in pozos if p.get("tipo", "reconstruir") != "nuevo"),
                  "nuevos": sum(1 for p in pozos if p.get("tipo") == "nuevo")},
    }


def partidas(obra: dict, tarifas) -> dict:
    """Partidas valoradas por capítulos. `tarifas` es un utils.tarifa_loader.TarifaLoader."""
    faltan: list[str] = []
    cap: dict[str, dict[str, dict]] = {k: {} for k in
                                       ("manga", "galeria", "arquetas", "tapas", "pozos")}

    def add(capk, code, qty, origen):
        if qty <= 0:
            return
        line = cap[capk].setdefault(code, {"codigo": code, "cantidad": 0, "origen": []})
        line["cantidad"] += qty
        line["origen"].append(origen)

    for t in obra.get("tramos", []):
        dn = str(t.get("dn", "")).upper()
        q = alza(t.get("long"))
        add("galeria" if dn == "GAL" else "manga", codigo_manga(dn), q, t.get("id"))

    arqs = list(obra.get("arquetas", []))
    sl = obra.get("arquetas_sin_localizar") or {}
    for a in arqs:
        mm = _mm(a.get("medida", "40x40"))
        add("arquetas", f"ARQ-RECON-{mm}", 1, a.get("id"))
        add("tapas", f"TAPA-{mm}", 1, a.get("id"))
    if int(sl.get("n") or 0):
        mm = _mm(sl.get("medida", "40x40"))
        add("arquetas", f"ARQ-RECON-{mm}", int(sl["n"]), "sin localizar")
        add("tapas", f"TAPA-{mm}", int(sl["n"]), "sin localizar")

    for p in obra.get("pozos", []):
        prof = max(1, alza(p.get("prof") or 1)) * 100
        if p.get("tipo") == "nuevo":
            add("pozos", f"POZ-{int(p.get('diam') or 100)}-{prof}", 1, p.get("id"))
        else:
            add("pozos", f"RECON-{prof}", 1, p.get("id"))
        add("tapas", "TAPA-6060", 1, p.get("id"))

    titulos = {"manga": "REHABILITACIÓN DE COLECTORES CON MANGA CONTINUA",
               "galeria": "RECONSTRUCCIÓN DE GALERÍA VISITABLE",
               "arquetas": "RECONSTRUCCIÓN DE ARQUETAS",
               "tapas": "TAPAS DE REGISTRO", "pozos": "POZOS DE REGISTRO"}
    capitulos, total, n = [], 0.0, 0
    for k in ("manga", "galeria", "arquetas", "tapas", "pozos"):
        if not cap[k]:
            continue
        n += 1
        lineas, sub = [], 0.0
        for code in sorted(cap[k], key=_orden_codigo, reverse=(k == "manga")):
            item = tarifas.lookup(code) if tarifas else None
            if not item:
                faltan.append(code)
                item = {"descripcion": "", "unidad": "", "precio": 0.0}
            ln = cap[k][code]
            unidad = "ml" if k in ("manga", "galeria") else "ud"
            importe = round(ln["cantidad"] * float(item["precio"]), 2)
            sub += importe
            lineas.append({"num": f"{n}.{len(lineas) + 1}", "codigo": code,
                           "descripcion": item["descripcion"], "unidad": unidad,
                           "cantidad": ln["cantidad"], "precio": float(item["precio"]),
                           "importe": importe, "origen": ln["origen"]})
        capitulos.append({"num": n, "titulo": titulos[k], "lineas": lineas, "subtotal": round(sub, 2)})
        total += sub
    return {"capitulos": capitulos, "total_sin_iva": round(total, 2), "faltan": sorted(set(faltan)),
            "generado": datetime.now().isoformat(timespec="seconds")}


def _orden_codigo(code: str):
    nums = [int(x) for x in re.findall(r"\d+", code)]
    return (-(nums[0] if nums else 0), code)


def obra_vacia(oid: str, nombre: str, ref: str, w: int, h: int, archivo: str) -> dict:
    return {"id": oid, "nombre": nombre, "ref": ref,
            "creado": datetime.now().isoformat(timespec="seconds"),
            "plano": {"archivo": archivo, "w": w, "h": h}, "escala_px_m": None,
            "tramos": [], "arquetas": [], "pozos": [],
            "arquetas_sin_localizar": {"n": 0, "medida": "40x40"}, "verificacion": {}}


def excel(obra: dict, tarifas, destino) -> None:
    """Excel con hojas MEDICIONES (tramo a tramo), RESUMEN y PARTIDAS, con fórmulas."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    F = "Arial"
    thin = Side(style="thin", color="999999")
    B = Border(left=thin, right=thin, top=thin, bottom=thin)
    HF = PatternFill("solid", fgColor="4F84B5")
    wb = openpyxl.Workbook()

    def head(ws, row, cols, widths):
        for i, (c, w) in enumerate(zip(cols, widths), 1):
            x = ws.cell(row, i, c)
            x.fill, x.font, x.border = HF, Font(name=F, bold=True, color="FFFFFF"), B
            x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.active
    ws.title = "MEDICIONES"
    ws["A1"] = f"MEDICIONES · {obra.get('nombre', '')} · {obra.get('ref', '')}"
    ws["A1"].font = Font(name=F, bold=True, size=13, color="1F4E79")
    head(ws, 3, ["ELEMENTO", "TIPO", "DN / MEDIDA", "LONG. EXACTA (m)", "ML AL ALZA", "PROF. (m)", "NOTA"],
         [12, 12, 14, 15, 12, 10, 50])
    r = 4
    for t in obra.get("tramos", []):
        vals = [t.get("id"), "Tramo", DN_NOMBRE.get(str(t.get("dn")), t.get("dn")), t.get("long"), None, None,
                t.get("nota", "")]
        for i, v in enumerate(vals, 1):
            ws.cell(r, i, v).border = B
        ws.cell(r, 5, f'=IF(D{r}="","",ROUNDUP(D{r},0))').border = B
        ws.cell(r, 4).number_format = "#,##0.00"
        r += 1
    last = r - 1
    for a in obra.get("arquetas", []):
        for i, v in enumerate([a.get("id"), "Arqueta", a.get("medida"), None, None, a.get("prof"), a.get("nota", "")], 1):
            ws.cell(r, i, v).border = B
        r += 1
    for p in obra.get("pozos", []):
        tipo = "Pozo nuevo" if p.get("tipo") == "nuevo" else "Pozo"
        for i, v in enumerate([p.get("id"), tipo, f"Ø{p.get('diam') or ''}" if p.get("tipo") == "nuevo" else "",
                               None, None, p.get("prof"), p.get("nota", "")], 1):
            ws.cell(r, i, v).border = B
        r += 1
    ws.cell(r + 1, 1, "TOTAL TUBERÍA").font = Font(name=F, bold=True)
    ws.cell(r + 1, 4, f"=SUM(D4:D{last})").number_format = "#,##0.00"
    ws.cell(r + 1, 5, f"=SUM(E4:E{last})")
    ws.freeze_panes = "A4"

    w2 = wb.create_sheet("PARTIDAS")
    w2["A1"] = f"PARTIDAS · {obra.get('nombre', '')}"
    w2["A1"].font = Font(name=F, bold=True, size=13, color="1F4E79")
    head(w2, 3, ["Nº", "CÓDIGO", "DESCRIPCIÓN", "UD", "UDS", "PRECIO", "IMPORTE"], [6, 18, 80, 6, 8, 12, 14])
    p = partidas(obra, tarifas)
    r, subs = 4, []
    for c in p["capitulos"]:
        w2.cell(r, 3, f"{c['num']}. {c['titulo']}").font = Font(name=F, bold=True)
        r += 1
        first = r
        for ln in c["lineas"]:
            for i, v in enumerate([ln["num"], ln["codigo"], ln["descripcion"], ln["unidad"], ln["cantidad"], ln["precio"]], 1):
                x = w2.cell(r, i, v)
                x.border = B
                x.alignment = Alignment(wrap_text=(i == 3), vertical="top")
            w2.cell(r, 7, f"=E{r}*F{r}").border = B
            for col in (6, 7):
                w2.cell(r, col).number_format = "#,##0.00"
            r += 1
        w2.cell(r, 3, f"Subtotal capítulo {c['num']}").font = Font(name=F, bold=True)
        w2.cell(r, 7, f"=SUM(G{first}:G{r - 1})").number_format = "#,##0.00"
        subs.append(f"G{r}")
        r += 2
    for lab, f in (("TOTAL SIN IVA", "=" + "+".join(subs) if subs else 0), ("IVA 21%", f"=G{r}*0.21"),
                   ("TOTAL CON IVA", f"=G{r}+G{r + 1}")):
        w2.cell(r, 3, lab).font = Font(name=F, bold=True)
        w2.cell(r, 7, f).number_format = "#,##0.00 €"
        r += 1
    wb.save(destino)
