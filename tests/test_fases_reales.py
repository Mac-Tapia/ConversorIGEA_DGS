"""Spec 054: fases reales en el DGS (tramos y SED monofásicos y bifásicos).

Lo medido en DIgSILENT en una copia de NJA202 (2026-11-01) está en la spec; aquí se comprueba
lo que el conversor escribe, con la muestra de las pruebas (que trae tramos monofásicos) y con
la misma muestra forzada a trifásica.
"""
from __future__ import annotations

import pytest

from convertersmartgrid import dgs
from convertersmartgrid.batch import convert_selection


def _tablas(texto: str) -> dict[str, tuple[list[str], list[list[str]]]]:
    tablas, actual = {}, None
    for linea in texto.splitlines():
        if linea.startswith('$$'):
            nombre, *campos = linea[2:].split(';')
            actual = nombre
            tablas[nombre] = ([c.split('(')[0] for c in campos], [])
        elif actual and linea.startswith('  '):
            tablas[actual][1].append(linea.strip().split(';'))
    return tablas


def _filas(tablas, nombre) -> list[dict[str, str]]:
    campos, filas = tablas.get(nombre, ([], []))
    return [dict(zip(campos, f)) for f in filas]


def _dgs(ds, feeder, carpeta, opciones) -> dict:
    manifiesto = convert_selection(ds, [feeder], carpeta, **opciones)
    assert manifiesto['summary']['ok'] == 1, manifiesto['feeders'][0].get('error')
    return _tablas((carpeta / f'{feeder}.dgs').read_text(encoding=dgs.DGS_ENCODING))


def test_ayudas_de_fases():
    """054:RF-3, 054:RF-5 — letras de fase (ABC si la fuente no dice), tecnología de la barra y
    qué fase de la barra toma cada fase del elemento."""
    assert dgs.letras_de_fase('') == 'ABC' and dgs.letras_de_fase('B') == 'B'
    assert dgs.PHTECH_POR_FASES == {3: 0, 2: 4, 1: 6}
    assert dgs.it2p_de('B', 'ABC') == {'it2p1': 1, 'it2p2': 1, 'it2p3': 2}
    assert dgs.it2p_de('B', 'B') == {'it2p1': 0, 'it2p2': 1, 'it2p3': 2}
    assert dgs.it2p_de('BC', 'ABC') == {'it2p1': 1, 'it2p2': 2, 'it2p3': 2}
    assert dgs.it2p_de('ABC', 'ABC') == {'it2p1': 0, 'it2p2': 1, 'it2p3': 2}


def test_sed_de_una_fase_que_no_llega_toma_las_del_ramal_en_txt_y_mdb():
    """054:RF-9 — en el modelo común, no solo en VNR-GIS: una SED C en un ramal AB (Pisco) dejaba su baja a 0 p.u."""
    from dataclasses import replace

    from convertersmartgrid.fases_red import fases_desde_la_cabecera
    from convertersmartgrid.model import Line, Load, _fases_coherentes

    def linea(i, a, b, fase):
        return Line(i, a, b, fase, 'T', 'T', 1.0, True)

    def carga(i, nodo, fase):
        return Load(i, i, '', '', nodo, .01, 0., 1., 10., 0., fase, sed_code=i)

    lineas = [linea('T0', 'H', 'N0', 'ABC'), linea('R1', 'N0', 'N1', 'AB'), linea('R2', 'N1', 'N2', 'A'),
              linea('R3', 'N2', 'N3', 'C')]                # otra letra: toma la del padre
    cargas = [carga('S1', 'N1', 'C'), carga('S2', 'N0', 'C'), carga('S3', 'N1', 'AB'), carga('S4', 'ISLA', 'C')]
    nuevas, resultado, avisos = _fases_coherentes('F', 'H', lineas, cargas)
    assert {x.section_id: x.phase for x in nuevas}['R3'] == 'A'
    assert [x.phase for x in resultado] == ['A', 'C', 'AB', 'C']       # la isla no se toca: nadie sabe qué le llega
    assert 'FASE_RECONSTRUIDA' in avisos[0] and '1 tramo' in avisos[0] and '1 SED' in avisos[0]
    # Cada SED con su alimentador, su fase original y la asignada, para el informe de conversión.
    assert avisos[1:] == ['F: FASE_RECONSTRUIDA, S1: fase C → A.']
    # Tres tras uno: devuelve sus fases aguas arriba, hasta un tramo que las tenga.
    cambiados, en_nodo = fases_desde_la_cabecera(
        [('A', 'H', 'N', 'ABC'), ('B', 'N', 'M', 'A'), ('C', 'M', 'P', 'ABC')], 'H')
    assert cambiados == {'B': 'ABC'} and en_nodo['P'] == 'ABC'
    # Lo coherente no cambia ni se anota, con cualquier código: los objetos son los mismos.
    bien = [replace(lineas[0], phase='7'), replace(lineas[1], phase='4')]
    nuevas, cargas_ok, avisos = _fases_coherentes('F', 'H', bien, [carga('S', 'N1', '1')])
    assert nuevas == bien and cargas_ok[0].phase == '1' and avisos == []


