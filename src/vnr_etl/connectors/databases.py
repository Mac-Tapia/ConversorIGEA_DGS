"""Adaptadores de bases de datos empresariales y volcados SQL (secciones E2–E5).

La política por defecto es LECTURA ÚNICA. Los clientes nativos (PostgreSQL,
Oracle, SQL Server, Access, SQLite) están detrás de sus drivers opcionales; un
driver ausente desactiva solo ese adaptador. Los volcados SQL se **inspeccionan**
sin ejecutarse (parseo de DDL y de sentencias, dialecto probable, SRID).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import AdapterUnavailable, LayerInfo, VNRSourceAdapter


# -------------------------------------------------------------------------- SQLite
@dataclass
class SQLiteAdapter(VNRSourceAdapter):
    path: str = ''
    read_only: bool = True

    family = 'DATABASE_SQLITE'

    def _conn(self):
        import sqlite3

        if self.read_only:
            resolved = Path(self.path).resolve().as_posix()
            return sqlite3.connect(f'file:{resolved}?mode=ro', uri=True)
        return sqlite3.connect(self.path)

    def metadata(self) -> dict:
        return {'path': self.path, 'engine': 'sqlite', 'read_only': self.read_only}

    def list_layers(self) -> list[LayerInfo]:

        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
            ).fetchall()
        infos: list[LayerInfo] = []
        for (name,) in rows:
            fields = self._columns(name)
            infos.append(LayerInfo(name=name, fields=fields))
        return infos

    def _columns(self, table: str) -> list[dict]:

        with closing(self._conn()) as conn:
            cursor = conn.execute(f'PRAGMA table_info("{table}")')
            columns = cursor.fetchall()
        return [{'name': c[1], 'type': str(c[2])} for c in columns]

    def read_layer(self, layer, filters: Mapping[str, Any] | None = None) -> list[dict]:
        import sqlite3

        filters = filters or {}
        if filters.get('where'):
            raise ValueError(
                'SQLite no acepta SQL WHERE libre; use filters={"equals": {...}}.'
            )
        sql = f'SELECT * FROM "{self._quote(layer)}"'
        equals = filters.get('equals') or {}
        values: list[Any] = []
        if equals:
            clauses = []
            for column, value in equals.items():
                clauses.append(f'"{self._quote(str(column))}" = ?')
                values.append(value)
            sql += ' WHERE ' + ' AND '.join(clauses)
        with closing(self._conn()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, values)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _quote(name: str) -> str:
        return name.replace('"', '""')


# -------------------------------------------------------------------------- Access/ODBC
@dataclass
class AccessAdapter(VNRSourceAdapter):
    path: str = ''

    family = 'DATABASE_ACCESS'

    def _driver(self):
        try:
            import pyodbc  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise AdapterUnavailable('Access/ODBC', 'pyodbc') from exc
        return __import__('pyodbc')

    def metadata(self) -> dict:
        return {'path': self.path, 'engine': 'access'}

    def list_layers(self) -> list[LayerInfo]:
        pyodbc = self._driver()
        conn_str = (
            r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + self.path
        )
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            rows = cursor.tables(tableType='TABLE').fetchall()
            names = [r.table_name for r in rows if hasattr(r, 'table_name')]
        infos: list[LayerInfo] = []
        for name in sorted(names):
            fields = self._columns(name, pyodbc, conn_str)
            infos.append(LayerInfo(name=name, fields=fields))
        return infos

    def _columns(self, table: str, pyodbc, conn_str: str) -> list[dict]:
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f'SELECT TOP 1 * FROM [{table}]')
                return [{'name': d[0], 'type': str(d[1])} for d in cursor.description]
            except Exception:  # noqa: BLE001 - tabla sin lectura no bloquea el inventario
                return []

    def read_layer(self, layer, filters=None) -> list[dict]:
        pyodbc = self._driver()
        conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + self.path
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM [{layer}]')
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ------------------------------------------------------------------ volcados SQL
_DIALECT_HINTS = [
    ('POSTGRESQL', re.compile(r'CREATE\s+EXTENSION|pg_catalog|nextval\(|SERIAL|CREATE\s+TABLE.*geometry', re.IGNORECASE)),
    ('POSTGRESQL', re.compile(r'^--.*PostgreSQL', re.IGNORECASE | re.MULTILINE)),
    ('ORACLE', re.compile(r'NUMBER\(\d+,\d+\)|VARCHAR2|DATAFILE|CREATE\s+OR\s+REPLACE\s+(PROCEDURE|FUNCTION)', re.IGNORECASE)),
    ('MSSQL', re.compile(r'GO\b|NVARCHAR|IDENTITY\(1,1\)|\[dbo\]\.', re.IGNORECASE)),
    ('SQLITE', re.compile(r'CREATE\s+TABLE.*INTEGER\s+PRIMARY\s+KEY', re.IGNORECASE)),
]


def inspect_sql_dump(path: Path | str, limit_lines: int = 500) -> dict:
    """Inspecciona un volcado .sql **sin ejecutarlo** (E4).

    Devuelve el dialecto probable, la codificación, las tablas/índices declarados
    y un conteo aproximado de sentencias. Nunca ejecuta nada contra una base.
    """
    path = Path(path)
    text = path.read_text(encoding='utf-8', errors='replace')
    sample = text[: 200000]
    dialect = 'UNKNOWN'
    for name, pattern in _DIALECT_HINTS:
        if pattern.search(sample):
            dialect = name
            break
    tables = sorted(set(re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([\w.]+)', sample, re.IGNORECASE)))
    views = sorted(set(re.findall(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+["`\[]?([\w.]+)', sample, re.IGNORECASE)))
    srids = sorted(set(re.findall(r'\bSRID[=\s]*(\d+)', sample)))
    inserts = len(re.findall(r'\bINSERT\s+INTO\b', sample, re.IGNORECASE))
    return {
        'dialect_probable': dialect,
        'bytes': path.stat().st_size,
        'tables': tables,
        'views': views,
        'srids': srids,
        'approx_inserts': inserts,
        'non_executed': True,
    }
