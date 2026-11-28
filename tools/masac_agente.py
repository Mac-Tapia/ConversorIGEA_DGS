#!/usr/bin/env python
"""Entrena, comprueba y pone en sombra el agente MASAC de obras (spec 114).

Tres órdenes, todas en CPU y sin DIgSILENT:

- ``juguete``: entrena MASAC con semilla fija en una red sintética pequeña (un alimentador) y lo compara con el azar,
  con la escalera, con NSGA-II y con la PPO GATv2 de la 074 en la misma red, medidos todos igual (máxima y valle).
- ``comprobar-api``: pasa la prueba ``parallel_api_test`` de PettingZoo al entorno, con las dependencias aparte del
  ``.venv`` (``requirements-madrl.txt``).
- ``sombra``: propone sobre la red de un JSON junto a la escalera, sin aplicar nada, y lo deja en el registro de
  experiencia con su explicación.

Uso:
    python tools/masac_agente.py juguete --semilla 1 --episodios 80 --salida <json> [--modelo-salida <carpeta>]
    python tools/masac_agente.py comprobar-api [--deps <carpeta>]
    python tools/masac_agente.py sombra --grafo <json> --modelo <carpeta> --registro <carpeta> --tension-min 0.95 \
        --tension-max 1.05 --carga-max 100 --banco-mvar 0.3 --costo-banco 10 --costo-maniobra 1 --costo-perdidas-mw 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

#: La red del juguete y sus límites: sintéticos, de ninguna empresa (un alimentador de 10 kV con su SET de 60/10 kV).
JUGUETE = {'sistemas': 1, 'sets': 1, 'alimentadores': 1, 'barras': 7, 'carga_mw': 0.4, 'semilla_red': 7}
LIMITES_JUGUETE = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100.0, 'banco_mvar': 0.3,
                   'costo_banco': 10.0, 'candidatos': 3, 'max_bancos': 3, 'max_pasos': 4}


def _deps_por_defecto() -> Path:
    return Path(os.environ.get('CSG_MADRL_DEPS') or Path.home() / '.convertersmartgrid' / 'madrl_deps')


def _parametros_juguete(solo_obras: bool):
    from convertersmartgrid.adaptadores.madrl_obras import ParametrosObras
    from convertersmartgrid.adaptadores.masac_entorno import ParametrosAgente

    obras = ParametrosObras(**LIMITES_JUGUETE)
    if solo_obras:
        return ParametrosAgente(obras, costo_maniobra=1.0, costo_perdidas_mw=5.0, factor_valle=0.4, max_tomas=0,
                                max_transferencias=0, max_consignas=0)
    return ParametrosAgente(obras, costo_maniobra=1.0, costo_perdidas_mw=5.0, factor_valle=0.4, paso_consigna_pu=0.01)


def juguete(args) -> int:
    from convertersmartgrid.adaptadores.madrl_obras import (
        EntornoObras,
        EntornoPlano,
        control_escalera,
        control_nsga2_sistema,
        zonas_por_alimentador,
    )
    from convertersmartgrid.adaptadores.masac_entorno import EntornoAgente, red_sintetica
    from convertersmartgrid.adaptadores.masac_politica import (
        ConfigMASAC,
        entrenar_masac,
        evaluar_azar,
        evaluar_masac,
        guardar_masac,
    )
    from convertersmartgrid.adaptadores.masac_sombra import medir_obras

    red = {k: v for k, v in JUGUETE.items() if k != 'semilla_red'}
    grafo = red_sintetica(JUGUETE['semilla_red'], **red)
    salida = {'red': JUGUETE, 'limites': LIMITES_JUGUETE, 'semilla': args.semilla, 'episodios': args.episodios,
              'dispositivo': 'cpu'}
    for clave, solo_obras in (('masac', False), ('masac_solo_obras', True)):
        entorno = EntornoAgente(grafo, _parametros_juguete(solo_obras))
        t0 = time.perf_counter()
        agente, curva = entrenar_masac(entorno, ConfigMASAC(episodios=args.episodios, semilla=args.semilla))
        salida[clave] = {**evaluar_masac(entorno, agente), 'segundos': round(time.perf_counter() - t0, 1),
                         'curva': [round(x, 3) for x in curva]}
        salida[f'azar_{clave}'] = evaluar_azar(entorno, args.episodios_azar, args.semilla)
        if clave == 'masac' and args.modelo_salida:
            guardar_masac(args.modelo_salida, agente, red=JUGUETE, limites=LIMITES_JUGUETE, semilla=args.semilla)
    entorno = EntornoAgente(grafo, _parametros_juguete(False))
    entorno.reset()
    zonas = zonas_por_alimentador(grafo)
    base = EntornoObras(grafo, zonas, entorno.p.obras)
    salida['escalera'] = medir_obras(entorno, base, control_escalera(base))
    base = EntornoObras(grafo, zonas, entorno.p.obras)
    salida['nsga2'] = medir_obras(entorno, base, control_nsga2_sistema(base, semilla=args.semilla))
    try:
        from convertersmartgrid.adaptadores.madrl_politica import Entrenamiento, entrenar_ppo, evaluar_politica
    except ImportError as exc:                                  # la PPO de la 074 pide torch_geometric
        salida['ppo_074'] = {'control': 'ppo_074', 'error': f'falta {exc.name}'}
    else:
        plano = EntornoPlano(EntornoObras(grafo, zonas, entorno.p.obras))
        t0 = time.perf_counter()
        from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu

        # 043:RF-6: la PPO de la 074 usa CUDA si la hay; entrena con el turno de GPU, como madrl_entrenar.py.
        with turno_gpu('masac_agente'):
            politica, curva = entrenar_ppo(plano, Entrenamiento(iteraciones=args.iteraciones_ppo,
                                                                 semilla=args.semilla))
        r = evaluar_politica(plano, politica)
        salida['ppo_074'] = {**medir_obras(entorno, plano.e, {**r, 'control': 'ppo_074'}),
                             'segundos': round(time.perf_counter() - t0, 1), 'curva': [round(x, 3) for x in curva]}
    for clave in ('azar_masac', 'masac', 'masac_solo_obras', 'escalera', 'nsga2', 'ppo_074'):
        c = salida[clave]
        if 'error' in c:
            print(f'{clave}: {c["error"]}')
            continue
        en_norma = c['en_norma'] if isinstance(c['en_norma'], bool) else f'{c["en_norma"]:.0%} de los episodios'
        retorno = f', retorno {c["retorno"]:.2f}' if 'retorno' in c else ''
        print(f'{clave}: en norma {en_norma}, obras {c["costo"]:.1f}, maniobras {c.get("costo_maniobras", 0.0):.1f}'
              f'{retorno}')
    supera = salida['masac']['retorno'] > salida['azar_masac']['retorno']
    print('MASAC supera al azar' if supera else 'MASAC NO supera al azar')
    salida['masac_supera_al_azar'] = supera
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(json.dumps(salida, ensure_ascii=False, indent=2, default=float), encoding='utf-8')
    return 0 if supera else 3


def comprobar_api(args) -> int:
    # Antes de importar el entorno: con PettingZoo en la ruta, el entorno es un ParallelEnv de verdad (114:RF-15).
    sys.path.insert(0, str(args.deps))
    try:
        import pettingzoo
        from pettingzoo.test import parallel_api_test
    except ImportError as exc:
        print(f'ERROR: falta PettingZoo en {args.deps} ({exc.name}); vea requirements-madrl.txt')
        return 2
    from convertersmartgrid.adaptadores.masac_entorno import EntornoAgente, red_sintetica

    entorno = EntornoAgente(red_sintetica(args.semilla, carga_mw=0.6), _parametros_juguete(False))
    if not isinstance(entorno, pettingzoo.ParallelEnv):
        print('ERROR: el entorno no es un ParallelEnv de PettingZoo')
        return 1
    parallel_api_test(entorno, num_cycles=args.ciclos)
    print(f'PettingZoo {pettingzoo.__version__}: {len(entorno.possible_agents)} agentes, API paralela correcta')
    return 0


def sombra(args) -> int:
    from convertersmartgrid.adaptadores.madrl_obras import ParametrosObras
    from convertersmartgrid.adaptadores.masac_entorno import ParametrosAgente
    from convertersmartgrid.adaptadores.masac_politica import cargar_masac
    from convertersmartgrid.adaptadores.masac_sombra import RegistroExperiencia, proponer_en_sombra

    grafo = json.loads(args.grafo.read_text(encoding='utf-8'))
    obras = ParametrosObras(args.tension_min, args.tension_max, args.carga_max, args.banco_mvar, args.costo_banco,
                            args.costo_terna_km, args.candidatos, args.max_bancos)
    p = ParametrosAgente(obras, args.costo_maniobra, args.costo_perdidas_mw, args.factor_valle, args.paso_consigna)
    politica = cargar_masac(args.modelo)
    propuesta = proponer_en_sombra(grafo, p, politica, registro=RegistroExperiencia(args.registro),
                                   protegidos=args.protegido or ())
    for d in propuesta['decisiones']:
        print(f'{d["agente"]}: {d["explicacion"]}')
    print(f'Acierta: {propuesta["acierta"]} (sin aplicar nada; la regla actual es la escalera).')
    if args.salida:
        args.salida.write_text(json.dumps(propuesta, ensure_ascii=False, indent=2, default=float), encoding='utf-8')
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Agente MASAC de obras: caso de juguete, API de PettingZoo y modo sombra (spec 114).')
    sub = p.add_subparsers(dest='orden', required=True)
    j = sub.add_parser('juguete', help='MASAC frente al azar, la escalera, NSGA-II y la PPO de la 074, con semilla fija')
    j.add_argument('--semilla', type=int, default=1)
    j.add_argument('--episodios', type=int, default=80)
    j.add_argument('--episodios-azar', type=int, default=50)
    j.add_argument('--iteraciones-ppo', type=int, default=40)
    j.add_argument('--salida', type=Path)
    j.add_argument('--modelo-salida', type=Path, help='Carpeta donde queda la política MASAC y su manifiesto')
    c = sub.add_parser('comprobar-api', help='parallel_api_test de PettingZoo sobre una red sintética sorteada')
    c.add_argument('--deps', type=Path, default=_deps_por_defecto(), help='Carpeta de las dependencias aparte')
    c.add_argument('--semilla', type=int, default=3)
    c.add_argument('--ciclos', type=int, default=50)
    s = sub.add_parser('sombra', help='Propone sobre una red sin aplicar nada y lo registra')
    s.add_argument('--grafo', type=Path, required=True, help='JSON con el grafo del oráculo')
    s.add_argument('--modelo', type=Path, required=True, help='Carpeta de la política MASAC guardada')
    s.add_argument('--registro', type=Path, required=True, help='Carpeta del registro de experiencia')
    s.add_argument('--tension-min', type=float, required=True)
    s.add_argument('--tension-max', type=float, required=True)
    s.add_argument('--carga-max', type=float, required=True, help='Cargabilidad máxima en %%')
    s.add_argument('--banco-mvar', type=float, required=True)
    s.add_argument('--costo-banco', type=float, required=True)
    s.add_argument('--costo-terna-km', type=float, help='Sin él, no se ofrecen ternas')
    s.add_argument('--candidatos', type=int, default=3, help='Los mismos con que se entrenó la política')
    s.add_argument('--max-bancos', type=int, default=3)
    s.add_argument('--costo-maniobra', type=float, required=True)
    s.add_argument('--costo-perdidas-mw', type=float, required=True)
    s.add_argument('--factor-valle', type=float, help='Demanda de valle frente a la máxima; sin él, solo máxima')
    s.add_argument('--paso-consigna', type=float, help='Paso de la consigna de las fuentes en p.u.; sin él, no se ofrece')
    s.add_argument('--protegido', action='append', help='Elemento que el operador cambió: no se ofrece (repetible)')
    s.add_argument('--salida', type=Path)
    args = p.parse_args(argv)
    return {'juguete': juguete, 'comprobar-api': comprobar_api, 'sombra': sombra}[args.orden](args)


if __name__ == '__main__':
    raise SystemExit(main())
