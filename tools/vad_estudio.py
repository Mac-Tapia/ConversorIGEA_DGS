#!/usr/bin/env python
"""Guion del estudio VAD: arma la empresa modelo sistema por sistema y deja su manifiesto (spec 108, T12).

No usa DIgSILENT ni la web: corre ``vad.trabajo.armar_empresa_modelo`` con un contexto de consola (Ctrl+C cancela
entre sistemas, y el manifiesto queda escrito también entonces).

    python tools/vad_estudio.py --espacio DIR --estudio ID --caso DIR [--registro DIR] [--formatos JSON]

* ``--espacio``: el espacio de trabajo con el estudio ya creado (``<espacio>/vad/<id>/estudio.json``).
* ``--caso``: la carpeta del caso, fuera de git (``CSG_VAD_CASO`` si no se da), con ``sistemas.json``:
  ``{"sistemas": {"<sistema>": {"anexo2": "<tablas del sistema>.json"}}}``.
* ``--registro``: las carpetas del registro normativo (por defecto ``config/vad`` y ``config/normativa``); con él se
  comprueba el estudio (conforme, no_conforme o desactualizado) antes de armar.

Salida: el manifiesto en ``<espacio>/vad/<id>/manifiesto.json``. Códigos: 0 todos los sistemas OK, 2 algún sistema
FAIL o la entrada no sirve, 130 cancelado.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))


class Cancelado(Exception):
    """Ctrl+C entre dos sistemas."""


class ContextoConsola:
    """Lo mismo que el JobContext del carril, en la consola."""

    def __init__(self) -> None:
        self.pedido = False

    def check_cancel(self) -> None:
        if self.pedido:
            raise Cancelado()

    def progress(self, index: int, total: int, label: str = '') -> None:
        print(f'[{index}/{total}] {label}', flush=True)

    def log(self, text: str) -> None:
        print(text, flush=True)


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows no es UTF-8: sin esto, la ayuda con «» o tildes sale ilegible para quien la lea por tubería.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, 'reconfigure'):
            flujo.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split('\n\n', 1)[1])
    p.add_argument('--espacio', required=True, type=Path)
    p.add_argument('--estudio', required=True)
    p.add_argument('--caso', type=Path, default=os.environ.get('CSG_VAD_CASO') or None)
    p.add_argument('--registro', type=Path, nargs='*',
                   default=[RAIZ / 'config' / 'vad', RAIZ / 'config' / 'normativa'])
    p.add_argument('--formatos', type=Path, default=RAIZ / 'config' / 'vad' / 'anexo2_formatos.json')
    args = p.parse_args(argv)
    from convertersmartgrid.registro_normativo import cargar_registro
    from convertersmartgrid.vad import VadError
    from convertersmartgrid.vad.anexo2 import cargar_formatos
    from convertersmartgrid.vad.estudio import comprobar_estudio
    from convertersmartgrid.vad.trabajo import (
        armar_empresa_modelo,
        leer_caso,
        pasos_del_caso,
    )

    if args.caso is None:
        print('falta el caso: --caso o la variable CSG_VAD_CASO', file=sys.stderr)
        return 2
    ctx = ContextoConsola()
    signal.signal(signal.SIGINT, lambda *_: setattr(ctx, 'pedido', True))
    try:
        registro = cargar_registro(*args.registro)
        estudio = comprobar_estudio(args.espacio, args.estudio, registro)
        print(f'estudio {estudio.id}: {estudio.estado}' + (f' ({"; ".join(estudio.motivos)})' if estudio.motivos else ''))
        manifiesto = armar_empresa_modelo(ctx, args.espacio, args.estudio, leer_caso(args.caso),
                                          pasos_del_caso(cargar_formatos(args.formatos), estudio.periodo))
    except Cancelado:
        print('cancelado: el manifiesto dice qué sistemas no llegaron a armarse', file=sys.stderr)
        return 130
    except VadError as exc:
        print(f'no se puede armar: {exc}', file=sys.stderr)
        return 2
    malos = [s for s, r in manifiesto['sistemas'].items() if r['estado'] != 'OK']
    for s, r in manifiesto['sistemas'].items():
        print(f'{s}: {r["estado"]}' + (f' en {r.get("paso")}: {r.get("error")}' if r['estado'] == 'FAIL' else ''))
    return 2 if malos else 0


if __name__ == '__main__':
    raise SystemExit(main())
