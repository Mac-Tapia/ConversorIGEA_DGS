"""Spec 012, aclaración de RF-6, RF-8, RF-9, RF-12 y RF-62 (2026-11-14): las tasas de falla y
los tiempos de reposición salen del histórico de interrupciones de la empresa.

Históricos sintéticos y sorteados: nombres y orden de las columnas, filas de título encima,
alimentadores, cómo se da la duración y cuántas interrupciones de cada clase. Ningún nombre
ni cifra de una empresa (constitución P13). El libro real solo se lee con CSG_INTERRUPCIONES.
"""

from __future__ import annotations

import datetime as dt
import os
import random
import re
import string
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from convertersmartgrid.aplicacion import datos_empresa as de
from convertersmartgrid.aplicacion import historico_interrupciones as hi

SEMILLAS = [random.randrange(10**6) for _ in range(4)]

TITULOS = {
    'fecha_inicio': ['Fecha inicio', 'FECHA DE INICIO', 'Fecha Ini.'],
    'hora_inicio': ['Hora inicio', 'HORA INI', 'Hora de inicio'],
    'fecha_fin': ['Fecha fin', 'FECHA DE REPOSICION', 'Fecha término'],
    'hora_fin': ['Hora fin', 'HORA DE REPOSICION', 'Hora término'],
    'fecha_fin_total': ['Fecha fin total', 'FECHA REPOSICION TOTAL'],
    'hora_fin_total': ['Hora fin total', 'HORA REPOSICION TOTAL'],
    'duracion': ['Duración (H:M)', 'DURAC.', 'Duración'],
    'alimentador': ['Alimentador', 'Circuito', 'Salida MT', 'Equipo y línea'],
    'causa': ['Causa', 'Motivo', 'Causa de la interrupción'],
    'programada': ['Tipo', 'Tipo de interrupción', 'Naturaleza'],
    'tension': ['Tensión (kV)', 'kV', 'Nivel de tensión'],
    'clientes': ['Usuarios afectados', 'Clientes afectados'],
}
CAUSAS = {
    'linea': ['Caída de conductor MT', 'Acercamiento de aves', 'Caída de árbol sobre la línea',
              'Descargas atmosféricas'],
    'cable': ['Falla de cable subterráneo', 'Falla en terminación de cable'],
    'transformador': ['Falla de transformador', 'Transformador quemado'],
}
NO_PROGRAMADA = ['Imprevista', 'No programada', 'Forzada']


def _nombre(rng):
    return ''.join(rng.choice(string.ascii_uppercase) for _ in range(rng.randint(1, 3))) + str(rng.randint(100, 999))


def _historico(rng):
    """Filas sorteadas y las tasas que tienen que salir de ellas."""
    alims = list(dict.fromkeys(_nombre(rng) for _ in range(rng.randint(2, 6))))
    exp = {a: {'linea': round(rng.uniform(5, 80), 3), 'cable': round(rng.uniform(0.5, 6), 3),
               'transformador': float(rng.randint(10, 300)), 'barra': float(rng.randint(20, 600))}
           for a in alims}
    d0 = dt.datetime(rng.randint(2015, 2023), rng.randint(1, 12), 1, 0, 0)
    dias = rng.randint(400, 2500)
    anios = dias / 365.25
    eventos = []          # (alimentador, clase, inicio, h_primera, h_total, programada, kv, causa)
    for a in alims:
        for clase in CAUSAS:
            for _ in range(rng.randint(0, 12)):
                h1 = rng.uniform(0.2, 9)
                ht = h1 + rng.uniform(0.5, 6) if rng.random() < 0.3 else h1
                eventos.append([a, clase, h1, ht, False, rng.choice([10, 13.2, 22.9]), rng.choice(CAUSAS[clase])])
        for _ in range(rng.randint(0, 3)):                    # momentáneas: transitoria de la línea
            eventos.append([a, 'linea', 3 / 60, 3 / 60, False, 10, rng.choice(CAUSAS['linea'])])
    # Lo que no cuenta: programadas, alta tensión, otro alimentador y causas sin clase.
    ruido = [[rng.choice(alims), 'x', 2.0, 2.0, True, 10, rng.choice(CAUSAS['transformador'])],
             [rng.choice(alims), 'x', 1.0, 1.0, False, 60, rng.choice(CAUSAS['linea'])],
             ['ZZ' + _nombre(rng), 'x', 1.0, 1.0, False, 10, rng.choice(CAUSAS['linea'])],
             [rng.choice(alims), 'x', 1.0, 1.0, False, 10, 'Causa no determinada']]
    todos = eventos + ruido
    momentos = sorted(rng.uniform(0, dias) for _ in todos)
    momentos[0], momentos[-1] = 0.0, float(dias)          # el periodo es exactamente ``dias``
    rng.shuffle(momentos)
    filas = [(e, d0 + dt.timedelta(days=m)) for e, m in zip(todos, momentos)]
    esperado = {}
    for clase in CAUSAS:
        lista = [e for e in eventos if e[1] == clase]
        sost = [e[3] for e in lista if e[3] > 5 / 60]
        mom = len(lista) - len(sost)
        e_total = sum(x[clase] for x in exp.values())
        esperado[clase] = {'permanente': len(sost) / (e_total * anios), 'transitoria': mom / (e_total * anios),
                           'reparacion_h': (sum(sost) / len(sost)) if sost else 0.0}
    primeras = [e[2] for e in eventos if e[3] > e[2] and e[3] > 5 / 60]
    return filas, exp, esperado, primeras


