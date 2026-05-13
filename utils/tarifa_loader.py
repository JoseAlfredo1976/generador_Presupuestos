"""
Loads price table from the TARIFAS Excel and supports code lookups.
"""
from pathlib import Path

import openpyxl


class TarifaLoader:
    def __init__(self, xlsx_path: Path):
        self._items: dict[str, dict] = {}
        if xlsx_path.exists():
            self._load(xlsx_path)

    def _load(self, path: Path):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                code = str(row[0]).strip()
                desc = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                unit = str(row[2]).strip() if len(row) > 2 and row[2] else "PA"
                # Try to parse price from col 4 (index 4) first, fallback to col 3
                price = 0.0
                for col_idx in (4, 3):
                    if len(row) > col_idx and row[col_idx] is not None:
                        raw = str(row[col_idx]).replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
                        try:
                            price = float(raw)
                            break
                        except ValueError:
                            continue
                self._items[code.upper()] = {
                    "codigo": code,
                    "descripcion": desc,
                    "unidad": unit,
                    "precio": price,
                }

    def lookup(self, query: str) -> dict | None:
        """Look up by exact code or fuzzy description match."""
        key = query.strip().upper()
        if key in self._items:
            return self._items[key]
        # Fuzzy: all words of query appear in description
        words = key.split()
        for item in self._items.values():
            if all(w in item["descripcion"].upper() for w in words):
                return item
        return None

    def all_codes(self) -> list[str]:
        return sorted(self._items.keys())

    def all_items(self) -> list[dict]:
        return list(self._items.values())

    def search(self, query: str) -> dict | None:
        """Fuzzy search by any word combination in description."""
        return self.lookup(query)
