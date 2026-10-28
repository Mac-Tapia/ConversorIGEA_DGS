"""Spec 022, T1: la estructura de la empresa (zonales, SET y alimentadores)."""
from __future__ import annotations

import json
import os
import random

import pytest

from igea_dgs import estructura as es

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _tabla(rng):
    """Estructura sorteada: zonales, SET con siglas y alimentadores, con su sistema."""
    sistemas = {f'SE{i:04d}': {'nombre': f'Sistema {i}', 'sector': str(rng.choice([2, 3, 4])),
                               'norma': rng.choice(['NTCSE', 'NTCSER'])}
                for i in range(rng.randint(1, 6))}
    zonales, n_set, n_ali = [], 0, 0
    for z in range(rng.randint(1, 5)):
        sets = []
        for _ in range(rng.randint(1, 4)):
            n_set += 1
            alis = []
            for _ in range(rng.randint(1, 8)):
                n_ali += 1
                alis.append({'codigo': f'X{n_ali:03d}', 'sistema': rng.choice(list(sistemas))})
            sets.append({'codigo': f'SET {n_set}', 'nombre': f'Nombre {n_set}',
                         'siglas': [f'S{n_set}'], 'alimentadores': alis})
        zonales.append({'nombre': f'Zonal {z}', 'sets': sets})
    return {'zonales': zonales, 'sistemas': sistemas}


def test_estructura_del_perfil():
    """022:RF-1, 022:RF-2 — zonales, SET y alimentadores con su sistema, sector y norma."""
    rng = random.Random(SEMILLA)
    datos = _tabla(rng)
    e = es.estructura_de_dict(datos)
    assert e.zonales == [z['nombre'] for z in datos['zonales']]
    for z in datos['zonales']:
        for st in z['sets']:
            for a in st['alimentadores']:
                assert e.set_de(a['codigo']).rotulo == f"{st['codigo'].upper()} {st['nombre']}"
                assert e.set_de(a['codigo']).zonal == z['nombre']
                s = e.sistemas[e.alimentadores[a['codigo']].sistema]
                assert s.norma == datos['sistemas'][a['sistema']]['norma']
            assert e.set_de_siglas(st['siglas'][0].lower()).codigo == st['codigo'].upper()


def test_la_estructura_va_en_un_json_aparte(tmp_path):
    """022:RF-1 — el perfil puede nombrar un JSON junto a él; sin estructura, None (RF-6)."""
    datos = _tabla(random.Random(SEMILLA))
    (tmp_path / 'e.json').write_text(json.dumps(datos), encoding='utf-8')
    assert es.estructura_de_perfil({'estructura': 'e.json'}, tmp_path).alimentadores
    assert es.estructura_de_perfil({}) is None
    with pytest.raises(es.EstructuraError):
        es.estructura_de_perfil({'estructura': 'no.json'}, tmp_path)


@pytest.mark.parametrize('mal, dice', [
    ('repetido', 'repetido'), ('sin_set', 'no tiene SET'), ('sin_zonal', 'no tiene zonal'),
])
def test_tabla_mal_formada(mal, dice):
    """022:RF-5 — alimentador repetido, sin SET o SET sin zonal: error que nombra la fila."""
    datos = {'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET 1', 'nombre': 'A', 'alimentadores': [{'codigo': 'A101'}]}]}]}
    if mal == 'repetido':
        datos['zonales'][0]['sets'].append({'codigo': 'SET 2', 'alimentadores': [{'codigo': 'a101'}]})
    elif mal == 'sin_set':
        datos['zonales'][0]['sets'].append({'codigo': '', 'alimentadores': [{'codigo': 'B1'}]})
    else:
        datos['zonales'].append({'nombre': '', 'sets': [{'codigo': 'SET 3', 'alimentadores': ['C1']}]})
    with pytest.raises(es.EstructuraError, match=dice) as exc:
        es.estructura_de_dict(datos)
    assert 'fila' in str(exc.value)