def _escribir(ruta: Path, filas, rng, *, sin=(), duracion=None, extra=()):
    """El histórico en bruto: columnas sorteadas, en orden sorteado, con un título encima.

    ``extra``: columnas añadidas, ``(título, valor(alimentador, número de fila))``."""
    duracion = duracion or rng.choice(['timedelta', 'minutos', 'fin'])
    conceptos = [k for k in TITULOS if k not in sin]
    if duracion == 'fin':
        conceptos = [k for k in conceptos if k != 'duracion']
    else:
        conceptos = [k for k in conceptos if k not in ('fecha_fin', 'hora_fin')]
    ruido = ['Observación', 'Código'] + [t for t, _ in extra]
    columnas = conceptos + ruido
    rng.shuffle(columnas)
    titulos = []
    for k in columnas:
        if k in TITULOS:
            t = rng.choice(TITULOS[k])
            if k == 'duracion' and duracion == 'minutos':
                t = 'Duración (min)'
            titulos.append(t)
        else:
            titulos.append(k)
    wb = Workbook()
    ws = wb.active
    ws.title = rng.choice(['Interrupciones', 'Registro', 'Hoja1'])
    for _ in range(rng.randint(0, 2)):
        ws.append(['REGISTRO DE INTERRUPCIONES'])
    ws.append(titulos)
    for n_fila, ((a, _clase, h1, ht, prog, kv, causa), ini) in enumerate(filas):
        fin, fin_t = ini + dt.timedelta(hours=h1), ini + dt.timedelta(hours=ht)
        valores = {
            'fecha_inicio': dt.datetime.combine(ini.date(), dt.time()), 'hora_inicio': ini.time(),
            'fecha_fin': dt.datetime.combine(fin.date(), dt.time()), 'hora_fin': fin.time(),
            'fecha_fin_total': dt.datetime.combine(fin_t.date(), dt.time()) if ht > h1 else None,
            'hora_fin_total': fin_t.time() if ht > h1 else None,
            'duracion': dt.timedelta(hours=h1) if duracion == 'timedelta' else round(h1 * 60, 6),
            'alimentador': a, 'causa': causa,
            'programada': 'Programada' if prog else rng.choice(NO_PROGRAMADA),
            'tension': kv, 'clientes': rng.randint(1, 500),
            'Observación': rng.choice(['sin novedad', 'cuadrilla 3', None]), 'Código': rng.randrange(10**6),
            **{t: f(a, n_fila) for t, f in extra}}
        ws.append([valores[k] for k in columnas])
    wb.save(ruta)
    return ruta


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_historico_sorteado_da_las_tasas_conocidas(tmp_path, semilla):
    """012:RF-8, RF-9, RF-62 — un histórico en bruto, con columnas y empresa sorteadas, da λ por
    km·año en líneas y cables, por unidad·año en transformadores, y r de las sostenidas."""
    rng = random.Random(semilla)
    filas, exp, esperado, _primeras = _historico(rng)
    ruta = _escribir(tmp_path / 'historico.xlsx', filas, rng)
    libro = de.leer_libro(ruta, red=exp)
    for clase, e in esperado.items():
        t = libro.tasas[clase]
        assert t.permanente == pytest.approx(e['permanente'], rel=1e-6, abs=1e-12), (semilla, clase)
        assert t.reparacion_h == pytest.approx(e['reparacion_h'], rel=1e-4, abs=1e-6), (semilla, clase)
    assert libro.tasas['barra'].permanente == 0          # ninguna falla de barra en el registro
    h = libro.historico
    assert h['excluidas']['programada'] == 1
    assert h['excluidas']['fuera de media tensión'] == 1
    assert h['excluidas']['alimentador que no está en la red del espacio'] == 1
    assert h['sin_clase'] == 1
    assert 'Tasas de falla' not in libro.hojas_que_faltan
    assert any('derivados del histórico' in a for a in libro.avisos)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_transitoria_y_tiempos_de_dos_reposiciones(tmp_path, semilla):
    """012:RF-8, RF-12 — las momentáneas (≤ 5 min, IEEE 1366) dan la tasa transitoria y la primera
    reposición de las repuestas en dos tiempos da el tiempo de localización y maniobra."""
    rng = random.Random(semilla)
    filas, exp, esperado, primeras = _historico(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng, duracion='timedelta'), red=exp)
    hay_mom = any(e['transitoria'] for e in esperado.values())
    if hay_mom:
        assert libro.tasas['linea'].transitoria == pytest.approx(esperado['linea']['transitoria'], rel=1e-6)
    if primeras:
        assert libro.tiempos_min['localizacion'] == pytest.approx(60 * sum(primeras) / len(primeras), rel=1e-4)
        assert libro.tiempos_min['manual'] == 0
        assert 'Tiempos' not in libro.hojas_que_faltan
        assert de.que_falta(libro, 'fiabilidad') == []
    else:
        assert 'Tiempos' in libro.hojas_que_faltan


