"""Spec 107 T19 (delta20, orden del auditor 28): las celdas sombreadas de los formatos de la Norma Tarifas (RCD
217-2013-OS/CD) «no deben ser llenadas» (F-302, nota (3)) y el motor de plantillas no las trata como hueco.

Las del motor usan la plantilla real del registro y mapeos sintéticos (el F-302 no está mapeado todavía; el F-101 lleva
en el total columnas que el mapeo real no tiene), con valores inventados para la prueba. Las del generador usan mapas y
filas sintéticos, sin las fuentes reales.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
FUENTE = {'nombre': 'fuente_sintetica.xlsx', 'huella': 'e' * 64}
#: recuento de celdas sombreadas por formato del apoyo (cc), frente «z6_cotejo_resto» (GRISES_217_resumen.txt).
RECUENTO_CC = {'F-101': 6, 'F-202': 18, 'F-203': 18, 'F-209': 20, 'F-302': 896, 'F-518': 8}
NOTA_F302 = '(3) Las celdas sombreadas no deben ser llenadas.'


def _modulo(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / 'tools' / 'normativa' / f'{nombre}.py')
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _celdas(resultado):
    return {c['celda']: c for c in resultado['celdas']}


def _avisos(resultado):
    return {a['celda']: a for a in resultado.get('avisos', [])}


def _f302(bloques):
    return {'esquema': 'pit_mapeo_formatos_v1', 'formatos': {'F-302': {'cabecera': [], 'bloques': bloques}}}


_SERVICIOS = {'bloque': 'servicios', 'fila_marca': 22, 'marca': 'Servicios Auxiliares',
              'columnas': [{'letra': 'B', 'rotulo': [9, 'B', 'TENSIÓN'], 'campo': 'tension'},
                           {'letra': 'H', 'rotulo': [10, 'H', 'Extranjera'], 'campo': 'sa_me'}]}
_ELEMENTOS = {'bloque': 'elementos', 'fila_marca': 14, 'marca': 'Celda de Línea',
              'columnas': [{'letra': 'D', 'rotulo': [10, 'D', 'Extranjera'], 'campo': 'basico_me'}]}


def _llenar(codigo, datos, mapeo):
    from convertersmartgrid.adaptadores.pit.plantillas import celdas_de_formato
    return celdas_de_formato(cargar_registro(NORMATIVA), codigo, {'fuente': FUENTE, **datos}, mapeo=mapeo)


def test_f302_sombreada_con_valor_no_se_escribe_y_avisa():
    """107:RF-9 (delta20) — F-302: un valor de la fuente para una celda sombreada (H22, servicios auxiliares en moneda
    extranjera) no se escribe y sale como aviso con el formato y la celda; no es un hueco. La B22, blanca, sí se
    escribe."""
    r = _llenar('F-302', {'bloques': {'servicios': [{'tension': '60 kV', 'sa_me': 100.0}]}}, _f302([_SERVICIOS]))
    celdas, avisos = _celdas(r), _avisos(r)
    assert celdas['F-302!B22']['valor'] == '60 kV'
    h22 = celdas['F-302!H22']
    assert h22['valor'] is None, 'una celda sombreada no se llena'
    assert h22.get('no_llenar') is True and 'motivo' not in h22['traza'], h22
    assert h22['traza'].get('no_llenar') == NOTA_F302
    assert set(avisos) == {'F-302!H22'}, avisos
    assert avisos['F-302!H22']['formato'] == 'F-302' and avisos['F-302!H22']['valor'] == 100.0


def test_f302_sombreada_vacia_no_es_hueco():
    """107:RF-9 (delta20) — F-302: una celda sombreada sin dato queda vacía a propósito, sin el motivo de hueco «la
    fuente no trae…» y sin aviso; la blanca sin dato sigue siendo un hueco con su motivo."""
    r = _llenar('F-302', {'bloques': {'servicios': [{'sa_me': None}]}}, _f302([_SERVICIOS]))
    celdas = _celdas(r)
    h22 = celdas['F-302!H22']
    assert h22['valor'] is None and 'motivo' not in h22['traza'], h22['traza']
    assert h22.get('no_llenar') is True
    assert 'la fuente no trae' in celdas['F-302!B22']['traza']['motivo']
    assert r.get('avisos') == []


def test_f302_sombreada_bajo_una_insercion_se_desplaza_como_las_demas():
    """107:RF-9 (delta20) — con 8 elementos (6 filas de ejemplo) se insertan 2 filas y los servicios auxiliares bajan
    de la 22 a la 24: la H24 es la H22 sombreada (no se escribe y avisa) y la B24 es la B22 blanca (se escribe),
    aunque en la plantilla la B24 sea sombreada."""
    datos = {'bloques': {'elementos': [{'basico_me': float(i)} for i in range(8)],
                         'servicios': [{'tension': '60 kV', 'sa_me': 100.0}]}}
    r = _llenar('F-302', datos, _f302([_ELEMENTOS, _SERVICIOS]))
    celdas, avisos = _celdas(r), _avisos(r)
    assert r['filas_a_insertar'] == {'elementos': 2}
    assert celdas['F-302!D21']['valor'] == 7.0, 'la fila insertada repite la última de ejemplo, que es blanca'
    assert celdas['F-302!B24']['valor'] == '60 kV' and not celdas['F-302!B24'].get('no_llenar')
    assert celdas['F-302!H24']['valor'] is None and celdas['F-302!H24'].get('no_llenar') is True
    assert set(avisos) == {'F-302!H24'} and avisos['F-302!H24']['celda_plantilla'] == 'H22', avisos


def _f101_con_fcp_y_fs_en_el_total():
    from convertersmartgrid.adaptadores.pit.plantillas import cargar_mapeo
    mapeo = copy.deepcopy(cargar_mapeo())
    grupo = mapeo['formatos']['F-101']['grupos'][0]
    grupo['total'] = [*grupo['total'], {'letra': 'F', 'campo': 'fcp'}, {'letra': 'G', 'campo': 'fs'}]
    return {'esquema': mapeo['esquema'], 'formatos': {'F-101': mapeo['formatos']['F-101']}}


def test_f101_fcp_y_fs_del_total_sistema_no_se_llenan():
    """107:RF-9 (delta20) — F-101: FCP y FS de «Total Sistema» (negras en el libro; nota (2): solo el FC) no se
    escriben aunque la fuente los traiga (aviso), y sin dato no son hueco. Un cuarto sistema, añadido tras los tres de
    la plantilla, repite el último y su total (fila 29) tampoco se llena."""
    fila = {'sistema': 'S', 'set': 'SET-1', 'barra': 'B1', 'tension_kv': 60.0, 'fc': 0.6, 'fcp': 0.8, 'fs': 0.9}
    miembros = [{'nombre': f'S{k}', 'filas': [dict(fila)], 'total': {'fc': 0.7, 'fcp': 0.9}} for k in range(4)]
    r = _llenar('F-101', {'grupos': {'sistemas': miembros}}, _f101_con_fcp_y_fs_en_el_total())
    celdas, avisos = _celdas(r), _avisos(r)
    assert r['grupos_a_insertar'] == {'sistemas': 1}
    for total in (8, 15, 22, 29):
        assert celdas[f'F-101!E{total}']['valor'] == 0.7
        for letra in 'FG':
            c = celdas[f'F-101!{letra}{total}']
            assert c['valor'] is None and c.get('no_llenar') is True and 'motivo' not in c['traza'], (letra, total, c)
    assert set(avisos) == {f'F-101!F{t}' for t in (8, 15, 22, 29)}, avisos
    assert celdas['F-101!F6']['valor'] == 0.8, 'el FCP de un devanado sí se llena'


def test_mapeo_real_del_f101_no_pone_nada_en_sus_sombreadas():
    """107:RF-9 (delta20) — el mapeo real del F-101 solo suma el FC en «Total Sistema»: ninguna columna de su total
    cae en una celda sombreada."""
    from convertersmartgrid.adaptadores.pit.plantillas import cargar_mapeo
    valor = cargar_registro(NORMATIVA).regla('pit.formato.F-101').regla.valor
    filas = (valor.get('no_llenar') or {}).get('filas') or {}
    grupo = cargar_mapeo()['formatos']['F-101']['grupos'][0]
    sombreadas_total = {letra for f in grupo['filas_total'] for letra in filas.get(str(f), [])}
    assert sombreadas_total == {'F', 'G'}, filas
    assert not sombreadas_total & {c['letra'] for c in grupo['total']}


def test_las_966_sombreadas_transcritas_con_el_recuento_de_cc():
    """107:RF-9 (delta20) — la transcripción de la 217-2013 lleva en cada formato sus celdas sombreadas
    («no_llenar»): 966, con el mismo recuento por formato que el apoyo (cc), todas vacías en la plantilla, con su
    motivo (en el F-302, su nota (3)) y su procedencia."""
    registro = cargar_registro(NORMATIVA)
    recuento = {}
    for regla in registro.norma('RCD 217-2013-OS/CD').reglas:
        if not regla.clave.startswith('pit.formato.'):
            continue
        valor = regla.valor
        nl = valor.get('no_llenar')
        assert isinstance(nl, dict) and nl.get('procedencia'), (regla.clave, 'sin no_llenar o sin su procedencia')
        con_texto = {(f['fila'], letra) for f in valor['filas'] for letra in f['celdas']}
        celdas = {(int(f), letra) for f, letras in nl['filas'].items() for letra in letras}
        assert not celdas & con_texto, (regla.clave, sorted(celdas & con_texto))
        assert nl['celdas'] == len(celdas)
        if celdas:
            recuento[valor['codigo']] = len(celdas)
            assert nl.get('motivo') and nl.get('relleno'), regla.clave
    assert recuento == RECUENTO_CC and sum(recuento.values()) == 966
    f302 = registro.regla('pit.formato.F-302').regla.valor['no_llenar']
    assert f302['motivo'] == NOTA_F302 and f302['nota'] == 'A112'
    assert registro.regla('pit.formato.F-101').regla.valor['no_llenar']['relleno'] == ['negro']


@pytest.mark.parametrize('con_valor', (True, False), ids=('con_valor', 'sin_valor'))
def test_las_966_sombreadas_quedan_vacias_y_sin_hueco_en_el_motor(con_valor):
    """107:RF-9 (delta20) — cada una de las 966 celdas sombreadas, pedida al motor como celda de cabecera, sale vacía,
    marcada «no_llenar» y sin motivo de hueco; con valor en la fuente da un aviso por celda, y sin valor ninguno."""
    registro = cargar_registro(NORMATIVA)
    total, avisos = 0, 0
    for codigo in RECUENTO_CC:
        valor = registro.regla(f'pit.formato.{codigo}').regla.valor
        filas = (valor.get('no_llenar') or {}).get('filas') or {}
        primera = valor['filas'][0]
        rotulo = [primera['fila'], *next((letra, t) for letra, t in primera['celdas'].items() if t == codigo)]
        cabecera = [{'celda': f'{letra}{f}', 'campo': f'{letra}{f}', 'rotulo': rotulo}
                    for f, letras in filas.items() for letra in letras]
        mapeo = {'esquema': 'pit_mapeo_formatos_v1', 'formatos': {codigo: {'cabecera': cabecera, 'bloques': []}}}
        datos = {'cabecera': {c['campo']: 1.0 for c in cabecera} if con_valor else {}}
        r = _llenar(codigo, datos, mapeo)
        for c in r['celdas']:
            assert c['valor'] is None and c.get('no_llenar') is True and 'motivo' not in c['traza'], c
        total += len(r['celdas'])
        avisos += len(r.get('avisos', []))
    assert total == 966
    assert avisos == (966 if con_valor else 0)


# --------------------------------------------------------------------------- generador: tools/normativa/sombreadas_217.py
_LITERALES = [{'fila': 1, 'celdas': {'A': 'OSINERGMIN', 'C': 'F-9'}},
              {'fila': 3, 'celdas': {'A': 'Rótulo', 'B': 'col'}},
              {'fila': 9, 'celdas': {'A': '(3) Las celdas sombreadas no deben ser llenadas.'}}]


def _entrada(celdas, libro='libro.xls', hoja='F-9', rgb=('(192, 192, 192)',)):
    return {'hoja': hoja, 'libro': libro, 'celdas_grises': list(celdas), 'rgb': list(rgb)}


def test_generador_no_llenar_por_fila_con_la_nota_del_formato():
    """107:RF-9, 107:RF-7 (delta20) — el generador da, por fila de la plantilla, las letras sombreadas (ordenadas como
    columnas), su número, la nota del formato que manda no llenarlas como motivo, el relleno y la procedencia; sin
    nota, el motivo general."""
    _modulo('fuentes')
    s = _modulo('sombreadas_217')
    nl = s.no_llenar('F-9', 'libro.xls', _LITERALES, _entrada(['AA4', 'B4', 'C5', 'B4']), 'procedencia X')
    assert nl == {'filas': {'4': ['B', 'AA'], '5': ['C']}, 'celdas': 3, 'procedencia': 'procedencia X',
                  'motivo': '(3) Las celdas sombreadas no deben ser llenadas.', 'nota': 'A9', 'relleno': ['gris 192']}
    sin_nota = s.no_llenar('F-9', 'libro.xls', _LITERALES[:2], _entrada(['B4'], rgb=('(0, 0, 0)',)), 'p')
    assert sin_nota.get('motivo') == 'celda sombreada en el libro oficial' and sin_nota.get('relleno') == ['negro']
    assert s.no_llenar('F-9', 'libro.xls', _LITERALES, _entrada([]), 'p') == {'filas': {}, 'celdas': 0,
                                                                                'procedencia': 'p'}


def test_generador_se_para_si_el_mapa_no_casa():
    """107:RF-7 (delta20) — una sombreada con texto en la transcripción, un mapa de otro libro o de otra hoja, una hoja
    sin entrada en el mapa o un mapa con otro sha256 paran el generador con su causa."""
    _modulo('fuentes')
    s = _modulo('sombreadas_217')
    with pytest.raises(SystemExit, match='B3'):
        s.no_llenar('F-9', 'libro.xls', _LITERALES, _entrada(['B3']), 'p')
    with pytest.raises(SystemExit, match='otro libro'):
        s.no_llenar('F-9', 'libro.xls', _LITERALES, _entrada(['B4'], libro='otro.xls'), 'p')
    with pytest.raises(SystemExit, match='otro libro'):
        s.no_llenar('F-9', 'libro.xls', _LITERALES, _entrada(['B4'], hoja='F-8'), 'p')
    with pytest.raises(SystemExit, match='no trae la hoja'):
        s.no_llenar('F-9', 'libro.xls', _LITERALES, None, 'p')


def test_generador_comprueba_el_sha_del_mapa(tmp_path):
    """107:RF-7 (delta20) — el mapa de celdas sombreadas se lee solo si su sha256 es el registrado."""
    _modulo('fuentes')
    s = _modulo('sombreadas_217')
    mapa = tmp_path / 'GRISES_217.json'
    mapa.write_text(json.dumps({'F-9': _entrada(['B4'])}), encoding='utf-8')
    with pytest.raises(SystemExit, match='FUENTE ALTERADA'):
        s.cargar_grises(mapa)
    assert s.cargar_grises(mapa, sys.modules['fuentes'].sha256(mapa)) == {'F-9': _entrada(['B4'])}



# ------------------------------------------------------- delta20 v2: F-101, colores y cotejo con el libro oficial (28)

#: los rellenos de color que no son gris, por formato (apoyo (cc), frente «z10_colores_217»).
COLORES_CC = {'F-305': 116, 'F-306': 20, 'F-401': 20, 'F-510': 8, 'F-522': 12}
NOTA_F101 = '(2) Para "Total Sistema" solo se consigna el valor del "FC" correspondiente'


def _formatos_217():
    datos = json.loads((NORMATIVA / 'rcd_217_2013_formatos.json').read_text(encoding='utf-8'))
    return {r['valor']['codigo']: r['valor'] for r in datos['reglas']}


def test_f101_lleva_como_motivo_el_literal_de_su_nota_2():
    """107:RF-9 (delta20 v2, orden de 28) — las celdas negras del F-101 (FCP y FS del «Total Sistema») llevan como
    motivo el literal de su nota (2), A25, y no el motivo general."""
    nl = _formatos_217()['F-101'].get('no_llenar') or {}
    assert (nl.get('motivo'), nl.get('nota')) == (NOTA_F101, 'A25')
    assert nl.get('celdas') == 6


def test_los_colores_son_observacion_sin_efecto_en_el_llenado():
    """107:RF-9 (delta20 v2, regla de 28) — los rellenos de color que no son gris (cabeceras de F-305, F-306, F-401,
    F-510 y F-522) se registran como observación, con su recuento, y NO son celdas que no se llenan: ninguna nota del
    formato ni de la norma lo dice."""
    formatos = _formatos_217()
    recuento = {c: (f.get('colores') or {}).get('celdas') for c, f in formatos.items() if f.get('colores')}
    assert recuento == COLORES_CC
    for codigo in COLORES_CC:
        colores = formatos[codigo]['colores']
        assert colores['efecto'].startswith('ninguno'), codigo
        de_color = {(fila, letra) for fila, letras in colores['filas'].items() for letra in letras}
        grises = {(fila, letra) for fila, letras in (formatos[codigo]['no_llenar'].get('filas') or {}).items()
                  for letra in letras}
        assert not de_color & grises, codigo


def test_generador_coteja_los_rellenos_del_libro_con_el_mapa_derivado():
    """107:RF-7 (delta20 v2) — el generador lee los rellenos del libro oficial con xlrd y los coteja con el mapa
    derivado: iguales pasan, y una celda gris o de color de más o de menos lo para."""
    sys.path.insert(0, str(RAIZ / 'tools' / 'normativa'))
    s = _modulo('sombreadas_217')
    leidos = {'F-9': {'celdas_grises': ['B4', 'C4'], 'colores': {'B2': '(204, 255, 204)'}}}
    grises = {'F-9': {'celdas_grises': ['C4', 'B4']}}
    colores = {'formatos': {'F-9': {'celdas_color': ['B2']}}}
    assert s.cotejar(leidos, grises, colores) is None
    with pytest.raises(s.MapaSombreadasError, match='sombreadas del libro oficial'):
        s.cotejar(leidos, {'F-9': {'celdas_grises': ['B4']}}, colores)
    with pytest.raises(s.MapaSombreadasError, match='de color del libro oficial'):
        s.cotejar(leidos, grises, {'formatos': {'F-9': {'celdas_color': []}}})


def test_colores_del_formato_por_fila():
    """107:RF-9 (delta20 v2) — la observación de colores agrupa sus celdas por fila de la plantilla, con sus rellenos
    y su efecto; un formato sin colores no la lleva."""
    sys.path.insert(0, str(RAIZ / 'tools' / 'normativa'))
    s = _modulo('sombreadas_217')
    obs = s.colores_del_formato({'colores': {'C6': '(204, 255, 204)', 'B6': '(204, 255, 204)', 'B7': '(255, 255, 153)'}})
    assert obs is not None, 'un formato con celdas de color lleva su observación'
    assert (obs.get('filas'), obs.get('celdas')) == ({'6': ['B', 'C'], '7': ['B']}, 3)
    assert obs.get('rellenos') == ['(204, 255, 204)', '(255, 255, 153)']
    assert str(obs.get('efecto', '')).startswith('ninguno')
    assert s.colores_del_formato({'colores': {}}) is None
