"""Spec 022, T15: SET y alimentadores nuevos de la entrega (RF-71 a RF-78).

La entrega RED_231026 de Electro Dunas trajo la SET Chincha Nueva (CN101 a CN201), PA219,
COH101 y SC215, que la tabla de la empresa aún no tenía: quedaban «Sin SET» y la
conversión por zonal los dejaba fuera. Las estructuras y las entregas se sortean.
"""
from __future__ import annotations

import os
import random
from types import SimpleNamespace

import pytest

from igea_dgs import estructura as es

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _estructura(rng):
    """Zonales separados 100 km en X; cada SET con siglas propias y sus alimentadores
    alrededor de su cabecera. Devuelve la estructura, las cabeceras y la SET de cada sigla."""
    zonales, cabeceras, n_set = [], {}, 0
    for z in range(rng.randint(2, 5)):
        sets = []
        for _ in range(rng.randint(1, 4)):
            n_set += 1
            siglas = f'Q{chr(65 + n_set // 26)}{chr(65 + n_set % 26)}'   # solo letras, únicas
            x0, y0 = 100_000.0 * z, 1_000.0 * n_set
            alis = []
            for k in range(rng.randint(1, 6)):
                codigo = f'{siglas}{100 + k}'
                alis.append({'codigo': codigo, 'sistema': f'SE{z:04d}'})
                cabeceras[codigo] = (x0 + rng.uniform(-50, 50), y0 + rng.uniform(-50, 50))
            sets.append({'codigo': f'SET {n_set}', 'nombre': f'Nombre {n_set}',
                         'siglas': [siglas] if rng.random() < 0.5 else [], 'alimentadores': alis})
        zonales.append({'nombre': f'Zonal {z}', 'sets': sets})
    datos = {'zonales': zonales,
             'sistemas': {f'SE{z:04d}': {'nombre': f'S{z}'} for z in range(len(zonales))}}
    return es.estructura_de_dict(datos), cabeceras


def test_nuevo_con_las_siglas_de_una_set_va_a_esa_set():
    """022:RF-71, 022:RF-72, 022:RF-76 — PA219 entra en Paracas por sus siglas, también si
    la SET no tiene siglas propias y solo las tienen sus alimentadores; con el sistema que
    comparten los de su SET."""
    rng = random.Random(SEMILLA)
    e, cab = _estructura(rng)
    cab = dict(cab)
    nuevos = {}
    for st in e.sets.values():
        de_la_set = sorted(a for a, x in e.alimentadores.items() if x.set_codigo == st.codigo)
        siglas = es.siglas_de(de_la_set[0])
        nuevo = f'{siglas}{900 + rng.randint(0, 99)}'
        nuevos[nuevo] = st.codigo
        cab[nuevo] = cab[de_la_set[0]] if rng.random() < 0.5 else None   # sin coordenadas, igual
    c = es.completar(e, cab)
    for nuevo, codigo in nuevos.items():
        assert c.set_de(nuevo).codigo == codigo, SEMILLA
        assert c.alimentadores[nuevo].sistema == c.alimentadores[
            next(a for a, x in e.alimentadores.items() if x.set_codigo == codigo)].sistema
        assert c.deducidos[nuevo].startswith('siglas')
    assert es.asignar(c, cab).sin_set == []


