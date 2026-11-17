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


# --- 107 T29 (paso 3c): la cadena regulatoria F-108 a F-112 -------------------------------------------------------
# Ventas, factores y redes sintéticos; las pérdidas son las del registro real, de la primera empresa que tenga
# fijación vigente (sin nombrarla aquí), y la otra empresa no está en ninguna fijación.
FECHA_FIJACION = '2026-11-16'
SIN_FIJACION = 'Empresa sintética sin fijación'
HORIZONTE = 30


def _cadena():
    """El módulo de la 3c: su ausencia es la falla de la aserción, no un error de importación."""
    import importlib
    import importlib.util
    assert importlib.util.find_spec('convertersmartgrid.pit.demanda_cadena') is not None, \
        'falta convertersmartgrid.pit.demanda_cadena (107 T29, paso 3c)'
    return importlib.import_module('convertersmartgrid.pit.demanda_cadena')


def _registro_real_y_empresa():
    registro = cargar_registro(NORMATIVA)
    for empresa in registro.empresas_de('vad.perdidas.factores_expansion'):
        try:
            rv = registro.regla_de_empresa('vad.perdidas.factores_expansion', empresa, FECHA_FIJACION)
        except RegistroError:
            continue
        return registro, empresa, rv.regla.valor['empresas'][empresa]
    raise AssertionError('el registro real no trae ninguna fijación vigente de pérdidas')


def _salida_3b(fc=0.5, fcp=0.8, fs=0.6, fpmwhs=(0.75, 0.25)):
    return {'anio': ANIO,
            'f102': {'filas': [{'sistema': 'SIS-1', 'set': 'SET-A', 'devanado': 'TA:lv'},
                               {'sistema': 'SIS-1', 'set': 'SET-B', 'devanado': 'TB:lv'}]},
            'f101': {'filas': [{'nivel': 'devanado', 'nombre': d, 'fc': fc, 'fcp': fcp, 'fs': fs}
                               for d in ('TA:lv', 'TB:lv')]},
            'f103': {'filas': [{'devanado': 'TA:lv', 'fpmwhs': fpmwhs[0]}, {'devanado': 'TB:lv', 'fpmwhs': fpmwhs[1]}]}}


def _red_cadena():
    red = _red([('BA', 'SET-A'), ('BB', 'SET-B')], trafo2=[{'id': 'TA', 'set': 'SET-A', 'hv': 'HA', 'lv': 'BA'},
                                                          {'id': 'TB', 'set': 'SET-B', 'hv': 'HB', 'lv': 'BB'}])
    for b in red.de_tipo('barra'):
        b['kv'] = 10.0
    return red


VENTAS = {'SIS-1': {'at': [100.0] * (HORIZONTE + 1), 'mt': [1000.0] * (HORIZONTE + 1),
                    'bt': [2000.0 + 10 * i for i in range(HORIZONTE + 1)]}}
FUENTE_VENTAS = {'nombre': 'ventas sintéticas', 'huella': 'h' * 16}


def test_cadena_empresa_de_la_fijacion_con_el_fe_en_cascada_y_no_con_1_mas_p():
    """107:RF-9 (aclaración, T29 3c) — la energía por barra sube cada nivel con los FE de energía de la fijación
    vigente de la empresa (MT · PEMT; BT · PEBT · PESED · PEMT; AT sin pérdidas), se reparte con el FPMWHS, y F-110 a
    F-112 aplican el art. 8.1 con el FC y, según el formato, el FCP o el FS. Con 1+p el resultado sería otro."""
    mod = _cadena()
    registro, empresa, tabla = _registro_real_y_empresa()
    fe, p = tabla['fe'], {k: v / 100 for k, v in tabla['porcentaje'].items()}
    salida = mod.cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), VENTAS, fecha=FECHA_FIJACION)
    e0 = 100.0 + 1000.0 * fe['PEMT'] + 2000.0 * fe['PEBT'] * fe['PESED'] * fe['PEMT']
    con_1p = 100.0 + 1000.0 * (1 + p['PEMT']) + 2000.0 * (1 + p['PEBT']) * (1 + p['PESED']) * (1 + p['PEMT'])
    assert abs(e0 - con_1p) > 1e-3, 'el caso tiene que distinguir el FE de 1+p'
    fila = _fila(salida['filas']['F-109'], 'devanado', 'TA:lv')
    assert fila['energia_mwh'][0] == pytest.approx(0.75 * e0) and fila['energia_mwh'][0] != pytest.approx(0.75 * con_1p)
    assert fila['barra'] == 'BA' and fila['tension_kv'] == 10.0 and len(fila['energia_mwh']) == HORIZONTE + 1
    pnc = _fila(salida['filas']['F-110'], 'devanado', 'TA:lv')['potencia_mw'][0]
    assert pnc == pytest.approx(0.75 * e0 / (8760 * 0.5), rel=1e-6)
    assert _fila(salida['filas']['F-111'], 'devanado', 'TA:lv')['potencia_mw'][0] == pytest.approx(pnc * 0.8, rel=1e-6)
    assert _fila(salida['filas']['F-112'], 'devanado', 'TA:lv')['potencia_mw'][0] == pytest.approx(pnc * 0.6, rel=1e-6)
    assert salida['perdidas']['regla'] == 'vad.perdidas.factores_expansion' and salida['perdidas']['huella']
    assert salida['f108']['SIS-1'][3]['total_mwh'] == 100.0 + 1000.0 + 2030.0


