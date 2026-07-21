"""Adaptadores de infraestructura para archivos Excel (openpyxl).

Aísla toda la lectura/escritura de `.xlsx`; no contiene reglas de negocio.
"""

from fijazo_api.infrastructure.excel.columns import COLUMNS, ColumnSpec

__all__ = ["COLUMNS", "ColumnSpec"]