def test_red_del_espacio_da_la_exposicion():
    """012:RF-9 — la exposición sale de la red del espacio: km de aérea y de cable por la longitud de
    cada tramo (en metros), transformadores por sus cargas y barras por sus nodos."""
    red = SimpleNamespace(
        feeders={'NET_A12': ('s1', 's2', 's3'), 'NET_B7': ('s4',)},
        line_configurations={'s1': {'Length': '1500', 'Overhead': '1'}, 's2': {'Length': '500', 'Overhead': '0'},
                             's3': {'Length': '250', 'Overhead': '1'}, 's4': {'Length': '1000', 'Overhead': '1'}},
        sections={'s1': {'FromNodeID': 'n1', 'ToNodeID': 'n2'}, 's2': {'FromNodeID': 'n2', 'ToNodeID': 'n3'},
                  's3': {'FromNodeID': 'n2', 'ToNodeID': 'n4'}, 's4': {'FromNodeID': 'm1', 'ToNodeID': 'm2'}},
        customer_loads_by_feeder={'NET_A12': (1, 2), 'NET_B7': (1,)})
    exp = hi.exposicion_de_red(red)
    assert exp['A12'] == {'linea': pytest.approx(1.75), 'cable': pytest.approx(0.5), 'transformador': 2.0,
                          'barra': 4.0}
    assert exp['B7']['linea'] == pytest.approx(1.0)
    assert hi.exposicion_de_red(None) == {}


def test_sin_red_no_inventa_tasas_y_lo_dice(tmp_path):
    """012:RF-9 — sin la red del espacio no hay con qué normalizar: ninguna tasa, y se dice."""
    rng = random.Random(SEMILLAS[0])
    filas, _exp, _esperado, _p = _historico(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng), red=None)
    assert libro.tasas == {}
    assert 'Tasas de falla' in libro.hojas_que_faltan
    assert any('Falta la red del espacio' in a for a in libro.avisos)
    assert de.que_falta(libro, 'fiabilidad')


def test_sin_columna_de_causa_no_da_ceros(tmp_path):
    """012:RF-8, RF-33 — sin causa ninguna falla tiene clase: no se dan tasas cero que parecerían una
    red sin fallas, y se nombra la columna que falta."""
    rng = random.Random(SEMILLAS[1])
    filas, exp, _e, _p = _historico(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng, sin=('causa',)), red=exp)
    assert libro.tasas == {}
    assert any('no tiene columna de causa' in a for a in libro.avisos)
    assert any('«Causa»' in a for a in libro.avisos)


def test_duracion_numerica_sin_unidad_se_calcula_por_las_fechas():
    """012:RF-16 — una duración que es un número sin unidad en el título no se adivina."""
    assert hi._factor_horas('Duración (min)') == pytest.approx(1 / 60)
    assert hi._factor_horas('Duración (h)') == 1.0
    assert hi._factor_horas('Duración') is None
    assert hi._factor_horas('DURAC. (H:M)') is None


def test_libro_resumido_sigue_igual(tmp_path):
    """012:RF-62, RF-8 — el libro de la plantilla se lee como siempre y no lleva histórico."""
    wb = Workbook()
    wb.remove(wb.active)
    filas = {'tasas': [[de.CLASES['linea'], None, 0.1, None, 3.0], [de.CLASES['barra'], None, 0.0, None, 1.0]],
             'tiempos': [[de.TIEMPOS['localizacion'], 20], [de.TIEMPOS['manual'], 15]]}
    for hoja in de.HOJAS:
        if hoja.clave not in filas:
            continue
        ws = wb.create_sheet(hoja.titulo)
        ws.append([c.titulo for c in hoja.columnas])
        ws.append([c.unidad for c in hoja.columnas])
        for f in filas[hoja.clave]:
            ws.append(f)
    # Una hoja extra con forma de histórico no cambia nada: manda la hoja «Tasas de falla».
    extra = wb.create_sheet('Interrupciones')
    extra.append(['Fecha inicio', 'Duración', 'Alimentador', 'Causa'])
    extra.append([dt.datetime(2024, 1, 1), dt.timedelta(hours=2), 'A1', 'Caída de conductor'])
    ruta = tmp_path / 'libro.xlsx'
    wb.save(ruta)
    libro = de.leer_libro(ruta, red={'A1': {'linea': 1.0}})
    assert libro.historico == {}
    assert libro.tasas['linea'] == de.Tasa('linea', 0.1, None, 3.0)
    assert libro.tiempos_min == {'localizacion': 20, 'manual': 15}
    assert de.Libro.desde_dict(libro.a_dict()) == libro


def test_procedencia_viaja_con_el_libro(tmp_path):
    """012:RF-20 — la procedencia (hoja, periodo, filas y criterio) se guarda y se muestra."""
    rng = random.Random(SEMILLAS[2])
    filas, exp, _e, _p = _historico(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng), red=exp)
    otra = de.Libro.desde_dict(libro.a_dict())
    assert otra.historico == libro.historico and otra.tasas == libro.tasas
    r = de.resumen(libro)['historico']
    assert r['periodo']['anios'] > 1 and r['usadas'] > 0 and 'IEEE Std 1366' in r['criterio']


