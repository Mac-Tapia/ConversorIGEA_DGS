#!/usr/bin/env python
"""Consolida la evaluación final de la 1.0 en ``docs/EVALUACION_FINAL_1.0.json`` (044:RF-10, RF-11).

Paso 4 del plan de la evaluación final: cada bloque deja sus medidas en una entrada JSON con la rev en que corrió y la
huella de cada conjunto sellado; esta herramienta las reúne, aplica Holm por bloque y separa los resultados negativos.
Se niega a escribir (código 1) si la rev no es el HEAD, si el árbol tiene cambios o si un conjunto ya no tiene la huella
con que se selló. ``--comprobar`` relee el informe escrito con las mismas comprobaciones.

    python tools/evaluacion_final.py --entrada <medidas.json> --rev <sha1 completo>
    python tools/evaluacion_final.py --comprobar

Códigos de salida: 0 informe escrito o válido, 1 rechazado (dice por qué).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--entrada', help='JSON con rev, conjuntos y bloques medidos')
    ap.add_argument('--rev', help='SHA-1 completo de la revisión candidata (el HEAD)')
    ap.add_argument('--repo', default=str(RAIZ), help='repositorio (por defecto, este)')
    ap.add_argument('--comprobar', action='store_true', help='relee el informe ya escrito')
    args = ap.parse_args(argv)
    if str(RAIZ / 'src') not in sys.path:
        sys.path.insert(0, str(RAIZ / 'src'))
    from convertersmartgrid.evaluacion_harness import informe_final as inf

    repo = Path(args.repo)
    try:
        if args.comprobar:
            inf.validar(json.loads((repo / inf.DESTINO).read_text(encoding='utf-8')), repo=repo)
            print(f'{inf.DESTINO}: válido')
            return 0
        if not args.entrada or not args.rev:
            ap.error('--entrada y --rev son obligatorios sin --comprobar')
        entrada = json.loads(Path(args.entrada).read_text(encoding='utf-8'))
        informe = inf.consolidar(entrada, repo=repo, rev=args.rev)
        ruta = inf.escribir(informe, repo)
    except (inf.InformeRechazado, OSError, ValueError) as exc:
        print(f'RECHAZADO: {exc}', file=sys.stderr)
        return 1
    medidas = sum(len(b) for b in informe['medidas'].values())
    print(f'{ruta}: {medidas} medidas en {len(informe["medidas"])} bloques, {len(informe["negativos"])} negativas, '
          f'rev {informe["rev"][:12]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
