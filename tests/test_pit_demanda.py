"""Spec 107 T28 (paso 3b de la demanda regulatoria): F-102, F-101 y F-103 desde la medida del año representativo
(aclaración de 107:RF-9; 107:RF-11). Curvas, topologías y registros sintéticos: sistemas, SET, devanados, alimentadores,
años y potencias inventados para la prueba, sin ninguna empresa real. Las dos últimas leen el registro real del COES.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from convertersmartgrid.pit.ambito import PitError
from convertersmartgrid.pit.demanda_regulatoria import (
    Topologia,
    curvas_por_devanado,
    datos_f101,
    datos_f102,
    datos_f103,
    instante_sein,
    tolerancia_de,
    topologia_desde,
)
from convertersmartgrid.pit.ambito import AreaPit
from convertersmartgrid.pit.red_area import RedArea
from convertersmartgrid.registro_normativo import RegistroError, cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
ANIO = 2031
T0 = datetime(ANIO, 3, 1, 18, 0)
Q15 = timedelta(minutes=15)


def _regla(clave, valor, **kw):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave} es {valor}»', 'pagina': '3', **kw}


def _registro(tmp_path, *, sein=None, mensuales=None, horas_punta=True, reporte=None, convencion=None):
    reglas = [_regla('pit.demanda.definiciones_factores', 'FC, FCP y FS'),
              _regla('pit.demanda.definiciones_participacion', 'FPHMS y FPMWHS'),
              _regla('medida.error_admisible_por_clase', {'0.2S': 0.3, '0.5S': 0.7}),
              _regla('medida.clase_por_defecto_mt', '0.5S')]
    if sein is not None:
        reglas.append(_regla(f'coes.sein.maxima_anual.{ANIO}', sein))
    if mensuales is not None:
        reglas.append(_regla(f'coes.sein.maximas_mensuales.{ANIO}', mensuales))
    if horas_punta:
        reglas.append(_regla('sein.horas_punta', {'desde': '17:00', 'hasta': '23:00'}))
    if reporte is not None:
        reglas.append(_regla(f'coes.sein.reporte_mensual.{ANIO}', reporte))
    if convencion is not None:
        reglas.append(_regla('coes.sein.convencion_por_defecto', convencion))
    carpeta = tmp_path / 'reg'
    carpeta.mkdir(exist_ok=True)
    (carpeta / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'SINT-DEMANDA', 'titulo': 'Norma sintética', 'estado_juridico': 'vigente_comprobada', 'sha256': 'c' * 64,
        'vigencia_desde': f'{ANIO}-01-01', 'reglas': reglas}]}), encoding='utf-8')
    return cargar_registro(carpeta)


def _curva(valores, desde=T0):
    return [(desde + i * Q15, float(p), float(p) / 4) for i, p in enumerate(valores)]


def _fila(filas, clave, valor):
    """La única fila con ``clave == valor``: si no está (o está repetida), falla la aserción y dice cuáles hay."""
    coinciden = [f for f in filas if f.get(clave) == valor]
    assert len(coinciden) == 1, f'se esperaba una fila con {clave}={valor!r}; hay {[f.get(clave) for f in filas]}'
    return coinciden[0]


def _por(filas, clave, esperadas):
    """Las filas por ``clave``, con la aserción de que están todas las esperadas."""
    d = {f.get(clave): f for f in filas}
    assert set(esperadas) <= set(d), f'faltan {sorted(set(esperadas) - set(d))} en {sorted(d)}'
    return d


TOPO = Topologia(sistemas={'SIS-1': ['SET-A']}, sets={'SET-A': ['D1', 'D2']}, devanados={'D1': ['A1'], 'D2': ['A2', 'A3']})


def _sein(registro):
    return instante_sein(registro, ANIO)


def test_factores_con_valores_conocidos(tmp_path):
    """107:RF-9 (T28) — curva constante: FC = 1; máxima en el mismo instante que la de su SET: FCP = 1; dos devanados
    desfasados: los FPHMS del sistema suman 1."""
    registro = _registro(tmp_path)
    curvas = {'A1': _curva([5, 5, 5, 5]), 'A2': _curva([1, 9, 2, 1]), 'A3': _curva([1, 1, 1, 1])}
    dev = curvas_por_devanado(curvas, TOPO, ANIO)
    f101 = _por(datos_f101(dev, TOPO, _sein(registro), registro, convencion='inicio', tolerancia=tolerancia_de(registro))['filas'],
                'nombre', ('D1', 'D2', 'SET-A'))
    assert f101['D1']['fc'] == 1.0
    assert f101['D2']['fcp'] == 1.0 and f101['SET-A']['fcp'] == 1.0
    assert f101['D2']['fc'] == round((2 + 10 + 3 + 2) / 4 / 10, 4)
    f103 = datos_f103(dev, TOPO, registro)['filas']
    assert sum(f['fphms'] for f in f103) == pytest.approx(1.0)
    assert sum(f['fpmwhs'] for f in f103) == pytest.approx(1.0)
    assert all(f['traza']['regla'] == 'pit.demanda.definiciones_participacion' for f in f103)


def test_sin_instante_del_sein_fs_y_columna_vacios_con_su_motivo(tmp_path):
    """107:RF-9 (T28) — sin la máxima del SEIN en el registro del COES, el FS y la columna SEIN de F-102 quedan vacíos
    con su motivo; nunca se toma la máxima de la empresa."""
    registro = _registro(tmp_path)
    dev = curvas_por_devanado({'A1': _curva([5, 6]), 'A2': _curva([1, 2]), 'A3': _curva([1, 1])}, TOPO, ANIO)
    sein = _sein(registro)
    fila = _fila(datos_f102(dev, TOPO, sein, convencion='inicio', tolerancia=tolerancia_de(registro))['filas'], 'devanado', 'D1')
    assert fila['sein']['kw'] is None and 'no trae la máxima anual del SEIN' in fila['sein']['motivo']
    f101 = _fila(datos_f101(dev, TOPO, sein, registro, convencion='inicio', tolerancia=tolerancia_de(registro))['filas'], 'nombre', 'D1')
    assert f101['fs'] is None and 'no trae la máxima anual' in f101['motivo_fs']


def test_sin_medida_de_un_alimentador_el_devanado_es_un_hueco(tmp_path):
    """107:RF-9 (T28) — sin la curva de un alimentador del devanado, el devanado entero es un hueco nombrado y no se
    escala la parte medida; su SET y su sistema también lo dicen."""
    registro = _registro(tmp_path)
    dev = curvas_por_devanado({'A1': _curva([5, 6]), 'A2': _curva([1, 2])}, TOPO, ANIO)
    assert dev['D2'].hueco and 'A3' in dev['D2'].hueco and not dev['D2'].puntos
    f102 = datos_f102(dev, TOPO, _sein(registro), convencion='inicio', tolerancia=tolerancia_de(registro))
    assert f102['huecos'] == [{'devanado': 'D2', 'motivo': dev['D2'].hueco}]
    assert f102['sets']['SET-A']['hueco'] and f102['sets']['SET-A']['coincidente_kw'] is None


def test_instante_incompleto_se_excluye_se_cuenta_y_no_se_rellena(tmp_path):
    """107:RF-9 (T28, condición de ca) — un instante en el que falta el registro de un alimentador no entra en la
    búsqueda de la máxima (aunque fuera la mayor) y el formato dice cuántos se excluyeron."""
    registro = _registro(tmp_path)
    a2 = _curva([1, 50, 2])
    del a2[1]                                    # A2 sin el instante de la mayor
    dev = curvas_por_devanado({'A1': _curva([5, 5, 5]), 'A2': a2, 'A3': _curva([1, 40, 1])}, TOPO, ANIO)
    assert dev['D2'].excluidos == 1 and len(dev['D2'].puntos) == 2
    fila = _fila(datos_f102(dev, TOPO, _sein(registro), convencion='inicio', tolerancia=tolerancia_de(registro))['filas'], 'devanado', 'D2')
    assert fila['no_coincidente']['kw'] == 3.0 and fila['excluidos'] == 1
    assert any('D2: 1 instantes excluidos' in a for a in datos_f102(dev, TOPO, _sein(registro), convencion='inicio', tolerancia=tolerancia_de(registro))['avisos'])


def test_anio_incompleto_avisa_con_el_porcentaje(tmp_path):
    """107:RF-9 (T28) — si la curva no cubre el año entero, se avisa con el porcentaje cubierto."""
    registro = _registro(tmp_path)
    dev = curvas_por_devanado({'A1': _curva([5] * 96), 'A2': _curva([1] * 96), 'A3': _curva([1] * 96)}, TOPO, ANIO)
    avisos = datos_f102(dev, TOPO, _sein(registro), convencion='inicio', tolerancia=tolerancia_de(registro))['avisos']
    assert any(a.startswith('D1: la curva cubre el 0.3 % del año (96 de 35040') for a in avisos)


def test_dos_perfiles_con_sistemas_distintos(tmp_path):
    """107:RF-11 (T28) — universalidad: la misma medida repartida en dos topologías da los factores de cada una."""
    registro = _registro(tmp_path)
    curvas = {'A1': _curva([4, 8]), 'A2': _curva([8, 4]), 'A3': _curva([1, 1])}
    uno = Topologia(sistemas={'S': ['X']}, sets={'X': ['D1', 'D2']}, devanados={'D1': ['A1'], 'D2': ['A2', 'A3']})
    dos = Topologia(sistemas={'S1': ['X'], 'S2': ['Y']}, sets={'X': ['D1'], 'Y': ['D2']},
                    devanados={'D1': ['A1'], 'D2': ['A2', 'A3']})
    f_uno = {f['devanado']: f['fphms'] for f in datos_f103(curvas_por_devanado(curvas, uno, ANIO), uno, registro)['filas']}
    f_dos = {f['devanado']: f['fphms'] for f in datos_f103(curvas_por_devanado(curvas, dos, ANIO), dos, registro)['filas']}
    assert f_uno == {'D1': round(4 / 13, 4), 'D2': round(9 / 13, 4)}
    assert f_dos == {'D1': 1.0, 'D2': 1.0}


@pytest.mark.parametrize('cerca, igual', ((9.0, True), (5.0, False)), ids=('alineaciones_iguales', 'alineaciones_distintas'))
def test_dos_alineaciones_del_intervalo_del_coes(tmp_path, cerca, igual):
    """107:RF-9 (T28, convención de ca y 28) — el COES no declara si su hora rotula el inicio o el fin del intervalo:
    si las dos alineaciones dan lo mismo se usa con la marca; si difieren, hueco con las dos cifras."""
    h = T0 + 2 * Q15
    registro = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': h.strftime('%Y-%m-%d'), 'hora': h.strftime('%H:%M')})
    dev = curvas_por_devanado({'A1': _curva([1, cerca, 9, 3]), 'A2': _curva([1, 1, 1, 1]), 'A3': _curva([0, 0, 0, 0])},
                              TOPO, ANIO)
    fila = _fila(datos_f102(dev, TOPO, _sein(registro), convencion='inicio',
                            tolerancia=tolerancia_de(registro, tolerancia_kw=0.5))['filas'], 'devanado', 'D1')
    assert fila['sein']['traza_sein']['tolerancia_origen'] == 'resolución del medidor declarada en el perfil'
    if igual:
        assert fila['sein']['kw'] == 9.0 and fila['sein']['traza_sein']['marca'].startswith('convención no declarada')
    else:
        assert fila['sein']['kw'] is None
        assert fila['sein']['traza_sein']['alineaciones'] == {'[h, h+15)': 9.0, '[h-15, h)': 5.0}


def test_fecha_anual_fuera_de_su_anio_se_detecta(tmp_path):
    """107:RF-9 (T28, condición de ca 05:25) — una máxima anual con fecha fuera del año de su estadística y sin la
    corrección marcada es un error que la nombra; con la corrección y su marca, se usa y se avisa con lo publicado."""
    fuera = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': f'{ANIO - 1}-11-19', 'hora': '20:00'})
    with pytest.raises(PitError, match=f'cae fuera del año {ANIO}'):
        instante_sein(fuera, ANIO)
    corregida = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': f'{ANIO}-11-19', 'hora': '20:00',
                                          'publicado': {'fecha': f'{ANIO - 1}-11-19', 'hora': '20:00'},
                                          'marca': 'corregido por el contraste mensual'},
                          mensuales={'NOV': 7000.0, 'DIC': 6900.0})
    sein = instante_sein(corregida, ANIO)
    assert sein.instante == datetime(ANIO, 11, 19, 20, 0) and sein.traza['marca'] == 'corregido por el contraste mensual'
    assert any(f'el COES publica {ANIO - 1}-11-19' in a for a in sein.avisos)


def test_contraste_mensual_distinto_se_nombra(tmp_path):
    """107:RF-9 (T28, ajuste 1 de ca) — si la mayor de las 12 mensuales no coincide con la anual, se nombra la
    diferencia."""
    registro = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': f'{ANIO}-03-01', 'hora': '19:00'},
                         mensuales={'MAR': 6990.0})
    assert any('diferencia +10.000 MW' in a for a in instante_sein(registro, ANIO).avisos)


def test_registro_real_del_coes_2024_corregido_y_2025():
    """107:RF-7, 107:RF-9 (T28) — el registro real: la máxima de 2024 se publica con año 2023 y se usa el 2024-11-19 a
    las 20:00 con su marca; la de 2025, tal como viene; las dos coinciden con su contraste mensual."""
    registro = cargar_registro(NORMATIVA)
    s24, s25 = instante_sein(registro, 2024), instante_sein(registro, 2025)
    assert s24.instante == datetime(2024, 11, 19, 20, 0) and s24.traza['publicado']['fecha'] == '2023-11-19'
    assert s25.instante == datetime(2025, 3, 26, 19, 0) and 'publicado' not in s25.traza
    assert not [a for a in s24.avisos + s25.avisos if 'no coincide' in a or 'horas punta' in a]


def test_registro_real_horas_punta_por_periodo():
    """107:RF-7 (T28) — la ventana de horas punta sale de la RM vigente en la fecha: la 153-2021-MINEM/DM (17:00-23:00)
    hasta el 2025-05-31 y la 189-2025-MINEM/DM (18:00-23:00) del 2025-06-01 al 2029-05-31; después no se supone."""
    registro = cargar_registro(NORMATIVA)
    assert registro.regla('sein.horas_punta', '2025-03-26').regla.valor == {'desde': '17:00', 'hasta': '23:00'}
    assert registro.regla('sein.horas_punta', '2025-07-01').regla.valor == {'desde': '18:00', 'hasta': '23:00'}
    assert registro.regla('sein.horas_punta', '2025-07-01').norma.acto == 'RM 189-2025-MINEM/DM'
    with pytest.raises(RegistroError, match='sein.horas_punta'):
        registro.regla('sein.horas_punta', '2029-06-01')


def _fila_sein_d1(tmp_path, tolerancia_de_registro, registro=None):
    h = T0 + 2 * Q15
    registro = registro or _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': h.strftime('%Y-%m-%d'),
                                                     'hora': h.strftime('%H:%M')})
    dev = curvas_por_devanado({'A1': _curva([1, 1004, 1000, 3]), 'A2': _curva([1, 1, 1, 1]), 'A3': _curva([0, 0, 0, 0])},
                              TOPO, ANIO)
    filas = datos_f102(dev, TOPO, _sein(registro), convencion='inicio', tolerancia=tolerancia_de_registro(registro))['filas']
    return _fila(filas, 'devanado', 'D1')


def test_tolerancia_con_la_clase_por_defecto_se_dice_en_la_salida(tmp_path):
    """107:RF-9 (T28, decisión de 28) — sin resolución ni clase del medidor en el perfil, se usa la clase por defecto
    en MT (0,5S, ±0,7 % de la RM 496-2005 Tabla 01) y la salida lo dice; 1000 y 1004 kW (0,4 %) dan lo mismo."""
    fila = _fila_sein_d1(tmp_path, tolerancia_de)
    assert fila['sein']['kw'] == 1000.0
    assert fila['sein']['traza_sein']['tolerancia_origen'].startswith('clase por defecto (práctica INACAL para MT')
    assert fila['sein']['traza_sein']['tolerancia_origen'].endswith('0.5S, ±0.7 %')


def test_tolerancia_con_la_clase_del_perfil(tmp_path):
    """107:RF-9 (T28, decisión de 28) — con la clase 0,2S declarada en el perfil manda su ±0,3 %: 1000 y 1004 kW
    (0,4 %) ya no dan lo mismo y queda el hueco con las dos cifras."""
    fila = _fila_sein_d1(tmp_path, lambda r: tolerancia_de(r, clase='0.2S'))
    assert fila['sein']['kw'] is None
    assert fila['sein']['traza_sein']['alineaciones'] == {'[h, h+15)': 1000.0, '[h-15, h)': 1004.0}
    assert fila['sein']['traza_sein']['tolerancia_origen'] == 'clase del medidor declarada en el perfil: 0.2S, ±0.3 %'


def test_tolerancia_del_registro_real():
    """107:RF-7 (T28) — el registro real trae el error admisible por clase de la RM 496-2005-MEM/DM y la clase por
    defecto del INACAL."""
    tol = tolerancia_de(cargar_registro(NORMATIVA))
    assert tol.relativa == pytest.approx(0.007) and tol.traza['acto'] == 'RM 496-2005-MEM/DM'


def test_fcp_de_la_set_en_la_hora_de_maxima_de_su_sistema(tmp_path):
    """107:RF-9 (T28, decisión de 28) — FCP de una SET = P de la SET en el intervalo de máxima de su sistema / máxima de
    la SET, con los dos términos de la misma curva y del mismo año."""
    registro = _registro(tmp_path)
    topo = Topologia(sistemas={'S': ['X', 'Y']}, sets={'X': ['D1'], 'Y': ['D2']}, devanados={'D1': ['A1'], 'D2': ['A2']})
    dev = curvas_por_devanado({'A1': _curva([10, 4]), 'A2': _curva([1, 9])}, topo, ANIO)
    f101 = _por(datos_f101(dev, topo, _sein(registro), registro, convencion='inicio', tolerancia=tolerancia_de(registro))['filas'],
                'nombre', ('X', 'Y', 'S'))
    assert f101['X']['fcp'] == 0.4 and f101['Y']['fcp'] == 1.0 and f101['S']['fcp'] == 1.0
    assert f101['X']['traza']['fcp'] == 'P a la hora de máxima de S / P máxima'


def _area(set_alimentadores):
    return AreaPit(codigo='AREA-S', titulares=('TIT',), set=tuple(set_alimentadores), set_alimentadores=set_alimentadores,
                   tension_min_kv=30.0, compartidos={})


def _red(barras, trafo2=(), trafo3=()):
    return RedArea('AREA-S', elementos={'barra': [{'id': b, 'set': s, 'rol': 'carga'} for b, s in barras],
                                        'trafo2': list(trafo2), 'trafo3': list(trafo3)})


def test_topologia_desde_el_perfil_y_la_red():
    """107:RF-9, 107:RF-11 (T28) — el devanado de cada alimentador sale del lado del transformador conectado a su
    barra: con una sola barra de carga en la SET no hace falta declararla; con dos, la dice el perfil."""
    area = _area({'SA': ('A1', 'A2'), 'SB': ('B1', 'B2')})
    red = _red([('BA', 'SA'), ('BB10', 'SB'), ('BB22', 'SB')],
               trafo2=[{'id': 'TA', 'set': 'SA', 'hv': 'HA', 'lv': 'BA'}],
               trafo3=[{'id': 'TB', 'set': 'SB', 'hv': 'HB', 'mv': 'BB22', 'lv': 'BB10'}])
    topo, huecos = topologia_desde(area, red, {'SIS': ['SA', 'SB']}, {'B1': 'BB10', 'B2': 'BB22'})
    assert huecos == []
    assert topo.devanados == {'TA:lv': ['A1', 'A2'], 'TB:lv': ['B1'], 'TB:mv': ['B2']}
    assert topo.sets == {'SA': ['TA:lv'], 'SB': ['TB:lv', 'TB:mv']} and topo.sistemas == {'SIS': ['SA', 'SB']}


def test_topologia_sin_sistemas_electricos_es_un_error():
    """107:RF-9 (T28) — sin los sistemas eléctricos del perfil no se supone que el área sea un solo sistema."""
    with pytest.raises(PitError, match='sistemas_electricos'):
        topologia_desde(_area({'SA': ('A1',)}), _red([('BA', 'SA')]), None)


def test_topologia_sin_barra_o_con_devanados_en_paralelo_deja_huecos():
    """107:RF-9 (T28) — un alimentador de una SET con dos barras sin la suya en el perfil, o en una barra con dos
    transformadores en paralelo, queda en un hueco con su causa; el reparto no se supone."""
    area = _area({'SA': ('A1',), 'SB': ('B1',)})
    red = _red([('BA', 'SA'), ('BB1', 'SB'), ('BB2', 'SB')],
               trafo2=[{'id': 'T1', 'set': 'SA', 'hv': 'H', 'lv': 'BA'}, {'id': 'T2', 'set': 'SA', 'hv': 'H', 'lv': 'BA'},
                       {'id': 'T3', 'set': 'SB', 'hv': 'H', 'lv': 'BB1'}])
    topo, huecos = topologia_desde(area, red, {'SIS': ['SA', 'SB']})
    assert topo.devanados == {}
    assert any(h.startswith('A1: la barra BA tiene 2 devanados en paralelo') for h in huecos)
    assert any(h.startswith('B1: la SET SB tiene 2 barras de carga') for h in huecos)


def test_reporte_mensual_que_da_otro_mes_se_nombra(tmp_path):
    """107:RF-9 (T28, tercera fuente de cc) — el reporte mensual del COES confirma la fecha y la hora de la anual en su
    mes y, si su mayor mes es otro, se nombra; manda la Estadística Anual."""
    registro = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': f'{ANIO}-03-01', 'hora': '19:00'},
                         reporte={'MAR': {'fecha': f'{ANIO}-03-01', 'hora': '19:00', 'potencia_mw': 6990.0},
                                  'DIC': {'fecha': f'{ANIO}-12-16', 'hora': '19:45', 'potencia_mw': 6991.0}})
    sein = instante_sein(registro, ANIO)
    assert 'reporte_mensual' in sein.traza, 'la traza no lleva el contraste con el reporte mensual'
    assert sein.traza['reporte_mensual']['confirma_fecha_y_hora'] is True
    assert any('da la mayor en DIC' in a and 'manda la estadística' in a for a in sein.avisos)


def test_registro_real_reporte_mensual_confirma_2024_y_nombra_los_meses():
    """107:RF-7, 107:RF-9 (T28) — el reporte de noviembre de 2024 confirma el 2024-11-19 20:00 corregido; en 2024 y
    2025 su mayor mes (febrero y diciembre) no es el de la Estadística Anual, y se nombra."""
    registro = cargar_registro(NORMATIVA)
    s24, s25 = instante_sein(registro, 2024), instante_sein(registro, 2025)
    assert 'reporte_mensual' in s24.traza, 'la traza no lleva el contraste con el reporte mensual'
    assert s24.traza['reporte_mensual']['confirma_fecha_y_hora'] is True
    assert any('da la mayor en FEB' in a for a in s24.avisos)
    assert any('da la mayor en DIC' in a for a in s25.avisos)


def _leer_falso(leidas, apartados, vistos):
    def leer(rutas, pares, *, centrales=None):
        vistos.append(list(pares))
        return leidas, apartados
    return leer


def test_curvas_de_la_medida_aparta_lo_que_falta(monkeypatch):
    """107:RF-9 (T28) — las curvas salen de los libros de cabecera del perfil; un alimentador apartado por la lectura
    o sin curva queda en hueco con su motivo, y sin pares cada alimentador se busca por su propio código."""
    from convertersmartgrid import pronostico_demanda
    vistos = []
    leidas = {'A1': {'curva': _curva([5, 6]), 'fuente': {'medidor': 'A1', 'libros': ['cab.xlsx']}}}
    monkeypatch.setattr(pronostico_demanda, 'curvas_de_cabecera',
                        _leer_falso(leidas, [{'objetivo': 'cabecera:A2', 'motivo': 'M2: sin curva'}], vistos))
    from convertersmartgrid.pit.demanda_regulatoria import curvas_de_la_medida
    curvas, fuentes, huecos = curvas_de_la_medida(['libros'], TOPO)
    assert vistos == [[('A1', 'A1'), ('A2', 'A2'), ('A3', 'A3')]]
    assert set(curvas) == {'A1'} and fuentes['A1']['libros'] == ['cab.xlsx']
    assert 'cabecera:A2: M2: sin curva' in huecos and 'cabecera:A3: sin curva en los libros' in huecos
    dev = curvas_por_devanado(curvas, TOPO, ANIO)
    assert dev['D2'].hueco and not dev['D2'].puntos


def test_demanda_regulatoria_de_punta_a_punta(tmp_path, monkeypatch):
    """107:RF-9, 107:RF-11 (T28) — del perfil, la red, la medida y el registro a F-101, F-102 y F-103, con la
    tolerancia por defecto dicha y sin huecos cuando todo está declarado."""
    from convertersmartgrid import pronostico_demanda
    h = T0 + Q15
    registro = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': h.strftime('%Y-%m-%d'), 'hora': h.strftime('%H:%M')})
    leidas = {a: {'curva': _curva(v), 'fuente': {'medidor': a}} for a, v in (('A1', [8, 8, 4, 2]), ('A2', [2, 2, 1, 1]))}
    monkeypatch.setattr(pronostico_demanda, 'curvas_de_cabecera', _leer_falso(leidas, [], []))
    from convertersmartgrid.pit.demanda_regulatoria import demanda_regulatoria
    area = _area({'SA': ('A1', 'A2')})
    red = _red([('BA', 'SA')], trafo2=[{'id': 'TA', 'set': 'SA', 'hv': 'HA', 'lv': 'BA'}])
    salida = demanda_regulatoria(registro, area, red, {'SIS': ['SA']}, ['libros'], ANIO, convencion='inicio')
    assert salida['huecos'] == {'topologia': [], 'medida': []}
    fila = _fila(salida['f102']['filas'], 'devanado', 'TA:lv')
    assert fila['no_coincidente']['kw'] == 10.0 and fila['sein']['kw'] == 10.0
    assert salida['tolerancia']['origen'].startswith('clase por defecto (práctica INACAL para MT')
    assert _fila(salida['f103']['filas'], 'devanado', 'TA:lv')['fphms'] == 1.0


def test_f102_y_f103_llenados_con_la_plantilla_oficial(monkeypatch):
    """107:RF-9 (T28) — F-102 y F-103 se llenan con el motor común sobre la plantilla oficial transcrita (RCD
    217-2013): cada momento en sus cuatro columnas, la barra y la tensión de la red, la Pmax del día de máxima del
    sistema y la energía en MWh; ninguna columna de la plantilla queda sin campo."""
    from convertersmartgrid import pronostico_demanda
    from convertersmartgrid.pit.demanda_regulatoria import celdas_f102_f103, demanda_regulatoria
    registro = cargar_registro(NORMATIVA)
    t0 = datetime(2025, 3, 26, 18, 45)
    leidas = {a: {'curva': _curva(v, desde=t0), 'fuente': {'medidor': a}}
              for a, v in (('A1', [8, 8, 4, 2]), ('A2', [2, 2, 1, 1]))}
    monkeypatch.setattr(pronostico_demanda, 'curvas_de_cabecera', _leer_falso(leidas, [], []))
    area = _area({'SA': ('A1', 'A2')})
    red = RedArea('AREA-S', elementos={'barra': [{'id': 'BA', 'set': 'SA', 'rol': 'carga', 'kv': 10.0}],
                                       'trafo2': [{'id': 'TA', 'set': 'SA', 'hv': 'HA', 'lv': 'BA'}]})
    salida = demanda_regulatoria(registro, area, red, {'SIS': ['SA']}, ['libros'], 2025, convencion='inicio')
    llenos = celdas_f102_f103(registro, salida, red, {'nombre': 'medida sintética', 'huella': 'a' * 64})
    c102 = {c['celda']: c['valor'] for c in llenos['F-102']['celdas']}
    c103 = {c['celda']: c['valor'] for c in llenos['F-103']['celdas']}
    assert {'F-102!A8', 'F-102!S8', 'F-102!O8'} <= set(c102) and {'F-103!E9', 'F-103!G9'} <= set(c103),         'F-102 y F-103 sin las celdas de su primera fila de datos'
    assert c102['F-102!A8'] == 'SIS' and c102['F-102!C8'] == 'BA' and c102['F-102!D8'] == 10.0
    assert c102['F-102!S8'] == 10.0 and c102['F-102!Q8'] == '2025/03/26'
    assert c102['F-102!O8'] == 10.0, 'la máxima del SEIN de 2025 (19:00) cae en un instante igual en las dos alineaciones'
    assert c103['F-103!E9'] == 10.0 and c103['F-103!F9'] == 1.0 and c103['F-103!H9'] == 1.0
    assert c103['F-103!G9'] == round((10 + 10 + 5 + 3) * 0.25 / 1000, 3)
    assert not [h for f in llenos.values() for h in f['huecos'] if 'columnas' in h]


def test_por_defecto_se_muestra_la_alineacion_de_fin_de_intervalo(tmp_path):
    """107:RF-9 (T28, decisión de 28) — si las dos alineaciones dan lo mismo dentro de la tolerancia y el registro
    trae la convención por defecto, se muestra la de fin de intervalo [h-15, h) con la marca de su procedencia."""
    h = T0 + 2 * Q15
    registro = _registro(tmp_path, sein={'potencia_mw': 7000.0, 'fecha': h.strftime('%Y-%m-%d'), 'hora': h.strftime('%H:%M')},
                         convencion={'alineacion': 'fin', 'marca': 'práctica observada del COES, no norma'})
    fila = _fila_sein_d1(tmp_path, tolerancia_de, registro=registro)
    assert fila['sein']['kw'] == 1004.0, 'se muestra la de fin de intervalo, no la de inicio (1000)'
    assert fila['sein']['traza_sein']['marca'].endswith('[h-15, h): práctica observada del COES, no norma')


def test_registro_real_pr30_por_vigencia():
    """107:RF-7 (T28, frente h de cc) — el PR-30 de la RCD 200-2017 rige hasta el 2026-12-31; desde el 2027-01-01
    manda el de la RCD 95-2026 (RCD 173-2026-OS/CD)."""
    registro = cargar_registro(NORMATIVA)
    claves = {r.clave for n in registro.normas.values() for r in n.reglas}
    assert {'coes.procedimiento.pr30', 'coes.sein.convencion_por_defecto'} <= claves, 'faltan las reglas en el registro'
    assert registro.regla('coes.procedimiento.pr30', '2026-06-01').regla.valor['aprobado_por'] == 'RCD 200-2017-OS/CD'
    assert registro.regla('coes.procedimiento.pr30', '2027-02-01').regla.valor['aprobado_por'] == 'RCD 95-2026-OS/CD'
    assert registro.regla('coes.sein.convencion_por_defecto').regla.valor['alineacion'] == 'fin'


def test_registro_real_del_coes_2022_y_su_contraste():
    """107:RF-7, 107:RF-9 (T28, frentes q y s de cc) — la máxima anual del SEIN de 2022 (Estadística Anual, cap. 05,
    hoja C2) es el 2022-12-06 a las 19:30, sin errata de año; su mayor mensual (hoja C9) coincide y el reporte mensual
    confirma la fecha y la hora. Es la misma que declaró en su F-102 la entrega de la empresa de prueba."""
    registro = cargar_registro(NORMATIVA)
    s22 = instante_sein(registro, 2022)
    assert s22.instante == datetime(2022, 12, 6, 19, 30) and 'publicado' not in s22.traza
    assert 'reporte_mensual' in s22.traza and s22.traza['reporte_mensual']['confirma_fecha_y_hora'] is True
    assert not [a for a in s22.avisos if 'no coincide' in a]


def test_la_cita_de_la_estadistica_da_la_fila_real_de_excel():
    """107:RF-7 (T28, frente s de cc) — la cita da la fila de Excel de la tabla, no el índice de la lista leída: en
    la estadística de 2024 la tabla comparativa tiene el título en la fila 45 y las cifras en las filas 48 y 49."""
    registro = cargar_registro(NORMATIVA)
    assert registro.regla('coes.sein.maxima_anual.2024').regla.pagina == \
        'hoja BD, título en la fila 45, cabecera D47, cifras D48 y D49'
    assert registro.regla('coes.sein.maximas_mensuales.2024').regla.pagina.endswith('hoja BD, filas 18-29 (columna E, lo ejecutado)')


def test_f101_un_bloque_por_sistema_con_el_fc_en_su_total(monkeypatch):
    """107:RF-9 (T28, delta18) — F-101 sobre su plantilla oficial: un bloque por sistema eléctrico con su cabecera
    «SISTEMA ELÉCTRICO k», una fila por devanado y el total «Total Sistema k» (el «2» del original es la llamada a la
    nota) con SOLO el FC; con más sistemas que huecos de la plantilla, se dice cuántos bloques insertar."""
    from convertersmartgrid import pronostico_demanda
    from convertersmartgrid.pit.demanda_regulatoria import celdas_f101, demanda_regulatoria
    registro = cargar_registro(NORMATIVA)
    t0 = datetime(2025, 3, 26, 18, 45)
    alims = {f'A{i}': [8 + i, 8 + i, 4, 2] for i in range(1, 5)}
    leidas = {a: {'curva': _curva(v, desde=t0), 'fuente': {'medidor': a}} for a, v in alims.items()}
    monkeypatch.setattr(pronostico_demanda, 'curvas_de_cabecera', _leer_falso(leidas, [], []))
    area = _area({f'S{i}': (f'A{i}',) for i in range(1, 5)})
    red = RedArea('AREA-S', elementos={
        'barra': [{'id': f'B{i}', 'set': f'S{i}', 'rol': 'carga', 'kv': 10.0} for i in range(1, 5)],
        'trafo2': [{'id': f'T{i}', 'set': f'S{i}', 'hv': f'H{i}', 'lv': f'B{i}'} for i in range(1, 5)]})
    sistemas = {f'SIS{i}': [f'S{i}'] for i in range(1, 5)}
    salida = demanda_regulatoria(registro, area, red, sistemas, ['libros'], 2025, convencion='inicio')
    llenos = celdas_f101(registro, salida, red, {'nombre': 'medida sintética', 'huella': 'b' * 64})
    c = {x['celda']: x['valor'] for x in llenos['celdas']}
    assert {'F-101!A5', 'F-101!A6', 'F-101!E8'} <= set(c), 'F-101 sin las celdas de su primer bloque'
    assert c['F-101!A5'] == 'SISTEMA ELÉCTRICO 1' and c['F-101!A6'] == 'SIS1' and c['F-101!C6'] == 'B1'
    assert c['F-101!A8'] == 'Total Sistema 1' and c['F-101!E8'] == 1.0 * c['F-101!E6']
    assert 'F-101!F8' not in c and 'F-101!G8' not in c, 'el total lleva solo el FC'
    assert c['F-101!A12'] == 'SISTEMA ELÉCTRICO 2' and c['F-101!A19'] == 'SISTEMA ELÉCTRICO 3'
    assert c['F-101!A26'] == 'SISTEMA ELÉCTRICO 4' and llenos['grupos_a_insertar'] == {'sistemas': 1}
