"""CLI local: no ejecuta comandos, imports ni proveedores indicados por JSON."""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

from .adaptadores import desde_ordenes, importar_upstream
from .contratos import sellar, validar
from .ejecucion import ejecutar, validar_integridad
from .publicacion import leer_informe, leer_json, publicar


def _dato(ruta):
    dato = leer_json(Path(ruta))
    return leer_informe(Path(ruta)) if isinstance(dato, dict) and dato.get(
        'esquema') == 'csg-harness-publicacion-v1' else dato


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Harness integral local: diagnóstico y evidencia; no promueve modelos')
    sub = parser.add_subparsers(dest='orden', required=True)
    p = sub.add_parser('sellar')
    p.add_argument('--config', required=True)
    p.add_argument('--salida', required=True)
    p = sub.add_parser('replay')
    p.add_argument('--config', required=True)
    p.add_argument('--predicciones', required=True)
    p.add_argument('--salida', required=True)
    p = sub.add_parser('ordenes')
    p.add_argument('--entrada', required=True)
    p.add_argument('--salida', required=True)
    p = sub.add_parser('importar')
    p.add_argument('--entrada', required=True)
    p.add_argument('--herramienta', choices=['promptfoo', 'lm_evaluation_harness', 'ragas'], required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--lock', required=True)
    p.add_argument('--salida', required=True)
    p = sub.add_parser('verificar')
    p.add_argument('--informe', required=True)
    args = parser.parse_args(argv)
    try:
        if args.orden == 'verificar':
            r = leer_informe(Path(args.informe))
            if 'suites' in r and 'configuracion' in r:
                validar_integridad(r)
            elif 'modelos' in r and 'suites' in r:
                validar(r)
            print(json.dumps({'integridad': True, 'modo': r.get('modo'),
                              'verificacion_es_aceptacion': False}))
            return 0
        destino = Path(args.salida).resolve()
        entradas = [getattr(args, k, None) for k in ('config', 'predicciones', 'entrada', 'lock')]
        if any(destino == Path(p).resolve() for p in entradas if p):
            raise ValueError('la salida no puede sobrescribir una entrada')
        code = 0
        if args.orden == 'sellar':
            r = sellar(_dato(args.config))
        elif args.orden == 'ordenes':
            dato = _dato(args.entrada)
            r = desde_ordenes(dato['metricas'] if 'casos' not in dato and 'metricas' in dato else dato)
        elif args.orden == 'importar':
            r = importar_upstream(_dato(args.entrada), herramienta=args.herramienta,
                                 commit=args.commit, lock=_dato(args.lock))
        else:
            cfg, guardadas = _dato(args.config), _dato(args.predicciones)
            validar(cfg)
            filas = guardadas.get('casos') if isinstance(guardadas, dict) else guardadas
            if not isinstance(filas, list):
                raise ValueError('predicciones requiere lista de casos identificados')
            esperados = {(s['id'], c['record_id'], rol)
                         for s in cfg['suites'] for c in s['casos'] if c['particion'] == 'prueba'
                         for rol in cfg['modelos']}
            por_clave = {}
            por_entrada = {}
            from .contratos import huella
            for fila in filas:
                clave = (fila['suite_id'], fila['record_id'], fila['rol'])
                if clave in por_clave or clave not in esperados:
                    raise ValueError('caso duplicado o ajeno al conjunto sellado')
                por_clave[clave] = fila
            # El proveedor recibe solo entradas; el mapa de invocación conserva el id
            # en una cola por suite/modelo, sin usar el gold como clave de búsqueda.
            for suite in cfg['suites']:
                for rol, modelo in cfg['modelos'].items():
                    for caso in suite['casos']:
                        if caso['particion'] == 'prueba':
                            clave = (suite['id'], caso['record_id'], rol)
                            llave = (suite['id'], huella(modelo), huella(caso['entrada']))
                            por_entrada.setdefault(llave, []).append(clave)

            def proveedor(modelo, suite, entrada):
                llave = (suite['id'], huella(modelo), huella(entrada))
                clave = por_entrada[llave].pop(0)
                fila = por_clave.get(clave)
                if fila is None or fila.get('estado') != 'ok':
                    raise ValueError('salida guardada ausente o fallida')
                if fila.get('entrada_hash') != huella(entrada):
                    raise ValueError('entrada guardada distinta')
                salida = deepcopy(fila['salida'])
                salida['clase_evidencia'] = 'replay'
                return salida

            r = ejecutar(cfg, proveedor, modo='replay')
            code = 0 if r['estado'] == 'COMPLETA' else 2
        digest = publicar(destino, r)
        print(json.dumps({'salida': str(destino), 'sha256': digest,
                          'modo': r.get('modo'), 'promocion_ejecutada': False}))
        return code
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(type(exc).__name__+': '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
