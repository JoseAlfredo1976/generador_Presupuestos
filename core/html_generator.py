"""
Generates a self-contained HTML viewer for the budget.
"""
from pathlib import Path
from datetime import datetime


class HtmlGenerator:
    def generate(self, output_path: Path, data: dict, items: list[dict]):
        total_sin_iva = sum(i["importe"] for i in items)
        iva = total_sin_iva * 0.21
        total_con_iva = total_sin_iva + iva

        rows_html = ""
        for item in items:
            rows_html += f"""
            <tr>
                <td>{_esc(item['descripcion'])}</td>
                <td class="center">{_esc(item['unidad'])}</td>
                <td class="right">{_fmt_qty(item['cantidad'])}</td>
                <td class="right">{_fmt_euro(item['precio_unitario'])}</td>
                <td class="right bold">{_fmt_euro(item['importe'])}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Presupuesto {_esc(data.get('[[CONTRATO_NUM]]',''))}</title>
<style>
  :root {{
    --blue: #4F84B5;
    --light: #f5f8fc;
    --border: #d0dce8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Calibri, Arial, sans-serif; color: #222; background: #eef2f7; }}
  .page {{ max-width: 900px; margin: 40px auto; background: white; padding: 48px; box-shadow: 0 2px 12px rgba(0,0,0,.12); }}
  h1 {{ color: var(--blue); font-size: 22px; text-align: center; margin-bottom: 4px; }}
  .subtitle {{ text-align: center; color: #666; font-size: 13px; margin-bottom: 32px; }}
  .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px 32px; margin-bottom: 32px; }}
  .meta-item label {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; }}
  .meta-item p {{ font-size: 14px; color: #333; margin-top: 2px; }}
  .section-title {{
    color: var(--blue);
    font-size: 16px;
    text-align: center;
    border-bottom: 2px solid var(--blue);
    padding-bottom: 6px;
    margin: 28px 0 16px;
  }}
  p.text {{ font-size: 13px; line-height: 1.6; color: #444; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{
    background: var(--blue);
    color: white;
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
  }}
  thead th.right {{ text-align: right; }}
  thead th.center {{ text-align: center; }}
  tbody tr:nth-child(even) {{ background: var(--light); }}
  tbody td {{ padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  td.right {{ text-align: right; }}
  td.center {{ text-align: center; }}
  td.bold {{ font-weight: 600; }}
  .totals-table {{ margin-top: 12px; }}
  .totals-table td {{ padding: 7px 12px; border: 1px solid var(--border); }}
  .totals-table .label {{ text-align: right; font-weight: 500; background: var(--light); }}
  .totals-table .total-final td {{ background: var(--blue); color: white; font-weight: 700; font-size: 15px; }}
  .footer {{ margin-top: 48px; text-align: center; color: #aaa; font-size: 11px; }}
  .signature-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-top: 32px; }}
  .sig-box {{ border: 1px solid var(--border); padding: 16px; border-radius: 4px; }}
  .sig-box h4 {{ font-size: 12px; color: #888; margin-bottom: 40px; }}
  @media print {{ body {{ background: white; }} .page {{ box-shadow: none; margin: 0; }} }}
</style>
</head>
<body>
<div class="page">

  <h1>PRESUPUESTO DE OBRA</h1>
  <p class="subtitle">Grupo Europa – Acometidas Europa S.L. &nbsp;|&nbsp; 91 386 21 12 / 04</p>

  <div class="meta-grid">
    <div class="meta-item">
      <label>Nº Contrato</label>
      <p>{_esc(data.get('[[CONTRATO_NUM]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Fecha</label>
      <p>{_esc(data.get('[[FECHA_LARGA]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Obra / Servicio</label>
      <p>{_esc(data.get('[[OBRA_COMUNIDAD]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Tipo de servicio</label>
      <p>{_esc(data.get('[[SERVICIO_COMUNIDAD]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Cliente</label>
      <p>{_esc(data.get('[[CLIENTE_NOMBRE]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Administrador</label>
      <p>{_esc(data.get('[[ADMINISTRACION]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Forma de pago</label>
      <p>{_esc(data.get('[[FORMA_PAGO]]',''))}</p>
    </div>
    <div class="meta-item">
      <label>Plazo de ejecución</label>
      <p>{_esc(data.get('[[PLAZO_EJECUCION]]',''))} días</p>
    </div>
  </div>

  <h2 class="section-title">Informe técnico</h2>
  <p class="text">{_esc(data.get('[[INFORME_TECNICO]]',''))}</p>

  <h2 class="section-title">Solución adoptada</h2>
  <p class="text">{_esc(data.get('[[SOLUCION_ADOPTAR]]',''))}</p>

  <h2 class="section-title">Memoria técnica</h2>
  <p class="text">{_esc(data.get('[[MEMORIA_TECNICA]]',''))}</p>

  <h2 class="section-title">Mediciones y Presupuesto</h2>
  <table>
    <thead>
      <tr>
        <th>Descripción</th>
        <th class="center">Ud</th>
        <th class="right">Uds</th>
        <th class="right">Precio (€)</th>
        <th class="right">Importe (€)</th>
      </tr>
    </thead>
    <tbody>{rows_html}
    </tbody>
  </table>

  <table class="totals-table">
    <tr>
      <td class="label" style="width:80%">TOTAL PRESUPUESTO (sin IVA)</td>
      <td class="right bold">{_fmt_euro(total_sin_iva)}</td>
    </tr>
    <tr>
      <td class="label">IVA (21%)</td>
      <td class="right">{_fmt_euro(iva)}</td>
    </tr>
    <tr class="total-final">
      <td class="label" style="background:var(--blue);color:white">TOTAL CON IVA</td>
      <td class="right">{_fmt_euro(total_con_iva)}</td>
    </tr>
  </table>

  <h2 class="section-title">Aceptación</h2>
  <p class="text">
    Madrid, a {_esc(data.get('[[FECHA_LARGA]]',''))}<br><br>
    El importe total de la presente oferta asciende a
    <strong>{_fmt_euro(total_sin_iva)}</strong> (IVA no incluido).
  </p>

  <div class="signature-row">
    <div class="sig-box">
      <h4>POR ACOMETIDAS EUROPA S.L.</h4>
      <p style="font-size:12px;color:#888">Firma y sello</p>
    </div>
    <div class="sig-box">
      <h4>EL CLIENTE – {_esc(data.get('[[CLIENTE_NOMBRE]]',''))}</h4>
      <p style="font-size:12px;color:#888">Nombre, DNI y firma</p>
    </div>
  </div>

  <div class="footer">
    Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} &nbsp;·&nbsp;
    Acometidas Europa S.L. &nbsp;·&nbsp; info@acometidas-europa.es
  </div>
</div>
</body>
</html>"""

        output_path.write_text(html, encoding="utf-8")


def _esc(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("\n", "<br>"))


def _fmt_euro(amount: float) -> str:
    s = f"{amount:,.2f} €"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_qty(qty: float) -> str:
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.2f}".replace(".", ",")