def _faltan_reales() -> list[str]:
    nombres = ('CSG_INTERRUPCIONES', 'CSG_RED', 'CSG_LOADS', 'CSG_EQUIPMENT')
    return [n for n in nombres if not (os.environ.get(n) and Path(os.environ[n]).is_file())]


@pytest.mark.skipif(bool(_faltan_reales()), reason='Faltan ' + ', '.join(_faltan_reales())
                    + ': el histórico real de interrupciones (CSG_INTERRUPCIONES) y la red TXT que lo normaliza.')
def test_historico_real_da_tasas_mayores_que_cero():
    """012:RF-6, RF-8, RF-62 — el histórico real de la empresa, tal cual, da tasas mayores que cero
    para las líneas y los transformadores, normalizadas con la red del TXT, y lo dice."""
    from convertersmartgrid.adaptadores.dataset import CymdistDataset

    ds = CymdistDataset.from_files(os.environ['CSG_RED'], os.environ['CSG_LOADS'], os.environ['CSG_EQUIPMENT'])
    libro = de.leer_libro(os.environ['CSG_INTERRUPCIONES'], red=ds)
    assert libro.tasas['linea'].permanente > 0 and libro.tasas['linea'].reparacion_h > 0
    assert libro.tasas['transformador'].permanente > 0
    assert de.clases_que_faltan(libro, {'linea': 1, 'cable': 1, 'transformador': 1, 'barra': 1}) == []
    assert de.que_falta(libro, 'fiabilidad') == []
    h = libro.historico
    assert h['usadas'] > 0 and h['excluidas'].get('programada', 0) > 0
    assert any('derivados del histórico' in a for a in libro.avisos)


def test_clase_sin_fallas_lleva_su_cota_superior_al_95(tmp_path):
    """012:RF-8, RF-20 — una clase con exposición y ninguna falla da λ = 0 (máxima verosimilitud),
    pero la nota y la procedencia llevan la cota exacta de Poisson al 95 %, −ln(0,05)/(exposición·años)
    ≈ 3/(exposición·años), la «regla del tres» (Hanley y Lippman-Hand, JAMA 1983)."""
    import math

    rng = random.Random(SEMILLAS[3])
    filas, exp, _e, _p = _historico(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng), red=exp)
    anios = libro.historico['periodo']['anios']
    e_barra = sum(x['barra'] for x in exp.values())
    barra = libro.historico['tasas']['barra']
    assert barra['permanente'] == 0
    assert barra['cota_95'] == pytest.approx(-math.log(0.05) / (e_barra * anios), rel=1e-3)
    nota = next(a for a in libro.avisos if a.startswith('Barra:'))
    assert 'cota superior al 95 %' in nota and 'regla del tres' in nota


def test_espacio_sin_red_convertida_dice_en_una_frase_que_falta(tmp_path):
    """012:RF-19, RF-63 — en un espacio sin conversión (un proyecto de DIgSILENT sin convertir,
    015:RF-70) el histórico se reconoce pero no hay exposición: la confiabilidad no se ofrece y dice,
    en una frase, que faltan las longitudes y los transformadores de la red, nunca cero tasas."""
    rng = random.Random(SEMILLAS[0])
    filas, _exp, _e, _p = _historico(rng)
    libro = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng), red=None)
    assert libro.tasas == {}
    falta = de.que_falta(libro, 'fiabilidad')
    assert falta[0] == hi.FALTA_RED and not any('Tasas de falla' in x for x in falta)
    assert 'longitud' in hi.FALTA_RED and 'transformadores' in hi.FALTA_RED and hi.FALTA_RED.count('.') <= 1


# ------------------------------------------------------------- exposición leída de DIgSILENT
#: Semillas fijas: la igualdad con la red convertida se comprueba siempre con los mismos sorteos.
SEMILLAS_EXPOSICION = (3, 17, 42, 101, 977)


@pytest.mark.parametrize('semilla', SEMILLAS_EXPOSICION)
def test_exposicion_leida_despues_da_lo_mismo_que_la_red_convertida(tmp_path, semilla):
    """012:RF-87 — en un espacio sin red convertida, la exposición que llega después (la que se lee
    del proyecto de DIgSILENT al aplicar el libro) da las mismas tasas, tiempos, cotas y hojas que
    el mismo histórico subido a un espacio con esa red, sin volver a leer el libro."""
    rng = random.Random(semilla)
    filas, exp, _esperado, _p = _historico(rng)
    ruta = _escribir(tmp_path / 'h.xlsx', filas, rng)
    sin = de.leer_libro(ruta, red=None)
    con = de.leer_libro(ruta, red=exp)
    assert sin.tasas == {}
    origen = 'el proyecto de DIgSILENT «P»'
    leido = de.con_exposicion(sin, exp, origen=origen)
    assert sin.tasas == {} and 'exposicion' not in sin.historico          # el original no cambia
    assert set(leido.tasas) == set(con.tasas), semilla
    for clase, t in con.tasas.items():
        u = leido.tasas[clase]
        assert u.permanente == pytest.approx(t.permanente, rel=1e-9, abs=1e-15), (semilla, clase)
        assert (u.transitoria is None) == (t.transitoria is None)
        if t.transitoria is not None:
            assert u.transitoria == pytest.approx(t.transitoria, rel=1e-9, abs=1e-15)
        assert u.reparacion_h == pytest.approx(t.reparacion_h, rel=1e-9, abs=1e-12)
        assert leido.historico['tasas'][clase].get('cota_95') == pytest.approx(
            con.historico['tasas'][clase].get('cota_95'))
    assert leido.tiempos_min == pytest.approx(con.tiempos_min)
    assert leido.hojas_que_faltan == con.hojas_que_faltan
    assert de.que_falta(leido, 'fiabilidad') == de.que_falta(con, 'fiabilidad')
    assert leido.historico['usadas'] == con.historico['usadas']
    assert set(leido.historico['por_alimentador']) == set(con.historico['por_alimentador'])
    assert leido.historico['exposicion']['origen'] == origen
    assert not any('Falta la red del espacio' in a for a in leido.avisos)
    assert any(origen in a and 'km' in a for a in leido.avisos)
    otra = de.Libro.desde_dict(leido.a_dict())                   # viaja en el plan y se guarda
    assert otra.tasas == leido.tasas and otra.historico == leido.historico


