#!/usr/bin/env python
"""Consulta y mantiene el búfer de episodios del gemelo digital (spec 024).

No abre DIgSILENT: trabaja con los episodios que ya registró la web.

    python tools/digital_twin_buffer.py list [--proyecto P] [--caso sin_proyecto] [--clase accepted]
    python tools/digital_twin_buffer.py show <episode_id>
    python tools/digital_twin_buffer.py validate episodio.json
    python tools/digital_twin_buffer.py register episodio.json
    python tools/digital_twin_buffer.py rebuild-index

Con ``--raiz`` se usa otro búfer; sin ella, ``IGEA_TWIN_DATA`` o el de la web.
Códigos de salida: 0 bien (también si ya estaba), 2 entrada no válida, 3 búfer
inaccesible o dañado.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from igea_dgs.digital_twin.buffer import BuferEpisodios, ColisionEpisodio, Consulta
from igea_dgs.digital_twin.episode import (
    EpisodioInvalido,
    episodio_a_dict,
    leer_episodio,
)


def _leer_json(ruta: str) -> dict:
    try:
        return json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise EpisodioInvalido('', f'{ruta}: {exc}') from exc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Búfer de episodios del gemelo digital (spec 024)')
    p.add_argument('--raiz', type=Path, help='Carpeta del búfer (por defecto, la de la web)')
    sub = p.add_subparsers(dest='orden', required=True)
    lista = sub.add_parser('list', help='Episodios que cumplen los filtros')
    for campo in ('proyecto', 'alimentador', 'caso', 'clase', 'accion', 'fuente'):
        lista.add_argument(f'--{campo}')
    sub.add_parser('show', help='Manifiesto de un episodio').add_argument('episode_id')
    sub.add_parser('validate', help='Valida un manifiesto sin guardarlo').add_argument('manifiesto')
    sub.add_parser('register', help='Valida y guarda un manifiesto').add_argument('manifiesto')
    sub.add_parser('rebuild-index', help='Rehace el índice desde los objetos')
    args = p.parse_args(argv)

    try:
        if args.orden == 'validate':
            e = leer_episodio(_leer_json(args.manifiesto))
            print(f'válido: {e.episode_id} ({e.clase.value}, {e.caso.value})')
            return 0
        bufer = BuferEpisodios(args.raiz)
        if args.orden == 'list':
            filtros = {k: getattr(args, k) for k in ('proyecto', 'alimentador', 'caso', 'clase',
                                                     'accion', 'fuente') if getattr(args, k)}
            for e in bufer.consultar(Consulta(**filtros)):
                print(f"{e.episode_id}  {e.creado}  {e.caso.value:<13} {e.clase.value:<26} "
                      f"{e.nativo['project']}  {','.join(e.nativo['feeders'])}")
            return 0
        if args.orden == 'show':
            print(json.dumps(episodio_a_dict(bufer.leer(args.episode_id)), indent=2, ensure_ascii=False))
            return 0
        if args.orden == 'register':
            e = leer_episodio(_leer_json(args.manifiesto))
            print(f'registrado: {bufer.guardar(e)}')
            return 0
        n = bufer.reconstruir_indice()
        print(f'índice rehecho con {n} episodio(s); en cuarentena: {len(bufer.cuarentena())}')
        return 0
    except EpisodioInvalido as exc:
        print(f'ERROR: episodio no válido: {exc}', file=sys.stderr)
        return 2
    except KeyError as exc:
        print(f'ERROR: {exc.args[0]}', file=sys.stderr)
        return 2
    except (ColisionEpisodio, OSError, sqlite3.DatabaseError) as exc:
        print(f'ERROR: búfer inaccesible o dañado: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
