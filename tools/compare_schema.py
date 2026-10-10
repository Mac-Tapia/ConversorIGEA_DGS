#!/usr/bin/env python
"""Compara las cabeceras de un DGS externo con un perfil de esquema empaquetado.

Lee las líneas ``$$Tabla;campo...`` del DGS y dice qué tablas del perfil faltan, cuáles
sobran y cuáles tienen otra cabecera. Sirve para comprobar un DGS exportado por otra
versión de PowerFactory antes de adoptar su perfil.

    python tools/compare_schema.py FICHERO.dgs [--profile pf21_dgs_1_8_4] [--report informe.txt]

Código de salida: 0 si coinciden, 2 si hay diferencias.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from igea_dgs.schema import load_schema


def headers(path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    text = raw.decode('utf-8', errors='replace')
    if '\ufffd' in text:
        text = raw.decode('latin-1', errors='replace')
    return {
        line[2:].split(';', 1)[0]: line.strip()
        for line in text.splitlines()
        if line.strip().startswith('$$')
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Cabeceras de un DGS frente a un perfil de esquema')
    parser.add_argument('dgs')
    parser.add_argument('--profile', default='pf21_dgs_1_8_4')
    parser.add_argument('--report')
    args = parser.parse_args(argv)
    schema = load_schema(args.profile)
    observed = headers(Path(args.dgs))
    missing = sorted(set(schema.tables) - set(observed))
    extra = sorted(set(observed) - set(schema.tables))
    mismatched = sorted(name for name in set(schema.tables) & set(observed) if schema.header(name) != observed[name])
    lines = [
        f'Perfil: {schema.profile}',
        f'Tablas del perfil: {len(schema.tables)}',
        f'Tablas del DGS: {len(observed)}',
        f'Cabeceras idénticas: {len(set(schema.tables) & set(observed)) - len(mismatched)}',
        f'Faltan: {missing}',
        f'Sobran: {extra}',
        f'Distintas: {mismatched}',
    ]
    report = '\n'.join(lines) + '\n'
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding='utf-8')
    print(report, end='')
    return 0 if not missing and not extra and not mismatched else 2


if __name__ == '__main__':
    raise SystemExit(main())
