#!/usr/bin/env python
"""Rol único frente a cuatro roles con los mismos casos: errores hallados, coste y latencia (047 T3).

    python tools/asistente_comparar_revision.py --solo-conjunto
    python tools/asistente_comparar_revision.py --modelo <modelo de Ollama> --salida <informe.json>

`--solo-conjunto` comprueba los casos sin Ollama. La medición usa Ollama local y espera su turno de GPU; una salida
existente se conserva, porque cada medición se hace una vez. Solo mide: no adopta nada ni autoriza ejecución.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))

CONJUNTO = RAIZ / 'docs' / 'REVISION_ROLES_CASOS_047.json'
#: Fijada antes de medir: si cambian los casos, cambia lo que se compara.
HUELLA = '102bdfbf1c049c893aa5906594a1cc20503a1b5344a20dc62c905bb84a21ca6d'
DEFECTOS = {None, 'fuentes', 'fisica', 'coste', 'riesgo'}


def huella() -> str:
    # Del contenido y no de los bytes: un cambio de fin de línea al sacarlo de git no es otro conjunto.
    contenido = json.loads(CONJUNTO.read_text(encoding='utf-8'))
    return hashlib.sha256(json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def leer_casos() -> list[dict]:
    if huella() != HUELLA:
        raise ValueError('el conjunto de casos cambió: no es el declarado antes de medir')
    casos = json.loads(CONJUNTO.read_text(encoding='utf-8'))['casos']
    ids = [c['id'] for c in casos]
    if len(set(ids)) != len(ids) or any(c['defecto'] not in DEFECTOS or not c['evidencia'] for c in casos):
        raise ValueError('casos repetidos, sin evidencia o con un defecto desconocido')
    return casos


def materializar(casos: list[dict], carpeta: Path) -> list[dict]:
    """Cada evidencia a un fichero con su huella, como la que custodia la web; contexto propio por caso."""
    salida = []
    for caso in casos:
        contexto = SimpleNamespace(project=caso['id'], source_fingerprint='casos-047')
        evidencia = {}
        for clave, texto in caso['evidencia'].items():
            ruta = carpeta / f"{caso['id']}_{clave}.txt"
            ruta.write_text(texto, encoding='utf-8')
            evidencia[clave] = {'archivo': str(ruta), 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest(),
                                'proyecto': caso['id'], 'fuente': 'casos-047', 'localizador': 'texto', 'fragmento': texto}
        restricciones = {'plan_completo': True, 'contexto_vigente': True}
        salida.append({'id': caso['id'], 'defecto': caso['defecto'], 'contexto': contexto, 'evidencia': evidencia,
                       'propuesta': {**caso['propuesta'], 'restricciones_deterministas': restricciones}})
    return salida


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--solo-conjunto', action='store_true', help='Comprueba los casos, sin Ollama.')
    p.add_argument('--modelo', help='Modelo de Ollama con que se mide.')
    p.add_argument('--salida', type=Path, help='Informe JSON; si existe, no se mide de nuevo.')
    args = p.parse_args(argv)
    casos = leer_casos()
    resumen = {'casos': len(casos), 'con_defecto': sum(c['defecto'] is not None for c in casos), 'conjunto_sha256': huella()}
    if args.solo_conjunto:
        print(json.dumps(resumen, ensure_ascii=True))
        return 0
    if not args.modelo or not args.salida:
        p.error('la medición pide --modelo y --salida')
    if args.salida.exists():
        print(f'{args.salida} ya existe: no se mide de nuevo.', file=sys.stderr)
        return 2
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.asistente.revision_roles import comparar_revision, revisor_ollama
    from convertersmartgrid.trabajadores_ml import turno_gpu

    cliente = ClienteOllama(modelo=args.modelo, tiempo_max_s=90.0)
    if args.modelo not in (cliente.modelos() or []):
        print(f'El modelo {args.modelo} no está en el Ollama de esta máquina.', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='csg-revision-') as carpeta, turno_gpu('revision-comparacion'):
        informe = comparar_revision(materializar(casos, Path(carpeta)),
                                    lambda medir: revisor_ollama(cliente, medir=medir))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps({**resumen, 'modelo': args.modelo, **informe}, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print(json.dumps({k: {c: informe[k][c] for c in ('detectados', 'perdidos', 'falsas_alarmas', 'sin_respuesta',
                                                     'tokens_entrada', 'tokens_salida', 'segundos')}
                      for k in ('rol_unico', 'equipo')}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
