"""
PDF conversion.
Strategy:
  1. Try LibreOffice headless (best fidelity from DOCX).
  2. Fall back to Microsoft Word via COM (Windows con Word instalado).
  3. Fall back to WeasyPrint converting the HTML viewer.
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
        Try LibreOffice, then Microsoft Word (COM), then WeasyPrint on the HTML.
        Returns the PDF Path on success, or None if all methods fail.
        """
        pdf_via_lo = self._try_libreoffice(docx_path, output_dir)
        if pdf_via_lo:
            return pdf_via_lo

        pdf_via_word = self._try_word(docx_path, output_dir)
        if pdf_via_word:
            return pdf_via_word

        if html_fallback_path and html_fallback_path.exists():
            return self._try_weasyprint(html_fallback_path, output_dir, docx_path.stem)

        return None

    # ------------------------------------------------------------------
    def _try_word(self, docx_path: Path, output_dir: Path) -> Path | None:
        """Convierte DOCX a PDF usando Microsoft Word instalado (via COM/pywin32)."""
        pdf_path = output_dir / (docx_path.stem + ".pdf")
        word = None
        pythoncom = None
        try:
            import pythoncom  # type: ignore
            import win32com.client as win32  # type: ignore
        except ImportError:
            return None
        try:
            pythoncom.CoInitialize()
            word = win32.DispatchEx("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(docx_path.resolve()), ReadOnly=True)
            # 17 = wdFormatPDF
            doc.SaveAs(str(pdf_path.resolve()), FileFormat=17)
            doc.Close(False)
            return pdf_path if pdf_path.exists() else None
        except Exception:
            return None
        finally:
            try:
                if word is not None:
                    word.Quit()
            except Exception:
                pass
            try:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()
            except Exception:
                pass

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