@pytest.mark.parametrize('layout', ('reducido', 'completo'))
@pytest.mark.parametrize('semilla', (1, 7, 23))
def test_fases_que_llegan_en_las_dos_disposiciones_y_con_cualquier_numero_de_workers(tmp_path, layout, semilla):
    """054:RF-9 — con un tamaño sorteado, ningún tramo ni SED del TXT queda con fases que no le llegan, y el DGS es
    idéntico byte a byte con uno y con varios procesos."""
    import random

    from synthetic_export import ExportSpec, load_export

    from convertersmartgrid.fases_red import fases_desde_la_cabecera
    from convertersmartgrid.model import build_feeder_model, decode_phase

    azar = random.Random(semilla)
    spec = ExportSpec(feeders=azar.randint(2, 4), sections_per_feeder=azar.randint(4, 9),
                      loads_per_feeder=azar.randint(2, 4), layout=layout)
    ds = load_export(spec, tmp_path / 'export')
    feeders = sorted(ds.feeders)
    for red in feeders:
        m = build_feeder_model(ds, red, strict=False)
        tramos = [(x.section_id, x.from_node, x.to_node, decode_phase(x.phase) or 'ABC') for x in m.lines]
        cambiados, en_nodo = fases_desde_la_cabecera(tramos, m.source_node)
        assert cambiados == {}, 'lo reconstruido ya no se tiene que reconstruir'
        for c in m.loads:
            if c.node_id in en_nodo:
                assert set(decode_phase(c.phase) or 'ABC') <= set(en_nodo[c.node_id])
    uno, varios = tmp_path / 'uno', tmp_path / 'varios'
    convert_selection(ds, feeders, uno, workers=1, source_crs='EPSG:32718')
    convert_selection(ds, feeders, varios, workers=2, source_crs='EPSG:32718')
    dgs_uno = sorted(uno.rglob('*.dgs'))
    assert dgs_uno and [x.name for x in dgs_uno] == [x.name for x in sorted(varios.rglob('*.dgs'))]
    for x in dgs_uno:
        assert x.read_bytes() == next(varios.rglob(x.name)).read_bytes()


def test_carga_monofasica_con_tres_fases_con_valor_recibe_su_potencia():
    """054:RF-11 — decide su técnica, no cuántas fases tienen valor; la trifásica no toca su modo (tres_fases)."""
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    ruta = Path(__file__).resolve().parents[1] / 'tools' / 'cargas_pf.py'
    spec = importlib.util.spec_from_file_location('cargas_pf_prueba', ruta)
    guion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guion)

    def carga(tecnica):
        return SimpleNamespace(i_sym=1, mode_inp='PC', phtech=tecnica, plini=1e-10, coslini=.97, pf_recap=0,
                               plinir=.008, plinis=.008, plinit=.008, qlinir=.002, qlinis=.002, qlinit=.002)

    mono = carga('1PH PH-E')
    guion.escribir_carga(mono, .0245, .004975)
    assert mono.plini == pytest.approx(.0245)
    # 054:RF-12: la trifásica de fases iguales va al escenario y no reescribe las fases compartidas entre casos.
    tres = carga("3PH-'D'")
    guion.escribir_carga(tres, .03, .006)
    assert tres.i_sym == 0 and tres.plini == pytest.approx(.03) and tres.plinir == pytest.approx(.008)
    # Con fases distintas conserva su reparto (054:RF-12).
    distinta = carga("3PH-'D'")
    distinta.plinir, distinta.plinis, distinta.plinit = .01, .02, .03
    guion.escribir_carga(distinta, .12, .006)
    assert distinta.i_sym == 1 and distinta.plinit == pytest.approx(.06)