def test_cadena_empresa_sin_fijacion_vigente_queda_no_transcrita_sin_valores_de_otra():
    """107:RF-9 (aclaración, T29 3c) — sin fijación vigente de la empresa, sus pérdidas quedan «no transcritas»:
    F-108 (sin pérdidas) se llena y F-109 a F-112 salen vacíos con ese motivo; nunca con los FE de otra empresa."""
    mod = _cadena()
    registro, _empresa, _tabla = _registro_real_y_empresa()
    salida = mod.cadena_regulatoria(registro, SIN_FIJACION, _salida_3b(), _red_cadena(), VENTAS, fecha=FECHA_FIJACION)
    assert 'no transcritas' in salida['perdidas']['motivo']
    assert salida['f108']['SIS-1'][0]['total_mwh'] == 3100.0
    for codigo, campo in (('F-109', 'energia_mwh'), ('F-110', 'potencia_mw'), ('F-111', 'potencia_mw'),
                          ('F-112', 'potencia_mw')):
        for fila in salida['filas'][codigo]:
            assert all(v is None for v in fila[campo]), f'{codigo} tomó valores sin fijación de la empresa'
            assert 'no transcritas' in fila['_motivos'][campo]
    celdas = mod.celdas_cadena(registro, salida, FUENTE_VENTAS, FECHA_FIJACION)
    vacia = next(c for c in celdas['F-109']['celdas'] if c['celda'] == 'F-109!E14')
    assert vacia['valor'] is None and 'no transcritas' in vacia['traza']['motivo']


def test_cadena_medicion_centralizada_que_no_se_separa_lleva_la_marca_aproximado():
    """107:RF-9 (aclaración, T29 3c) — una SET cuya medición centralizada no separa sus devanados lleva la marca
    «aproximado» con su motivo en cada fila y en cada celda; la otra SET no la lleva."""
    mod = _cadena()
    registro, empresa, _tabla = _registro_real_y_empresa()
    salida = mod.cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), VENTAS, fecha=FECHA_FIJACION,
                                    centralizadas={'SET-A': 'medición centralizada de la SET sin separar devanados'})
    for codigo in ('F-109', 'F-110', 'F-111', 'F-112'):
        assert _fila(salida['filas'][codigo], 'devanado', 'TA:lv').get('aproximado', '').startswith('aproximado')
        assert 'aproximado' not in _fila(salida['filas'][codigo], 'devanado', 'TB:lv')
    celdas = mod.celdas_cadena(registro, salida, FUENTE_VENTAS, FECHA_FIJACION)
    por_celda = {c['celda']: c for c in celdas['F-112']['celdas']}
    assert por_celda['F-112!E13']['traza']['marca'] == 'aproximado'
    assert 'marca' not in por_celda['F-112!E14']['traza'] and por_celda['F-112!E14']['valor'] is not None