def test_tabla_en_excel_como_la_publica_la_empresa(tmp_path):
    """022:RF-4, 022:RF-5 — la tabla en Excel con los encabezados de la tabla pública, la SET
    con su nombre en la misma celda; una fila repetida se nombra."""
    from openpyxl import Workbook

    rng = random.Random(SEMILLA)
    datos = _tabla(rng)
    wb = Workbook()
    h = wb.active
    h.append(['SISTEMAS ELÉCTRICOS'])
    h.append(['Zonal', 'Codigo Sist. Elect.', 'Nombre Sist. Elect.', 'Aplicación Final 2023-2026',
              'Codigo SET', 'Siglas', 'Codigo VNR Alimentador', 'OBSERVACION'])
    for z in datos['zonales']:
        for st in z['sets']:
            for a in st['alimentadores']:
                s = datos['sistemas'][a['sistema']]
                h.append([z['nombre'], a['sistema'], s['nombre'], s['sector'],
                          f"{st['codigo']} {st['nombre'].upper()}", st['siglas'][0], a['codigo'],
                          'FUERA DE SERVICIO'])
    wb.save(tmp_path / 't.xlsx')
    e = es.leer_tabla_excel(tmp_path / 't.xlsx')
    primero = datos['zonales'][0]['sets'][0]
    st = e.set_de(primero['alimentadores'][0]['codigo'])
    assert (st.codigo, st.nombre) == (primero['codigo'].upper(), primero['nombre'].upper())
    assert len(e.alimentadores) == sum(len(s['alimentadores']) for z in datos['zonales'] for s in z['sets'])
    h.append([datos['zonales'][0]['nombre'], '', '', '', 'SET 99 OTRA', '',
              primero['alimentadores'][0]['codigo']])
    wb.save(tmp_path / 't.xlsx')
    with pytest.raises(es.EstructuraError, match=r'fila \d+.*repetido'):
        es.leer_tabla_excel(tmp_path / 't.xlsx')


def test_asignar_la_entrega():
    """022:RF-19, 022:RF-20, 022:RF-25b — los de la entrega con su SET; los que no están en
    la estructura, «Sin SET»; los de la estructura que no vienen, faltan; SET, zonales y
    sistemas sin redes, omitidos."""
    rng = random.Random(SEMILLA)
    e = es.estructura_de_dict(_tabla(rng))
    todos = sorted(e.alimentadores)
    entrega = rng.sample(todos, rng.randint(1, len(todos))) + ['NUEVO1', 'nuevo2']
    a = es.asignar(e, entrega)
    assert a.sin_set == ['NUEVO1', 'NUEVO2']
    assert set(a.set_de) == {x for x in entrega if x in e.alimentadores}
    assert sorted(a.faltan) == sorted(set(todos) - set(entrega))
    assert set(a.sets) | set(a.omitidos['sets']) == set(e.sets)
    assert all(e.sets[s].zonal in a.zonales for s in a.sets)
    assert not set(a.zonales) & set(a.omitidos['zonales'])
    assert set(a.sistemas) == {e.alimentadores[x].sistema for x in a.set_de}