def test_un_acoplador_lleva_las_fases_de_sus_dos_barras():
    """054:RF-3 — trifásico entre trifásicas, como siempre; entre una trifásica y una monofásica, monofásico."""
    assert dgs.fases_de_union('ABC', 'ABC') == 'ABC'
    assert dgs.fases_de_union('ABC', 'B') == 'B' and dgs.fases_de_union('B', 'ABC') == 'B'
    assert dgs.fases_de_union('AB', 'BC') == 'B'
    # Datos que no casan: la barra con menos fases decide, y DIgSILENT calcula.
    assert dgs.fases_de_union('A', 'BC') == 'A'
    assert dgs.it2p_de('B', 'ABC')['it2p1'] == 1 and dgs.it2p_de('B', 'B')['it2p1'] == 0


def test_fases_de_la_sed_por_su_norma():
    """054:RF-1 — sufijo de la norma del regulador: 01 una fase, 02 dos, 03/04/05 tres; las
    letras, las del tramo que llega a su nodo; sin sufijo, trifásica."""
    from vnr_etl.connectors.sqlserver_vnr import fases_de_sed

    assert fases_de_sed('SM03701', 'A') == 'A' and fases_de_sed('SM00501', 'B') == 'B'
    assert fases_de_sed('SB01002', 'ABC') == 'AB' and fases_de_sed('SB00702', 'BC') == 'BC'
    assert fases_de_sed('SB01503', 'ABC') == fases_de_sed('SB10004', 'A') == 'ABC'
    assert fases_de_sed('SC30005', 'ABC') == fases_de_sed('', 'A') == 'ABC'


def test_tramos_monofasicos_con_sus_fases(ds, sample_feeder, tmp_path, opciones_reales):
    """054:RF-2, 054:RF-3, 054:RF-8 — cada tramo monofásico o bifásico con un tipo de su número
    de fases; cada barra con la tecnología de lo que llega a ella; cada cubículo con una fase de
    la barra que existe."""
    t = _dgs(ds, sample_feeder, tmp_path, opciones_reales)
    if 'phtech' not in t['ElmTerm'][0]:
        pytest.skip('la muestra no tiene tramos monofásicos ni bifásicos')
    tipos = {f['FID']: f for f in _filas(t, 'TypLne')}
    fases_tipo = {fid: int(f['nlnph']) for fid, f in tipos.items()}
    assert set(fases_tipo.values()) - {3}, 'ningún tipo con menos de 3 fases'
    assert all(f['loc_name'].endswith(f"_{f['nlnph']}F") for f in tipos.values() if f['nlnph'] != '3')
    lineas = {f['FID']: f['typ_id'] for f in _filas(t, 'ElmLne')}
    barras = {f['FID']: f for f in _filas(t, 'ElmTerm')}
    for c in (f for f in _filas(t, 'StaCubic') if f['obj_id'] in lineas):
        n_linea = fases_tipo[lineas[c['obj_id']]]
        n_barra = {0: 3, 4: 2, 6: 1}[int(barras[c['fold_id']]['phtech'])]
        assert n_linea <= n_barra, (c, n_linea, n_barra)
        assert all(0 <= int(c[f'it2p{k}']) < n_barra for k in range(1, n_linea + 1)), c


def test_todo_trifasico_no_cambia_el_dgs(ds, sample_feeder, tmp_path, opciones_reales, monkeypatch):
    """054:RF-5, 054:RF-6 — con todas las fases ABC, el DGS no trae la columna de fases de la
    barra, ni tipos «_1F»/«_2F», ni trafos monofásicos, y es igual con 1 y con 2 hilos."""
    monkeypatch.setattr(dgs, 'letras_de_fase', lambda _f: 'ABC')
    a, b = tmp_path / 'a', tmp_path / 'b'
    t = _dgs(ds, sample_feeder, a, {**opciones_reales, 'workers': 1})
    assert 'phtech' not in t['ElmTerm'][0]
    assert all(f['nlnph'] == '3' for f in _filas(t, 'TypLne'))
    assert all(f['nt2ph'] == '3' for f in _filas(t, 'TypTr2'))
    _dgs(ds, sample_feeder, b, {**opciones_reales, 'workers': 2})
    assert (a / f'{sample_feeder}.dgs').read_bytes() == (b / f'{sample_feeder}.dgs').read_bytes()


