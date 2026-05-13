"""
PDF conversion.
Strategy:
  1. Try LibreOffice headless (best fidelity from DOCX).
  2. Fall back to WeasyPrint converting the HTML viewer (always works).
"""
import shutil
import subprocess
from pathlib import Path


class PdfConverter:
    def __init__(self):
        self.soffice = shutil.which("soffice") or shutil.which("libreoffice")

    def convert(self, docx_path: Path, output_dir: Path,
                html_fallback_path: Path | None = None) -> Path | None:
        """
        Try LibreOffice first; if that fails, use WeasyPrint on the HTML file.
        Returns the PDF Path on success, or None if both methods fail.
        """
        pdf_via_lo = self._try_libreoffice(docx_path, output_dir)
        if pdf_via_lo:
            return pdf_via_lo

        if html_fallback_path and html_fallback_path.exists():
            return self._try_weasyprint(html_fallback_path, output_dir, docx_path.stem)

        return None

    # ------------------------------------------------------------------
    def _try_libreoffice(self, docx_path: Path, output_dir: Path) -> Path | None:
        if not self.soffice:
            return None
        try:
            result = subprocess.run(
                [
                    self.soffice,
                    "--headless",
                    "--norestore",
                    "--convert-to", "pdf",
                    "--outdir", str(output_dir.resolve()),
                    str(docx_path.resolve()),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                pdf_path = output_dir / (docx_path.stem + ".pdf")
                if pdf_path.exists():
                    return pdf_path
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def _try_weasyprint(self, html_path: Path, output_dir: Path, stem: str) -> Path | None:
        try:
            import weasyprint
            pdf_path = output_dir / f"{stem}.pdf"
            weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            return pdf_path if pdf_path.exists() else None
        except Exception:
            return None
