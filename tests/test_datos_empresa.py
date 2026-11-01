"""Spec 012, T3: el libro de la empresa con tasas de falla, tiempos y costes.

Libros sintéticos y sorteados: clases, filas por tipo, telemandados, bancos, moneda y
cifras. Ninguna cifra ni moneda es de una empresa (constitución P13).
"""

from __future__ import annotations

import random
import string

import pytest
from openpyxl import Workbook, load_workbook

from convertersmartgrid import datos_empresa as de

SEMILLAS = [random.randrange(10**6) for _ in range(4)]


def _moneda(rng):
    return ''.join(rng.choice(string.ascii_uppercase) for _ in range(rng.randint(1, 4)))


def _datos(rng):
    """Contenido sorteado de un libro válido, hoja por hoja (sin títulos ni unidades)."""
    clases = rng.sample(list(de.CLASES), rng.randint(1, len(de.CLASES)))
    tasas = [[de.CLASES[c], None, round(rng.uniform(0, 2), 4),
              rng.choice([None, round(rng.uniform(0, 5), 4)]), round(rng.uniform(0.1, 12), 3)]
             for c in clases]
    tipos = [f'T{i}_{rng.randrange(999)}' for i in range(rng.randint(0, 3))]
    for t in tipos:
        tasas.append([de.CLASES[rng.choice(de.POR_KM)], t, round(rng.uniform(0, 2), 4), None,
                      round(rng.uniform(0.1, 12), 3)])
    tele = [f'EQ{rng.randrange(10**5)}' for _ in range(rng.randint(0, 4))]
    tiempos = [[de.TIEMPOS['localizacion'], rng.uniform(1, 90)], [de.TIEMPOS['manual'], rng.uniform(1, 90)]]
    if tele:
        tiempos.append([de.TIEMPOS['telemandada'], rng.uniform(0.1, 5)])
    tasa = rng.choice([0.0, round(rng.uniform(1, 15), 2)])
    bancos = [[rng.choice([50, 100, 150, 300]) * rng.randint(1, 3), rng.randint(1, 6),
               rng.choice(['trifásico', 'Monofasico']), round(rng.uniform(100, 9000), 2),
               rng.randint(5, 30)] for _ in range(rng.randint(1, 3))]
    moneda = _moneda(rng)
    costes = [[de.COSTES['energia'], round(rng.uniform(0.01, 1), 4), f'{moneda}/kWh'],
              [de.COSTES['descuento'], tasa, '%']]
    return {'tasas': tasas, 'tiempos': tiempos, 'telemandados': [[t] for t in tele],
            'bancos': bancos, 'costes': costes}, {'clases': clases, 'tipos': tipos, 'tele': tele,
                                                    'tasa': tasa / 100, 'moneda': moneda}


def _escribir(ruta, datos, *, sin=(), unidades=None):
    wb = Workbook()
    wb.remove(wb.active)
    for hoja in de.HOJAS:
        if hoja.clave in sin:
            continue
        ws = wb.create_sheet(hoja.titulo)
        ws.append([c.titulo for c in hoja.columnas])
        ws.append((unidades or {}).get(hoja.clave) or [c.unidad for c in hoja.columnas])
        for fila in datos.get(hoja.clave, []):
            ws.append(fila)
    wb.save(ruta)
    return ruta


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_libro_valido_se_lee_entero(tmp_path, semilla):
    """012:RF-6, 012:RF-62, 012:RF-8, 012:RF-10, 012:RF-12, 012:RF-13, 012:RF-14, 012:RF-15 —
    una hoja por grupo; por clase, falla permanente, transitoria y reparación; tiempos en
    minutos; telemandados; bancos; coste de la energía y tasa, con la moneda del libro."""
    rng = random.Random(semilla)
    datos, esperado = _datos(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'l.xlsx', datos))
    assert set(libro.tasas) == set(esperado['clases'])
    for fila in datos['tasas']:
        clase = next(k for k, v in de.CLASES.items() if v == fila[0])
        t = libro.tasas_por_tipo[fila[1]] if fila[1] else libro.tasas[clase]
        assert (t.permanente, t.reparacion_h) == pytest.approx((fila[2], fila[4]))
        assert t.transitoria == (pytest.approx(fila[3]) if fila[3] is not None else None)
    assert set(libro.tiempos_min) >= {'localizacion', 'manual'}
    assert ('telemandada' in libro.tiempos_min) == bool(esperado['tele'])
    assert list(libro.telemandados) == sorted(esperado['tele'])
    assert len(libro.bancos) == len(datos['bancos'])
    assert libro.moneda == esperado['moneda'] and libro.tasa_descuento == pytest.approx(esperado['tasa'])
    assert not libro.hojas_que_faltan
    assert de.Libro.desde_dict(libro.a_dict()) == libro