def test_sed_monofasica_como_trafo_monofasico(ds, sample_feeder, tmp_path, opciones_reales, monkeypatch):
    """054:RF-4 — una SED cuya carga es de una fase: trafo de 1 fase en D a la tensión entre
    líneas (con «_1F» en su tipo), su barra de baja 1PH, su acoplador de 1 fase y su carga
    equilibrada (DIgSILENT la hace «1PH PH-E»)."""
    from dataclasses import replace

    import convertersmartgrid.batch as batch

    construir = batch.write_dgs

    def escribir(model, path, **kw):
        claves = {s.load_key for s in model.seds}
        model.loads[:] = [replace(c, phase='A') if (c.section_id, c.device_number) in claves else c
                          for c in model.loads]
        return construir(model, path, **kw)

    monkeypatch.setattr(batch, 'write_dgs', escribir)
    t = _dgs(ds, sample_feeder, tmp_path, opciones_reales)
    trafos = _filas(t, 'TypTr2')
    if not trafos:
        pytest.skip('la muestra no tiene SED')
    for tipo in trafos:
        assert (tipo['nt2ph'], tipo['tr2cn_h'], tipo['tr2cn_l']) == ('1', 'D', 'D')
        assert tipo['loc_name'].endswith('_1F')
        assert float(tipo['utrn_h']) > 1.0, 'tensión entre líneas de MT, no la de fase'
    barras_bt = [f for f in _filas(t, 'ElmTerm') if f['loc_name'].endswith('_BT')]
    assert barras_bt and all(f['phtech'] == '6' for f in barras_bt)
    acopladores = [f for f in _filas(t, 'ElmCoup') if f['loc_name'].startswith('SW_')]
    assert all(f['nphase'] == '1' for f in acopladores)
    cargas_sed = {f['loc_name'] for f in _filas(t, 'ElmLod')}
    assert cargas_sed and all(f['i_sym'] == '1' for f in _filas(t, 'ElmLod')
                              if f['fold_id'] in {s['FID'] for s in _filas(t, 'ElmSubstat')})


def test_flujo_desequilibrado_si_hay_monofasicos():
    """054:RF-7 — con una línea o un trafo de menos de 3 fases, la red pide el flujo
    desequilibrado, y el flujo común lo pone; toda trifásica, no se toca."""
    from types import SimpleNamespace as N

    def app(lineas=3, trafos=3):
        objetos = {'ElmLne': [N(typ_id=N(nlnph=3)), N(typ_id=N(nlnph=lineas))],
                   'ElmTr2': [N(typ_id=N(nt2ph=trafos)), N(typ_id=None)]}
        ldf = N(iopt_net=0, Execute=lambda: 0)
        return N(GetCalcRelevantObjects=lambda patron: objetos[patron[2:]],
                 GetFromStudyCase=lambda _n: ldf, IsLdfValid=lambda: True, ldf=ldf)

    assert not dgs.red_con_monofasicos(app())
    assert dgs.red_con_monofasicos(app(lineas=1)) and dgs.red_con_monofasicos(app(trafos=1))
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    import cargas_pf

    a = app(lineas=1)
    a.GetCalcRelevantObjects = (lambda f: lambda patron: [] if patron == '*.ElmTerm' else f(patron))(
        a.GetCalcRelevantObjects)
    assert cargas_pf.flujo_de_carga(a)['converged'] and a.ldf.iopt_net == 1
    b = app()
    b.GetCalcRelevantObjects = (lambda f: lambda patron: [] if patron == '*.ElmTerm' else f(patron))(
        b.GetCalcRelevantObjects)
    cargas_pf.flujo_de_carga(b)
    assert b.ldf.iopt_net == 0


