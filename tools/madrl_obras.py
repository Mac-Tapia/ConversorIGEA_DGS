#!/usr/bin/env python
"""Mide los controles del piloto MADRL sobre la red de un episodio del gemelo o un grafo (spec 074).

Solo lee: no abre DIgSILENT ni escribe en el búfer. Los límites y costos se declaran, porque un piloto
universal no puede traer los de una empresa.

Uso:
    python tools/madrl_obras.py --buffer <carpeta> --proyecto <nombre> --tension-min 0.95 --tension-max 1.05 \
        --carga-max 100 --banco-mvar 0.3 --costo-banco 1 --salida <json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Mide la escalera y NSGA-II en el entorno del piloto MADRL (spec 074).')
    origen = p.add_mutually_exclusive_group(required=True)
    origen.add_argument('--grafo', type=Path, help='JSON con el grafo del oráculo')
    origen.add_argument('--proyecto', help='Proyecto cuya red se toma del búfer de episodios')
    p.add_argument('--buffer', type=Path, help='Carpeta del búfer de episodios, con --proyecto')
    p.add_argument('--caso', default='sin_proyecto', help='Caso de los episodios, con --proyecto')
    p.add_argument('--tension-min', type=float, required=True)
    p.add_argument('--tension-max', type=float, required=True)
    p.add_argument('--carga-max', type=float, required=True, help='Cargabilidad máxima en %%')
    p.add_argument('--banco-mvar', type=float, required=True)
    p.add_argument('--costo-banco', type=float, required=True)
    p.add_argument('--costo-terna-km', type=float, help='Sin él, no se ofrecen ternas')
    p.add_argument('--candidatos', type=int, default=8)
    p.add_argument('--max-bancos', type=int, default=3)
    p.add_argument('--generaciones', type=int, default=30)
    p.add_argument('--poblacion', type=int, default=40)
    p.add_argument('--salida', type=Path, help='JSON con el resultado')
    args = p.parse_args(argv)

    from convertersmartgrid.madrl_obras import (
        ParametrosObras,
        comparar_controles,
        control_nsga2,
        fidelidad,
        zonas_por_fuente,
    )

    if args.grafo:
        grafo = json.loads(args.grafo.read_text(encoding='utf-8'))
    else:
        from convertersmartgrid.digital_twin.buffer import BuferEpisodios, Consulta
        from convertersmartgrid.digital_twin.evolutivo import red_del_gemelo

        episodios = BuferEpisodios(args.buffer).consultar(Consulta(proyecto=args.proyecto, caso=args.caso))
        grafo = red_del_gemelo(episodios)
        if grafo is None:
            print(f'ERROR: el búfer no tiene la red de {args.proyecto} en {args.caso}')
            return 2
        # 074:RF-7: una red que el entorno no reproduce no sirve de referencia para el aprendizaje.
        medido = next((e for e in reversed(episodios) if not (e.accion or {}).get('escenario') and e.flujo
                       and ((e.topologia or {}).get('grafo') or {}).get('nodos')), None)
        if medido is not None:
            carga = (medido.flujo.get('cargabilidad') or {}).get('valores') or {}
            f = fidelidad(medido.topologia['grafo'], (medido.flujo.get('tensiones') or {}).get('valores') or {},
                          {**(carga.get('lineas') or {}), **(carga.get('transformadores') or {})})
            print(f"Fidelidad frente a DIgSILENT: {f['motivo']}" + (
                f" (tensión media {f['error_tension_pu']:.4f}, máx. {f['error_tension_max_pu']:.4f} p.u.; "
                f"carga media {f['error_carga_pct']:.1f}, máx. {f['error_carga_max_pct']:.1f} %)" if 'error_carga_pct' in f else ''))
            if not f['vale']:
                print('Esta red no entra al piloto; los controles que siguen solo orientan.')
    zonas = zonas_por_fuente(grafo)
    if not zonas:
        print('ERROR: el grafo no tiene ninguna fuente')
        return 2
    parametros = ParametrosObras(args.tension_min, args.tension_max, args.carga_max, args.banco_mvar, args.costo_banco,
                                 args.costo_terna_km, args.candidatos, args.max_bancos)
    r = comparar_controles(grafo, zonas, parametros, medir_nsga2=lambda e: control_nsga2(
        e, generaciones=args.generaciones, poblacion=args.poblacion))
    print(f"{len(grafo['nodos'])} barras, {len(zonas)} agente(s); al inicio: en norma {r['inicio']['en_norma']}, "
          f"mínima {r['inicio']['vm_min']:.4f} p.u.")
    for clave in ('escalera', 'nsga2'):
        c = r[clave]
        print(f"{clave}: en norma {c['en_norma']}, costo {c['costo']:.1f}, mínima {c['vm_min']:.4f} p.u., "
              f"{len(c['obras'])} obra(s), {c['evaluaciones']} evaluación(es)")
    if args.salida:
        args.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