def test_cadena_aviso_compara_la_regulatoria_con_la_de_diagnostico_por_set_y_anio_sin_corregir():
    """107:RF-9 (aclaración, T29 3c) — el aviso compara por SET y año la F-112 con la potencia de diagnóstico, con la
    diferencia en %; ninguna de las dos se corrige."""
    mod = _cadena()
    registro, empresa, _tabla = _registro_real_y_empresa()
    sin = mod.cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), VENTAS, fecha=FECHA_FIJACION)
    reg = _fila(sin['filas']['F-112'], 'devanado', 'TA:lv')['potencia_mw']
    con = mod.cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), VENTAS, fecha=FECHA_FIJACION,
                                 diagnostico_mw={'SET-A': [reg[0] / 1.1] * (HORIZONTE + 1)})
    assert _fila(con['filas']['F-112'], 'devanado', 'TA:lv')['potencia_mw'] == reg
    del_anio_0 = [a for a in con['avisos'] if a.startswith('SET SET-A, año 0:')]
    assert len(del_anio_0) == 1 and '+10.0 %' in del_anio_0[0]
    assert len([a for a in con['avisos'] if a.startswith('SET SET-A,')]) == HORIZONTE + 1
    assert not [a for a in con['avisos'] if a.startswith('SET SET-B,')]


def test_cadena_f108_ocupa_las_filas_de_sus_anios_sin_insertar_y_f109_a_f112_con_la_plantilla_oficial():
    """107:RF-9 (T29 3c) — F-108 lleva un año por fila en las 31 filas de la plantilla, sin filas que insertar, y
    F-109 a F-112 una columna por año desde «AÑO / 0», con el rótulo de cada columna comprobado en la plantilla."""
    mod = _cadena()
    registro, empresa, _tabla = _registro_real_y_empresa()
    salida = mod.cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), VENTAS, fecha=FECHA_FIJACION)
    celdas = mod.celdas_cadena(registro, salida, FUENTE_VENTAS, FECHA_FIJACION)
    f108 = celdas['F-108']['SIS-1']
    assert f108['filas_a_insertar'] == {} and not f108['huecos']
    c108 = {c['celda']: c['valor'] for c in f108['celdas']}
    assert c108['F-108!B6'] == 'SIS-1' and c108['F-108!F10'] == 3100.0 and c108['F-108!E40'] == 2300.0
    for codigo, fila_dato in (('F-109', 14), ('F-110', 13), ('F-111', 13), ('F-112', 13)):
        c = {x['celda']: x for x in celdas[codigo]['celdas']}
        assert c[f'{codigo}!B{fila_dato}']['valor'] == 'SET-A' and c[f'{codigo}!AI{fila_dato}']['traza']['anio'] == 30
        assert not celdas[codigo]['huecos'] and celdas[codigo]['filas_a_insertar'] == {}


# --- 107 T30 (paso 3d): historia, modelos comparados y resúmenes ------------------------------------------------------
def _resumen():
    """El módulo de la 3d: su ausencia es la falla de la aserción, no un error de importación."""
    import importlib
    import importlib.util
    assert importlib.util.find_spec('convertersmartgrid.pit.demanda_resumen') is not None, \
        'falta convertersmartgrid.pit.demanda_resumen (107 T30, paso 3d)'
    return importlib.import_module('convertersmartgrid.pit.demanda_resumen')


def _cadena_hecha():
    registro, empresa, _tabla = _registro_real_y_empresa()
    return registro, _cadena().cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), VENTAS,
                                                  fecha=FECHA_FIJACION)


def _libres(potencia=2.0, energia=500.0):
    """Un usuario libre sintético en una barra de 60 kV (AT) y otro en la barra MT de SET-A."""
    at = {'sistema': 'SIS-1', 'set': 'SET-L', 'barra': 'BL', 'tension_kv': 60.0}
    mt = {'sistema': 'SIS-1', 'set': 'SET-A', 'barra': 'BA', 'tension_kv': 10.0}
    serie_p = [potencia] * (HORIZONTE + 1)
    return {'F-115': [{**at, 'energia_mwh': [energia] * (HORIZONTE + 1)}, {**mt, 'energia_mwh': [energia] * (HORIZONTE + 1)}],
            **{c: [{**at, 'potencia_mw': serie_p}, {**mt, 'potencia_mw': serie_p}] for c in ('F-116', 'F-117', 'F-118')}}


