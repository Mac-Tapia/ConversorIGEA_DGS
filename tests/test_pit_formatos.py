"""Spec 107 T19 — formatos del PIT desde la norma registrada (107:RF-9, aclaración; 107:RF-11).

Los formatos que se emiten son los que lista la norma vigente del registro, no una lista del código: dos registros
sintéticos con listas y transcripciones distintas dan formatos distintos. Un formato listado y no transcrito se nombra
en el resumen del expediente, sin inventar sus columnas, y una celda que sale de otro formato se escribe como fórmula
vinculada a la celda de la que sale. Todo sintético: actos, códigos y valores inventados para la prueba.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from convertersmartgrid.pit.ambito import PitError
from convertersmartgrid.pit.cuadros import (
    codigos_de_grupos,
    formatos_aplicables,
    plan_de_cuadros,
)
from convertersmartgrid.pit.expediente import abrir, emitir
from convertersmartgrid.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]


def _regla(clave, valor, pagina='1'):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave}»', 'pagina': pagina}


def _formato(codigo, titulo):
    return _regla(f'pit.formato.{codigo}', {'codigo': codigo, 'titulo': titulo, 'libro': 'libro.xls', 'hoja': codigo,
                                             'sha256_libro': 'c' * 64,
                                             'filas': [{'fila': 1, 'celdas': {'A': 'REGULADOR', 'C': codigo}},
                                                       {'fila': 2, 'celdas': {'A': titulo}}]},
                  pagina=f'libro libro.xls, hoja {codigo}')


def _registro(carpeta: Path, grupos: dict, transcritos: list[str], *, lista='pit.formatos_x', vigencia='2001-01-01'):
    carpeta.mkdir(parents=True, exist_ok=True)
    reglas = [_regla(lista, {'grupos': grupos, 'transcrito': bool(transcritos)})]
    reglas += [_formato(c, f'Formato {c}') for c in transcritos]
    (carpeta / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT-FORMATOS', 'titulo': 'Norma sintética de formatos', 'estado_juridico': 'vigente_comprobada',
         'sha256': 'a' * 64, 'vigencia_desde': vigencia, 'reglas': reglas}]}), encoding='utf-8')
    return cargar_registro(carpeta)


def test_codigos_de_grupos_sale_de_los_rangos_registrados():
    """107:RF-9 — «F-101 a F-103» y «F-401» se expanden sin una lista fija; un rango mal escrito es un error."""
    assert codigos_de_grupos({'F-101 a F-103': 'Demanda', 'F-401': 'COyM'}) == ['F-101', 'F-102', 'F-103', 'F-401']
    with pytest.raises(PitError, match='F-9 a F-x'):
        codigos_de_grupos({'F-9 a F-x': 'mal'})
    with pytest.raises(PitError, match='F-105 a F-101'):
        codigos_de_grupos({'F-105 a F-101': 'al revés'})


@pytest.mark.parametrize('grupos, transcritos, no_transcritos', (
    ({'F-001 a F-002': 'General', 'F-201 a F-204': 'Red'}, ['F-001', 'F-002', 'F-201', 'F-203'], ['F-202', 'F-204']),
    ({'F-501 a F-503': 'Tarifas'}, ['F-501', 'F-502', 'F-503'], []),
), ids=('registro_a', 'registro_b'))
def test_los_formatos_salen_del_registro(tmp_path, grupos, transcritos, no_transcritos):
    """107:RF-9 — el número y la lista de formatos salen del registro; los no transcritos se nombran."""
    registro = _registro(tmp_path / 'reg', grupos, transcritos)
    aplicables = formatos_aplicables(registro)
    codigos = codigos_de_grupos(grupos)
    assert [f['codigo'] for f in aplicables['formatos']] == codigos
    assert aplicables['no_transcritos'] == no_transcritos
    assert aplicables['norma'] == 'SINT-FORMATOS'
    for f in aplicables['formatos']:
        assert f['transcrito'] is (f['codigo'] in transcritos)
        if f['transcrito']:
            assert f['titulo'] == f'Formato {f["codigo"]}' and f['hoja'] == f['codigo'] and f['regla']['huella']
        else:
            assert 'titulo' not in f, 'un formato no transcrito no se inventa'


def test_sin_lista_de_formatos_en_el_registro_es_un_error_que_lo_dice(tmp_path):
    """107:RF-9 — sin la regla que lista los formatos no se emite una lista supuesta."""
    (tmp_path / 'r').mkdir()
    (tmp_path / 'r' / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT', 'titulo': 'Sin formatos', 'estado_juridico': 'vigente_comprobada', 'sha256': 'a' * 64,
         'reglas': [_regla('pit.vida_util_anios', 30)]}]}), encoding='utf-8')
    with pytest.raises(PitError, match='lista los formatos'):
        formatos_aplicables(cargar_registro(tmp_path / 'r'))


def test_no_transcrito_nombrado_en_el_resumen_del_expediente(tmp_path):
    """107:RF-9 — el expediente guarda los formatos aplicables y su resumen nombra el que no está transcrito."""
    registro = _registro(tmp_path / 'reg', {'F-201 a F-203': 'Red'}, ['F-201', 'F-203'])
    aplicables = formatos_aplicables(registro)
    carpeta = abrir(tmp_path / 'espacio', 'AREA-X', '2001-2004', registro, fecha_apertura='2001-06-01')
    salidas = emitir(carpeta, registro, celdas=[], formatos=aplicables, no_transcritos=['pit.cuadro.y'])
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert resumen['cuadros_no_transcritos'] == ['F-202', 'pit.cuadro.y']
    guardado = json.loads(salidas['formatos'].read_text(encoding='utf-8'))
    assert [f['codigo'] for f in guardado['formatos']] == ['F-201', 'F-202', 'F-203']
    relacion = json.loads(salidas['relacion'].read_text(encoding='utf-8'))
    assert 'formatos.json' in json.dumps(relacion, ensure_ascii=False)


def test_celda_derivada_se_escribe_como_formula_vinculada(tmp_path):
    """107:RF-9 — la celda que sale de otro formato se escribe vinculada a su origen, no como cifra copiada."""
    registro = _registro(tmp_path / 'reg', {'F-305 a F-306': 'Inversión'}, ['F-305', 'F-306'])
    aplicables = formatos_aplicables(registro)
    modelo = tmp_path / 'modelo.xlsx'
    modelo.write_bytes(b'')
    plan = plan_de_cuadros([], {'modelo': str(modelo)}, destino=tmp_path / 'salida.xlsx', formatos=aplicables,
                           vinculos=[{'celda': 'F-306!C8', 'origen': 'F-305!D12'}])
    assert plan['formulas'] == [{'celda': 'F-306!C8', 'formula': "='F-305'!D12"}]
    assert not plan['escribir'], 'la celda derivada no se escribe como valor'


@pytest.mark.parametrize('vinculo, mensaje', (
    ({'celda': 'F-306!C8', 'origen': 'F-999!D12'}, 'F-999'),
    ({'celda': 'F-306!C8', 'origen': 'F-307!D12'}, 'F-307'),
    ({'celda': 'F-306', 'origen': 'F-305!D12'}, 'F-306'),
), ids=('origen_no_listado', 'origen_no_transcrito', 'celda_sin_hoja'))
def test_vinculo_a_un_formato_que_no_esta_es_un_error(tmp_path, vinculo, mensaje):
    """107:RF-9 — un vínculo a un formato que no se lista, que no está transcrito o mal escrito se rechaza."""
    registro = _registro(tmp_path / 'reg', {'F-305 a F-307': 'Inversión'}, ['F-305', 'F-306'])
    modelo = tmp_path / 'modelo.xlsx'
    modelo.write_bytes(b'')
    with pytest.raises(PitError, match=mensaje):
        plan_de_cuadros([], {'modelo': str(modelo)}, destino=tmp_path / 's.xlsx',
                        formatos=formatos_aplicables(registro), vinculos=[vinculo])


def test_registro_real_lista_y_transcribe_los_formatos_de_la_norma_tarifas():
    """107:RF-9 (107 T19) — en el registro real, cada formato que lista la norma vigente está transcrito."""
    aplicables = formatos_aplicables(cargar_registro(RAIZ / 'config' / 'normativa'))
    assert aplicables['formatos'] and aplicables['no_transcritos'] == []
    assert any(f['codigo'] == 'F-208' for f in aplicables['formatos'])


# --------------------------------------------------------------------------- T26: el F-208 (107:RF-18)
# El módulo se importa dentro de cada prueba, así que en la copia _rojo solo fallan las del F-208.
NORMATIVA = RAIZ / 'config' / 'normativa'
FUENTE = {'nombre': 'historico_sintetico.xlsx', 'huella': 'd' * 64}


def _f208():
    from convertersmartgrid.pit import f208
    return f208


def test_f208_estructura_sale_de_la_plantilla_transcrita():
    """107:RF-18 — bloques, columnas y primera fila de datos salen de la hoja F-208 transcrita, con su cita."""
    estructura = _f208().estructura_f208(cargar_registro(NORMATIVA))
    bloques = {b['bloque']: b for b in estructura['bloques']}
    assert set(bloques) == {'interrupciones', 'indices', 'barras'}
    assert [c['campo'] for c in bloques['interrupciones']['columnas']] == [
        'nominacion', 'fecha', 'hora_inicio', 'hora_fin', 'tipo', 'ens_kwh']
    assert [c['campo'] for c in bloques['indices']['columnas']] == [
        'nominacion', 'saifi', 'saidi', 'saifi_tolerancia', 'saidi_tolerancia', 'cumple']
    assert [c['campo'] for c in bloques['barras']['columnas']] == [
        'nominacion', 'caida_kv', 'caida_pct', 'tolerancia_kv', 'tolerancia_pct', 'cumple']
    for b in bloques.values():
        assert b['primera_fila_datos'] > max(b['filas_cabecera']) > b['fila_titulo'], b['bloque']
    assert estructura['regla']['pagina'].endswith('hoja F-208') and estructura['regla']['huella']


def test_f208_con_fallas_sinteticas_llena_los_indices():
    """107:RF-18 — con fallas e índices sintéticos se llenan las celdas, con su traza; «Cumple» sale del cálculo."""
    fuentes = {'fuente': FUENTE,
               'interrupciones': [
                   {'nominacion': 'L-X1', 'fecha': '2001-03-04', 'hora_inicio': '10:00', 'hora_fin': '11:30',
                    'tipo': 'Forzada', 'ens_kwh': 1234.5},
                   {'nominacion': 'L-X2', 'fecha': '2001-05-06', 'hora_inicio': '08:00', 'hora_fin': '08:20',
                    'tipo': 'Programada', 'ens_kwh': 50.0}],
               'indices': [{'nominacion': 'L-X1', 'saifi': 2.0, 'saidi': 3.5, 'saifi_tolerancia': 3.0,
                            'saidi_tolerancia': 4.0},
                           {'nominacion': 'L-X2', 'saifi': 5.0, 'saidi': 1.0, 'saifi_tolerancia': 3.0,
                            'saidi_tolerancia': 4.0}],
               'barras': [{'nominacion': 'SET-X/B1', 'caida_kv': 0.4, 'caida_pct': 6.0, 'tolerancia_kv': 0.5,
                           'tolerancia_pct': 5.0}]}
    resultado = _f208().celdas_f208(cargar_registro(NORMATIVA), fuentes)
    celdas = {(c['bloque'], c['fila'], c['campo']): c for c in resultado['celdas']}
    assert celdas[('interrupciones', 1, 'ens_kwh')]['valor'] == 1234.5
    assert celdas[('interrupciones', 2, 'tipo')]['valor'] == 'Programada'
    assert celdas[('indices', 1, 'cumple')]['valor'] == 'SI'
    assert celdas[('indices', 2, 'cumple')]['valor'] == 'NO', 'SAIFI 5 > tolerancia 3'
    assert celdas[('barras', 1, 'cumple')]['valor'] == 'NO', '6 % > 5 %'
    assert not resultado['huecos']
    for c in resultado['celdas']:
        assert c['cuadro'] == 'F-208' and c['celda'].startswith('F-208!')
        assert all(c['traza'].get(k) for k in ('fuente', 'calculo', 'motor', 'regla')), c['id']
        assert c['traza']['fuente']['huella'] == FUENTE['huella']


def test_f208_sin_fallas_cada_celda_vacia_con_su_hueco_nombrado():
    """107:RF-18 — sin fuentes importadas, cada celda de la primera fila de cada bloque queda vacía y su hueco se
    nombra; nunca un cero ni un bloque vacío en silencio."""
    resultado = _f208().celdas_f208(cargar_registro(NORMATIVA), {'fuente': FUENTE})
    assert resultado['celdas']
    for c in resultado['celdas']:
        assert c['valor'] is None and c['fila'] == 1 and c['traza']['motivo'], c['id']
    assert sorted(h['bloque'] for h in resultado['huecos']) == ['barras', 'indices', 'interrupciones']
    assert all(h['causa'] for h in resultado['huecos'])


def test_f208_tolerancia_que_falta_deja_cumple_vacio_con_su_motivo():
    """107:RF-18 — sin la tolerancia, «Cumple» no se supone."""
    fuentes = {'fuente': FUENTE, 'indices': [{'nominacion': 'L-X1', 'saifi': 2.0, 'saidi': 3.5}]}
    resultado = _f208().celdas_f208(cargar_registro(NORMATIVA), fuentes)
    cumple = next(c for c in resultado['celdas'] if c['bloque'] == 'indices' and c['campo'] == 'cumple')
    assert cumple['valor'] is None and 'tolerancia' in cumple['traza']['motivo']


@pytest.mark.parametrize('cambio, mensaje', (
    ({'interrupciones': [{'nominacion': 'L-X1', 'tipo': 'Otra'}]}, 'Forzada o Programada'),
    ({'interrupciones': [{'nominacion': 'L-X1', 'tipo': 'Forzada', 'ens_kwh': -1}]}, 'ens_kwh'),
    ({'fuente': {}}, 'fuente'),
), ids=('tipo_invalido', 'ens_negativa', 'sin_fuente'))
def test_f208_entrada_invalida_es_un_error_que_la_nombra(cambio, mensaje):
    """107:RF-18 — un tipo que la nota (2) del formato no admite, una ENS negativa o una fuente sin huella se
    rechazan nombrándolos."""
    with pytest.raises(PitError, match=mensaje):
        _f208().celdas_f208(cargar_registro(NORMATIVA), {'fuente': FUENTE, **cambio})


def test_f208_sin_plantilla_transcrita_es_un_error(tmp_path):
    """107:RF-18 — sin la hoja F-208 transcrita no se inventa su estructura."""
    registro = _registro(tmp_path / 'reg', {'F-201 a F-208': 'Red'}, ['F-201'])
    with pytest.raises(PitError, match='F-208'):
        _f208().estructura_f208(registro)


def test_f208_sus_celdas_entran_en_el_expediente(tmp_path):
    """107:RF-9, 107:RF-18 — las celdas del F-208 traen la traza que el expediente exige."""
    registro = cargar_registro(NORMATIVA)
    celdas = _f208().celdas_f208(registro, {'fuente': FUENTE})['celdas']
    carpeta = abrir(tmp_path / 'espacio', 'AREA-X', '2001-2004', registro, fecha_apertura='2001-06-01')
    salidas = emitir(carpeta, registro, celdas=celdas)
    assert len(json.loads(salidas['cuadros'].read_text(encoding='utf-8'))) == len(celdas)


# --------------------------------------------------------------------------- T19b: el llenado de los formatos
def _llenado():
    from convertersmartgrid.pit import llenado
    return llenado


def test_llenado_formatos_exigidos_salen_del_num_5_7():
    """107:RF-9 (T19b) — los formatos que exige el estudio del plan salen de la regla citada del num. 5.7, sin los de
    tarifas y compensaciones."""
    registro = cargar_registro(NORMATIVA)
    exigidos = _llenado().formatos_exigidos(registro)
    assert 'F-001' in exigidos and 'F-208' in exigidos and 'F-401' in exigidos
    assert not [c for c in exigidos if c.startswith('F-5')]
    regla = registro.regla('pit.plan.formatos_exigidos').regla
    assert regla.citada and '5.7' in regla.articulo_o_anexo


def test_llenado_ningun_formato_exigido_vacio_en_silencio():
    """107:RF-9 (T19b) — cada formato exigido sale llenado o como plantilla nombrada con su causa; los que aún no tienen
    mapeo se listan como pendientes, que es lo que impide cerrar T19."""
    registro = cargar_registro(NORMATIVA)
    resultado = _llenado().llenar_formatos(registro, {})
    exigidos = _llenado().formatos_exigidos(registro)
    assert [f['codigo'] for f in resultado['formatos']] == exigidos
    for f in resultado['formatos']:
        assert f['estado'] in ('llenado', 'plantilla'), f
        if f['estado'] == 'plantilla':
            assert f['causa'] and f['titulo'], f['codigo']
    f208 = next(f for f in resultado['formatos'] if f['codigo'] == 'F-208')
    assert f208['estado'] == 'plantilla' and 'sin datos de origen' in f208['causa']
    assert 'F-208' not in resultado['pendientes_de_mapeo']
    assert set(resultado['pendientes_de_mapeo']) == {
        f['codigo'] for f in resultado['formatos'] if 'sin mapeo' in f['causa']}


def test_llenado_con_la_fuente_del_f208_lo_llena_con_su_traza():
    """107:RF-9, 107:RF-18 (T19b) — con la fuente del F-208, el formato sale llenado y sus celdas entran al resultado."""
    registro = cargar_registro(NORMATIVA)
    fuentes = {'F-208': {'fuente': FUENTE, 'indices': [{'nominacion': 'L-X1', 'saifi': 2.0, 'saidi': 3.5,
                                                         'saifi_tolerancia': 3.0, 'saidi_tolerancia': 4.0}]}}
    resultado = _llenado().llenar_formatos(registro, fuentes)
    f208 = next(f for f in resultado['formatos'] if f['codigo'] == 'F-208')
    assert f208['estado'] == 'llenado' and {h['bloque'] for h in f208['huecos']} == {'interrupciones', 'barras'}
    assert any(c['cuadro'] == 'F-208' and c['valor'] == 'SI' for c in resultado['celdas'])


def test_llenado_formato_exigido_sin_transcribir_es_plantilla_con_su_causa(tmp_path):
    """107:RF-9 (T19b) — un formato exigido que el registro no transcribe sale nombrado, no inventado."""
    _registro(tmp_path / 'reg', {'F-201 a F-203': 'Red'}, ['F-201', 'F-203'])
    plan = json.loads((tmp_path / 'reg' / 'r.json').read_text(encoding='utf-8'))
    plan['normas'][0]['reglas'].append(_regla('pit.plan.formatos_exigidos', {'grupos': ['F-201 a F-203']}))
    (tmp_path / 'reg' / 'r.json').write_text(json.dumps(plan), encoding='utf-8')
    resultado = _llenado().llenar_formatos(cargar_registro(tmp_path / 'reg'), {})
    f202 = next(f for f in resultado['formatos'] if f['codigo'] == 'F-202')
    assert f202['estado'] == 'plantilla' and 'no transcrito' in f202['causa']


def test_llenado_sin_regla_de_formatos_exigidos_es_un_error(tmp_path):
    """107:RF-9 (T19b) — sin la regla del num. 5.7 no se supone qué formatos lleva el estudio."""
    registro = _registro(tmp_path / 'reg', {'F-201 a F-203': 'Red'}, ['F-201'])
    with pytest.raises(PitError, match='pit.plan.formatos_exigidos'):
        _llenado().formatos_exigidos(registro)


# --------------------------------------------------------------------------- T19b: F-001 a F-003 desde la red
FUENTE_RED = {'nombre': 'red_sintetica.xlsx', 'huella': 'b' * 64}


def _red(lineas_extra=0):
    from convertersmartgrid.pit.red_area import RedArea
    barras = [{'id': 'B1', 'kv': 138.0, 'set': 'SET-A'}, {'id': 'B2', 'kv': 60.0, 'set': 'SET-A'},
              {'id': 'B3', 'kv': 60.0, 'set': 'SET-B'}, {'id': 'B4', 'kv': 22.9, 'set': 'SET-B'},
              {'id': 'B5', 'kv': 66.0, 'set': 'SET-C'}, {'id': 'B6', 'kv': 22.9, 'set': 'SET-A'},
              {'id': 'B7', 'kv': 10.0, 'set': 'SET-A'}]
    linea = {'r_ohm_per_km': 0.1, 'x_ohm_per_km': 0.4, 'c_nf_per_km': 9.0, 'max_i_ka': 0.5}
    lineas = [{'id': 'L1', 'desde': 'B2', 'hasta': 'B3', 'longitud_km': 12.5, 'titular': 'TIT-1', **linea},
              {'id': 'L2', 'desde': 'B5', 'hasta': 'B3', 'longitud_km': 3.0, 'titular': 'TIT-1', **linea}]
    lineas += [{'id': f'LX{i}', 'desde': 'B2', 'hasta': 'B3', 'longitud_km': 1.0, 'titular': 'TIT-2', **linea}
               for i in range(lineas_extra)]
    trafo2 = [{'id': 'TR1', 'hv': 'B1', 'lv': 'B2', 'sn_mva': 50.0, 'vn_hv_kv': 138.0, 'vn_lv_kv': 60.0,
               'vk_percent': 10.0, 'vkr_percent': 0.4, 'pfe_kw': 30.0, 'i0_percent': 0.1, 'titular': 'TIT-1'},
              {'id': 'TR2', 'hv': 'B3', 'lv': 'B4', 'sn_mva': 25.0, 'vn_hv_kv': 60.0, 'vn_lv_kv': 22.9,
               'vk_percent': 8.0, 'vkr_percent': 0.5, 'pfe_kw': 15.0, 'i0_percent': 0.1, 'titular': 'TIT-2'}]
    trafo3 = [{'id': 'TT1', 'hv': 'B2', 'mv': 'B6', 'lv': 'B7', 'sn_hv_mva': 30.0, 'sn_mv_mva': 30.0,
               'sn_lv_mva': 10.0, 'vn_hv_kv': 60.0, 'vn_mv_kv': 22.9, 'vn_lv_kv': 10.0, 'vk_hv_percent': 9.0,
               'vk_mv_percent': 6.0, 'vk_lv_percent': 12.0, 'vkr_hv_percent': 0.3, 'vkr_mv_percent': 0.2,
               'vkr_lv_percent': 0.4, 'pfe_kw': 24.0, 'i0_percent': 0.1, 'titular': 'TIT-1'}]
    comp = [{'id': 'C1', 'barra': 'B4', 'q_mvar': -2.0, 'tipo_compensacion': 'Capacitor', 'titular': 'TIT-2'},
            {'id': 'C2', 'barra': 'B6', 'q_mvar': 1.0, 'titular': 'TIT-1'}]
    return RedArea('AD-X', elementos={'barra': barras, 'linea': lineas, 'trafo2': trafo2, 'trafo3': trafo3,
                                      'compensacion': comp})


def _celdas(resultado):
    return {c['celda']: c for c in resultado['celdas']}


def test_f001_por_titular_con_los_niveles_de_la_regla_12_1_1():
    """107:RF-9 (T19b) — km por nivel y SET por transformación, por titular, con la regla 12.1.1; una línea de una
    tensión que no está en la regla se nombra como hueco, no se aproxima."""
    resultado = _llenado().llenar_formatos(cargar_registro(NORMATIVA),
                                           {'red': {'fuente': FUENTE_RED, 'red': _red()}})
    celdas = _celdas(resultado)
    assert celdas['F-001!B4']['valor'] == 'AD-X'
    assert (celdas['F-001!A8']['valor'], celdas['F-001!C8']['valor'], celdas['F-001!D8']['valor']) == ('TIT-1', 12.5, 1)
    assert (celdas['F-001!A9']['valor'], celdas['F-001!E9']['valor']) == ('TIT-2', 1)
    # Total AT/MT: SET-A de TIT-1 (su transformador de tres devanados 60/22,9/10 kV) y SET-B de TIT-2.
    assert celdas['F-001!E8']['valor'] == 1
    assert celdas['F-001!C12']['valor'] == 12.5 and celdas['F-001!E12']['valor'] == 2
    f001 = next(f for f in resultado['formatos'] if f['codigo'] == 'F-001')
    assert f001['estado'] == 'llenado' and any('L2' in h['causa'] and '66' in h['causa'] for h in f001['huecos'])
    assert {'F-001', 'F-002', 'F-003'}.isdisjoint(resultado['pendientes_de_mapeo'])


def test_f002_lineas_con_su_calculo_y_b_solo_con_la_frecuencia():
    """107:RF-9 (T19b) — cada línea en su fila, con la tensión de envío; B solo si el perfil da la frecuencia, y lo que
    la red no trae queda vacío con su motivo."""
    from convertersmartgrid.pit.formatos_red import datos_f002
    from convertersmartgrid.pit.plantillas import celdas_de_formato
    registro = cargar_registro(NORMATIVA)
    con = _celdas(celdas_de_formato(registro, 'F-002', datos_f002(_red(), FUENTE_RED, frecuencia_hz=60)))
    assert con['F-002!A10']['valor'] == 'SET-A-SET-B' and con['F-002!G10']['valor'] == 60.0
    assert con['F-002!L10']['valor'] == 12.5
    assert con['F-002!Q10']['valor'] == pytest.approx(2 * 3.141592653589793 * 60 * 9.0e-9)
    sin = _celdas(celdas_de_formato(registro, 'F-002', datos_f002(_red(), FUENTE_RED)))
    assert sin['F-002!Q10']['valor'] is None and 'frecuencia' in sin['F-002!Q10']['traza']['motivo']
    assert sin['F-002!C10']['valor'] is None and 'puesta en servicio' in sin['F-002!C10']['traza']['motivo']


def test_f003_dos_y_tres_devanados_y_compensacion():
    """107:RF-9 (T19b) — Pcu% = vkr%, Pfe% = P0/Sn, P-S/S-T/P-T de la red; la potencia de un equipo que no se declara
    capacitor no va a la columna de capacitores, y las columnas sin campo se nombran."""
    from convertersmartgrid.pit.formatos_red import datos_f003
    from convertersmartgrid.pit.plantillas import celdas_de_formato
    resultado = celdas_de_formato(cargar_registro(NORMATIVA), 'F-003', datos_f003(_red(), FUENTE_RED))
    c = _celdas(resultado)
    assert c['F-003!L12']['valor'] == 0.4 and c['F-003!M12']['valor'] == pytest.approx(0.06)
    assert (c['F-003!N22']['valor'], c['F-003!P22']['valor'], c['F-003!O22']['valor']) == (9.0, 6.0, 12.0)
    assert c['F-003!T22']['valor'] == pytest.approx(24.0 / 30000 * 100)
    assert c['F-003!M33']['valor'] == 2.0 and c['F-003!M34']['valor'] is None
    assert 'capacitor' in c['F-003!M34']['traza']['motivo']
    assert any(h['bloque'] == 'compensacion' and h.get('columnas') for h in resultado['huecos'])


def test_bloque_con_mas_filas_que_la_plantilla_dice_cuantas_insertar():
    """107:RF-9 (T19b) — la plantilla trae 5 filas de ejemplo de líneas; con 8 líneas hay que insertar 3."""
    from convertersmartgrid.pit.formatos_red import datos_f002
    from convertersmartgrid.pit.plantillas import celdas_de_formato
    resultado = celdas_de_formato(cargar_registro(NORMATIVA), 'F-002', datos_f002(_red(6), FUENTE_RED))
    assert resultado['filas_a_insertar'] == {'lineas': 3}
    assert '!A17' in max((c['celda'] for c in resultado['celdas'] if c['campo'] == 'nombre'),
                         key=lambda x: int(x.split('A')[-1]))


def test_mapeo_que_no_coincide_con_la_plantilla_es_un_error(tmp_path):
    """107:RF-9 (T19b) — si la norma cambia un rótulo, no se llena la columna equivocada: el error lo nombra."""
    from convertersmartgrid.pit.formatos_red import datos_f002
    from convertersmartgrid.pit.plantillas import cargar_mapeo, celdas_de_formato
    mapeo = cargar_mapeo()
    mapeo['formatos']['F-002']['bloques'][0]['columnas'][6]['rotulo'] = [9, 'G', '(MW)']
    with pytest.raises(PitError, match='G9'):
        celdas_de_formato(cargar_registro(NORMATIVA), 'F-002', datos_f002(_red(), FUENTE_RED), mapeo=mapeo)


def test_sin_regla_de_niveles_no_se_clasifica_el_f001(tmp_path):
    """107:RF-9 (T19b) — sin la regla 12.1.1 no se supone qué es MAT o AT."""
    from convertersmartgrid.pit.formatos_red import datos_f001
    registro = _registro(tmp_path / 'reg', {'F-001 a F-003': 'General'}, ['F-001'])
    with pytest.raises(PitError, match='pit.niveles_tension_kv'):
        datos_f001(_red(), registro, FUENTE_RED)


# --------------------------------------------------------------------------- T27 (3a): series anuales del motor
_MAPEO_SERIES = {'esquema': 'pit_mapeo_formatos_v1', 'formatos': {
    'F-110': {'bloques': [{'bloque': 'barras', 'fila_marca': 13, 'marca': 'ELÉCTRICO 1',
                           'columnas': [{'letra': 'C', 'rotulo': [7, 'C', 'BARRA'], 'campo': 'barra'}],
                           'serie_columnas': {'fila_rotulo': 8, 'desde': 'E', 'rotulo_cero': 'AÑO / 0',
                                              'campo': 'potencia_mw'}}]},
    'F-119': {'bloques': [{'bloque': 'anios', 'fila_marca': 8, 'marca': '0', 'serie_filas': {'columna': 'A'},
                           'columnas': [{'letra': 'B', 'rotulo': [7, 'B', 'MAT'], 'campo': 'mat_gwh'}]}]}}}  # rótulo sin la llamada (1) (delta17)


def _registro_con_horizonte(tmp_path, anios):
    """El registro real con otro horizonte de demanda: la regla del horizonte se sustituye en una norma sintética
    posterior, que es la que manda por su vigencia."""
    carpeta = tmp_path / 'reg'
    carpeta.mkdir()
    for f in NORMATIVA.glob('*.json'):
        (carpeta / f.name).write_bytes(f.read_bytes())
    (carpeta / 'zz_horizonte.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT-HORIZONTE', 'titulo': 'Horizonte sintético', 'estado_juridico': 'vigente_comprobada',
         'sha256': 'f' * 64, 'vigencia_desde': '2099-01-01',
         'reglas': [_regla('pit.horizonte_demanda_anios', anios)]}]}), encoding='utf-8')
    return cargar_registro(carpeta)


@pytest.mark.parametrize('anios, ultima', ((30, 'AI'), (10, 'O')), ids=('norma_30', 'norma_10'))
def test_serie_en_columnas_sale_del_horizonte_de_la_norma(tmp_path, anios, ultima):
    """107:RF-9, 107:RF-11 (T27 3a) — una columna por año, del 0 al horizonte de la regla registrada, con el rótulo de
    cada año comprobado en la plantilla; ningún número de años en el código."""
    from convertersmartgrid.pit.plantillas import celdas_de_formato
    registro = _registro_con_horizonte(tmp_path, anios) if anios != 30 else cargar_registro(NORMATIVA)
    datos = {'fuente': FUENTE, 'bloques': {'barras': [{'barra': 'B1', 'potencia_mw': [float(i) for i in
                                                                                    range(anios + 1)]}]}}
    celdas = [c for c in celdas_de_formato(registro, 'F-110', datos, mapeo=_MAPEO_SERIES)['celdas']
              if c['campo'] == 'potencia_mw']
    assert len(celdas) == anios + 1
    assert celdas[0]['celda'] == 'F-110!E13' and celdas[-1]['celda'] == f'F-110!{ultima}13'
    assert celdas[-1]['valor'] == float(anios) and celdas[-1]['traza']['anio'] == anios


def test_serie_mas_larga_que_la_plantilla_es_un_error(tmp_path):
    """107:RF-9 (T27 3a) — si la norma pide más años que columnas tiene la plantilla, el error lo dice."""
    from convertersmartgrid.pit.plantillas import celdas_de_formato
    with pytest.raises(PitError, match='año 31'):
        celdas_de_formato(_registro_con_horizonte(tmp_path, 40), 'F-110',
                          {'fuente': FUENTE, 'bloques': {'barras': []}}, mapeo=_MAPEO_SERIES)


def test_serie_en_filas_comprueba_cada_anio(tmp_path):
    """107:RF-9 (T27 3a) — la serie en filas (F-119) lleva un año por fila del 0 al horizonte, comprobado en la
    plantilla; un año que falta en la fuente queda vacío con su motivo."""
    from convertersmartgrid.pit.plantillas import celdas_de_formato
    datos = {'fuente': FUENTE, 'bloques': {'anios': [{'mat_gwh': 1.5}, {'mat_gwh': 1.6}]}}
    resultado = celdas_de_formato(_registro_con_horizonte(tmp_path, 10), 'F-119', datos, mapeo=_MAPEO_SERIES)
    celdas = {c['celda']: c for c in resultado['celdas']}
    assert celdas['F-119!B8']['valor'] == 1.5 and celdas['F-119!B9']['valor'] == 1.6
