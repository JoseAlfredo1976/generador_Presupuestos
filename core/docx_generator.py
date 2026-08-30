"""
DOCX generation: fills [[VARIABLE]] placeholders in the Word template.
Handles:
  - Variables split across XML runs
  - Headers and footers (word/header*.xml, word/footer*.xml)
  - Multiple line items in mediciones tables (1 or 2 opciones)
  - Multi-paragraph text fields
"""
import re
import zipfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from lxml import etree

WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WNS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

MULTILINE_VARS = {"[[INFORME_TECNICO]]", "[[SOLUCION_ADOPTAR]]", "[[MEMORIA_TECNICA]]",
                  "[[MEMORIA_TRADICIONAL]]", "[[MEMORIA_MULTILINER]]"}

# Formato forzado al insertar texto en estos placeholders: (fuente, tamano_halfpt, negrita)
_FORCED_FORMAT: dict[str, tuple[str, str, bool]] = {
    "[[INFORME_TECNICO]]":    ("Calibri", "22", False),   # 11pt
    "[[SOLUCION_ADOPTAR]]":   ("Calibri", "22", False),
    "[[MEMORIA_TECNICA]]":    ("Calibri", "22", False),
    "[[MEMORIA_TRADICIONAL]]":("Calibri", "22", False),
    "[[MEMORIA_MULTILINER]]": ("Calibri", "22", False),
    "[[FECHA_LARGA]]":        ("Calibri", "24", False),   # 12pt
}

# Parrafos que deben eliminarse por completo (no solo vaciarse) cuando su
# placeholder resuelve a cadena vacia. Usado para no dejar etiquetas o lineas
# huerfanas (p.ej. "ADMINISTRACION:" sin dato) en la portada.
_COLLAPSE_IF_EMPTY = {
    "[[ADMINISTRACION]]",
    "[[ADMINISTRACION_LABEL]]",
    "[[ADMINISTRACION_TELEFONO]]",
    "[[ADMINISTRACION_CORREO ELECTRONICO]]",
    "[[ADMINISTRACION_CORREOELECTRONICO]]",
    "[[ADMINISTRACION_PROVINCIA]]",
}


def _w(tag: str) -> str:
    return f"{W}{tag}"


