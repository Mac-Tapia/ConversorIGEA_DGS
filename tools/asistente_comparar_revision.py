#!/usr/bin/env python
"""Rol único frente a cuatro roles con los mismos casos: errores hallados, coste y latencia (047 T3).

    python tools/asistente_comparar_revision.py --solo-conjunto [--conjunto <casos.json>]
    python tools/asistente_comparar_revision.py --modelo <modelo de Ollama> [--conjunto <casos.json>] --salida <informe.json>

`--solo-conjunto` comprueba los casos sin Ollama. Sin `--conjunto`, los de `docs/REVISION_ROLES_CASOS_047.json`. Un
conjunto se mide solo si su huella es la declarada antes de medir (047:RF-43): la de `DECLARADOS` y, si el fichero la
trae, la de su clave `declaracion`; la huella va al informe. La medición usa Ollama local y espera su turno de GPU; una
salida existente se conserva, porque cada medición se hace una vez. Solo mide: no adopta nada ni autoriza ejecución.
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
#: 047 T8: los 12 casos de 2026-11-03 orientaron el diagnóstico, así que la medida que cierra la T8 es con otro conjunto,
#: declarado el 2026-11-19 antes de medir (su huella, también en la spec y en el fichero).
HUELLA_047B = '54f2a035bc7c173d87830a5faaf2e5fdca79851df448abb854efff60e2f4e910'
#: 047 T8, MEJ24: la medida del 047b (2026-11-21) orientó la corrección del encargo, así que la siguiente es con otro
#: conjunto, declarado el 2026-11-21 antes de medir.
HUELLA_047C = '04f19184a45fed27966a880bd0f89a23d819db6836da22f13e3ab79ecd618d88'
#: 047 T8, MEJ24b: la medida del 047c (2026-11-21) orientó las contradicciones estructuradas (047:RF-48 a RF-50), así
#: que la siguiente es con otro conjunto, declarado el 2026-11-21 antes de medir.
HUELLA_047D = '2da22130778488aa9e2a71583e6799c30fb41ce403796a5d6261fbb1a50887cc'
#: 047 T11, MEJ24c: la medida del 047d (2026-11-21) orientó las contradicciones fundadas y por base (047:RF-52 a
#: RF-56), así que la siguiente es con otro conjunto, declarado el 2026-11-21 antes de medir.
HUELLA_047E = '649863d4f383978a1e1e62984a4aa7b95140a76c556078a057b667adae0ae5da'
#: 047 T13, MEJ24d: la medida del 047e (2026-11-21) orientó las cuentas, la conversión a total y la comprobación del
#: coste (047:RF-75 a RF-78), así que la siguiente es con otro conjunto, declarado el 2026-11-21 antes de medir.
HUELLA_047F = '05c423913e4e49d4ebb370fd8d760f89e4cfb3319ce9001395dde08da33afea6'
#: 047 T14, MEJ24e: la medida del 047f (2026-11-22) orientó las reglas de RF-79 a RF-83, así que la siguiente es con
#: otro conjunto, declarado el 2026-11-22 antes de medir.
HUELLA_047G = '6553d4ae2cdb29b228e56d209cebb15ce53c4ae823deb0d9e17628ed60b4ca8a'
#: Conjuntos declarados, por nombre de fichero; el de siempre usa ``HUELLA``.
DECLARADOS = {'REVISION_ROLES_CASOS_047b.json': HUELLA_047B, 'REVISION_ROLES_CASOS_047c.json': HUELLA_047C,
              'REVISION_ROLES_CASOS_047d.json': HUELLA_047D, 'REVISION_ROLES_CASOS_047e.json': HUELLA_047E,
              'REVISION_ROLES_CASOS_047f.json': HUELLA_047F,
              'REVISION_ROLES_CASOS_047g.json': HUELLA_047G}
#: La clave del fichero que declara su huella; no entra en la huella.
DECLARACION = 'declaracion'
DEFECTOS = {None, 'fuentes', 'fisica', 'coste', 'riesgo'}
#: El de ``revision_roles.TOKENS``, sin cargar el paquete para ``--help`` (una prueba comprueba que son iguales).
TOKENS = 1024


def _contenido(ruta: Path) -> dict:
    return json.loads(Path(ruta).read_text(encoding='utf-8'))


def huella(ruta: Path | None = None) -> str:
    """Del contenido y no de los bytes: un cambio de fin de línea al sacarlo de git no es otro conjunto.

    La clave ``declaracion`` queda fuera, para que el fichero pueda llevar su propia huella.
    """
    contenido = {k: v for k, v in _contenido(ruta or CONJUNTO).items() if k != DECLARACION}
    return hashlib.sha256(json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def huella_declarada(ruta: Path | None = None) -> str:
    """La huella fijada antes de medir; sin ninguna, el conjunto no se mide (047:RF-43)."""
    ruta = Path(ruta or CONJUNTO)
    if ruta.resolve() == CONJUNTO.resolve():
        return HUELLA
    propia = (_contenido(ruta).get(DECLARACION) or {}).get('sha256')
    registrada = DECLARADOS.get(ruta.name)
    if registrada and propia and propia != registrada:
        raise ValueError(f'{ruta.name}: la huella de su declaración no es la registrada en la herramienta')
    if not (registrada or propia):
        raise ValueError(f'{ruta.name}: conjunto sin huella declarada antes de medir; no se mide')
    return registrada or propia


def leer_casos(ruta: Path | None = None) -> list[dict]:
    ruta = Path(ruta or CONJUNTO)
    declarada, medida = huella_declarada(ruta), huella(ruta)
    if medida != declarada:
        raise ValueError(f'el conjunto de casos cambió: no es el declarado antes de medir ({ruta.name}: huella '
                         f'{medida[:12]}…, declarada {declarada[:12]}…)')
    casos = _contenido(ruta)['casos']
    ids = [c['id'] for c in casos]
    if len(set(ids)) != len(ids) or any(c['defecto'] not in DEFECTOS or not c['evidencia'] for c in casos):
        raise ValueError('casos repetidos, sin evidencia o con un defecto desconocido')
    return casos


def materializar(casos: list[dict], carpeta: Path) -> list[dict]:
    """Cada evidencia a un fichero con su huella, como la que custodia la web; contexto propio por caso."""
    salida = []
    for caso in casos:
        # Proyecto y fichero opacos: con el id del caso («sano-…», «defecto-…») la etiqueta llegaba al revisor (047:RF-39).
        proyecto = 'caso-' + hashlib.sha256(caso['id'].encode('utf-8')).hexdigest()[:12]
        contexto = SimpleNamespace(project=proyecto, source_fingerprint='casos-047')
        evidencia = {}
        for clave, texto in caso['evidencia'].items():
            ruta = carpeta / f"{proyecto}_{clave}.txt"
            ruta.write_text(texto, encoding='utf-8')
            evidencia[clave] = {'archivo': str(ruta), 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest(),
                                'proyecto': proyecto, 'fuente': 'casos-047', 'localizador': 'texto', 'fragmento': texto}
        restricciones = {'plan_completo': True, 'contexto_vigente': True}
        salida.append({'id': caso['id'], 'defecto': caso['defecto'], 'contexto': contexto, 'evidencia': evidencia,
                       'propuesta': {**caso['propuesta'], 'restricciones_deterministas': restricciones}})
    return salida


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--solo-conjunto', action='store_true', help='Comprueba los casos, sin Ollama.')
    p.add_argument('--conjunto', type=Path, default=CONJUNTO,
                   help='Casos JSON con su huella declarada (por defecto docs/REVISION_ROLES_CASOS_047.json).')
    p.add_argument('--modelo', help='Modelo de Ollama con que se mide.')
    p.add_argument('--salida', type=Path, help='Informe JSON; si existe, no se mide de nuevo.')
    p.add_argument('--tokens', type=int, default=TOKENS, help=f'Tope de tokens por intervención (por defecto {TOKENS}).')
    args = p.parse_args(argv)
    try:
        casos = leer_casos(args.conjunto)
    except (OSError, ValueError, KeyError) as e:
        print(f'No se mide: {e}', file=sys.stderr)
        return 2
    resumen = {'casos': len(casos), 'con_defecto': sum(c['defecto'] is not None for c in casos),
               'conjunto': args.conjunto.name, 'conjunto_sha256': huella(args.conjunto)}
    if args.solo_conjunto:
        print(json.dumps(resumen, ensure_ascii=True))
        return 0
    if not args.modelo or not args.salida:
        p.error('la medición pide --modelo y --salida')
    if not 1 <= args.tokens <= 4096:
        p.error('--tokens: entre 1 y 4096')
    if args.salida.exists():
        print(f'{args.salida} ya existe: no se mide de nuevo.', file=sys.stderr)
        return 2
    from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision, revisor_ollama
    from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu

    cliente = ClienteOllama(modelo=args.modelo, tiempo_max_s=90.0)
    if args.modelo not in (cliente.modelos() or []):
        print(f'El modelo {args.modelo} no está en el Ollama de esta máquina.', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='csg-revision-') as carpeta, turno_gpu('revision-comparacion'):
        informe = comparar_revision(materializar(casos, Path(carpeta)),
                                    lambda medir: revisor_ollama(cliente, num_predict=args.tokens, medir=medir),
                                    tope=args.tokens)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps({**resumen, 'modelo': args.modelo, 'tokens': args.tokens, **informe},
                                      ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print(json.dumps({k: {c: informe[k][c] for c in ('detectados', 'perdidos', 'falsas_alarmas', 'sin_respuesta',
                                                     'motivos_sin_respuesta', 'tokens_entrada', 'tokens_salida',
                                                     'max_tokens_salida', 'en_tope', 'contradicciones_descartadas',
                                                     'decisiones_recalculadas', 'comprobaciones_fallidas',
                                                     'segundos')}
                      for k in ('rol_unico', 'equipo')}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
