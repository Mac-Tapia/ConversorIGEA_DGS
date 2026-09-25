"""Empareja exportaciones TXT y bases Access que son la misma foto de la red.

Uso:
    python tools/emparejar_entradas.py CARPETA [CARPETA ...] [--mdb BASE.mdb ...]
                                       [--pruebas] [--json salida.json]

Busca en las carpetas los RED (por contenido, no por nombre) y las bases ``.mdb``, lee
de cada una solo nodos y tramos, y dice qué parejas son la misma exportación (ver
``igea_dgs.huella``). Con ``--pruebas`` ejecuta además las pruebas que comparan el TXT
con la base, pero **solo** con parejas de la misma foto. Con otra combinación, las
pruebas PA217/SL143 fallaban 10 veces por la renumeración de nodos, no por el código.

Código de salida: 0 si hay al menos una pareja válida, 1 si no hay ninguna.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
# La consola de Windows es cp1252 por defecto y revienta con «→» o «≥».
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from igea_dgs.huella import comparar  # noqa: E402
from igea_dgs.identify import CARGA, EQUIPOS, RED, identificar  # noqa: E402

PRUEBAS_CRUZADAS = ('tests/test_feeder_pa217.py', 'tests/test_feeder_sl143.py',
                    'tests/test_access_input.py')

# Solo para la huella: nodos y tramos no dependen del catálogo, y hay bases de red sin
# él (260924.mdb). Nunca se usa para convertir.
_CATALOGO_FICTICIO = {'LINE': ({'ID': '_huella_'},)}


def _fecha(path: Path) -> str:
    """La fecha que el nombre lleva dentro (``RED_030826`` → ``030826``), o ``''``."""
    m = re.search(r'\d{6}', path.stem)
    return m.group(0) if m else ''


def _txt_por_carpeta(carpetas: list[Path]) -> list[dict]:
    """Un trío por cada RED: CARGA y EQUIPOS de la misma fecha o, si no, de la carpeta."""
    trios = []
    for carpeta in carpetas:
        tipos: dict[str, list[Path]] = {RED: [], CARGA: [], EQUIPOS: []}
        for f in sorted(carpeta.rglob('*.txt')):
            tipo = identificar(f).tipo
            if tipo in tipos:
                tipos[tipo].append(f)
        for red in tipos[RED]:
            fecha = _fecha(red)

            def elegir(tipo: str) -> tuple[Path | None, bool]:
                mismos = [f for f in tipos[tipo] if f.parent == red.parent and fecha and _fecha(f) == fecha]
                if mismos:
                    return mismos[0], False
                otros = [f for f in tipos[tipo] if f.parent == red.parent]
                return (otros[0], True) if otros else (None, True)

            carga, carga_prestada = elegir(CARGA)
            equipos, equipos_prestado = elegir(EQUIPOS)
            if carga is None or equipos is None:
                print(f'  (se omite {red}: falta CARGA o EQUIPOS en su carpeta)')
                continue
            trios.append({'red': red, 'carga': carga, 'equipos': equipos,
                          'prestados': [n for n, p in (('carga', carga_prestada), ('equipos', equipos_prestado)) if p]})
    return trios


def _leer_txt(trio: dict):
    from igea_dgs.dataset import CymdistDataset

    return CymdistDataset.from_files(trio['red'], trio['carga'], trio['equipos'])


def _leer_mdb(ruta: Path):
    from igea_dgs.access import read_access_dataset

    return read_access_dataset(ruta, equipment_tables=_CATALOGO_FICTICIO)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('carpetas', nargs='*', type=Path, help='Carpetas con TXT y/o .mdb')
    ap.add_argument('--mdb', action='append', type=Path, default=[], help='Base concreta (repetible)')
    ap.add_argument('--equipment-mdb', type=Path, help='Base con catálogo para ejecutar las pruebas')
    ap.add_argument('--pruebas', action='store_true', help='Ejecutar las pruebas cruzadas con la mejor pareja')
    ap.add_argument('--json', type=Path, help='Guardar la matriz de parecido')
    args = ap.parse_args(argv)

    carpetas = [c for c in args.carpetas if c.is_dir()]
    mdbs = list(args.mdb) + [m for c in carpetas for m in sorted(c.rglob('*.mdb'))]
    trios = _txt_por_carpeta(carpetas)
    if not trios or not mdbs:
        print(f'Hacen falta TXT y bases: {len(trios)} RED y {len(mdbs)} .mdb encontrados.')
        return 1

    print(f'Leyendo {len(trios)} exportación(es) TXT y {len(mdbs)} base(s)…', flush=True)
    txt = {}
    for trio in trios:
        try:
            txt[trio['red']] = (trio, _leer_txt(trio))
        except (OSError, ValueError) as exc:
            print(f'  TXT ilegible {trio["red"].name}: {exc}')
    bases = {}
    for m in dict.fromkeys(mdbs):
        try:
            bases[m] = _leer_mdb(m)
        except Exception as exc:  # noqa: BLE001 - borde de herramienta: se informa y se sigue
            print(f'  base ilegible {m.name}: {exc}')

    filas = []
    for red, (trio, ds_txt) in txt.items():
        for m, ds_mdb in bases.items():
            c = comparar(ds_txt, ds_mdb)
            filas.append({'red': str(red), 'carga': str(trio['carga']), 'equipos': str(trio['equipos']),
                          'prestados': trio['prestados'], 'mdb': str(m), **c.as_dict(), 'motivo': c.motivo()})
    filas.sort(key=lambda f: (f['misma_foto'], f['nodos'], f['tramos']), reverse=True)

    print(f'\n{"RED":<28} {"BASE":<24} {"nodos":>7} {"tramos":>7}  ¿misma foto?')
    for f in filas:
        print(f'{Path(f["red"]).name[:28]:<28} {Path(f["mdb"]).name[:24]:<24} '
              f'{f["nodos"]:>7.1%} {f["tramos"]:>7.1%}  {"SÍ" if f["misma_foto"] else "no"}')
    if args.json:
        args.json.write_text(json.dumps(filas, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    validas = [f for f in filas if f['misma_foto']]
    if not validas:
        mejor = filas[0] if filas else None
        print('\nNinguna pareja es la misma exportación.')
        if mejor:
            print(f'La más parecida: {Path(mejor["red"]).name} + {Path(mejor["mdb"]).name}. {mejor["motivo"]}')
        print('Pida a la distribuidora el TXT y la base de la MISMA exportación.')
        return 1

    def variables(fila: dict) -> dict[str, str]:
        env = {'IGEA_RED': fila['red'], 'IGEA_LOADS': fila['carga'],
               'IGEA_EQUIPMENT': fila['equipos'], 'IGEA_MDB': fila['mdb']}
        if args.equipment_mdb:
            env['IGEA_EQUIPMENT_MDB'] = str(args.equipment_mdb)
        return env

    def mostrar(fila: dict) -> None:
        print(f'\nPareja: {Path(fila["red"]).name} + {Path(fila["mdb"]).name}')
        if fila['prestados']:
            print(f'  Aviso: {", ".join(fila["prestados"])} tomado(s) de otra exportación de la carpeta.')
        print('Variables para la suite:')
        for k, v in variables(fila).items():
            print(f'  {k}="{v}"')

    if not args.pruebas:
        mostrar(validas[0])
        return 0

    # Mismos identificadores no garantiza mismo contenido: una base editada después
    # (20260919.mdb) conserva los ID y cambia islas o estados de maniobra. Por eso se
    # prueban las parejas válidas una a una y se queda la primera en verde.
    resultados = []
    for fila in validas:
        mostrar(fila)
        cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *PRUEBAS_CRUZADAS]
        proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **variables(fila)},
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
        resumen = next((ln for ln in reversed(proc.stdout.splitlines()) if ' in ' in ln), '?')
        print(f'  → {resumen}')
        resultados.append((fila, proc.returncode, resumen))
        # En verde de verdad: sin fallos y sin omisiones. Una base ilegible «pasa»
        # omitiendo casi todo (BaseDatos1.mdb: 17 pasadas, 58 omitidas).
        if proc.returncode == 0 and 'skipped' not in resumen:
            print(f'\nEN VERDE con {Path(fila["mdb"]).name}. Use esas variables.')
            return 0
    print('\nNinguna pareja válida pasa entera. Resúmenes:')
    for fila, _rc, resumen in resultados:
        print(f'  {Path(fila["mdb"]).name}: {resumen}')
    return 1

if __name__ == '__main__':
    raise SystemExit(main())
