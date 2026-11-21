#!/usr/bin/env python
"""Aplica la puerta del aprendizaje en alimentadores no vistos y prepara su confirmación en DIgSILENT (spec 074, T8).

``aplicar``: con un modelo GATv2 que dejó ``madrl_entrenar.py --modelo-salida`` y unas redes que no vio, sella la
separación en ``<salida>/separacion.json`` antes de aplicar nada; mide en cada red NSGA-II del sistema (la
referencia) y la política, con los límites y costos del entrenamiento; escribe ``informe.json`` con la medida y la
decisión. Si pasa y se dan ``--espacio`` y ``--proyecto`` (de prueba, «PRUEBA…»), deja ``orden_confirmacion.json``;
si no pasa, ``ARCHIVADO.json``: el piloto se archiva con su medida y no entra en el flujo.

``confirmar``: ejecuta esa orden por la web, como el operador (spec 011): guarda las obras, las simula y las aplica en
el proyecto de prueba, y deja ``confirmacion.json``. No abre DIgSILENT por su cuenta.

Uso:
    python tools/madrl_puerta.py aplicar --modelo <carpeta> --no-vistos <g1.json> [<g2.json> ...] \
        --dispositivo cuda --salida <carpeta> [--espacio ID --proyecto PRUEBA_<nombre>]
    python tools/madrl_puerta.py confirmar --orden <carpeta>/orden_confirmacion.json [--url http://127.0.0.1:8765]

Códigos de salida: 0 pasa (o confirmada), 3 archivar, 2 no se pudo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # ``sistema_web``, también cargado suelto
    sys.path.append(str(HERE))

INFORME, ORDEN, ARCHIVADO, CONFIRMACION = 'informe.json', 'orden_confirmacion.json', 'ARCHIVADO.json', 'confirmacion.json'


def _escribir(ruta: Path, datos: Any) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=float) + '\n', encoding='utf-8')


def cargar_politica(carpeta: Path, manifiesto: dict, dispositivo: str):
    """Los pesos, solo si su huella es la del manifiesto: otro fichero sería otro modelo."""
    from convertersmartgrid.adaptadores.madrl_puerta import PuertaError, huella_fichero

    if manifiesto.get('politica') != 'gatv2':
        raise PuertaError('Solo la política GATv2 se aplica a redes no vistas: la de MaskablePPO tiene el espacio de '
                          'acciones de su red de entrenamiento.')
    pesos = carpeta / 'politica.pt'
    if not pesos.is_file() or huella_fichero(pesos) != manifiesto['huella_pesos']:
        raise PuertaError(f'{pesos}: los pesos no son los del manifiesto del modelo.')
    # Las comprobaciones, antes de cargar la biblioteca: un modelo ajeno se rechaza sin ella.
    import torch

    from convertersmartgrid.adaptadores.madrl_politica import crear_politica

    politica = crear_politica(manifiesto['ocultas'], manifiesto['cabezas'])
    politica.load_state_dict(torch.load(pesos, map_location=dispositivo, weights_only=True))
    return politica.to(dispositivo).eval()


def medir_red(nombre: str, grafo: dict, parametros, politica, *, generaciones: int, poblacion: int) -> dict:
    """La referencia (NSGA-II del sistema) y la política sobre la misma red y las mismas obras (074:RF-5, RF-6)."""
    from convertersmartgrid.adaptadores.madrl_obras import (
        EntornoObras,
        EntornoPlano,
        control_nsga2_sistema,
        zonas_por_alimentador,
    )
    from convertersmartgrid.adaptadores.madrl_politica import evaluar_politica
    from convertersmartgrid.adaptadores.madrl_puerta import obra_de

    zonas = zonas_por_alimentador(grafo)
    referencia = control_nsga2_sistema(EntornoObras(grafo, zonas, parametros), generaciones=generaciones,
                                       poblacion=poblacion)
    plano = EntornoPlano(EntornoObras(grafo, zonas, parametros))
    aprendido = evaluar_politica(plano, politica)
    obras = [{'agente': a, 'tipo': x.tipo, 'elemento': x.elemento, 'costo': x.costo, 'obra': obra_de(x, parametros)}
             for a, hechas in sorted(plano.e.hechas.items()) for x in (plano.e.acciones[a][i] for i in sorted(hechas))]
    return {'nombre': nombre, 'alimentadores': len(zonas), 'referencia': referencia, 'aprendido': aprendido,
            'obras_aprendidas': obras}


def aplicar(args) -> int:
    from convertersmartgrid.adaptadores.madrl_puerta import (
        PuertaError,
        decidir,
        exigir_proyecto_de_prueba,
        fijar_separacion,
        orden_confirmacion,
        parametros_de,
        red_declarada,
        sellar_separacion,
    )

    try:
        manifiesto = json.loads((args.modelo / 'modelo.json').read_text(encoding='utf-8'))
        parametros = parametros_de(manifiesto)
        if args.proyecto is not None:                        # antes de medir: una orden que no se podría preparar
            exigir_proyecto_de_prueba(args.espacio or '', args.proyecto)
        grafos = {str(r): json.loads(Path(r).read_text(encoding='utf-8')) for r in args.no_vistos}
        # 074:RF-13: la separación queda sellada en disco antes de cargar la política o medir nada.
        separacion = fijar_separacion(args.salida, sellar_separacion(
            manifiesto, [red_declarada(Path(n).name, g) for n, g in grafos.items()]))
        print(f"Separación sellada: {len(separacion['no_vistos'])} redes no vistas, sello {separacion['sello'][:12]}")
        politica = cargar_politica(args.modelo, manifiesto, args.dispositivo)
    except (OSError, ValueError, KeyError) as exc:   # justificado: PuertaError es ValueError; todo se dice y sale con 2
        print(f'ERROR: {exc}')
        return 2

    def medir_todas() -> list[dict]:
        return [medir_red(Path(n).name, g, parametros, politica, generaciones=args.generaciones,
                          poblacion=args.poblacion) for n, g in grafos.items()]

    if args.dispositivo == 'cuda':
        from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu

        with turno_gpu('madrl_puerta'):
            medidas = medir_todas()
    else:
        print('Aviso: en cpu solo se comprueba el montaje; la puerta del piloto se aplica en la GPU.')
        medidas = medir_todas()
    informe = {**decidir(separacion, medidas), 'dispositivo': args.dispositivo}
    _escribir(args.salida / INFORME, informe)
    for m in medidas:
        r, a = m['referencia'], m['aprendido']
        print(f"{m['nombre']}: referencia en norma {r['en_norma']}, costo {r['costo']:.1f}; "
              f"aprendido en norma {a['en_norma']}, costo {a['costo']:.1f}")
    print(f"Decisión: {informe['decision']} ({informe['puerta']['motivo']})")
    if informe['decision'] == 'archivar':
        _escribir(args.salida / ARCHIVADO, {'sello_separacion': informe['sello_separacion'], 'puerta': informe['puerta'],
                                            'integrado_en_flujo': False, 'informe': INFORME})
        return 3
    if args.proyecto is None:
        print('Pasa: para preparar la confirmación en DIgSILENT, repita con --espacio y --proyecto (de prueba).')
        return 0
    try:
        orden = orden_confirmacion(informe, espacio=args.espacio, proyecto=args.proyecto)
    except PuertaError as exc:
        print(f'ERROR: {exc}')
        return 2
    _escribir(args.salida / ORDEN, orden)
    print(f'Orden de confirmación: {args.salida / ORDEN}; ejecútela con '
          f'«python tools/madrl_puerta.py confirmar --orden {args.salida / ORDEN}».')
    return 0


def ejecutar_orden(orden: dict, web) -> dict:
    """Los pasos de la orden por la web: las obras se guardan, se simulan y se aplican, como las del operador."""
    ids = [web._pedir('POST', f"/api/workspaces/{orden['espacio']}/obras", json=o)['id'] for o in orden['obras']]
    cuerpo = {'project': orden['proyecto'], 'feeders': orden['feeders'], 'ids': ids}
    simulada = web.esperar(web.post('/pf/obras/simular', json=cuerpo), limite_s=3 * 3600)
    if simulada.get('status') != 'done':
        return {'ids': ids, 'simular': simulada, 'aplicar': None, 'confirmada': False}
    aplicada = web.esperar(web.post('/pf/obras/aplicar', json=cuerpo), limite_s=3 * 3600)
    informe = (aplicada.get('result') or {}).get('informe') or {}
    confirmada = aplicada.get('status') == 'done' and not informe.get('error')
    return {'ids': ids, 'simular': simulada, 'aplicar': aplicada, 'confirmada': confirmada}


def confirmar(args, web=None) -> int:
    from convertersmartgrid.adaptadores.madrl_puerta import (
        SEPARACION,
        orden_valida,
    )

    try:
        orden = json.loads(args.orden.read_text(encoding='utf-8'))
        separacion = json.loads((args.orden.parent / SEPARACION).read_text(encoding='utf-8'))
        orden_valida(orden, separacion)
    except (OSError, ValueError, KeyError) as exc:   # justificado: PuertaError es ValueError; se dice y sale con 2
        print(f'ERROR: {exc}')
        return 2
    if web is None:
        from sistema_web import Web

        web = Web(args.url, orden['espacio'])
    try:
        salida = ejecutar_orden(orden, web)
    except (OSError, RuntimeError, TimeoutError) as exc:   # justificado: la web no respondió; se deja escrito
        salida = {'confirmada': False, 'error': str(exc)}
    _escribir(args.orden.parent / CONFIRMACION, {'orden': orden['huella'], **salida})
    print(f"Confirmación en DIgSILENT: {'hecha' if salida['confirmada'] else 'no confirmada'} "
          f'({args.orden.parent / CONFIRMACION})')
    return 0 if salida['confirmada'] else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Puerta del aprendizaje en alimentadores no vistos y su confirmación en '
                                            'DIgSILENT (spec 074).')
    sub = p.add_subparsers(dest='accion', required=True)
    a = sub.add_parser('aplicar', help='Sella la separación, mide y decide: pasa o archivar')
    a.add_argument('--modelo', type=Path, required=True, help='Carpeta de madrl_entrenar.py --modelo-salida')
    a.add_argument('--no-vistos', type=Path, nargs='+', required=True, help='JSON de grafos que el modelo no vio')
    a.add_argument('--dispositivo', choices=('cuda', 'cpu'), required=True, help='cpu: solo para comprobar el montaje')
    a.add_argument('--salida', type=Path, required=True, help='Carpeta del informe; una por separación')
    a.add_argument('--generaciones', type=int, default=30, help='De NSGA-II, la referencia')
    a.add_argument('--poblacion', type=int, default=40)
    a.add_argument('--espacio', help='Espacio de la web donde se confirmará, si pasa')
    a.add_argument('--proyecto', help='Proyecto de prueba de DIgSILENT («PRUEBA…») donde se confirmará, si pasa')
    c = sub.add_parser('confirmar', help='Ejecuta la orden de confirmación por la web')
    c.add_argument('--orden', type=Path, required=True)
    c.add_argument('--url', default='http://127.0.0.1:8765', help='Dirección de la web')
    args = p.parse_args(argv)
    return aplicar(args) if args.accion == 'aplicar' else confirmar(args)


if __name__ == '__main__':
    raise SystemExit(main())