def test_resumen_f119_suma_regulados_y_libres_por_nivel_en_gwh():
    """107:RF-9 (aclaración, T30 3d) — F-119 suma por nivel (MAT, AT y MT, por la tensión de cada barra según el num.
    12.1.1) la energía de F-109 (regulados) y la de F-115 (libres), en GWh, con el total del año."""
    mod = _resumen()
    registro, cadena = _cadena_hecha()
    resumen = mod.resumen_demanda(registro, cadena, _libres(), FECHA_FIJACION)
    regulada = sum(f['energia_mwh'][0] for f in cadena['filas']['F-109'])
    anio0 = resumen['f119'][0]
    assert anio0['mt_gwh'] == pytest.approx((regulada + 500.0) / 1000) and anio0['at_gwh'] == pytest.approx(0.5)
    assert anio0['mat_gwh'] == 0.0 and anio0['total_gwh'] == pytest.approx((regulada + 1000.0) / 1000)
    celdas = {c['celda']: c['valor'] for c in mod.celdas_resumen(registro, resumen, 'AREA-S', FUENTE_VENTAS,
                                                                  FECHA_FIJACION)['F-119']['celdas']}
    assert celdas['F-119!B5'] == 'AREA-S' and celdas['F-119!A8'] == 0 and celdas['F-119!D8'] == pytest.approx(anio0['mt_gwh'])
    assert celdas['F-119!A38'] == 30


def test_resumen_f120_a_f122_suman_por_barra_regulados_y_libres_con_su_tc():
    """107:RF-9 (aclaración, T30 3d) — F-120, F-121 y F-122 suman por barra F-110/F-116, F-111/F-117 y F-112/F-118; la
    barra solo de libres entra con su valor, y la TC es la tasa promedio entre el año 0 y el último."""
    mod = _resumen()
    registro, cadena = _cadena_hecha()
    resumen = mod.resumen_demanda(registro, cadena, _libres(), FECHA_FIJACION)
    for resumen_codigo, regulado in (('F-120', 'F-110'), ('F-121', 'F-111'), ('F-122', 'F-112')):
        reg = _fila(cadena['filas'][regulado], 'devanado', 'TA:lv')['potencia_mw']
        fila = _fila(resumen['filas'][resumen_codigo], 'barra', 'BA')
        assert fila['potencia_mw'][0] == pytest.approx(reg[0] + 2.0) and fila['potencia_mw'][30] == pytest.approx(reg[30] + 2.0)
        assert fila['tc_pct'] == pytest.approx(((reg[30] + 2.0) / (reg[0] + 2.0)) ** (1 / 30) * 100 - 100)
        assert _fila(resumen['filas'][resumen_codigo], 'barra', 'BL')['potencia_mw'][0] == 2.0
    hecho = mod.celdas_resumen(registro, resumen, 'AREA-S', FUENTE_VENTAS, FECHA_FIJACION)['F-122']
    c = {x['celda']: x['valor'] for x in hecho['celdas']}
    assert c['F-122!C13'] == 'BA' and isinstance(c['F-122!AJ13'], float)
    assert any(h['bloque'] == 'totales' for h in hecho['huecos']), 'las filas de totales se nombran como hueco'


def test_resumen_sin_proyeccion_de_libres_no_suma_y_lo_dice_salvo_area_sin_libres():
    """107:RF-9 (aclaración, T30 3d) — sin la proyección de los usuarios libres, los resúmenes no se suman y cada
    celda dice la causa; si el perfil declara que el área no tiene usuarios libres, van solo los regulados."""
    mod = _resumen()
    registro, cadena = _cadena_hecha()
    sin = mod.resumen_demanda(registro, cadena, None, FECHA_FIJACION)
    assert all(v is None for f in sin['filas']['F-121'] for v in f['potencia_mw'])
    assert 'usuarios libres' in sin['motivo'] and sin['f119'][0]['total_gwh'] is None
    celda = next(c for c in mod.celdas_resumen(registro, sin, 'AREA-S', FUENTE_VENTAS, FECHA_FIJACION)['F-119']['celdas']
                 if c['celda'] == 'F-119!B8')
    assert celda['valor'] is None and 'usuarios libres' in celda['traza']['motivo']
    solo = mod.resumen_demanda(registro, cadena, {'sin_usuarios_libres': 'el área no tiene usuarios libres'},
                               FECHA_FIJACION)
    reg = _fila(cadena['filas']['F-110'], 'devanado', 'TA:lv')['potencia_mw']
    assert _fila(solo['filas']['F-120'], 'barra', 'BA')['potencia_mw'] == reg