class DocxGenerator:
    def __init__(self, template_path: Path):
        self.template_path = template_path

    def generate(self, output_path: Path, data: dict,
                 items: list[dict] | None = None,
                 items_a: list[dict] | None = None,
                 items_b: list[dict] | None = None,
                 subc_items: list[dict] | None = None):
        with open(self.template_path, "rb") as f:
            buf = BytesIO(f.read())

        out_buf = BytesIO()
        with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for zi in zin.infolist():
                raw = zin.read(zi.filename)
                name = zi.filename
                if name == "word/document.xml":
                    raw = self._process_document_xml(raw, data, items, items_a, items_b, subc_items)
                elif (name.startswith("word/header") or name.startswith("word/footer")) and name.endswith(".xml"):
                    raw = self._process_simple_xml(raw, data)
                zout.writestr(zi, raw)

        output_path.write_bytes(out_buf.getvalue())

    # ------------------------------------------------------------------
    # Per-part processors
    # ------------------------------------------------------------------
    def _process_document_xml(self, raw: bytes, data: dict,
                               items, items_a, items_b, subc_items) -> bytes:
        root = etree.fromstring(raw)
        self._merge_split_placeholders(root)
        paras_to_remove = []
        for para in root.iter(_w("p")):
            self._replace_in_paragraph(para, data, paras_to_remove)
        self._remove_collapsed_paragraphs(paras_to_remove)
        if items:
            self._expand_mediciones_table(root, items, "[[DESCRIPCION_PARTIDA]]")
        if items_a:
            self._expand_mediciones_table(root, items_a, "[[DESCRIPCION_PARTIDA_A]]")
        if items_b:
            self._expand_mediciones_table(root, items_b, "[[DESCRIPCION_PARTIDA_B]]")
        if subc_items:
            self._expand_subcontrata_table(root, subc_items)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def _process_simple_xml(self, raw: bytes, data: dict) -> bytes:
        try:
            root = etree.fromstring(raw)
        except etree.XMLSyntaxError:
            return raw
        self._merge_split_placeholders(root)
        paras_to_remove = []
        for para in root.iter(_w("p")):
            self._replace_in_paragraph(para, data, paras_to_remove)
        self._remove_collapsed_paragraphs(paras_to_remove)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def _remove_collapsed_paragraphs(self, paras_to_remove: list):
        for para in paras_to_remove:
            parent = para.getparent()
            if parent is not None:
                parent.remove(para)

    # ------------------------------------------------------------------
    # Step 1: merge ONLY the runs where [[PLACEHOLDER]] is split
    # ------------------------------------------------------------------
    def _merge_split_placeholders(self, root):
        """Merge adjacent runs only when [[ appears without its closing ]]."""
        for para in root.iter(_w("p")):
            self._merge_split_in_para(para)

    def _merge_split_in_para(self, para):
        changed = True
        while changed:
            changed = False
            runs = list(para.findall(_w("r")))
            for i, r in enumerate(runs):
                txt = "".join(t.text or "" for t in r.findall(_w("t")))
                if txt.count("[[") > txt.count("]]") and i + 1 < len(runs):
                    self._merge_two_runs(para, r, runs[i + 1])
                    changed = True
                    break

    def _merge_two_runs(self, para, run_a, run_b):
        """Append run_b's text into run_a, preserving run_a formatting."""
        text_a = "".join(t.text or "" for t in run_a.findall(_w("t")))
        text_b = "".join(t.text or "" for t in run_b.findall(_w("t")))
        for t in list(run_a.findall(_w("t"))):
            run_a.remove(t)
        t_elem = etree.SubElement(run_a, _w("t"))
        t_elem.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t_elem.text = text_a + text_b
        para.remove(run_b)

    # ------------------------------------------------------------------
    # Step 2: replace variables in a paragraph
    # ------------------------------------------------------------------
    def _replace_in_paragraph(self, para, data: dict, paras_to_remove: list | None = None):
        for run in para.findall(_w("r")):
            for t in run.findall(_w("t")):
                if not t.text:
                    continue
                original_text = t.text
                stripped = original_text.strip()
                new_text = t.text
                matched_ph = None
                for placeholder, value in data.items():
                    if placeholder in new_text:
                        new_text = new_text.replace(placeholder, str(value) if value is not None else "")
                        if matched_ph is None:
                            matched_ph = placeholder
                if new_text != t.text:
                    t.text = new_text
                    # Apply forced formatting if configured
                    if matched_ph and matched_ph in _FORCED_FORMAT:
                        self._apply_run_format(run, *_FORCED_FORMAT[matched_ph])
                # Si el run es EXACTAMENTE uno o varios placeholders marcados para
                # colapsar (p.ej. "[[ADMINISTRACION]] [[ADMINISTRACION_PROVINCIA]]")
                # y TODOS sus valores resueltos estan vacios, elimina el parrafo
                # entero (no solo el texto), para no dejar lineas/etiquetas huerfanas.
                if paras_to_remove is not None and stripped:
                    tokens = stripped.split()
                    if tokens and all(tok in _COLLAPSE_IF_EMPTY for tok in tokens):
                        if all(not (data.get(tok) and str(data.get(tok)).strip()) for tok in tokens):
                            paras_to_remove.append(para)

    def _apply_run_format(self, run, font_name: str, sz_halfpt: str, bold: bool):
        """Force font/size/color on a run."""
        rpr = run.find(_w("rPr"))
        if rpr is None:
            rpr = etree.Element(_w("rPr"))
            run.insert(0, rpr)
        # Font
        rfonts = rpr.find(_w("rFonts"))
        if rfonts is None:
            rfonts = etree.SubElement(rpr, _w("rFonts"))
        for attr in ("ascii", "hAnsi", "cs"):
            rfonts.set(_w(attr), font_name)
        # Size
        sz = rpr.find(_w("sz"))
        if sz is None:
            sz = etree.SubElement(rpr, _w("sz"))
        sz.set(_w("val"), sz_halfpt)
        szCs = rpr.find(_w("szCs"))
        if szCs is None:
            szCs = etree.SubElement(rpr, _w("szCs"))
        szCs.set(_w("val"), sz_halfpt)
        # Color: black
        color = rpr.find(_w("color"))
        if color is None:
            color = etree.SubElement(rpr, _w("color"))
        color.set(_w("val"), "000000")
        color.attrib.pop(_w("themeColor"), None)
        # Bold
        b_el = rpr.find(_w("b"))
        if bold and b_el is None:
            etree.SubElement(rpr, _w("b"))
        elif not bold and b_el is not None:
            rpr.remove(b_el)

    # ------------------------------------------------------------------
    # Step 3: expand mediciones table
    # ------------------------------------------------------------------
    def _expand_mediciones_table(self, root, items: list[dict], placeholder: str):
        if not items:
            return

        for tbl in root.iter(_w("tbl")):
            template_tr = None
            for tr in tbl.findall(_w("tr")):
                row_text = "".join(
                    (t.text or "") for t in tr.iter(_w("t"))
                )
                if placeholder in row_text:
                    template_tr = tr
                    break

            if template_tr is None:
                continue

            parent = template_tr.getparent()
            idx = list(parent).index(template_tr)

            for i, item in enumerate(items):
                new_tr = deepcopy(template_tr)
                self._fill_item_row(new_tr, item)
                parent.insert(idx + i, new_tr)

            parent.remove(template_tr)

    def _fill_item_row(self, tr, item: dict):
        cells = tr.findall(f".//{_w('tc')}")
        # Column order: DESCRIPCION | UD | UDS/CANTIDAD | PRECIO_UNITARIO | IMPORTE
        mapping = {
            0: item.get("descripcion", ""),
            1: item.get("unidad", "PA"),
            2: _fmt_qty(item.get("cantidad", 1)),
            3: _fmt_euro(item.get("precio_unitario", 0)),
            4: _fmt_euro(item.get("importe", 0)),
        }
        for col_idx, cell in enumerate(cells):
            if col_idx not in mapping:
                continue
            for t in cell.iter(_w("t")):
                text = t.text or ""
                if "[[" in text:
                    t.text = mapping[col_idx]
            # Force black color on all runs in the cell
            for run in cell.iter(_w("r")):
                rpr = run.find(_w("rPr"))
                if rpr is None:
                    rpr = etree.Element(_w("rPr"))
                    run.insert(0, rpr)
                color = rpr.find(_w("color"))
                if color is None:
                    color = etree.SubElement(rpr, _w("color"))
                color.set(_w("val"), "000000")
                color.attrib.pop(_w("themeColor"), None)

        # Auto-height
        trpr = tr.find(_w("trPr"))
        if trpr is None:
            trpr = etree.Element(_w("trPr"))
            tr.insert(0, trpr)
        trh = trpr.find(_w("trHeight"))
        if trh is None:
            trh = etree.SubElement(trpr, _w("trHeight"))
        trh.set(_w("val"), "0")
        trh.set(_w("hRule"), "auto")


    # ------------------------------------------------------------------
    # Subcontrata table: 4 columns (desc | qty | price | total)
    # ------------------------------------------------------------------
    def _expand_subcontrata_table(self, root, items: list[dict]):
        """Expand the 4-column partidas table in subcontrata contracts."""
        if not items:
            return
        placeholder = "[[DESCRIPCION_PARTIDA]]"
        for tbl in root.iter(_w("tbl")):
            template_tr = None
            for tr in tbl.findall(_w("tr")):
                row_text = "".join((t.text or "") for t in tr.iter(_w("t")))
                if placeholder in row_text:
                    template_tr = tr
                    break
            if template_tr is None:
                continue

            parent = template_tr.getparent()
            idx = list(parent).index(template_tr)
            for i, item in enumerate(items):
                new_tr = deepcopy(template_tr)
                self._fill_subc_row(new_tr, item)
                parent.insert(idx + i, new_tr)
            parent.remove(template_tr)

    def _fill_subc_row(self, tr, item: dict):
        """Fill a 4-column subcontrata row: desc | qty | price | total."""
        cells = list(tr.findall(f".//{_w('tc')}"))
        mapping = {
            0: item.get("descripcion", ""),
            1: _fmt_qty(item.get("cantidad", 1)),
            2: _fmt_euro(item.get("precio_unitario", 0)),
            3: _fmt_euro(item.get("importe", 0)),
        }
        for col_idx, cell in enumerate(cells):
            if col_idx not in mapping:
                continue
            for t in cell.iter(_w("t")):
                if t.text and "[[" in t.text:
                    t.text = mapping[col_idx]
            for run in cell.iter(_w("r")):
                rpr = run.find(_w("rPr"))
                if rpr is None:
                    rpr = etree.Element(_w("rPr"))
                    run.insert(0, rpr)
                color = rpr.find(_w("color"))
                if color is None:
                    color = etree.SubElement(rpr, _w("color"))
                color.set(_w("val"), "000000")
                color.attrib.pop(_w("themeColor"), None)
        trpr = tr.find(_w("trPr"))
        if trpr is None:
            trpr = etree.Element(_w("trPr"))
            tr.insert(0, trpr)
        trh = trpr.find(_w("trHeight"))
        if trh is None:
            trh = etree.SubElement(trpr, _w("trHeight"))
        trh.set(_w("val"), "0")
        trh.set(_w("hRule"), "auto")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _fmt_euro(amount: float) -> str:
    s = f"{amount:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_qty(qty: float) -> str:
    if qty == int(qty):
        return str(int(qty))
    return str(qty).replace(".", ",")