def test_exposicion_leida_sin_alimentadores_comunes_no_da_tasas_y_lo_dice(tmp_path):
    """012:RF-89 — si con la exposición leída ninguna interrupción cae en un alimentador del
    proyecto, o el histórico no tiene causa, no se da ninguna tasa (nada de ceros que parezcan una
    red sin fallas) y lo que falta lo dice en una frase que no es «falta la red»."""
    rng = random.Random(SEMILLAS_EXPOSICION[0])
    filas, exp, _e, _p = _historico(rng)
    sin = de.leer_libro(_escribir(tmp_path / 'h.xlsx', filas, rng), red=None)
    otros = {'Q' + a: v for a, v in exp.items()}
    leido = de.con_exposicion(sin, otros, origen='el proyecto de DIgSILENT «P»')
    assert leido.tasas == {} and leido.historico['usadas'] == 0
    falta = de.que_falta(leido, 'fiabilidad')
    assert falta[0] == hi.SIN_TASAS and hi.FALTA_RED not in falta
    sin_causa = de.leer_libro(_escribir(tmp_path / 'c.xlsx', filas, rng, sin=('causa',)), red=None)
    leido = de.con_exposicion(sin_causa, exp, origen='el proyecto de DIgSILENT «P»')
    assert leido.tasas == {} and de.que_falta(leido, 'fiabilidad')[0] == hi.SIN_TASAS
    assert hi.SIN_TASAS.count('.') <= 1 and 'causa' in hi.SIN_TASAS and 'alimentador' in hi.SIN_TASAS


def test_sin_red_convertida_dice_que_la_exposicion_se_lee_al_aplicar_el_libro(tmp_path):
    """012:RF-88 — antes de aplicar el libro, en un espacio sin red convertida, la frase que falta
    dice que la longitud y los transformadores se leen del proyecto de DIgSILENT al aplicarlo."""
    assert 'DIgSILENT' in hi.FALTA_RED and 'aplicar' in hi.FALTA_RED


# ------------------------------------------------- columna del alimentador por su contenido (T18)
def _sin_titulo(filas, rng, ruta, **kw):
    """El histórico con la columna del alimentador bajo un título que no la nombra."""
    return _escribir(ruta, filas, rng, sin=('alimentador',), extra=(('Instalación', lambda a, _n: a),), **kw)


def _avisos_columna(libro):
    return [a for a in libro.avisos if a.startswith('Columna del alimentador')]


@pytest.mark.parametrize('semilla', SEMILLAS_EXPOSICION)
def test_columna_del_alimentador_sin_titulo_se_elige_por_su_contenido(tmp_path, semilla):
    """012:RF-90, 012:RF-91 — sin un título que la nombre, la columna del alimentador es la que contiene
    la mayoría de los alimentadores del proyecto (aclaración de RF-90); da las tasas conocidas y el
    aviso dice cuál y por qué, con la red convertida y con la exposición leída de DIgSILENT."""
    rng = random.Random(semilla)
    filas, exp, esperado, _p = _historico(rng)
    ruta = _sin_titulo(filas, rng, tmp_path / 'h.xlsx')
    sin = de.leer_libro(ruta, red=None)
    assert sin.tasas == {}
    leido = de.con_exposicion(sin, exp, origen='el proyecto de DIgSILENT «P»')
    con = de.leer_libro(ruta, red=exp)
    m = len(exp)
    n = len({e[0] for e, _ini in filas} & set(exp))
    assert n > m / 2, f'precondición del sorteo {semilla}: solo {n} de {m} alimentadores tienen interrupciones'
    for libro, donde in ((leido, 'del proyecto'), (con, 'de la red del espacio')):
        for clase, e in esperado.items():
            assert libro.tasas[clase].permanente == pytest.approx(e['permanente'], rel=1e-6, abs=1e-12), clase
        assert _avisos_columna(libro) == [f'Columna del alimentador: «Instalación», por contenido: {n} de {m} '
                                          f'alimentadores {donde} están en ella.'], semilla
        assert not any('«Alimentador»: se usa lo que hay' in a for a in libro.avisos)
    for clase, t in con.tasas.items():
        assert leido.tasas[clase].permanente == pytest.approx(t.permanente, rel=1e-9, abs=1e-15)