def test_siglas_nuevas_forman_una_set_deducida_en_el_zonal_mas_cercano():
    """022:RF-73, 022:RF-74, 022:RF-76 — CN101 a CN201: una SET deducida «SET CN» con los
    cuatro, en el zonal de la cabecera conocida más cercana, sin sistema eléctrico."""
    rng = random.Random(SEMILLA)
    e, cab = _estructura(rng)
    cerca = rng.choice(sorted(cab))
    zonal = e.set_de(cerca).zonal
    x, y = cab[cerca]
    cab = dict(cab)
    nuevos = [f'ZN{100 + k}' for k in range(rng.randint(1, 5))]
    for i, n in enumerate(nuevos):
        # Uno puede no tener coordenadas: basta con que las tenga alguno de la SET (RF-74).
        cab[n] = None if i and rng.random() < 0.3 else (x + 6_500 + i, y)
    c = es.completar(e, cab)
    for n in nuevos:
        st = c.set_de(n)
        assert st.codigo == 'SET ZN' and st.zonal == zonal, SEMILLA
        assert c.alimentadores[n].sistema == ''
        assert c.deducidos[n].startswith('SET deducida')
    assert c.set_de_siglas('ZN').codigo == 'SET ZN'
    assert es.asignar(c, cab).sets.count('SET ZN') == 1


def test_sin_coordenadas_queda_sin_set():
    """022:RF-75 — sin ninguna cabecera con coordenadas no hay zonal: «Sin SET» (RF-19)."""
    e, cab = _estructura(random.Random(SEMILLA))
    cab = {**cab, 'ZZ101': None, 'ZZ102': None}
    c = es.completar(e, cab)
    assert c.set_de('ZZ101') is None and 'ZZ101' not in c.deducidos
    assert es.asignar(c, cab).sin_set == ['ZZ101', 'ZZ102']


def test_completar_no_cambia_la_estructura_y_es_determinista():
    """022:RF-77 — la estructura de entrada no cambia; el resultado no depende del orden de
    la entrega (DGS idéntico byte a byte)."""
    rng = random.Random(SEMILLA)
    e, cab = _estructura(rng)
    antes = (dict(e.sets), dict(e.alimentadores), list(e.zonales))
    cab = {**cab, 'NUEVA101': (5.0, 5.0), 'NUEVA102': (6.0, 6.0), 'OTRA7': (400_000.0, 0.0)}
    claves = list(cab)
    rng.shuffle(claves)
    a = es.completar(e, cab)
    b = es.completar(e, {k: cab[k] for k in claves})
    assert (dict(e.sets), dict(e.alimentadores), list(e.zonales)) == antes
    assert a.sets == b.sets and a.alimentadores == b.alimentadores and a.deducidos == b.deducidos
    assert list(a.sets) == list(b.sets)
    sin_nuevos = es.completar(e, {k: v for k, v in cab.items() if k in e.alimentadores})
    assert sin_nuevos.deducidos == {} and sin_nuevos.alimentadores == e.alimentadores


def test_las_cabeceras_salen_del_inventario(tmp_path):
    """022:RF-77 — el inventario da la cabecera de cada alimentador, la misma para TXT, MDB y
    VNR-GIS, que llegan como el mismo dataset; en las dos disposiciones del export."""
    from igea_dgs.dataset import CymdistDataset
    from igea_dgs.inventory import build_dataset_inventory
    from synthetic_export import ExportSpec, write_export

    rng = random.Random(SEMILLA)
    for layout in ('reducido', 'completo'):
        spec = ExportSpec(feeders=rng.randint(1, 5), layout=layout)
        red, loads, equip = write_export(spec, tmp_path / layout)
        inv = build_dataset_inventory(CymdistDataset.from_files(red, loads, equip))
        cab = es.cabeceras_de_inventario(inv['feeders'])
        assert len(cab) == spec.feeders
        assert all(isinstance(xy, tuple) and len(xy) == 2 for xy in cab.values()), SEMILLA


