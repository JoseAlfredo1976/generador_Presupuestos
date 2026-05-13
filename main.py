#!/usr/bin/env python3
"""
Generador de Presupuestos de Obra – Grupo Europa
Uso: python main.py
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import print as rprint

from core.docx_generator import DocxGenerator
from core.excel_generator import ExcelGenerator
from core.html_generator import HtmlGenerator
from core.pdf_converter import PdfConverter
from utils.tarifa_loader import TarifaLoader

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
TARIFAS_DIR = BASE_DIR / "tarifas"
SALIDAS_DIR = BASE_DIR / "salidas"

console = Console()

TEMPLATE_FILE = TEMPLATES_DIR / "MODELO_MAESTRO.docx"
TARIFAS_FILE = TARIFAS_DIR / "TARIFAS.xlsx"


def check_setup():
    SALIDAS_DIR.mkdir(exist_ok=True)
    if not TEMPLATE_FILE.exists():
        console.print(Panel(
            "[red]Falta la plantilla Word.[/red]\n\n"
            "Copia el archivo [bold]MODELO MAESTRO OBRA PRO DEFINITIVO- 1 OPCION. IA.docx[/bold]\n"
            f"desde Google Drive a: [cyan]{TEMPLATE_FILE}[/cyan]\n\n"
            "Carpeta Drive: GENERADOR DE PRESUPUESTOS / PAQUETE COMPARTIR / PLANTILLAS IA GRUPO EUROPA / 02 PRESUPUESTOS OBRA /",
            title="[yellow]Configuración requerida[/yellow]",
            expand=False,
        ))
        sys.exit(1)


def ask(prompt: str, default: str = "") -> str:
    val = Prompt.ask(f"[cyan]{prompt}[/cyan]", default=default)
    return val.strip()


def ask_date(prompt: str, default_days_offset: int = 0) -> str:
    default_date = (datetime.now() + timedelta(days=default_days_offset)).strftime("%d/%m/%Y")
    raw = ask(prompt, default_date)
    # Normalize to long Spanish date
    try:
        dt = datetime.strptime(raw, "%d/%m/%Y")
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        return f"{dt.day} de {meses[dt.month - 1]} de {dt.year}"
    except ValueError:
        return raw


def collect_items(tarifas: TarifaLoader) -> list[dict]:
    items = []
    console.print("\n[bold yellow]Partidas de obra[/bold yellow] (deja descripción en blanco para terminar)\n")

    while True:
        console.rule(f"Partida {len(items) + 1}")
        desc = ask("Descripción (o código tarifa, ej: ARQ-4040-50)")
        if not desc:
            if not items:
                console.print("[red]Debes añadir al menos una partida.[/red]")
                continue
            break

        # Try to look up in tarifas
        tarifa = tarifas.lookup(desc)
        if tarifa:
            console.print(f"[green]Tarifa encontrada:[/green] {tarifa['descripcion'][:80]}...")
            use_tarifa = Confirm.ask("¿Usar esta tarifa?", default=True)
            if use_tarifa:
                unit = tarifa.get("unidad", "PA")
                default_price = str(tarifa.get("precio", ""))
                full_desc = tarifa["descripcion"]
            else:
                full_desc = desc
                unit = ask("Unidad (PA, m, m², ud...)", "PA")
                default_price = ""
        else:
            full_desc = desc
            unit = ask("Unidad (PA, m, m², ud...)", "PA")
            default_price = ""

        qty_str = ask("Cantidad", "1")
        try:
            qty = float(qty_str.replace(",", "."))
        except ValueError:
            qty = 1.0

        price_str = ask("Precio unitario (€)", default_price)
        try:
            price = float(price_str.replace("€", "").replace(".", "").replace(",", ".").strip())
        except ValueError:
            price = 0.0

        total = qty * price

        items.append({
            "descripcion": full_desc,
            "unidad": unit,
            "cantidad": qty,
            "precio_unitario": price,
            "importe": total,
        })

        # Show running total
        subtotal = sum(i["importe"] for i in items)
        console.print(f"[dim]Subtotal acumulado: {subtotal:,.2f} €[/dim]")

    return items


def format_euro(amount: float) -> str:
    return f"{amount:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    console.print(Panel(
        "[bold blue]GENERADOR DE PRESUPUESTOS DE OBRA[/bold blue]\n[dim]Grupo Europa – Acometidas Europa S.L.[/dim]",
        expand=False,
    ))

    check_setup()

    tarifas = TarifaLoader(TARIFAS_FILE)

    console.print("\n[bold]Datos del presupuesto[/bold]\n")

    num_contrato = ask("Número de contrato (ej: 4680/26)")
    obra = ask("Nombre de la obra / ubicación (ej: C/ Ejemplo 10, Madrid)")
    servicio = ask("Tipo de servicio (ej: Saneamiento, Pocería, Fontanería)")
    provincia = ask("Provincia", "Madrid")

    console.print("\n[bold]Datos del cliente[/bold]\n")
    cliente_nombre = ask("Nombre del cliente / comunidad")
    cliente_dir = ask("Dirección del cliente")
    cliente_tel = ask("Teléfono")
    cliente_email = ask("Email")
    administracion = ask("Administrador/promotor (si aplica)", "")

    console.print("\n[bold]Fechas[/bold]\n")
    fecha_contrato_raw = ask("Fecha del contrato (dd/mm/aaaa)", datetime.now().strftime("%d/%m/%Y"))
    try:
        dt = datetime.strptime(fecha_contrato_raw, "%d/%m/%Y")
        meses = ["enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        fecha_larga = f"{dt.day} de {meses[dt.month-1]} de {dt.year}"
        fecha_contrato = dt.strftime("%d/%m/%Y")
    except ValueError:
        fecha_larga = fecha_contrato_raw
        fecha_contrato = fecha_contrato_raw

    plazo = ask("Plazo de ejecución (días)", "30")
    forma_pago = ask("Forma de pago", "50% al inicio, 50% a la finalización")

    console.print("\n[bold]Textos técnicos[/bold]\n")
    informe = ask("Informe técnico (resumen)", f"Anomalías detectadas en la red de saneamiento del edificio sito en {obra}.")
    solucion = ask("Solución adoptada", f"Reparación de las anomalías existentes en la red de saneamiento.")
    memoria = ask("Memoria técnica (descripción de trabajos)", f"Se realizarán los trabajos necesarios para la reparación y puesta en servicio de la red de saneamiento del edificio.")

    # Collect line items
    items = collect_items(tarifas)

    # Calculate totals
    total_sin_iva = sum(i["importe"] for i in items)
    iva = total_sin_iva * 0.21
    total_con_iva = total_sin_iva + iva

    # Summary table
    console.print()
    table = Table(title="Resumen del presupuesto", show_header=True)
    table.add_column("Descripción", style="white", min_width=40)
    table.add_column("Ud", justify="center")
    table.add_column("Cant.", justify="right")
    table.add_column("Precio", justify="right")
    table.add_column("Importe", justify="right", style="green")
    for item in items:
        table.add_row(
            item["descripcion"][:60] + ("..." if len(item["descripcion"]) > 60 else ""),
            item["unidad"],
            str(item["cantidad"]).rstrip("0").rstrip("."),
            format_euro(item["precio_unitario"]),
            format_euro(item["importe"]),
        )
    table.add_section()
    table.add_row("[bold]TOTAL SIN IVA[/bold]", "", "", "", f"[bold]{format_euro(total_sin_iva)}[/bold]")
    table.add_row("IVA (21%)", "", "", "", format_euro(iva))
    table.add_row("[bold]TOTAL CON IVA[/bold]", "", "", "", f"[bold cyan]{format_euro(total_con_iva)}[/bold cyan]")
    console.print(table)

    if not Confirm.ask("\n¿Generar documentos?", default=True):
        console.print("Cancelado.")
        return

    # Output folder
    num_safe = num_contrato.replace("/", "-").replace("\\", "-")
    obra_safe = obra[:30].replace("/", "-").replace("\\", "-").replace(":", "")
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = SALIDAS_DIR / f"{today}_Presupuesto_{num_safe}_{obra_safe}"
    output_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "[[CONTRATO_NUM]]": num_contrato,
        "[[FECHA_CONTRATO]]": fecha_contrato,
        "[[FECHA_LARGA]]": fecha_larga,
        "[[OBRA_COMUNIDAD]]": obra,
        "[[SERVICIO_COMUNIDAD]]": servicio,
        "[[CLIENTE_NOMBRE]]": cliente_nombre,
        "[[CLIENTE_DIRECCION]]": cliente_dir,
        "[[CLIENTE_TELEFONO]]": cliente_tel,
        "[[CLIENTE_EMAIL]]": cliente_email,
        "[[PROVINCIA]]": provincia,
        "[[ADMINISTRACION]]": administracion or "—",
        "[[INFORME_TECNICO]]": informe,
        "[[SOLUCION_ADOPTAR]]": solucion,
        "[[MEMORIA_TECNICA]]": memoria,
        "[[TOTAL_PRESUPUESTO]]": format_euro(total_sin_iva),
        "[[RESUMEN_VALORACION]]": format_euro(total_sin_iva),
        "[[FORMA_PAGO]]": forma_pago,
        "[[PLAZO_EJECUCION]]": plazo,
        "[[FECHA_INICIO_OBRA_LARGA]]": fecha_larga,
        "[[FECHA_FIN_OBRA]]": "",
    }

    with console.status("[bold green]Generando documentos...[/bold green]"):
        # DOCX
        docx_path = output_dir / f"{today}_Presupuesto_{num_safe}.docx"
        gen = DocxGenerator(TEMPLATE_FILE)
        gen.generate(docx_path, data, items)
        console.print(f"[green]✓[/green] DOCX: {docx_path.name}")

        # Excel
        xlsx_path = output_dir / f"{today}_Valoracion_{num_safe}.xlsx"
        excel_gen = ExcelGenerator()
        excel_gen.generate(xlsx_path, data, items)
        console.print(f"[green]✓[/green] Excel: {xlsx_path.name}")

        # HTML
        html_path = output_dir / f"{today}_Visor_{num_safe}.html"
        html_gen = HtmlGenerator()
        html_gen.generate(html_path, data, items)
        console.print(f"[green]✓[/green] HTML: {html_path.name}")

        # PDF (LibreOffice first, WeasyPrint HTML fallback)
        pdf_conv = PdfConverter()
        pdf_path = pdf_conv.convert(docx_path, output_dir, html_fallback_path=html_path)
        if pdf_path:
            console.print(f"[green]✓[/green] PDF: {pdf_path.name}")
        else:
            console.print("[yellow]⚠[/yellow] PDF: no generado (LibreOffice no disponible)")

    console.print(Panel(
        f"[bold green]¡Documentos generados![/bold green]\n\nCarpeta: [cyan]{output_dir}[/cyan]",
        expand=False,
    ))


if __name__ == "__main__":
    main()