def test_resumen_historia_f104_y_f105_del_menos_20_al_0_con_sus_tasas_y_desde_las_exogenas_de_la_031():
    """107:RF-9 (aclaración, T30 3d) — F-104 y F-105 llevan los años −20 a 0 de la plantilla (el 0 es el
    representativo), la tasa de crecimiento de cada variable y el total de ventas; F-104 sale del registro de exógenas
    de la 031 con lo publicado hasta el corte, el PBI en millones de soles y los clientes como hueco con su causa."""
    from datetime import date

    from convertersmartgrid.proyeccion_anual import CifraExogena, RegistroExogenas
    mod = _resumen()
    registro = cargar_registro(NORMATIVA)
    cifras = tuple(CifraExogena(v, 'Región sintética', a, valor, 'nivel', u, 'fuente sintética', date(a + 1, 3, 1), 'x')
                   for a in range(2000, 2023)
                   for v, valor, u in (('pbi', 1e9 * (1.03 ** (a - 2000)), 'soles de 2007'),
                                       ('poblacion', 1e6 + 1000 * (a - 2000), 'habitantes')))
    exo = RegistroExogenas('exógenas sintéticas', 'e' * 64, cifras)
    historia = mod.historia_desde_exogenas(exo, 'Región sintética', 2022, '2024-12-31')
    historia.update(area='AREA-S', ventas={a: {'at': 10.0, 'mt': 20.0 + a - 2002, 'bt': 30.0} for a in range(2002, 2023)})
    hecho = mod.celdas_historia(registro, historia, FUENTE_VENTAS)
    c104 = {c['celda']: c for c in hecho['F-104']['celdas']}
    assert c104['F-104!B29']['valor'] == pytest.approx(1e3 * 1.03 ** 22) and c104['F-104!C29']['valor'] == pytest.approx(3.0)
    assert c104['F-104!F9']['valor'] == 1e6 + 2000 and c104['F-104!D29']['valor'] is None
    assert 'clientes' in c104['F-104!D29']['traza']['motivo']
    c105 = {c['celda']: c['valor'] for c in hecho['F-105']['celdas']}
    assert c105['F-105!E29'] == 10.0 + 40.0 + 30.0 and c105['F-105!C9'] == 20.0 and c105['F-105!B5'] == 'AREA-S'
    assert hecho['F-105']['filas_a_insertar'] == {} and not hecho['F-105']['huecos']


def test_resumen_modelos_comparados_f106_y_f107_con_su_ecuacion_y_sus_estadisticos():
    """107:RF-9 (aclaración, T30 3d) — F-106 (tendencias, por sistema) y F-107 (econométrico, del área) llevan la
    proyección de cada modelo comparado por año, su nombre en la cabecera de su columna, la ecuación, el r², el F y el
    t (en F-107, el de cada variable) tal como los dio la proyección; un modelo de más se nombra como hueco."""
    mod = _resumen()
    registro = cargar_registro(NORMATIVA)
    modelo = {'nombre': 'lineal', 'proyeccion': [100.0 + i for i in range(HORIZONTE + 1)], 'ecuacion': 'V = a + b·t',
              'r2': 0.95, 'f': 120.0, 'f_prob': 0.001, 't': {'valor': 8.1, 'prob': 0.002}}
    f106 = {c['celda']: c['valor'] for c in mod.celdas_modelos(registro, 'F-106', 'SIS-1', [modelo], FUENTE_VENTAS)['celdas']}
    assert f106['F-106!B5'] == 'SIS-1' and f106['F-106!C8'] == 'lineal' and f106['F-106!C39'] == 130.0
    assert f106['F-106!C42'] == 'V = a + b·t' and f106['F-106!C44'] == 0.95 and f106['F-106!C48'] == 8.1
    assert f106['F-106!C52'] == 120.0 and f106['F-106!C53'] == 0.001
    eco = {**modelo, 'nombre': 'elasticidad', 't': {'pbi': (5.0, 0.01), 'poblacion': (3.0, 0.02)}}
    hecho = mod.celdas_modelos(registro, 'F-107', 'AREA-S', [eco] * 6, FUENTE_VENTAS)
    f107 = {c['celda']: c['valor'] for c in hecho['celdas']}
    assert f107['F-107!A52'] == 'pbi' and f107['F-107!C52'] == 5.0 and f107['F-107!C53'] == 0.01
    assert f107['F-107!A54'] == 'poblacion' and f107['F-107!G54'] == 3.0 and f107['F-107!C48'] == 120.0
    assert any('6 modelos' in h['causa'] for h in hecho['huecos'])