def test_columna_del_alimentador_con_titulo_lo_dice(tmp_path):
    """012:RF-91 — la columna nombrada por su título se elige por título, y el aviso lo dice."""
    rng = random.Random(SEMILLAS_EXPOSICION[1])
    filas, exp, _e, _p = _historico(rng)
    ruta = _escribir(tmp_path / 'h.xlsx', filas, rng)
    con = de.leer_libro(ruta, red=exp)
    titulo = con.historico['columnas']['Alimentador']
    assert _avisos_columna(con) == [f'Columna del alimentador: «{titulo}», por título.']
    leido = de.con_exposicion(de.leer_libro(ruta, red=None), exp, origen='el proyecto de DIgSILENT «P»')
    assert _avisos_columna(leido) == [f'Columna del alimentador: «{titulo}», por título.']


def test_columna_del_alimentador_empate_igual_elige_la_primera_y_distinto_es_un_error(tmp_path):
    """012:RF-90, 012:RF-92 — dos columnas con la misma mayoría: si dicen lo mismo, vale la primera; si no,
    un error que nombra las dos, sin ninguna tasa."""
    rng = random.Random(SEMILLAS_EXPOSICION[2])
    filas, exp, esperado, _p = _historico(rng)
    while len(exp) < 2:
        filas, exp, esperado, _p = _historico(rng)
    copia = _escribir(tmp_path / 'igual.xlsx', filas, rng, sin=('alimentador',),
                      extra=(('Instalación', lambda a, _n: a), ('Zona de servicio', lambda a, _n: a)))
    leido = de.con_exposicion(de.leer_libro(copia, red=None), exp, origen='el proyecto de DIgSILENT «P»')
    for clase, e in esperado.items():
        assert leido.tasas[clase].permanente == pytest.approx(e['permanente'], rel=1e-6, abs=1e-12)
    assert len(_avisos_columna(leido)) == 1 and 'por contenido' in _avisos_columna(leido)[0]
    nombres = sorted(exp)
    otro = {a: nombres[(i + 1) % len(nombres)] for i, a in enumerate(nombres)}
    rotada = _escribir(tmp_path / 'distinto.xlsx', filas, rng, sin=('alimentador',),
                       extra=(('Instalación', lambda a, _n: a), ('Zona de servicio', lambda a, _n: otro.get(a, a))))
    with pytest.raises(ValueError) as e:
        de.con_exposicion(de.leer_libro(rotada, red=None), exp, origen='el proyecto de DIgSILENT «P»')
    assert '«Instalación»' in str(e.value) and '«Zona de servicio»' in str(e.value)
    con = de.leer_libro(rotada, red=exp)
    assert con.tasas == {}
    falta = de.que_falta(con, 'fiabilidad')[0]
    assert '«Instalación»' in falta and '«Zona de servicio»' in falta


#: Para las pruebas con filas explícitas.
PROYECTO_P = 'el proyecto de DIgSILENT «P»'


def _explicitas(alims, por_alim=3):
    """Filas sin sorteo: ``por_alim`` fallas sostenidas de línea por alimentador, de una hora, una
    por día desde el 2020-01-01, en el orden de ``alims``."""
    filas, dia = [], 0
    for a in alims:
        for _ in range(por_alim):
            filas.append(([a, 'linea', 1.0, 1.0, False, 10, CAUSAS['linea'][0]],
                          dt.datetime(2020, 1, 1) + dt.timedelta(days=dia)))
            dia += 1
    return filas


def _exp_explicita(alims):
    return {a: {'linea': 10.0, 'cable': 1.0, 'transformador': 10.0, 'barra': 20.0} for a in alims}


def test_columna_casi_vacia_no_es_la_del_alimentador(tmp_path):
    """012:RF-90, 012:RF-92 — filas explícitas: una columna con todos los alimentadores del proyecto
    pero vacía en la mayoría de las filas no es la del alimentador; sola, el error nombra los
    títulos encontrados y no hay ninguna tasa; con la columna llena, la elegida es esa."""
    alims = ['AB101', 'AB102', 'AB103', 'AB104']
    filas = _explicitas(alims)
    casi = ('Referencia', lambda a, n: a if n % 3 == 0 else None)       # 4 de 12 filas
    llenas = sum(1 for n in range(len(filas)) if n % 3 == 0)
    assert llenas * 2 < len(filas), f'precondición: la columna casi vacía llena {llenas} de {len(filas)} filas'
    exp = _exp_explicita(alims)
    sola = _escribir(tmp_path / 'casi.xlsx', filas, random.Random(0), sin=('alimentador',), extra=(casi,))
    with pytest.raises(ValueError) as e:
        de.con_exposicion(de.leer_libro(sola, red=None), exp, origen=PROYECTO_P)
    msg = str(e.value)
    assert '«Referencia»' in msg and '«Observación»' in msg and 'del proyecto' in msg
    assert re.sub(r'«[^»]*»', '', msg).rstrip('.').count('.') == 0     # una sola frase (los títulos aparte)
    con = de.leer_libro(sola, red=exp)
    assert con.tasas == {} and '«Referencia»' in de.que_falta(con, 'fiabilidad')[0]
    ambas = _escribir(tmp_path / 'ambas.xlsx', filas, random.Random(0), sin=('alimentador',),
                      extra=(casi, ('Instalación', lambda a, _n: a)))
    leido = de.con_exposicion(de.leer_libro(ambas, red=None), exp, origen=PROYECTO_P)
    assert leido.tasas and _avisos_columna(leido) == [
        'Columna del alimentador: «Instalación», por contenido: 4 de 4 alimentadores del proyecto están en ella.']


