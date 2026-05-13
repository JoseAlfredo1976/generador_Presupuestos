#!/usr/bin/env python3
"""
Descarga las plantillas desde Google Drive usando gdown.
Uso: python download_templates.py

Requiere: pip install gdown
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
TARIFAS_DIR = BASE_DIR / "tarifas"

TEMPLATES = {
    # 01 PRESUPUESTOS DESATASCOS
    "MODELO_DESATASCO.docx":            "1N8Iwt9w0nC_rt4J1CQhRTM6Zgf2dE7S_",
    "MODELO_CCTV_BAJANTE.docx":         "1FCh_ZtI2plyR811k5YJx1Kyx3SQTIoIL",
    "MODELO_INSPECCION_ZUM.docx":       "1dx5PN146DP_eMy2XcInYZfxqSYc2EDa2",
    "MODELO_LIMPIEZA_AEREA.docx":       "1ULfQY_s1S2aEMFbmMbi_SOmzWFg3s-xs",
    "MODELO_FRESADOR.docx":             "1rEDlfRUzwe64J0T-3nj8O0wFDSrHLLL_",
    "MODELO_ROBOT_LIMPIEZA.docx":       "1mpKh29I4g9YKFTU04OAZ_zwvPvTM4ELZ",
    "MODELO_FUGA_AGUA.docx":            "1B-XaFVntWQMXZFsT-D1xYnHyhb00fXSg",
    "MODELO_VACIADO_FOSA.docx":         "1t1gO2I9QWc58cgDXkZSXyrQzs3W5Cmy5",
    # 02 PRESUPUESTOS OBRA
    "MODELO_MAESTRO_1OPCION.docx":      "1Pr1KU3bE-7Uave53WzVkUXPR1fV-Mxrc",
    "MODELO_MAESTRO_2OPCIONES.docx":    "1IvnbvsFkm4bjzFjwVDSmYkxwZmYFolU5",
    # 03 INFORMES
    "MODELO_INFORME_DESATASCO.docx":    "1QTY7E3j0ACGVeKedtJnigUr6IXEVE3Xn",
    # 04 CONTRATOS
    "MODELO_CONTRATO_SANEAMIENTO.docx": "10TNQrx_bFN4eLYXHmhcNQj7Y0a_zYK_J",
    "MODELO_CONTRATO_BOMBEO.doc":       "19ggAFXCo36qsZvQBsktv5x9lb7at0lXI",
    # 05 PRL Y CERTIFICADOS
    "MODELO_PLAN_SEGURIDAD.docx":       "1_NjvTVlvh0AdGQKLrzyr8kul_tQvFMcH",
    "MODELO_CERTIFICADO_OBRA.docx":     "1FFzXb6R3mTLYEIc_4hYrpB1HQnas0eJn",
    # 06 AMIANTO
    "MODELO_BAJANTES_AMIANTO.docx":     "1_XosYxVkXMvC4mUtaI9dJydvtnhQQzy7",
}
TARIFAS_ID = "1hrIuXd6vgVHITd096pWJwCzGlPBgspor"


def main():
    try:
        import gdown
    except ImportError:
        print("Instalando gdown...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "gdown", "-q"], check=True)
        import gdown

    TEMPLATES_DIR.mkdir(exist_ok=True)
    TARIFAS_DIR.mkdir(exist_ok=True)

    for filename, file_id in TEMPLATES.items():
        dest = TEMPLATES_DIR / filename
        if not dest.exists():
            print(f"Descargando {filename} ...")
            gdown.download(id=file_id, output=str(dest), quiet=False)
        else:
            print(f"Ya existe: {filename}")

    tarifas_out = TARIFAS_DIR / "TARIFAS.xlsx"
    if not tarifas_out.exists():
        print(f"Descargando TARIFAS.xlsx ...")
        gdown.download(id=TARIFAS_ID, output=str(tarifas_out), quiet=False)
    else:
        print(f"Ya existe: TARIFAS.xlsx")

    print("\n✓ Listo. Ejecuta: python app.py")


if __name__ == "__main__":
    main()