def test_resumen_llenado_ningun_formato_de_demanda_pendiente_sin_causa_nombrada():
    """107:RF-9 (aclaración, T30 3d) — `llenado.pendientes_de_mapeo` no lista ningún formato de demanda (F-101 a
    F-124) sin su causa nombrada, y con sus fuentes los de la 3b, la 3c y la 3d salen llenados."""
    from convertersmartgrid.pit import llenado
    registro, cadena = _cadena_hecha()
    sin_fuentes = llenado.llenar_formatos(registro, {})
    demanda = [c for c in sin_fuentes['pendientes_de_mapeo'] if c.startswith('F-1')]
    # PIT-F113-118, PIT-F123 y PIT-F124 (orden de c2: nada queda con una causa): ningún formato de demanda pendiente.
    assert demanda == [], f'formatos de demanda sin mapeo: {demanda}'
    salida_3b = {'f102': {'filas': []}, 'f101': {'filas': []}, 'f103': {'filas': []}}
    fuentes = {'demanda_3b': {'fuente': FUENTE_VENTAS, 'salida': salida_3b, 'red': _red_cadena()},
               'cadena': {'fuente': FUENTE_VENTAS, 'cadena': cadena},
               'historia': {'fuente': FUENTE_VENTAS, 'historia': None},
               'tendencias': {'fuente': FUENTE_VENTAS, 'sistemas': {}},
               'econometrico': {'fuente': FUENTE_VENTAS, 'area': 'AREA-S', 'modelos': []},
               'resumen': {'fuente': FUENTE_VENTAS, 'cadena': cadena, 'libres': None, 'area': 'AREA-S'}}
    con = {f['codigo']: f for f in llenado.llenar_formatos(registro, fuentes, FECHA_FIJACION)['formatos']}
    llenados = ['F-%d' % n for n in (*range(101, 113), *range(119, 123))]
    assert [c for c in llenados if con[c]['estado'] != 'llenado'] == []


def test_resumen_formato_por_sistema_con_dos_sistemas_pide_su_copia_de_hoja_y_el_libro_no_se_escribe(tmp_path):
    """107:RF-9 (T30 3d) — F-108 va una hoja por sistema eléctrico: con dos sistemas, el segundo va a «F-108 (2)», el
    resultado lo pide en ``hojas_a_copiar`` y el plan del libro se detiene diciéndolo en lugar de escribir en una hoja
    que no existe."""
    from convertersmartgrid.pit import llenado
    from convertersmartgrid.pit.cuadros import plan_de_formatos
    registro, empresa, _tabla = _registro_real_y_empresa()
    dos = {**VENTAS, 'SIS-2': VENTAS['SIS-1']}
    cadena = _cadena().cadena_regulatoria(registro, empresa, _salida_3b(), _red_cadena(), dos, fecha=FECHA_FIJACION)
    hecho = llenado.llenar_formatos(registro, {'cadena': {'fuente': FUENTE_VENTAS, 'cadena': cadena}}, FECHA_FIJACION)
    f108 = hecho['resultados']['F-108']
    assert f108['hojas_a_copiar'] == [{'de': 'F-108', 'a': 'F-108 (2)', 'sistema': 'SIS-2'}]
    assert {c['celda'] for c in f108['celdas']} >= {'F-108!B6', 'F-108 (2)!B6'}
    with pytest.raises(PitError, match=r'F-108 \(2\)'):
        plan_de_formatos([f108], modelo=tmp_path / 'm.xlsx', destino=tmp_path / 'd.xlsx')