def test_la_estructura_de_electro_dunas_en_su_perfil(tmp_path):
    """022:RF-3, 022:RF-46 — el perfil local que hereda de Electro Dunas trae la estructura
    de la tabla pública: 4 zonales, NA205 en SET 51 Nasca, siglas SI → SEIN, PA → Paracas."""
    from pathlib import Path

    from igea_dgs.perfil_empresa import estructura_empresa

    local = tmp_path / 'perfil_empresa.json'
    local.write_text('{"perfil": "electro_dunas"}', encoding='utf-8')
    carpeta = Path(__file__).resolve().parents[1] / 'config' / 'perfiles'
    e = estructura_empresa(local, carpeta=carpeta)
    assert e.zonales == ['Chincha', 'Pisco', 'Ica', 'Nasca']
    assert e.set_de('NA205').rotulo == 'SET 51 Nasca'
    assert e.set_de_siglas('SI').codigo == 'SEIN' and e.set_de_siglas('PA').nombre == 'Paracas'
    assert e.sistemas[e.alimentadores['TA122'].sistema].norma == 'NTCSER'
    # SET nueva que la tabla pública aún no trae: PO101 sale de su SET, no de Alto la Luna.
    assert e.set_de('PO101').rotulo == 'SET 35 Pampa de Ocas'
    # 022:RF-80: PO101 es del sistema Pisco (operador, 2026-10-23).
    assert e.set_de_siglas('PO').zonal == 'Pisco' and e.alimentadores['PO101'].sistema == 'SE0046'
    # 022:RF-79: la SET Chincha Nueva, nueva en RED_231026, en Chincha y su sistema.
    # 022:RF-90: CHN es la canónica; CN, la de la red de RED_231026, la misma SET.
    for a in ('CHN101', 'CHN102', 'CHN103', 'CHN201'):
        assert e.set_de(a).rotulo == 'SET CHN Chincha Nueva' and e.set_de(a).zonal == 'Chincha'
        assert e.sistemas[e.alimentadores[a].sistema].nombre == 'Chincha'
    assert e.set_de_siglas('CN').codigo == e.set_de_siglas('CHN').codigo == 'SET CHN'
    assert e.sets['SET CHN'].siglas[0] == 'CHN'
    # 022:RF-70: el zonal Nasca no cabe en una hoja; los demás siguen con una red.
    assert e.zonales_por_set == {'Nasca'}
    sin = tmp_path / 'otro.json'
    sin.write_text('{}', encoding='utf-8')
    assert estructura_empresa(sin, carpeta=carpeta) is None


# --------------------------------------------------------------- 022:RF-37 a RF-46
def _ed():
    from pathlib import Path

    from igea_dgs.perfil_empresa import estructura_empresa
    carpeta = Path(__file__).resolve().parents[1] / 'config' / 'perfiles'
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / 'p.json').write_text('{"perfil": "electro_dunas"}', encoding='utf-8')
    return estructura_empresa(d / 'p.json', carpeta=carpeta)


def test_medidores_de_barra_del_libro(tmp_path):
    """022:RF-37 — las filas «Barra» del libro de medidores, con su nivel, sus siglas, si es
    de central y la barra suelta de un alimentador («Barra/CHI201»)."""
    from openpyxl import Workbook

    from igea_dgs.demanda_medida import leer_medidores_de_barra

    wb = Workbook()
    h = wb.active
    h.append(['codigo alimentador', 'Medidor', 'Nivel Tension', 'siglas'])
    for fila in (['PA217', 'PA217', 22.9, 'PA'], ['Barra', 'B-PA2T1', 22.9, 'PA'],
                 ['Barra', 'B-PA6T1', 60, 'PA'], ['Barra CT ', 'CT_PEDREG', 10, 'PE'],
                 ['Barra/CHI201', 'CHB2T1', 22.9, None], ['Barra', 'B-PN1T2  ', 10, 'PN']):
        h.append(fila)
    wb.save(tmp_path / 'm.xlsx')
    ms = leer_medidores_de_barra(tmp_path / 'm.xlsx')
    assert [m.medidor for m in ms] == ['B-PA2T1', 'B-PA6T1', 'CT_PEDREG', 'CHB2T1', 'B-PN1T2']
    ct = next(m for m in ms if m.medidor == 'CT_PEDREG')
    assert ct.central and ct.siglas == 'PE' and ct.kv == 10
    assert next(m for m in ms if m.medidor == 'CHB2T1').alimentador == 'CHI201'


