"""El diagrama cabe en una hoja normalizada y las coordenadas que faltan salen del grafo.

Dos cosas que el operador ve en PowerFactory y que un DGS puede estropear sin error:

* **La hoja.** PowerFactory dimensiona la hoja importada con el recuadro de los
  gráficos. A 2,08 u/m una red de 50 km pedía una hoja a medida de 38 m de ancho. En
  modo hoja todo debe caer dentro de la hoja pedida, con la misma escala en X y en Y y
  los símbolos en múltiplos de la cuadrícula.
* **Los nodos sin coordenadas.** Se colocan por el grafo: en cadena, en proporción a la
  longitud del tramo; en rama terminal, a la longitud del TXT. Nunca se usan para medir.
"""

from __future__ import annotations

import math

import pytest

from synthetic_export import ExportSpec, load_export
from igea_dgs.coordenadas import ORIGEN_GRAFO, completar_coordenadas

pytest.importorskip('pyproj')


def _dataset(tmp_path, **kw):
    spec = ExportSpec(feeders=1, sections_per_feeder=kw.pop('secciones', 6),
                      loads_per_feeder=2, switches_per_feeder=1, **kw)
    return load_export(spec, tmp_path)


def _cadena(ds):
    """Nodos de la cadena principal del sintético, en orden desde la cabecera."""
    net = ds.feeder_ids()[0]
    secs = [ds.sections[s] for s in ds.feeders[net]]
    siguiente = {s['FromNodeID']: s['ToNodeID'] for s in secs}
    n = next(iter(ds.sources.values()))['NodeID']
    orden = [n]
    while n in siguiente:
        n = siguiente[n]
        orden.append(n)
    return orden


def _xy(ds, n):
    return float(ds.nodes[n]['CoordX']), float(ds.nodes[n]['CoordY'])


# ---------------------------------------------------------------------------
# Coordenadas por el grafo
# ---------------------------------------------------------------------------

def test_sin_huecos_no_toca_nada(tmp_path):
    ds = _dataset(tmp_path)
    antes = {n: dict(v) for n, v in ds.nodes.items()}
    inf = completar_coordenadas(ds)
    assert inf.nodos_sin_coordenada == 0 and ds.nodes == antes