def test_tasa_por_tipo_manda_sobre_la_de_su_clase(tmp_path):
    """012:RF-11, 012:RF-9 — una fila con el tipo del proyecto se usa para ese tipo; los demás
    elementos de su clase, con la de la clase. Solo líneas y cables llevan fila por tipo."""
    datos, _ = _datos(random.Random(7))
    datos['tasas'] = [[de.CLASES['linea'], None, 0.2, None, 3.0], [de.CLASES['linea'], 'TIPO_X', 0.7, None, 5.0]]
    libro = de.leer_libro(_escribir(tmp_path / 'l.xlsx', datos))
    assert de.tasa_para(libro, 'linea', 'TIPO_X').permanente == 0.7
    assert de.tasa_para(libro, 'linea', 'OTRO').permanente == 0.2
    assert de.POR_KM == ('linea', 'cable')
    datos['tasas'].append([de.CLASES['barra'], 'B_X', 0.1, None, 1.0])
    with pytest.raises(de.DatosEmpresaError, match='solo las líneas y los cables'):
        de.leer_libro(_escribir(tmp_path / 'm.xlsx', datos))


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_cada_error_nombra_hoja_fila_y_columna(tmp_path, semilla):
    """012:RF-16 — un negativo, una celda obligatoria vacía o otra unidad se rechazan
    nombrando la hoja, la fila y la columna; se dicen todos a la vez."""
    rng = random.Random(semilla)
    datos, _ = _datos(rng)
    n_neg = rng.randrange(len(datos['tasas']))
    datos['tasas'][n_neg][2] = -abs(rng.uniform(0.1, 3))
    datos['bancos'][0][3] = None
    with pytest.raises(de.DatosEmpresaError) as e:
        de.leer_libro(_escribir(tmp_path / 'l.xlsx', datos, unidades={'tiempos': ['-', 'h']}))
    errores = e.value.errores
    assert any(f'Hoja «Tasas de falla», fila {n_neg + 3}, columna «Falla permanente»' in x and 'negativo' in x
               for x in errores)
    assert any('Hoja «Bancos de condensadores», fila 3, columna «Inversión»: está vacía' in x for x in errores)
    assert any('Hoja «Tiempos», fila 2, columna «Valor»' in x and '«min»' in x for x in errores)


def test_unidad_del_coste_y_de_la_tasa(tmp_path):
    """012:RF-15, 012:RF-16 — la energía va en moneda por kWh y la tasa en %; otra unidad,
    o la unidad vacía de la plantilla, se rechaza."""
    datos, _ = _datos(random.Random(3))
    datos['costes'][0][2] = None
    datos['costes'][1][2] = 'tanto por uno'
    with pytest.raises(de.DatosEmpresaError) as e:
        de.leer_libro(_escribir(tmp_path / 'l.xlsx', datos))
    assert any('Hoja «Costes», fila 3, columna «Unidad»' in x for x in e.value.errores)
    assert any('Hoja «Costes», fila 4, columna «Unidad»' in x and '%' in x for x in e.value.errores)