def test_barras_de_calibracion_con_la_estructura_de_electro_dunas():
    """022:RF-38, 022:RF-42, 022:RF-43, 022:RF-44, 022:RF-45, 022:RF-46 — cada medidor a la
    barra de su SET y nivel; los de 220 kV no; T1 y T2 de Pueblo Nuevo en la misma barra; la
    central en su barra; SI es SEIN; unas siglas sin SET (QX), barra suelta de sus
    alimentadores; sin medidor de barra, el alimentador queda con su propia máxima.
    022:RF-81: CHNB1T1 es de la SET CHN y lleva a CN101, que el libro llama CHN101."""
    from igea_dgs.demanda_medida import MedidorBarra, barras_de_calibracion

    M = lambda med, kv, sig, ct=False, al='': MedidorBarra(med, kv, sig, ct, 1, al)  # noqa: E731
    medidores = [M('B-PA2T1', 22.9, 'PA'), M('B-PA1T1', 10.0, 'PA'), M('B-PA6T1', 220.0, 'PA'),
                 M('B-PN1T1', 10.0, 'PN'), M('B-PN1T2', 10.0, 'PN'), M('B-PN2T2', 22.9, 'PN'),
                 M('CT_PEDREG', 10.0, 'PE', True), M('B-PE1T1', 10.0, 'PE'), M('B-SI1T1', 10.0, 'SI'),
                 M('CHNB1T1', 10.0, 'CHN'), M('QXB1T1', 10.0, 'QX'), M('CT_BH4 NA', 22.9, 'NA', True)]
    kv = {'PA217': 22.9, 'PA111': 10.0, 'PN107': 10.0, 'PE103': 10.0, 'SI112': 10.0, 'NA203': 22.9,
          'CN101': 10.0, 'QX101': 10.0}
    barras, avisos = barras_de_calibracion(_ed(), medidores, list(kv), kv)
    por = {b.clave: b for b in barras}
    assert por['SET 32 22.9 kV'].alimentadores == ['PA217'] and por['SET 32 22.9 kV'].medidores == ['B-PA2T1']
    assert por['SET 32 10 kV'].alimentadores == ['PA111']
    assert por['SET 23 10 kV'].medidores == ['B-PN1T1', 'B-PN1T2']
    assert por['SET 25 10 kV'].centrales == ['CT_PEDREG']
    assert por['SEIN 10 kV'].alimentadores == ['SI112']
    assert por['SET CHN 10 kV'].alimentadores == ['CN101'] and por['SET CHN 10 kV'].medidores == ['CHNB1T1']
    assert por['Suelta QX 10 kV'].alimentadores == ['QX101'] and por['Suelta QX 10 kV'].suelta
    assert not any('220' in b.clave for b in barras)
    assert not any('NA203' in b.alimentadores for b in barras), 'SET 51 solo tiene la central'
    assert any('QX' in a and '022:RF-45' in a for a in avisos)
    assert not any('CHN' in a for a in avisos)


def test_barra_de_60_kv_fija_el_instante_de_toda_su_set():
    """022:RF-84, 022:RF-85, 022:RF-86 — la barra de 60 kV de una SET se lleva todos sus
    alimentadores, de 10 y 22,9 kV, por delante de sus barras de media; la columna SET vale
    con siglas, código o nombre; una SET sin 60 kV sigue con su media; un 60 kV sin SET y
    uno de 220 kV no se usan, sin barra suelta."""
    import random

    from igea_dgs.demanda_medida import MedidorBarra, barras_de_calibracion

    e = _ed()
    rng = random.Random(84)
    M = lambda med, kv, set_: MedidorBarra(med, kv, set_, False, 1)  # noqa: E731
    pn = rng.choice(['PN', 'SET 23', 'Pueblo Nuevo'])                # RF-85: cualquiera vale
    medidores = [M('B-PN60-1', 60.0, pn), M('B-PN60-2', 60.0, 'PN'), M('B-PN1T1', 10.0, 'PN'),
                 M('B-PA1T1', 10.0, 'PA'), M('B-XX60', 60.0, 'XX'), M('B-PN220', 220.0, 'PN')]
    kv = {'PN107': 10.0, 'PN209': 22.9, 'PA111': 10.0}
    barras, avisos = barras_de_calibracion(e, medidores, list(kv), kv)
    por = {b.clave: b for b in barras}
    alta = por['SET 23 60 kV']
    assert alta.alta and alta.medidores == ['B-PN60-1', 'B-PN60-2'], pn
    # PN107 sigue en su barra de 10 kV, que toma el instante de la de 60 kV; PN209, sin
    # barra de 22,9 kV con medidor, va a la de 60 kV con el mismo instante.
    assert por['SET 23 10 kV'].alimentadores == ['PN107'] and por['SET 23 10 kV'].de_alta == 'SET 23 60 kV'
    assert alta.alimentadores == ['PN209']
    assert por['SET 32 10 kV'].alimentadores == ['PA111'] and not por['SET 32 10 kV'].de_alta
    assert not any('XX' in b.clave or '220' in b.clave for b in barras)
    assert any('B-XX60' in a and '022:RF-86' in a for a in avisos)
    assert e.set_de_texto('Chincha Nueva').codigo == 'SET CHN' and e.set_de_texto('') is None
    # Grafías del libro real (2026-10-27): sin espacio, nombre con «SET», siglas de sus
    # alimentadores; y sin columna SET, por el nombre del medidor.
    assert e.set_de_texto('SET41').codigo == 'SET 41' and e.set_de_texto('SET CHINCHA NUEVA').codigo == 'SET CHN'
    assert e.set_de_texto('IN').codigo == 'SET 44' and e.set_de_texto('LTSETINDP_S') is None
    for med, st in (('TMB6T2', 'SET 22'), ('B-PU6T1', 'SET 53'), ('CHNB6T1', 'SET CHN'),
                    ('TA6TR2', 'SET 41'), ('CAB1T2', 'SET 21'), ('B-SPIT1', None)):
        assert (e.set_de_medidor(med).codigo if e.set_de_medidor(med) else None) == st, med
    sin_col = [MedidorBarra('TMB6T2', 60.0, '', False, 1), MedidorBarra('B-TM1T1', 10.0, 'SET 22', False, 2)]
    barras, avisos = barras_de_calibracion(e, sin_col, ['TM101'], {'TM101': 10.0})
    por = {b.clave: b for b in barras}
    assert por['SET 22 10 kV'].de_alta == 'SET 22 60 kV' and por['SET 22 60 kV'].medidores == ['TMB6T2']
    assert any('TMB6T2' in a and 'vacía' in a for a in avisos)


