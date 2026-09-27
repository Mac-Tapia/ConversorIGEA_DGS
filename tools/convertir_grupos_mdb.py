"""Varios alimentadores de una base CYMDIST en un solo DGS, importado y con flujo.

    python tools\\convertir_grupos_mdb.py --mdb D:\\...\\260924.mdb ^
        --catalogo input\\catalogo_parametros.xlsx ^
        --grupo CA101_PE104=CA101,PE104 --grupo NA203_NA205=NA203,NA205 ^
        --out-dir output\\grupos_260924 --importar

Qué hace con cada grupo:

1. Lee la red de la base Access. Si la base no trae tablas de equipos (``CYMEQ*``
   vacías), los parámetros salen del **Excel de catálogo**: la identidad de cada tramo
   —código, material, sección, aéreo o subterráneo— es la de la base; los valores, los
   ``*_modelo_*`` del Excel; y las filas marcadas ``ficha`` o ``derivado`` los
   reemplazan (``catalog.aplicar_correcciones``). Un código que el Excel no tenga se
   completa con el del mismo material y sección, y se informa.
2. Construye cada alimentador en modo **estricto** con su geografía: longitudes y
   dibujo a escala real desde las coordenadas de la base.
3. Funde los tramos puente ``DEFAULT`` (``igea_dgs.puentes``): los seccionadores pasan a
   ``ElmCoup`` y las SED quedan en su barra. Ningún elemento de la base se pierde; el
   cuadre elemento a elemento va en el informe.
4. Une los alimentadores del grupo en una sola red (``combine``) y escribe el DGS.
5. Con ``--importar``: lo importa en PowerFactory como proyecto nuevo, corre el flujo
   —solo opciones del *solver*, sin tocar el modelo— y comprueba que lo importado
   coincide con el DGS y que hay diagrama.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from igea_dgs.access import read_access_dataset  # noqa: E402
from igea_dgs.catalog import (  # noqa: E402
    aplicar_correcciones, leer_catalogo, leer_trafos, tablas_equipo_desde_catalogo,
)
from igea_dgs.combine import combine_models  # noqa: E402
from igea_dgs.dgs import write_dgs  # noqa: E402
from igea_dgs.geography import assert_metre_source_crs, build_geography  # noqa: E402
from igea_dgs.model import build_feeder_model  # noqa: E402
from igea_dgs.naming import feeder_short_name  # noqa: E402
from igea_dgs.puentes import es_puente, fundir_puentes  # noqa: E402
from igea_dgs.sed_potencia import redimensionar_sobrecargadas  # noqa: E402
from igea_dgs.trafomix import excluir_trafomix  # noqa: E402
from igea_dgs.validate import parse_dgs, validate_dgs  # noqa: E402

#: Tipo de marcador de CYMDIST. Solo sirve para que los tramos puente tengan un tipo
#: mientras se construye el modelo: se funden antes de escribir y ninguno llega al
#: DGS (se comprueba). Sin él, el resolvedor los asignaría por parecido de nombre a un
#: conductor real.
MARCADOR_DEFAULT = {'ID': 'DEFAULT', 'R1': '0.4', 'R0': '0.4', 'X1': '0.4', 'X0': '1.4',
                    'B1': '0', 'B0': '0', 'Amps': '400'}


def _net_ids(dataset, nombres: list[str]) -> list[str]:
    por_nombre = {feeder_short_name(n): n for n in dataset.feeder_ids()}
    faltan = [n for n in nombres if n not in por_nombre and n not in dataset.feeder_ids()]
    if faltan:
        raise SystemExit(f'No están en la base: {", ".join(faltan)}')
    return [por_nombre.get(n, n) for n in nombres]


def _mdb_inventario(dataset, nets: list[str]) -> dict:
    """Lo que la base trae para estos alimentadores, contado en la fuente."""
    secciones = [s for n in nets for s in dataset.feeders.get(n, ())]
    ids = set(secciones)
    lc = [dataset.line_configurations[s] for s in secciones if s in dataset.line_configurations]
    return {
        'tramos': len(secciones),
        'tramos_aereos': sum(1 for x in lc if x['Overhead'] == '1'),
        'tramos_subterraneos': sum(1 for x in lc if x['Overhead'] == '0'),
        'tramos_DEFAULT': sum(1 for x in lc if x['LineCableID'].upper() == 'DEFAULT'),
        'seccionadores': sum(1 for d in dataset.sectionalizer_settings if d['SectionID'] in ids),
        'interruptores': sum(1 for d in dataset.switch_settings if d['SectionID'] in ids),
        'cargas': sum(1 for k in dataset.load_placements if k[0] in ids),
        'puntos_intermedios': sum(1 for p in dataset.intermediate_nodes if p['SectionID'] in ids),
        'codigos': dict(Counter(x['LineCableID'] for x in lc).most_common()),
    }


def construir_grupo(dataset, nombre: str, nets: list[str], *, correcciones, crs: str,
                    out_dir: Path, trafos: dict | None = None, hoja: str | None = None) -> dict:
    modelos, por_alimentador = [], {}
    for net in nets:
        m = build_feeder_model(dataset, net, strict=True, include_geography=True)
        cambios = aplicar_correcciones(m, correcciones) if correcciones else []
        puentes = fundir_puentes(m)
        # Trafomix (medición MT, SED «M…»): no son SED. Antes de redimensionar, para
        # que un trafomix no cuente como transformador sobrecargado.
        tfx = excluir_trafomix(m)
        redimensiones = redimensionar_sobrecargadas(m)
        m.diagram_sheet = hoja
        # Todo tramo lleva su símbolo, también los de menos de 1 m: no se omite nada.
        m.diagram_max_stub_m = -1.0
        restos = [ln.section_id for ln in m.lines if es_puente(ln)]
        if restos:
            raise SystemExit(f'{m.name}: quedaron tramos DEFAULT sin fundir: {restos[:5]}')
        por_alimentador[m.name] = {
            'kV': m.nominal_kv,
            'lineas': len(m.lines), 'barras': len(m.nodes), 'cargas': len(m.loads),
            'seds': len(m.seds), 'interruptores_en_tramo': len(m.devices),
            'interruptores_sin_tramo': len(m.couplers),
            'km': round(sum(ln.length_m for ln in m.lines) / 1000.0, 3),
            'puentes': puentes.__dict__,
            'catalogo_cambios': [c.linea() for c in cambios],
            'sed_redimensionadas': [r.linea() for r in redimensiones],
            'trafomix_excluidos': tfx.excluidos,
            'trafomix_cargas_nulas_quitadas': tfx.cargas_nulas_quitadas,
            'trafomix_con_carga_en_mt': tfx.cargas_conservadas_mt,
            'tipos': sorted({t.code for t in m.line_types.values()}),
            'islas': m.islands,
        }
        modelos.append(m)
        print(f'  {m.name}: {len(m.lines)} líneas, {len(m.couplers)} seccionadores sin tramo, '
              f'{len(m.loads)} cargas, {len(m.seds)} SED — {puentes.texto()}')
        if cambios:
            print(f'    catálogo: {len(cambios)} característica(s) reemplazadas por ficha')
        for r in redimensiones:
            print(f'    SED redimensionada — {r.linea()}')

    combinado, informe = combine_models(modelos, name=nombre)
    geografia = build_geography(dataset, combinado, source_crs=crs)
    destino = out_dir / f'{nombre}.dgs'
    manifiesto = write_dgs(combinado, destino, geography=geografia, trafos=trafos)
    kvas = [round(max(float(s.design_kva), 1.0), 3) for s in combinado.seds]
    trafos_catalogo = sum(1 for k in kvas if k in (trafos or {}))
    validacion = validate_dgs(combinado, destino, geography=geografia)
    tablas = parse_dgs(destino)
    en_dgs = {cls: len(t.get('rows_dict', [])) for cls, t in tablas.items()}
    return {
        'modelo': combinado, 'geografia': geografia, 'dgs': destino,
        'union': informe.text(), 'por_alimentador': por_alimentador,
        'enlaces_entre_alimentadores': len(getattr(combinado.combined, 'ties', ()) or ()),
        'fuera_de_servicio': sorted(getattr(combinado.combined, 'de_energised', ()) or ()),
        'validacion': {k: validacion.get(k) for k in (
            'status', 'errors_total', 'schema_errors', 'structural_errors',
            'connection_errors', 'graphic_errors', 'numeric_errors') if k in validacion},
        'en_dgs': en_dgs,
        'hoja': manifiesto.diagram_sheet,
        'cuadricula_mm': manifiesto.diagram_grid_mm,
        'trafos': {'con_datos_de_catalogo': trafos_catalogo,
                   'con_calculo_reglamento': len(kvas) - trafos_catalogo,
                   'potencias_sin_catalogo': sorted({k for k in kvas if k not in (trafos or {})})},
    }


def cuadre(mdb: dict, res: dict) -> list[str]:
    """Cada elemento de la base, en su sitio del DGS. Devuelve las discrepancias."""
    m = res['modelo']
    fundidos = sum(a['puentes']['fundidos'] for a in res['por_alimentador'].values())
    con_equipo = sum(a['puentes']['tramos'] - a['puentes']['fundidos']
                     for a in res['por_alimentador'].values())
    dgs = res['en_dgs']
    fallos = []
    if mdb['tramos'] != len(m.lines) + fundidos + con_equipo:
        fallos.append(f"tramos: base {mdb['tramos']} ≠ líneas {len(m.lines)} + puentes "
                      f"fundidos {fundidos} + puentes con equipo {con_equipo}")
    if dgs.get('ElmLne', 0) != len(m.lines):
        fallos.append(f"ElmLne {dgs.get('ElmLne', 0)} ≠ líneas del modelo {len(m.lines)}")
    maniobras = mdb['seccionadores'] + mdb['interruptores']
    if maniobras != dgs.get('StaSwitch', 0) + len(m.couplers):
        fallos.append(f"maniobras: base {maniobras} ≠ StaSwitch {dgs.get('StaSwitch', 0)} "
                      f"+ ElmCoup de red {len(m.couplers)}")
    quitadas = sum(a['trafomix_cargas_nulas_quitadas'] for a in res['por_alimentador'].values())
    if mdb['cargas'] - quitadas != dgs.get('ElmLod', 0):
        fallos.append(f"cargas: base {mdb['cargas']} − {quitadas} trafomix de 0 kW "
                      f"≠ ElmLod {dgs.get('ElmLod', 0)}")
    if any(t.code.upper() == 'DEFAULT' for t in m.line_types.values()):
        fallos.append('queda un TypLne DEFAULT en el DGS')
    return fallos


# ---------------------------------------------------------------------------
# PowerFactory
# ---------------------------------------------------------------------------

def _salida_pf(app) -> str:
    for metodo in ('GetOutputWindow',):
        fn = getattr(app, metodo, None)
        if fn is None:
            continue
        try:
            ventana = fn()
            contenido = getattr(ventana, 'GetContent', None)
            if contenido is not None:
                return '\n'.join(str(x) for x in (contenido() or []))
            return str(ventana or '')
        except Exception:  # noqa: BLE001 - varía entre versiones de PF
            return ''
    return ''


def importar(dgs: Path, proyecto: str, en_dgs: dict, hoja=None, grid_mm: float = 0.0) -> dict:
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
    t = time.time()
    info = import_dgs_file(app, dgs, project_name=proyecto)
    salida_import = _salida_pf(app)
    activate_base_study_and_scenario(app)
    ensure_operation_scenario(app)
    print(f'  importado en {time.time() - t:.0f} s como «{info["project_name"]}»')

    # La red se busca por su nombre dentro del proyecto importado: la lista de objetos
    # relevantes para el cálculo puede traer otra primero (la «Summary Grid»).
    proyecto_pf = app.GetActiveProject()
    red_nombre = dgs.stem
    redes = [n for n in (proyecto_pf.GetContents('*.ElmNet', 1) if proyecto_pf else [])
             if n.loc_name == red_nombre]
    if not redes:
        raise SystemExit(f'No se encontró la red «{red_nombre}» en el proyecto importado.')
    inventario = inventory_network(redes[0])

    ldf = execute_load_flow(app, relaxed=False)
    if not ldf.get('pass'):
        print('  primer flujo sin convergencia; se repite con opciones relajadas del solver')
        ldf = execute_load_flow(app, relaxed=True)
    tensiones, sin_resultado = [], 0
    for b in app.GetCalcRelevantObjects('*.ElmTerm'):
        try:
            if b.HasResults():
                u = b.GetAttribute('m:u')
                if u is not None:
                    tensiones.append(float(u))
                    continue
        except Exception:  # noqa: BLE001
            pass
        sin_resultado += 1
    salida_ldf = _salida_pf(app)

    # El diagrama se comprueba por sus objetos, no por una imagen: con el motor sin
    # ventana, WriteWMF produce un fichero de 1 KB sin dibujo, que no prueba nada.
    diagrama, graficos, conectores = None, None, None
    diagrama = redes[0].GetAttribute('pDiagram')
    fuera_de_hoja = None
    formato_importado = diagrama.GetAttribute('cDrawFormat') if diagrama is not None else None
    if diagrama is not None and hoja is not None and hoja.formato:
        # El perfil DGS no tiene campos de hoja: se fijan sobre el diagrama importado.
        diagrama.SetAttribute('cDrawFormat', hoja.formato)
        diagrama.SetAttribute('cDrawOrient', 1 if hoja.orientacion == 'horizontal' else 0)
        diagrama.SetAttribute('rGridX', grid_mm)
        diagrama.SetAttribute('rGridY', grid_mm)
        fuera_de_hoja = sum(
            1 for g in diagrama.GetContents('*.IntGrf', 0)
            if not (0.0 <= g.GetAttribute('rCenterX') <= hoja.width
                    and 0.0 <= g.GetAttribute('rCenterY') <= hoja.height))
    if diagrama is not None:
        graficos = len(diagrama.GetContents('*.IntGrf', 0))
        conectores = len(diagrama.GetContents('*.IntGrfcon', 1))

    def lineas_de_error(texto: str) -> list[str]:
        return [x for x in texto.splitlines()
                if 'error' in x.lower() and 'errors: 0' not in x.lower()]

    diferencias = {}
    for clave, cls in (('lines', 'ElmLne'), ('loads', 'ElmLod'), ('switches', 'StaSwitch'),
                       ('couplers', 'ElmCoup'), ('transformers_2w', 'ElmTr2'),
                       ('substations_sed', 'ElmSubstat'), ('sources', 'ElmXnet')):
        if inventario.get(clave) != en_dgs.get(cls, 0):
            diferencias[cls] = {'powerfactory': inventario.get(clave), 'dgs': en_dgs.get(cls, 0)}
    if graficos is not None and graficos != en_dgs.get('IntGrf', 0):
        diferencias['IntGrf'] = {'powerfactory': graficos, 'dgs': en_dgs.get('IntGrf', 0)}

    return {
        'proyecto': info['project_name'], 'errores_import': info['errors'],
        'inventario_pf': inventario, 'diferencias_con_dgs': diferencias,
        'flujo': {k: ldf.get(k) for k in ('pass', 'return_code', 'return_meaning',
                                          'ldf_valid', 'relaxed', 'errors')},
        'tension_pu': {'min': min(tensiones), 'max': max(tensiones)} if tensiones else None,
        'barras_con_resultado': len(tensiones), 'barras_sin_resultado': sin_resultado,
        'diagrama': diagrama.loc_name if diagrama is not None else None,
        'graficos': graficos, 'conectores': conectores,
        'formato_al_importar': formato_importado,
        'hoja': (f'{hoja.formato} {hoja.orientacion}' if hoja is not None and hoja.formato else None),
        'graficos_fuera_de_hoja': fuera_de_hoja,
        'errores_ventana_import': lineas_de_error(salida_import)[:50],
        'errores_ventana_flujo': lineas_de_error(salida_ldf)[:50],
    }


def main(argv: list[str] | None = None) -> int:
    """Convierte cada grupo por el camino del producto (batch.convert_group) e importa."""
    from types import SimpleNamespace

    from igea_dgs.batch import convert_group
    from igea_dgs.dgs import formato_hoja
    from igea_dgs.reglas import REGLAS_PROYECTO, catalogo_del_proyecto, normalizar_hoja
    from dataclasses import replace

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mdb', required=True)
    p.add_argument(
        '--equipment-db',
        default=None,
        help='MDB complementaria con CYMEQOVERHEADLINE/CYMEQCABLE cuando --mdb no las contiene.',
    )
    p.add_argument('--catalogo', default=None,
                   help='Excel de parámetros. Por defecto el del proyecto (input/).')
    p.add_argument('--grupo', action='append', required=True,
                   help='NOMBRE=AL1,AL2 — alimentadores que van en un mismo DGS. Repetible.')
    p.add_argument('--out-dir', default=str(RAIZ / 'output' / 'grupos'))
    p.add_argument('--source-crs', default='EPSG:32718')
    p.add_argument('--importar', action='store_true')
    p.add_argument('--hoja', default='AUTO', choices=('AUTO', 'A0', 'A1', 'A2', 'A3', 'A4'),
                   help='Lienzo AUTO a escala real (defecto), o hoja A0 … A4.')
    args = p.parse_args(argv)

    assert_metre_source_crs(args.source_crs)
    catalogo = Path(args.catalogo) if args.catalogo else catalogo_del_proyecto()
    reglas = replace(REGLAS_PROYECTO, hoja=normalizar_hoja(args.hoja))
    grupos = {}
    for g in args.grupo:
        nombre, _, lista = g.partition('=')
        grupos[nombre.strip()] = [x.strip() for x in lista.split(',') if x.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'Leyendo {Path(args.mdb).name}…  (catálogo: {catalogo})')
    # La misma lectura que la interfaz: si la base no trae CYMEQ*, el catálogo del
    # proyecto entra por la regla del lector Access.
    dataset = read_access_dataset(args.mdb, equipment_db=args.equipment_db)

    resumen = {'mdb': str(args.mdb), 'equipment_db': str(args.equipment_db) if args.equipment_db else None,
               'catalogo': str(catalogo), 'reglas': reglas.__dict__,
               'grupos': {}}
    fallo = False
    for nombre, feeders in grupos.items():
        print(f'\n=== {nombre}: {", ".join(feeders)} ===')
        man = convert_group(dataset, feeders, out_dir, name=nombre, strict=True,
                            source_crs=args.source_crs, reglas=reglas, catalogo=catalogo)
        print(f"  {man.get('entrada', '')}")
        for alim, inf in (man.get('reglas_por_alimentador') or {}).items():
            print(f"  {alim}: puentes {(inf.get('puentes') or {}).get('tramos', 0)}, "
                  f"trafomix excluidos {(inf.get('trafomix') or {}).get('excluidos', 0)}, "
                  f"SED redimensionadas {len(inf.get('sed_redimensionadas') or [])}, "
                  f"fichas de catálogo {len(inf.get('catalogo') or [])}")
        comp = man.get('completitud') or {}
        print(f"  estado {man['status']} — validación {man.get('errors_total')} errores — "
              f"completitud {'OK' if not comp.get('fallos') else comp['fallos']}")
        print(f"  entrada {comp.get('entrada')}\n  DGS     {comp.get('dgs')}")
        if man.get('de_energised_nodes'):
            print(f"  AVISO: {len(man['de_energised_nodes'])} barras sin camino a fuente "
                  f"(fuera de servicio): {man['de_energised_nodes'][:6]}")
        grupo = {k: man.get(k) for k in (
            'feeders', 'network_ids', 'status', 'error', 'dgs', 'errors_total', 'counts',
            'union', 'ties', 'de_energised_nodes', 'completitud', 'hoja',
            'reglas_por_alimentador', 'entrada')}
        fallo |= man['status'] != 'ok'
        if args.importar and man['status'] == 'ok':
            hoja = man['hoja']
            hoja_ns = None
            grid_mm = 0.0
            if hoja:
                ancho, alto = formato_hoja(hoja['formato'])
                if hoja['orientacion'] == 'vertical':
                    ancho, alto = alto, ancho
                hoja_ns = SimpleNamespace(
                    formato=hoja['formato'], orientacion=hoja['orientacion'],
                    width=ancho, height=alto,
                )
                grid_mm = hoja['cuadricula_mm']
            en_dgs = {c: len(t.get('rows_dict', [])) for c, t in parse_dgs(man['dgs']).items()}
            print('  importando en PowerFactory…')
            pf = importar(Path(man['dgs']).resolve(), f'{nombre}_{time.strftime("%H%M%S")}',
                          en_dgs, hoja=hoja_ns, grid_mm=grid_mm)
            grupo['powerfactory'] = pf
            ok = (pf['flujo']['pass'] and not pf['diferencias_con_dgs']
                  and not pf['graficos_fuera_de_hoja']
                  and not pf['errores_import'] and not pf['errores_ventana_import']
                  and not pf['errores_ventana_flujo'] and pf['graficos'])
            fallo |= not ok
            print(f"  proyecto PF: {pf['proyecto']}; hoja: {pf['formato_al_importar']} → {pf['hoja']}; "
                  f"gráficos fuera de hoja: {pf['graficos_fuera_de_hoja']}")
            print(f"  flujo: {'CONVERGE' if pf['flujo']['pass'] else 'NO CONVERGE'} "
                  f"(relajado={pf['flujo']['relaxed']}); tensión {pf['tension_pu']}")
            print(f"  PowerFactory vs DGS: {pf['diferencias_con_dgs'] or 'idénticos'}; "
                  f"gráficos {pf['graficos']}; errores import {len(pf['errores_ventana_import'])}, "
                  f"flujo {len(pf['errores_ventana_flujo'])}")
        resumen['grupos'][nombre] = grupo

    informe = out_dir / 'informe_grupos.json'
    informe.write_text(json.dumps(resumen, indent=2, ensure_ascii=False, default=str) + '\n',
                       encoding='utf-8')
    print(f'\nInforme: {informe}')
    return 1 if fallo else 0


if __name__ == '__main__':
    raise SystemExit(main())