def test_columna_del_alimentador_umbral_de_cobertura(tmp_path):
    """012:RF-90 — aclaración de RF-90, filas explícitas: de un proyecto con 4 alimentadores, una
    columna con 2 (la mitad justa) no basta y con 3 sí, aunque el libro traiga otros valores. Los
    otros no tienen forma de alimentador, para que el respaldo por forma (aclaración de RF-91) no
    entre y se mida solo la cobertura."""
    proyecto = ['AB101', 'AB102', 'AB103', 'AB104']
    otros = ['NORTE', 'SUR', 'ESTE', 'OESTE']
    for k, elegida in ((2, False), (3, True)):
        filas = _explicitas(proyecto[:k] + otros)
        sin = de.leer_libro(_escribir(tmp_path / f'k{k}.xlsx', filas, random.Random(0), sin=('alimentador',),
                                      extra=(('Instalación', lambda a, _n: a),)), red=None)
        if elegida:
            leido = de.con_exposicion(sin, _exp_explicita(proyecto), origen=PROYECTO_P)
            assert _avisos_columna(leido) == ['Columna del alimentador: «Instalación», por contenido: 3 de 4 '
                                              'alimentadores del proyecto están en ella.']
            assert leido.tasas['linea'].permanente > 0
        else:
            with pytest.raises(ValueError):
                de.con_exposicion(sin, _exp_explicita(proyecto), origen=PROYECTO_P)


def test_columna_del_alimentador_desempate_por_forma(tmp_path):
    """012:RF-90 — aclaración de RF-90, filas explícitas: dos columnas con los mismos alimentadores
    del proyecto; gana la que tiene más valores con forma de alimentador, sin error."""
    alims = ['AB101', 'AB102', 'AB103', 'AB104']
    filas = _explicitas(alims)
    exp = _exp_explicita(alims)
    ruta = _escribir(tmp_path / 'forma.xlsx', filas, random.Random(0), sin=('alimentador',),
                     extra=(('Zona de servicio', lambda a, n: a if n % 3 != 1 else 'sin dato'),
                            ('Instalación', lambda a, _n: a)))
    for libro in (de.con_exposicion(de.leer_libro(ruta, red=None), exp, origen=PROYECTO_P),
                  de.leer_libro(ruta, red=exp)):
        assert libro.tasas
        assert '«Instalación», por contenido: 4 de 4' in _avisos_columna(libro)[0]


def test_libro_de_toda_la_empresa_y_proyecto_con_pocos_alimentadores(tmp_path):
    """012:RF-90, 012:RF-91 — aclaración de RF-90, filas explícitas: un libro con 40 alimentadores y un
    proyecto con 3; la columna sin título se elige por cobertura (3 de 3), igual con y sin red, y
    las tasas son las del mismo libro con la columna titulada «Alimentador»."""
    empresa = [f'AL{101 + i}' for i in range(40)]
    proyecto = empresa[5:8]
    filas = _explicitas(empresa)
    exp = _exp_explicita(proyecto)
    zona = ('Zona de servicio', lambda _a, n: 'NORTE' if n % 2 else 'SUR')
    ruta = _escribir(tmp_path / 'empresa.xlsx', filas, random.Random(0), sin=('alimentador',),
                     extra=(('Instalación', lambda a, _n: a), zona))
    leido = de.con_exposicion(de.leer_libro(ruta, red=None), exp, origen=PROYECTO_P)
    con = de.leer_libro(ruta, red=exp)
    titulado = de.leer_libro(_escribir(tmp_path / 'titulado.xlsx', filas, random.Random(0)), red=exp)
    assert titulado.tasas['linea'].permanente > 0
    for libro, donde in ((leido, 'del proyecto'), (con, 'de la red del espacio')):
        assert set(libro.tasas) == set(titulado.tasas)
        for clase, t in titulado.tasas.items():
            assert libro.tasas[clase].permanente == pytest.approx(t.permanente, rel=1e-9, abs=1e-15), clase
        assert _avisos_columna(libro) == [f'Columna del alimentador: «Instalación», por contenido: 3 de 3 '
                                          f'alimentadores {donde} están en ella.']
        assert libro.historico['usadas'] == 9


# ------------------------------------------- respaldo por la forma de los valores (T18c, aclaración de RF-91)
def _por_forma(n, m, k, donde):
    return (f'Columna del alimentador: «Instalación», elegida por la forma de sus valores: {n} de {m} '
            f'distintos; {k} alimentadores {donde} con interrupciones.')