def test_ramales_monofasicos_repartidos_entre_fases():
    """054:RF-1, 054:RF-5 — VNR-GIS no dice la fase de un ramal monofásico: cada ramal entero va a
    una fase, el de más kVA a la de menos, y se anota; los trifásicos no se tocan."""
    from vnr_etl.connectors.sqlserver_vnr import repartir_ramales_monofasicos
    from vnr_etl.models.canonical import CanonicalModel, Load, Section

    m = CanonicalModel()
    m.sections += [Section('T0', 'H', 'N0', phases='ABC', feeder_id='F'),
                   Section('R1a', 'N0', 'X1', phases='A', feeder_id='F'),
                   Section('R1b', 'X1', 'X2', phases='A', feeder_id='F'),
                   Section('R2', 'N0', 'Y1', phases='A', feeder_id='F'),
                   Section('R3', 'N0', 'Z1', phases='A', feeder_id='F')]
    m.loads += [Load('S1', 'X2', phases='A', feeder_id='F', connected_kva=50.0),
                Load('S2', 'Y1', phases='A', feeder_id='F', connected_kva=30.0),
                Load('S3', 'Z1', phases='A', feeder_id='F', connected_kva=20.0),
                Load('S4', 'N0', phases='ABC', feeder_id='F', connected_kva=100.0)]
    avisos = []
    repartir_ramales_monofasicos(m, 'F', avisos)
    fase = {s.section_id: s.phases for s in m.sections}
    assert fase['T0'] == 'ABC' and fase['R1a'] == fase['R1b']
    assert {fase['R1a'], fase['R2'], fase['R3']} == {'A', 'B', 'C'}
    assert {c.load_id: c.phases for c in m.loads} == {'S1': fase['R1a'], 'S2': fase['R2'],
                                                       'S3': fase['R3'], 'S4': 'ABC'}
    assert avisos and avisos[0]['code'] == 'FASE_DEDUCIDA'


def test_un_ramal_toma_solo_una_fase_del_tramo_del_que_sale():
    """054:RF-1 — un ramal que cuelga de un tramo bifásico AB va a la A o a la B, nunca a la C."""
    from vnr_etl.connectors.sqlserver_vnr import repartir_ramales_monofasicos
    from vnr_etl.models.canonical import CanonicalModel, Load, Section

    m = CanonicalModel()
    m.sections += [Section('T0', 'H', 'N0', phases='ABC', feeder_id='F'),
                   Section('T1', 'N0', 'N1', phases='AB', feeder_id='F')]
    m.sections += [Section(f'R{i}', 'N1', f'X{i}', phases='A', feeder_id='F') for i in range(4)]
    m.loads += [Load(f'S{i}', f'X{i}', phases='A', feeder_id='F', connected_kva=10.0 * (i + 1))
                for i in range(4)]
    repartir_ramales_monofasicos(m, 'F', [])
    fases = {s.phases for s in m.sections if s.section_id.startswith('R')}
    assert fases <= {'A', 'B'} and fases == {'A', 'B'}


def test_fases_coherentes_desde_la_cabecera():
    """054:RF-9 — un tramo trifásico tras uno monofásico devuelve sus fases aguas arriba; un
    monofásico con otra letra que su padre toma la del padre; una SED, las que le llegan."""
    from vnr_etl.connectors.sqlserver_vnr import coherencia_de_fases
    from vnr_etl.models.canonical import CanonicalModel, Load, Section

    m = CanonicalModel()
    m.sections += [Section('T0', 'H', 'N0', phases='ABC', feeder_id='F'),
                   Section('M1', 'N0', 'N1', phases='C', feeder_id='F'),
                   Section('T2', 'N1', 'N2', phases='ABC', feeder_id='F'),     # tres tras una
                   Section('R1', 'N0', 'X1', phases='B', feeder_id='F'),
                   Section('R2', 'X1', 'X2', phases='A', feeder_id='F')]      # otra letra
    m.loads += [Load('S1', 'N2', phases='ABC', feeder_id='F'),
                Load('S2', 'X2', phases='C', feeder_id='F'),
                Load('S3', 'X1', phases='ABC', feeder_id='F')]   # trifásica en un ramal: la B
    avisos = []
    coherencia_de_fases(m, 'F', 'H', avisos)
    fase = {s.section_id: s.phases for s in m.sections}
    assert fase['M1'] == 'ABC' and fase['T2'] == 'ABC'
    assert fase['R2'] == 'B'
    assert {c.load_id: c.phases for c in m.loads} == {'S1': 'ABC', 'S2': 'B', 'S3': 'B'}
    assert fase['R1'] == 'B'                       # la SED no sube fases al tramo
    assert avisos and avisos[0]['code'] == 'FASE_RECONSTRUIDA'
    # Lo que ya es coherente no cambia ni se anota.
    avisos = []
    coherencia_de_fases(m, 'F', 'H', avisos)
    assert avisos == []

