#!/usr/bin/env python
"""Puesta en uso provisional de un modelo que no pasa las puertas, por decisión del usuario (085:RF-26 a RF-33).

No aprueba nada: el candidato sigue rechazado, las puertas no cambian y cada plan espera la confirmación del operador.
El registro guarda quién lo decidió, cuándo, por qué, sus cifras y el modelo anterior.

Subórdenes:
  ver     El modelo en uso, si es provisional, y las cifras del último candidato. No cambia nada.
  poner   Pone en uso el candidato indicado. Pide --candidato, --decidido-por y --motivo.
  volver  Vuelve al modelo anterior con el puntero y el registro de acuerdo.

Sin GPU, sin DIgSILENT y sin Ollama: solo lee el registro y mueve el puntero. La carpeta de datos es la de la web, o
la de CSG_ASISTENTE_DATA.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))


def _imprimir(dato) -> None:
    sys.stdout.buffer.write((json.dumps(dato, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))


def _ver(familia: str) -> int:
    from convertersmartgrid.asistente import modelos_en_uso as meu
    from convertersmartgrid.asistente.transformer import version_promovida

    reg, ultimo = meu.registro(), None
    if (reg.raiz / familia / 'latest.json').is_file():
        hecho = reg.ultimo(familia)
        # Las cifras sin la lista de fallos: son 60 líneas que no deciden nada aquí.
        ultimo = {'candidate_id': hecho['candidate_id'], 'status': hecho['status'], 'cifras': meu.cifras_de(hecho['detalle']),
                  'reabre': hecho['detalle']['smoke_reload'].get('ok')}
    _imprimir({'carpeta': str(reg.raiz.parent), 'en_uso': version_promovida(meu.FAMILIAS[familia]),
               'provisional': meu.uso_provisional(familia), 'ultimo_candidato': ultimo})
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='orden', required=True)
    for nombre, ayuda in (('ver', 'el modelo en uso y el último candidato, sin cambiar nada'),
                          ('poner', 'pone en uso el candidato, sin aprobarlo'),
                          ('volver', 'vuelve al modelo anterior')):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument('--familia', choices=('transformer', 'clasificador'), default='transformer')
        if nombre == 'poner':
            s.add_argument('--candidato', required=True, help='identidad completa del candidato en el registro')
            s.add_argument('--decidido-por', required=True, help='quién lo decide; queda en el registro')
            s.add_argument('--motivo', required=True)
            s.add_argument('--fecha', help='fecha de la decisión; por omisión, ahora')
    return p


def main(argv=None) -> int:
    a = _parser().parse_args(argv)
    if a.orden == 'ver':
        return _ver(a.familia)
    from convertersmartgrid.asistente import modelos_en_uso as meu

    try:
        if a.orden == 'poner':
            _imprimir(meu.poner_provisional(a.familia, a.candidato, decidido_por=a.decidido_por, motivo=a.motivo, fecha=a.fecha))
            return 0
        version = meu.volver_al_anterior(a.familia)
    except (OSError, ValueError) as exc:
        print(f'No se cambió el modelo en uso: {exc}', file=sys.stderr)
        return 1
    if version is None:
        print('No hay un modelo anterior al que volver.', file=sys.stderr)
        return 1
    _imprimir({'en_uso': version})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