def test_nodo_intermedio_se_interpola_entre_sus_vecinos(tmp_path):
    ds = _dataset(tmp_path)
    cadena = _cadena(ds)
    medio = cadena[len(cadena) // 2]
    real = _xy(ds, medio)
    ds.nodes[medio]['CoordX'] = ''
    ds.nodes[medio]['CoordY'] = ''
    inf = completar_coordenadas(ds)
    assert inf.interpolados == 1 and ds.nodes[medio]['CoordOrigen'] == ORIGEN_GRAFO
    # En el sintético los tramos son iguales y rectos: la interpolación es exacta.
    assert math.dist(_xy(ds, medio), real) < 0.5


def test_rama_terminal_se_prolonga_con_la_longitud_del_txt(tmp_path):
    ds = _dataset(tmp_path)
    cadena = _cadena(ds)
    punta, previo = cadena[-1], cadena[-2]
    ds.nodes[punta]['CoordX'] = ''
    ds.nodes[punta]['CoordY'] = ''
    completar_coordenadas(ds)
    sid = next(s for s, v in ds.sections.items()
               if {v['FromNodeID'], v['ToNodeID']} == {previo, punta})
    largo = float(ds.line_configurations[sid]['Length'])
    assert math.dist(_xy(ds, punta), _xy(ds, previo)) == pytest.approx(largo, rel=1e-6)


def test_componente_sin_ancla_no_se_inventa(tmp_path):
    ds = _dataset(tmp_path)
    for n in ds.nodes.values():
        n['CoordX'] = ''
        n['CoordY'] = ''
    inf = completar_coordenadas(ds)
    assert inf.completados == 0 and inf.sin_ancla
    assert all(not v.get('CoordX') for v in ds.nodes.values())


def test_la_coordenada_inferida_no_cambia_la_longitud_electrica(tmp_path):
    from igea_dgs.model import build_feeder_model

    ds = _dataset(tmp_path)
    cadena = _cadena(ds)
    medio = cadena[len(cadena) // 2]
    ds.nodes[medio]['CoordX'] = ''
    ds.nodes[medio]['CoordY'] = ''
    completar_coordenadas(ds)
    m = build_feeder_model(ds, ds.feeder_ids()[0], strict=False, include_geography=True)
    assert m.nodes[medio].coord_inferida
    for ln in m.lines:
        if medio in (ln.from_node, ln.to_node):
            assert ln.length_source == 'txt'


# ---------------------------------------------------------------------------
# Encaje en la hoja
# ---------------------------------------------------------------------------

def _dgs_en_hoja(tmp_path, formato='A3', **kw):
    from igea_dgs.dgs import write_dgs
    from igea_dgs.geography import build_geography
    from igea_dgs.model import build_feeder_model
    from igea_dgs.validate import parse_dgs, validate_dgs

    ds = _dataset(tmp_path, **kw)
    m = build_feeder_model(ds, ds.feeder_ids()[0], strict=False, include_geography=True)
    m.diagram_sheet = formato
    geo = build_geography(ds, m)
    out = tmp_path / 'h.dgs'
    man = write_dgs(m, out, geography=geo)
    return m, geo, man, validate_dgs(m, out, geography=geo), parse_dgs(out)


def _coordenadas(tablas):
    pts = [(float(r['rCenterX']), float(r['rCenterY'])) for r in tablas['IntGrf']['rows_dict']]
    for c in tablas['IntGrfcon']['rows_dict']:
        n = int(float(c['rX:SIZEROW']))
        pts += [(float(c[f'rX:{i}']), float(c[f'rY:{i}'])) for i in range(n)]
    return pts


def test_el_modo_adaptativo_conserva_la_escala_de_referencia(tmp_path):
    from igea_dgs.dgs import NA205_DIAGRAM_UNITS_PER_METER, write_dgs
    from igea_dgs.geography import build_geography
    from igea_dgs.model import build_feeder_model

    escalas = []
    anchos = []
    for nombre, secciones in (('corta', 6), ('larga', 60)):
        ds = _dataset(tmp_path / nombre, secciones=secciones)
        model = build_feeder_model(
            ds, ds.feeder_ids()[0], strict=False, include_geography=True,
        )
        geography = build_geography(ds, model)
        manifest = write_dgs(model, tmp_path / f'{nombre}.dgs', geography=geography)
        escalas.append(manifest.diagram_sheet.scale)
        anchos.append(manifest.diagram_sheet.width)

    assert escalas == pytest.approx([NA205_DIAGRAM_UNITS_PER_METER] * 2)
    assert anchos[1] > anchos[0]


@pytest.mark.parametrize('formato', ['A0', 'A3', 'A4'])
def test_todo_el_dibujo_cabe_en_la_hoja(tmp_path, formato):
    from igea_dgs.dgs import FORMATOS_HOJA

    _m, _g, man, rep, tablas = _dgs_en_hoja(tmp_path, formato)
    assert rep['errors_total'] == 0, rep
    ancho, alto = FORMATOS_HOJA[formato]
    if man.diagram_sheet.orientacion == 'vertical':
        ancho, alto = alto, ancho
    pts = _coordenadas(tablas)
    assert min(x for x, _ in pts) >= 0 and max(x for x, _ in pts) <= ancho
    assert min(y for _, y in pts) >= 0 and max(y for _, y in pts) <= alto
    # Proporcionada: ocupa al menos el 80 % del lado que la limita.
    uso = max((max(x for x, _ in pts) - min(x for x, _ in pts)) / ancho,
              (max(y for _, y in pts) - min(y for _, y in pts)) / alto)
    assert uso > 0.8


def test_escala_isotropa_conserva_la_forma_de_la_red(tmp_path):
    _m, geo, man, _r, _t = _dgs_en_hoja(tmp_path, 'A3')
    s = man.diagram_sheet.scale
    ids = sorted(geo.nodes)[:2] + sorted(geo.nodes)[-2:]
    for a, b in ((ids[0], ids[-1]), (ids[1], ids[-2])):
        pa, pb = geo.nodes[a], geo.nodes[b]
        metros = math.dist((pa.x, pa.y), (pb.x, pb.y))
        from igea_dgs.dgs import _diagram_mapper_hoja
        mp, _ = _diagram_mapper_hoja(geo, 'A3')
        assert math.dist(mp(pa), mp(pb)) == pytest.approx(metros * s, rel=2e-3)


def test_simbolos_en_multiplos_de_la_cuadricula(tmp_path):
    from igea_dgs.dgs import CUADRICULAS_MM, TAMANO_PROPIO_SIMBOLO, PROPORCION_SIMBOLO

    _m, _g, man, _r, tablas = _dgs_en_hoja(tmp_path, 'A3')
    assert man.diagram_grid_mm in CUADRICULAS_MM
    tamanos = {r['sSymNam']: float(r['rSizeX']) for r in tablas['IntGrf']['rows_dict']}
    base = None
    for sym, rsize in tamanos.items():
        mm = rsize * TAMANO_PROPIO_SIMBOLO[sym] / PROPORCION_SIMBOLO[sym]
        base = base or mm
        assert mm == pytest.approx(base, rel=1e-3), 'todos parten del mismo símbolo tipo'
    assert (base / man.diagram_grid_mm) == pytest.approx(round(base / man.diagram_grid_mm), abs=1e-6)


def test_red_alta_va_en_hoja_vertical(tmp_path):
    from igea_dgs.dgs import _diagram_mapper_hoja
    from igea_dgs.geography import GeoPoint, GeographyManifest

    geo = GeographyManifest(
        feeder='V', network_id='V', source_node='a', source_crs='EPSG:32718',
        target_crs='EPSG:4326',
        nodes={'a': GeoPoint(lat=-14.0, lon=-75.0, x=0, y=0),
               'b': GeoPoint(lat=-13.9, lon=-75.0, x=0, y=11000)},
        lines={}, source_xy_bounds=(0, 0, 0, 11000), target_bounds=(-75, -14, -75, -13.9),
        intermediate_point_count=0, intermediate_section_count=0,
    )
    _mp, hoja = _diagram_mapper_hoja(geo, 'A1')
    assert hoja.orientacion == 'vertical' and hoja.width < hoja.height


def test_formato_desconocido_se_rechaza(tmp_path):
    with pytest.raises(ValueError, match='Formato de hoja'):
        _dgs_en_hoja(tmp_path, 'B7')