def test_proyecto_con_pocos_alimentadores_con_interrupciones_elige_por_forma(tmp_path):
    """012:RF-91, 012:RF-90 — aclaración de RF-91, filas explícitas: un proyecto con 10 alimentadores y
    solo 3 con interrupciones no llega a la cobertura; la única columna llena cuyos valores
    distintos tienen forma de alimentador y que nombra alguno del proyecto es la elegida, igual
    con red y sin red, sin error."""
    proyecto = [f'AB{101 + i}' for i in range(10)]
    empresa = proyecto[:3] + ['ZQ901', 'ZQ902', 'ZQ903', 'ZQ904', 'ZQ905']
    filas = _explicitas(empresa)
    exp = _exp_explicita(proyecto)
    zona = ('Zona de servicio', lambda _a, n: 'NORTE' if n % 2 else 'SUR')
    ruta = _escribir(tmp_path / 'forma.xlsx', filas, random.Random(0), sin=('alimentador',),
                     extra=(('Instalación', lambda a, _n: a), zona))
    leido = de.con_exposicion(de.leer_libro(ruta, red=None), exp, origen=PROYECTO_P)
    con = de.leer_libro(ruta, red=exp)
    assert _avisos_columna(leido) == [_por_forma(8, 8, 3, 'del proyecto')]
    assert _avisos_columna(con) == [_por_forma(8, 8, 3, 'de la red del espacio')]
    assert leido.tasas['linea'].permanente > 0 and leido.historico['usadas'] == 9
    for clase, t in con.tasas.items():
        assert leido.tasas[clase].permanente == pytest.approx(t.permanente, rel=1e-9, abs=1e-15), clase


def test_dos_columnas_con_forma_de_alimentador_es_un_error(tmp_path):
    """012:RF-92, 012:RF-91 — aclaración de RF-91, filas explícitas: sin cobertura y con dos columnas
    que podrían ser la del alimentador por su forma, no se elige ninguna: el error de siempre, con
    los títulos, y ninguna tasa."""
    proyecto = [f'AB{101 + i}' for i in range(10)]
    empresa = proyecto[:3] + ['ZQ901', 'ZQ902', 'ZQ903', 'ZQ904', 'ZQ905']
    otro = {a: empresa[(i + 1) % len(empresa)] for i, a in enumerate(empresa)}
    filas = _explicitas(empresa)
    exp = _exp_explicita(proyecto)
    ruta = _escribir(tmp_path / 'dos.xlsx', filas, random.Random(0), sin=('alimentador',),
                     extra=(('Instalación', lambda a, _n: a), ('Respaldo', lambda a, _n: otro[a])))
    with pytest.raises(ValueError) as e:
        de.con_exposicion(de.leer_libro(ruta, red=None), exp, origen=PROYECTO_P)
    assert '«Instalación»' in str(e.value) and '«Respaldo»' in str(e.value)
    con = de.leer_libro(ruta, red=exp)
    assert con.tasas == {} and '«Respaldo»' in de.que_falta(con, 'fiabilidad')[0]


def test_columna_con_el_70_por_ciento_de_forma_no_gana(tmp_path):
    """012:RF-91, 012:RF-92 — aclaración de RF-91, filas explícitas: con 7 de 10 valores distintos
    con forma de alimentador (el 70 %) la columna no gana y se da el error; con 8 de 10 (el 80 %), sí."""
    proyecto = [f'AB{101 + i}' for i in range(10)]
    exp = _exp_explicita(proyecto)
    sin_forma = ['NORTE', 'SUR', 'CENTRO']
    for con_forma, gana in ((7, False), (8, True)):
        valores = proyecto[:3] + [f'ZQ{901 + i}' for i in range(con_forma - 3)] + sin_forma[:10 - con_forma]
        assert len(set(valores)) == 10, valores
        filas = _explicitas(valores)
        ruta = _escribir(tmp_path / f'f{con_forma}.xlsx', filas, random.Random(0), sin=('alimentador',),
                         extra=(('Instalación', lambda a, _n: a),))
        sin = de.leer_libro(ruta, red=None)
        if gana:
            leido = de.con_exposicion(sin, exp, origen=PROYECTO_P)
            assert _avisos_columna(leido) == [_por_forma(8, 10, 3, 'del proyecto')]
        else:
            with pytest.raises(ValueError) as e:
                de.con_exposicion(sin, exp, origen=PROYECTO_P)
            assert '«Instalación»' in str(e.value)
            assert de.leer_libro(ruta, red=exp).tasas == {}


@pytest.mark.parametrize('origen, esperado', [
    ('el proyecto de DIgSILENT «P1»', 'Exposición leída del proyecto de DIgSILENT «P1»'),
    ('la red convertida', 'Exposición leída de la red convertida'),
])
def test_la_frase_de_la_exposicion_contrae_de_el(origen, esperado):
    """086:RF-134 — la frase de la exposición dice «del proyecto», nunca «de el proyecto» (bloque DIgSILENT del 20-11,
    «Aplicar el libro»: «Exposición leída de el proyecto de DIgSILENT …»)."""
    frase = hi.frase_exposicion(hi.resumen_exposicion({'F1': {'linea': 1.0}}, origen))
    assert frase.startswith(esperado), frase
    assert ' de el ' not in frase