@pytest.mark.parametrize('falta', ['tasas', 'tiempos', 'telemandados', 'bancos', 'costes'])
def test_hoja_que_falta_bloquea_solo_sus_estudios(tmp_path, falta):
    """012:RF-63, 012:RF-18 — sin una hoja se dice cuál y solo quedan bloqueados los estudios
    que la necesitan."""
    datos, _ = _datos(random.Random(11))
    if falta == 'tiempos':
        datos['telemandados'] = []
    if falta == 'costes':
        datos['bancos'] = []        # sin tasa no hay anualidad; los bancos no importan aquí
    libro = de.leer_libro(_escribir(tmp_path / 'l.xlsx', datos, sin=(falta,)))
    titulo = de.POR_CLAVE[falta].titulo
    assert libro.hojas_que_faltan == [titulo]
    for estudio, hojas in de.NECESITA.items():
        bloqueado = bool(de.que_falta(libro, estudio))
        assert bloqueado == (falta in hojas or (estudio == 'condensadores' and not libro.bancos)), estudio
        if falta in hojas:
            assert any(titulo in x for x in de.que_falta(libro, estudio))
            assert any(titulo in a and estudio in a for a in libro.avisos)


def test_sin_libro_los_tres_estudios_dicen_que_falta():
    """012:RF-19 — sin libro, confiabilidad, reconectadores y condensadores dicen qué les falta."""
    for estudio in de.NECESITA:
        assert de.que_falta(None, estudio) and 'libro' in de.que_falta(None, estudio)[0]
    assert de.que_falta(None, 'flujo') == []


def test_clase_de_la_red_que_el_libro_no_trae():
    """012:RF-17 — una clase que la red tiene y el libro no se nombra con cuántos elementos;
    una que el libro trae y la red no, se ignora."""
    rng = random.Random(5)
    trae = set(rng.sample(list(de.CLASES), 3))
    libro = de.Libro(tasas={c: de.Tasa(c, 0.1, None, 1.0) for c in trae})
    conteo = {c: rng.randint(1, 50) for c in de.CLASES}
    faltan = de.clases_que_faltan(libro, conteo)
    assert len(faltan) == len(de.CLASES) - len(trae)
    for c in set(de.CLASES) - trae:
        assert any(de.CLASES[c] in f and str(conteo[c]) in f for f in faltan)
    assert de.clases_que_faltan(libro, {c: conteo[c] for c in trae}) == []


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_anualidad_de_los_bancos(tmp_path, semilla):
    """012:RF-64, 012:RF-65, 012:RF-14 — el coste anual es la anualidad de la inversión; con
    tasa cero, la inversión entre la vida útil."""
    rng = random.Random(semilla)
    inv, vida, i = rng.uniform(100, 10_000), rng.randint(5, 30), rng.uniform(0.01, 0.2)
    assert de.anualidad(inv, i, vida) == pytest.approx(inv * i * (1 + i) ** vida / ((1 + i) ** vida - 1))
    assert de.anualidad(inv, 0.0, vida) == pytest.approx(inv / vida)
    datos, esperado = _datos(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'l.xlsx', datos))
    for b, fila in zip(libro.bancos, datos['bancos']):
        assert b.coste_anual == pytest.approx(de.anualidad(fila[3], esperado['tasa'], fila[4]))


def test_plantilla_con_sus_hojas_columnas_unidades_y_una_fila_por_clase(tmp_path):
    """012:RF-7 — la plantilla trae cada hoja con sus columnas y unidades y una fila por
    clase, sin cifras ni moneda: sin rellenar se rechaza por sus celdas vacías."""
    ruta = de.plantilla(tmp_path / 'plantilla.xlsx')
    wb = load_workbook(ruta)
    assert wb.sheetnames == [h.titulo for h in de.HOJAS]
    for h in de.HOJAS:
        ws = wb[h.titulo]
        assert [c.value for c in ws[1]] == [c.titulo for c in h.columnas]
        assert [c.value for c in ws[2]] == [c.unidad for c in h.columnas]
    clases = [fila[0].value for fila in wb['Tasas de falla'].iter_rows(min_row=3)]
    assert clases == list(de.CLASES.values())
    assert all(c.value is None for fila in wb['Tasas de falla'].iter_rows(min_row=3) for c in fila[2:])
    with pytest.raises(de.DatosEmpresaError, match='está vacía'):
        de.leer_libro(ruta)


def test_un_fichero_que_no_es_libro(tmp_path):
    """012:RF-6 — un fichero que no es un libro Excel se rechaza diciéndolo."""
    ruta = tmp_path / 'x.xlsx'
    ruta.write_text('no soy un libro', encoding='utf-8')
    with pytest.raises(de.DatosEmpresaError, match='no es un libro Excel'):
        de.leer_libro(ruta)
