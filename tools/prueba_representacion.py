"""Prueba de representación en PowerFactory: red, cargas y SED del TXT, en una hoja.

    python tools\\prueba_representacion.py --red R.txt --cargas C.txt --equipos E.txt ^
        --hoja A0 --out-dir output\\representacion --importar PE104 --importar NA205

Por cada alimentador:

1. Toma del TXT los valores y coordenadas de cada elemento. Los nodos sin
   ``CoordX/CoordY`` se colocan por el grafo (``igea_dgs.coordenadas``) y quedan
   marcados como inferidos.
2. Excluye los trafomix —medición de MT registrada como SED ``M…``—
   (``igea_dgs.trafomix``).
3. Encaja el diagrama en la hoja pedida con escala isótropa y dimensiona los símbolos
   en múltiplos de la cuadrícula (``FeederModel.diagram_sheet``).
4. Valida el DGS y **audita la completitud contra el TXT**: tramos, barras, cargas,
   kW, kvar y maniobras. Todo lo que no llega al DGS se explica o es un fallo.
5. Con ``--importar`` (o ``--muestra``), lo importa en PowerFactory, fija la hoja y la
   cuadrícula del diagrama, comprueba allí que todo gráfico cae dentro de la hoja y
   que lo importado coincide con el DGS, y corre el flujo de potencia.

Sale con 0 si todo cuadra, 1 si algo no.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from igea_dgs.coordenadas import completar_coordenadas  # noqa: E402
from igea_dgs.dataset import CymdistDataset  # noqa: E402
from igea_dgs.dgs import formato_hoja, write_dgs  # noqa: E402
from igea_dgs.geography import assert_metre_source_crs, build_geography  # noqa: E402
from igea_dgs.model import _calc_p_q, build_feeder_model  # noqa: E402
from igea_dgs.naming import feeder_short_name  # noqa: E402
from igea_dgs.sed_potencia import redimensionar_sobrecargadas  # noqa: E402
from igea_dgs.trafomix import es_trafomix, excluir_trafomix  # noqa: E402
from igea_dgs.validate import parse_dgs, validate_dgs  # noqa: E402


# ---------------------------------------------------------------------------
# Completitud: el TXT contra el DGS
# ---------------------------------------------------------------------------

def auditar(dataset, net: str, model, tablas: dict, trafomix) -> dict:
    """Todo lo que el TXT trae para el alimentador, ¿está en el DGS?"""
    secciones = set(dataset.feeders.get(net, ()))
    nodos_txt = {n for s in secciones for n in (dataset.sections[s]['FromNodeID'],
                                                   dataset.sections[s]['ToNodeID'])}
    cargas_txt = dataset.customer_loads_by_feeder.get(net, ())
    # Solo las que el CARGA ubica en un tramo (LOADS): las demás no tienen dónde ir.
    ubicadas = [(k, r) for k, r in cargas_txt if k in dataset.load_placements]
    kw_txt = kvar_txt = 0.0
    for _k, fila in ubicadas:
        p, q, _pf = _calc_p_q(fila)
        kw_txt += p * 1000.0
        kvar_txt += q * 1000.0
    maniobras_txt = len(dataset.switching_by_feeder.get(net, ()))

    n = lambda cls: len(tablas.get(cls, {}).get('rows_dict', []))  # noqa: E731
    red_fids = {r['FID'] for r in tablas['ElmNet']['rows_dict']}
    barras_red = sum(1 for r in tablas['ElmTerm']['rows_dict'] if r.get('fold_id') in red_fids)
    kw_dgs = sum(float(r.get('plini') or 0) for r in tablas['ElmLod']['rows_dict']) * 1000.0
    kvar_dgs = sum(float(r.get('qlini') or 0) for r in tablas['ElmLod']['rows_dict']) * 1000.0
    cargas_esperadas = len(ubicadas) - trafomix.cargas_nulas_quitadas

    fallos = []
    if n('ElmLne') != len(secciones):
        fallos.append(f'tramos: TXT {len(secciones)} ≠ ElmLne {n("ElmLne")}')
    if barras_red != len(nodos_txt):
        fallos.append(f'barras: TXT {len(nodos_txt)} ≠ ElmTerm de red {barras_red}')
    if n('ElmLod') != cargas_esperadas:
        fallos.append(f'cargas: TXT {len(ubicadas)} − {trafomix.cargas_nulas_quitadas} trafomix '
                      f'= {cargas_esperadas} ≠ ElmLod {n("ElmLod")}')
    if abs(kw_dgs - kw_txt) > max(0.5, 1e-4 * kw_txt):
        fallos.append(f'kW: TXT {kw_txt:,.1f} ≠ DGS {kw_dgs:,.1f}')
    if abs(kvar_dgs - kvar_txt) > max(0.5, 1e-4 * abs(kvar_txt)):
        fallos.append(f'kvar: TXT {kvar_txt:,.1f} ≠ DGS {kvar_dgs:,.1f}')
    if n('StaSwitch') != maniobras_txt:
        fallos.append(f'maniobras: TXT {maniobras_txt} ≠ StaSwitch {n("StaSwitch")}')
    if any(es_trafomix(s.code) for s in model.seds):
        fallos.append('queda un trafomix modelado como SED')
    return {
        'txt': {'tramos': len(secciones), 'barras': len(nodos_txt),
                'cargas_en_carga': len(cargas_txt), 'cargas_ubicadas': len(ubicadas),
                'kW': round(kw_txt, 3), 'kvar': round(kvar_txt, 3), 'maniobras': maniobras_txt},
        'dgs': {'ElmLne': n('ElmLne'), 'ElmTerm_red': barras_red, 'ElmLod': n('ElmLod'),
                'ElmSubstat': n('ElmSubstat'), 'ElmTr2': n('ElmTr2'),
                'StaSwitch': n('StaSwitch'), 'kW': round(kw_dgs, 3), 'kvar': round(kvar_dgs, 3)},
        'cargas_sin_ubicar_en_txt': len(cargas_txt) - len(ubicadas),
        'islas': model.islands or {},
        'fallos': fallos,
    }


# ---------------------------------------------------------------------------
# PowerFactory
# ---------------------------------------------------------------------------

def importar(dgs: Path, red_nombre: str, hoja, grid_mm: float, en_dgs: dict) -> dict:
    pf_dir = Path(r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12')
    sys.path.insert(0, str(pf_dir))
    sys.path.insert(0, str(RAIZ / 'tools'))
    import powerfactory  # type: ignore
    from powerfactory_acceptance import (  # type: ignore
        activate_base_study_and_scenario, ensure_operation_scenario, execute_load_flow,
        import_dgs_file, inventory_network,
    )

    app = powerfactory.GetApplication()
    if app is None:
        raise SystemExit('PowerFactory no respondió.')
    try:
        app.ClearOutputWindow()
    except Exception:  # noqa: BLE001
        pass
    proyecto = f'REPR_{red_nombre}_{time.strftime("%H%M%S")}'
    info = import_dgs_file(app, dgs, project_name=proyecto)
    activate_base_study_and_scenario(app)
    ensure_operation_scenario(app)
    prj = app.GetActiveProject()
    redes = [n for n in prj.GetContents('*.ElmNet', 1) if n.loc_name == red_nombre]
    if not redes:
        return {'proyecto': proyecto, 'error': f'no se encontró la red {red_nombre}'}
    red = redes[0]
    diagrama = red.GetAttribute('pDiagram')
    formato_importado = diagrama.GetAttribute('cDrawFormat') if diagrama else None

    # La hoja y la cuadrícula no caben en el DGS (el perfil no tiene esos campos): se
    # fijan aquí, sobre el diagrama importado.
    ajustes = {}
    if diagrama is not None:
        for attr, valor in (('cDrawFormat', hoja.formato),
                            ('cDrawOrient', 1 if hoja.orientacion == 'horizontal' else 0),
                            ('rGridX', grid_mm), ('rGridY', grid_mm), ('grid_on', 1)):
            try:
                diagrama.SetAttribute(attr, valor)
                ajustes[attr] = diagrama.GetAttribute(attr)
            except Exception as exc:  # noqa: BLE001
                ajustes[attr] = f'ERROR {exc}'

    # Todo gráfico dentro de la hoja, leído de PowerFactory y no del DGS.
    ancho, alto = hoja.width, hoja.height
    fuera, graficos = [], 0
    if diagrama is not None:
        for g in diagrama.GetContents('*.IntGrf', 0):
            graficos += 1
            x, y = g.GetAttribute('rCenterX'), g.GetAttribute('rCenterY')
            if not (0.0 <= x <= ancho and 0.0 <= y <= alto):
                fuera.append((g.loc_name, round(x, 2), round(y, 2)))

    inventario = inventory_network(red)
    diferencias = {}
    for clave, cls in (('lines', 'ElmLne'), ('loads', 'ElmLod'), ('switches', 'StaSwitch'),
                       ('couplers', 'ElmCoup'), ('transformers_2w', 'ElmTr2'),
                       ('substations_sed', 'ElmSubstat'), ('sources', 'ElmXnet')):
        if inventario.get(clave) != en_dgs.get(cls, 0):
            diferencias[cls] = {'powerfactory': inventario.get(clave), 'dgs': en_dgs.get(cls, 0)}
    if graficos != en_dgs.get('IntGrf', 0):
        diferencias['IntGrf'] = {'powerfactory': graficos, 'dgs': en_dgs.get('IntGrf', 0)}

    ldf = execute_load_flow(app, relaxed=False)
    tensiones = sorted(b.GetAttribute('m:u') for b in app.GetCalcRelevantObjects('*.ElmTerm')
                       if b.HasResults() and b.GetAttribute('m:u') is not None)
    return {
        'proyecto': proyecto, 'errores_import': info['errors'],
        'formato_creado_al_importar': formato_importado, 'ajustes_diagrama': ajustes,
        'hoja_mm': [ancho, alto], 'graficos': graficos, 'graficos_fuera_de_hoja': fuera[:20],
        'n_fuera_de_hoja': len(fuera), 'diferencias_con_dgs': diferencias,
        'flujo': {k: ldf.get(k) for k in ('pass', 'return_meaning', 'errors')},
        'tension_pu': [round(tensiones[0], 4), round(tensiones[-1], 4)] if tensiones else None,
    }


# ---------------------------------------------------------------------------

def elegir_muestra(res: dict[str, dict], extra: list[str]) -> list[str]:
    """Pequeño, mediano, grande, más alargado, más denso en cargas, y los pedidos."""
    ok = {k: v for k, v in res.items() if not v.get('error')}
    if not ok:
        return extra
    por_tramos = sorted(ok, key=lambda k: ok[k]['audit']['dgs']['ElmLne'])
    elegidos = [por_tramos[0], por_tramos[len(por_tramos) // 2], por_tramos[-1],
                max(ok, key=lambda k: ok[k]['aspecto']),
                max(ok, key=lambda k: ok[k]['audit']['dgs']['ElmLod']
                    / max(ok[k]['audit']['dgs']['ElmLne'], 1))]
    verticales = [k for k in ok if ok[k]['hoja']['orientacion'] == 'vertical']
    if verticales:
        elegidos.append(verticales[0])
    salida = []
    for k in elegidos + extra:
        if k in ok and k not in salida:
            salida.append(k)
    return salida


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--red', required=True)
    p.add_argument('--cargas', required=True)
    p.add_argument('--equipos', required=True)
    p.add_argument('--hoja', default='A0', help='Formato de hoja: A0 … A4 (defecto A0).')
    p.add_argument('--feeder', action='append', default=[],
                   help='Limitar a estos alimentadores. Repetible. Por defecto, todos.')
    p.add_argument('--importar', action='append', default=[],
                   help='Importar este alimentador en PowerFactory. Repetible.')
    p.add_argument('--muestra', action='store_true',
                   help='Importar además una muestra representativa.')
    p.add_argument('--source-crs', default='EPSG:32718')
    p.add_argument('--sin-redimensionar-sed', dest='redimensionar_sed', action='store_false',
                   help='Respetar el kVA del TXT aunque la SED no pueda con su carga.')
    p.add_argument('--out-dir', default=str(RAIZ / 'output' / 'representacion'))
    args = p.parse_args(argv)

    formato_hoja(args.hoja)
    assert_metre_source_crs(args.source_crs)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ds = CymdistDataset.from_files(args.red, args.cargas, args.equipos)
    coords = completar_coordenadas(ds)
    print(coords.texto())

    nombres = {feeder_short_name(n): n for n in ds.feeder_ids()}
    elegidos = [nombres.get(f, f) for f in args.feeder] or list(ds.feeder_ids())
    res: dict[str, dict] = {}
    for net in elegidos:
        nombre = feeder_short_name(net)
        if not ds.feeders.get(net):
            res[nombre] = {'error': 'sin tramos (solo cabecera)', 'omitido': True}
            continue
        try:
            m = build_feeder_model(ds, net, strict=False, include_geography=True)
            tfx = excluir_trafomix(m)
            # SED con más carga que kVA en el TXT: al tamaño normalizado que la cubre
            # (decisión del usuario, igual que en la base 260924). Queda listado.
            redim = redimensionar_sobrecargadas(m) if args.redimensionar_sed else []
            m.diagram_sheet = args.hoja
            m.diagram_max_stub_m = -1.0   # todo tramo con su símbolo: no se omite nada
            geo = build_geography(ds, m, source_crs=args.source_crs)
            destino = out / f'{nombre}.dgs'
            man = write_dgs(m, destino, geography=geo)
            val = validate_dgs(m, destino, geography=geo)
            tablas = parse_dgs(destino)
        except Exception as exc:  # noqa: BLE001 - uno roto no para la prueba
            res[nombre] = {'error': str(exc)}
            print(f'  FALLO {nombre}: {exc}')
            continue
        hoja = man.diagram_sheet
        xs = [p.x for p in geo.nodes.values()]
        ys = [p.y for p in geo.nodes.values()]
        aspecto = max(max(xs) - min(xs), 1) / max(max(ys) - min(ys), 1)
        audit = auditar(ds, net, m, tablas, tfx)
        res[nombre] = {
            'network_id': net, 'dgs': str(destino),
            'validacion_errores': val['errors_total'],
            'hoja': {'formato': hoja.formato, 'orientacion': hoja.orientacion,
                     'ancho_mm': hoja.width, 'alto_mm': hoja.height,
                     'escala_mm_por_m': hoja.scale, 'escala_1_a': round(1000.0 / hoja.scale),
                     'cuadricula_mm': man.diagram_grid_mm},
            'aspecto': max(aspecto, 1 / aspecto),
            'nodos_inferidos': sum(1 for nd in m.nodes.values() if nd.coord_inferida),
            'trafomix': tfx.texto(), 'audit': audit,
            'sed_redimensionadas': [r.linea() for r in redim],
            'en_dgs': {c: len(t.get('rows_dict', [])) for c, t in tablas.items()},
            '_hoja': hoja,
        }
        estado = 'OK' if not audit['fallos'] and not val['errors_total'] else 'REVISAR'
        print(f"  {estado:7} {nombre:8} {hoja.formato} {hoja.orientacion:10} 1:{round(1000 / hoja.scale):>7,} "
              f"cuadrícula {man.diagram_grid_mm:g} mm | {audit['dgs']['ElmLne']} tramos, "
              f"{audit['dgs']['ElmLod']} cargas, {audit['dgs']['ElmSubstat']} SED, "
              f"{tfx.excluidos} trafomix | val {val['errors_total']} err"
              + (f" | {'; '.join(audit['fallos'])}" if audit['fallos'] else ''))

    a_importar = list(dict.fromkeys(args.importar))
    if args.muestra:
        a_importar = elegir_muestra(res, a_importar)
    for nombre in a_importar:
        r = res.get(nombre)
        if not r or r.get('error'):
            print(f'  no se importa {nombre}: {r.get("error") if r else "no convertido"}')
            continue
        print(f'  importando {nombre} en PowerFactory…')
        r['powerfactory'] = importar(Path(r['dgs']).resolve(), nombre, r['_hoja'],
                                     r['hoja']['cuadricula_mm'], r['en_dgs'])
        pf = r['powerfactory']
        print(f"    formato al importar: {pf.get('formato_creado_al_importar')} → {pf.get('ajustes_diagrama', {}).get('cDrawFormat')}; "
              f"gráficos {pf.get('graficos')}, fuera de hoja {pf.get('n_fuera_de_hoja')}; "
              f"PF vs DGS: {pf.get('diferencias_con_dgs') or 'idénticos'}; "
              f"flujo {'CONVERGE' if pf.get('flujo', {}).get('pass') else 'NO'} {pf.get('tension_pu')}")

    for r in res.values():
        r.pop('_hoja', None)
    convertidos = [r for r in res.values() if not r.get('error')]
    resumen = {
        'coordenadas': coords.texto(), 'hoja': args.hoja,
        'alimentadores': len(res), 'convertidos': len(convertidos),
        'omitidos_sin_tramos': [k for k, v in res.items() if v.get('omitido')],
        'fallidos': {k: v['error'] for k, v in res.items() if v.get('error') and not v.get('omitido')},
        'con_descuadre': {k: v['audit']['fallos'] for k, v in res.items()
                          if not v.get('error') and v['audit']['fallos']},
        'con_errores_validacion': [k for k, v in res.items()
                                   if not v.get('error') and v['validacion_errores']],
        'detalle': res,
    }
    (out / 'informe_representacion.json').write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f"\n{resumen['convertidos']} de {resumen['alimentadores']} convertidos; "
          f"sin tramos: {len(resumen['omitidos_sin_tramos'])}; fallidos: {len(resumen['fallidos'])}; "
          f"con descuadre: {len(resumen['con_descuadre'])}; "
          f"con errores de validación: {len(resumen['con_errores_validacion'])}")
    pf_mal = [k for k, v in res.items() if 'powerfactory' in v and (
        v['powerfactory'].get('n_fuera_de_hoja') or v['powerfactory'].get('diferencias_con_dgs')
        or not v['powerfactory'].get('flujo', {}).get('pass'))]
    fallo = bool(resumen['fallidos'] or resumen['con_descuadre']
                 or resumen['con_errores_validacion'] or pf_mal)
    return 1 if fallo else 0


if __name__ == '__main__':
    raise SystemExit(main())