def test_la_web_ve_la_estructura_completada_y_avisa(monkeypatch):
    """022:RF-77, 022:RF-78 — la estructura del espacio ya trae los nuevos: la selección por
    zonal los incluye y el resumen dice cuáles, con su SET, su zonal y la regla."""
    from igea_dgs import perfil_empresa
    from igea_dgs.web import services

    e, cab = _estructura(random.Random(SEMILLA))
    cerca = sorted(cab)[0]
    zonal = e.set_de(cerca).zonal
    cab = {**cab, 'ZN101': cab[cerca]}
    monkeypatch.setattr(perfil_empresa, 'estructura_empresa', lambda *a, **k: e)
    filas = [{'feeder': f, 'network_id': f'NET_{f}', 'cabecera_xy': list(xy) if xy else None}
             for f, xy in cab.items()]
    ws = SimpleNamespace(demanda={}, inventory={'feeders': filas})
    completa = services.estructura_del_espacio(ws)
    assert completa.set_de('ZN101').zonal == zonal
    monkeypatch.setattr(services, 'group_selection', lambda *_a, **_k: sorted(cab))
    monkeypatch.setattr(services, 'require_loaded', lambda _ws: None)
    elegidos, _nombre, _e = services.sistema_seleccion(ws, [zonal])
    assert 'ZN101' in elegidos
    resumen = services.estructura_resumen(ws)
    d = {x['alimentador']: x for x in resumen['deducidos']}
    assert d['ZN101']['set'] == 'SET ZN' and d['ZN101']['zonal'] == zonal
    assert 'deducida' in d['ZN101']['regla']


def test_la_web_convierte_una_set_sola(monkeypatch):
    """022:RF-82 — con `sets`, solo los alimentadores de esa SET y un nombre con su zonal y
    su código; el resumen trae cada SET con su rótulo y sus alimentadores; una SET que no
    está en la estructura se rechaza."""
    from igea_dgs import perfil_empresa
    from igea_dgs.web import services

    e, cab = _estructura(random.Random(SEMILLA))
    monkeypatch.setattr(perfil_empresa, 'estructura_empresa', lambda *a, **k: e)
    filas = [{'feeder': f, 'network_id': f'NET_{f}', 'cabecera_xy': list(xy) if xy else None}
             for f, xy in cab.items()]
    ws = SimpleNamespace(demanda={}, inventory={'feeders': filas})
    monkeypatch.setattr(services, 'group_selection', lambda *_a, **_k: sorted(cab))
    monkeypatch.setattr(services, 'require_loaded', lambda _ws: None)
    st = e.set_de(sorted(cab)[0])
    esperados = sorted(f for f in cab if e.set_de(f).codigo == st.codigo)
    elegidos, nombre, _e = services.sistema_seleccion(ws, [], [st.codigo])
    assert elegidos == esperados, SEMILLA
    assert nombre.startswith('SISTEMA_') and st.codigo.replace(' ', '_') in nombre
    detalle = {s['codigo']: s for z in services.estructura_resumen(ws)['zonales']
               for s in z['sets_detalle']}
    assert detalle[st.codigo]['alimentadores'] == esperados and detalle[st.codigo]['rotulo'] == st.rotulo
    with pytest.raises(services.UserError, match='SET que no están'):
        services.sistema_seleccion(ws, [], ['SET NO_EXISTE'])


def test_el_informe_de_la_conversion_avisa_de_los_deducidos():
    """022:RF-78 — el aviso de la red unida nombra a cada alimentador deducido."""
    e, cab = _estructura(random.Random(SEMILLA))
    cab = {**cab, 'ZN101': next(iter(cab.values()))}
    c = es.completar(e, cab)
    texto = es.aviso_deducidos(c, ['ZN101', sorted(e.alimentadores)[0]])
    assert 'ZN101' in texto and 'SET ZN' in texto and '022:RF-78' in texto
    assert es.aviso_deducidos(c, sorted(e.alimentadores)[:1]) == ''


@pytest.mark.parametrize('codigo, siglas', [('PA219', 'PA'), ('CHI201', 'CHI'), ('cn101', 'CN'),
                                            ('SI112', 'SI'), ('X', ''), ('123', '')])
def test_siglas_de_un_codigo(codigo, siglas):
    """022:RF-71 — las siglas son las letras del código antes del número."""
    assert es.siglas_de(codigo) == siglas
