"""
Lee y escribe la configuracion de la app (config/app_config.json).
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "app_config.json"

_DEFAULTS = {
    "output_base_path": "",
    "output_subfolder": "PRESUPUESTOS GRUPO EUROPA",
}


def load() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Rellenar claves que falten con defaults
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_DEFAULTS)


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_output_base() -> Path | None:
    """Devuelve la ruta base configurada, o None si no esta definida o no existe."""
    cfg = load()
    raw = (cfg.get("output_base_path") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.exists():
        return None
    return p