def test_siglas_de_una_set_nueva_son_el_mismo_alimentador():
    """022:RF-81 — CN101 de la red y CHN101 de los libros son el mismo alimentador de la SET
    nueva Chincha Nueva: misma SET, sus medidores y no «faltan»; sin siglas declaradas
    juntas, nada se casa."""
    from igea_dgs.demanda_medida import Medidor, medidores_de
    from igea_dgs.estructura import asignar

    e = _ed()
    for a in ('CHN101', 'CHN102', 'CHN103', 'CHN201'):
        assert e.set_de(a).codigo == 'SET CHN' and e.alimentador(a).codigo == a
    assert e.equivalentes('CN101') == ['CN101', 'CHN101']
    assert e.equivalentes('PA217') == ['PA217'] and e.equivalentes('XYZ1') == ['XYZ1']
    a = asignar(e, ['CHN101', 'CN102', 'CHN103', 'CHN201'])
    assert set(a.set_de.values()) == {'SET CHN'} and not a.sin_set
    assert not {'CHN101', 'CHN102', 'CHN103', 'CHN201'} & set(a.faltan)
    assert e.alimentador('CN102').codigo == 'CHN102', 'la grafía de la red, al canónico'
    libro = [Medidor('CHN101', 'CHN1-M1', 2), Medidor('CN102', 'CN2-M1', 3)]
    assert medidores_de(libro, 'CN101', e.equivalentes('CN101')[1:]) == ['CHN1-M1']
    assert medidores_de(libro, 'CN101') == [], 'sin grafías, el libro no se casa'


def test_maxima_de_la_barra_suma_sus_transformadores():
    """022:RF-39, 022:RF-40 — la máxima de la suma registro a registro, solo en las fechas
    que tienen todos, y su fecha es el instante de sus alimentadores."""
    from datetime import datetime, timedelta

    from igea_dgs.demanda_medida import maxima_de_barra

    t0 = datetime(2026, 7, 1)
    t1 = [(t0 + timedelta(minutes=15 * i), 100.0 + i, 10.0) for i in range(10)]
    t2 = [(t0 + timedelta(minutes=15 * i), 200.0 - 3 * i, 20.0) for i in range(1, 11)]
    m = maxima_de_barra([t1, t2])
    assert m['fecha'] == t0 + timedelta(minutes=15) and m['kw'] == pytest.approx(101 + 197)
    assert m['registros'] == 9 and m['kvar'] == pytest.approx(30.0)
    assert maxima_de_barra([t1, t2], periodo='2026-08') is None
