"""107 T3 y PIT-ANON-ELEMENTOS — los elementos de las modificaciones del PIT sin nombres en claro: el registro guarda
sus huellas, el PIT casa por huella con la red del usuario y la lista local, fuera de git, pone los nombres (107:RF-7,
107:RF-11; la forma de 076:RF-6 con la sal de 086:RF-33).

Nombres sintéticos en las pruebas; el registro real solo se lee para comprobar que no lleva ningún nombre.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest
from convertersmartgrid.pit import PitError
from convertersmartgrid.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
#: Los ficheros del registro con elementos de las modificaciones del PIT.
CON_ELEMENTOS = ('rcd_186_189_2026.json', 'rcd_199_2026.json')
R199 = 'RCD 199-2026-OS/CD'


def _dominio():
    """La huella de un solo cuerpo: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.dominio.huellas_terminos') is not None,         'falta convertersmartgrid.dominio.huellas_terminos (PIT-ANON-ELEMENTOS)'
    return importlib.import_module('convertersmartgrid.dominio.huellas_terminos')


def huella(texto):
    return _dominio().huella(texto)


def normalizar(texto):
    return _dominio().normalizar(texto)


def _modulo():
    """El módulo de la pieza: su ausencia es la falla de la aserción, no un error de importación."""
    assert importlib.util.find_spec('convertersmartgrid.pit.elementos_modificacion') is not None, \
        'falta convertersmartgrid.pit.elementos_modificacion (PIT-ANON-ELEMENTOS)'
    return importlib.import_module('convertersmartgrid.pit.elementos_modificacion')


def _huellas_del_fichero(datos):
    """Todas las huellas de nombre que guarda un fichero del registro."""
    salida = set()

    def recorrer(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k.endswith('_huella') and isinstance(v, str):
                    salida.add(v)
                elif k.endswith('_huella') and isinstance(v, list):
                    salida.update(v)
                else:
                    recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)
    recorrer(datos)
    return salida


def _trozos(texto, largo=7):
    palabras = normalizar(texto).split()
    for i in range(len(palabras)):
        for n in range(1, largo + 1):
            if i + n <= len(palabras):
                yield ' '.join(palabras[i:i + n])


def test_107_t3_la_199_trae_los_cuadros_6_4_a_6_7_y_la_correccion_del_it_655():
    """107:RF-7 (107 T3) — la 199-2026 trae los elementos del Área 9 del IT 655-2026-GRT, con su huella de fichero:
    2 que se agregan, 18 que se reprograman, 7 que se eliminan y 1 de baja; y la corrección del módulo de la línea de
    138 kV de la §6.5, de doble a simple terna."""
    _modulo()
    registro = cargar_registro(NORMATIVA)
    elementos = {v.norma.acto: v.regla for v in registro.reglas_vigentes('pit.modificacion_2025_2029.elementos',
                                                                          '2026-11-16')}
    assert R199 in elementos, 'la 199-2026 no trae la regla de sus elementos'
    valor = elementos[R199].valor
    assert valor['area'] == 9 and valor['informe'] == 'IT 655-2026-GRT' and valor['informe_sha256'].startswith('aec882cf')
    assert {c: len(f) for c, f in valor['cuadros'].items()} == {'6.4 agregan': 2, '6.5 reprograman': 18,
                                                                '6.6 eliminan': 7, '6.7 baja': 1}
    assert elementos[R199].citada and 'Área de Demanda 9' in elementos[R199].cita_literal
    correccion = registro.regla('pit.modificacion_2025_2029.correccion_error_material', '2026-11-16').regla
    assert correccion.valor['modulo_registrado'] == 'LT-138COR0PMD0C5240A'
    assert correccion.valor['modulo_correcto'] == 'LT-138COR0PMS0C5240A' and 'simple terna' in correccion.cita_literal


@pytest.mark.parametrize('fichero', CON_ELEMENTOS)
def test_107_rf11_ningun_nombre_en_claro_en_el_registro_publico(fichero):
    """107:RF-11 (PIT-ANON-ELEMENTOS, comprobación permanente) — ningún elemento trae titular ni instalación en claro, y
    ningún trozo del fichero (de una a siete palabras) da una huella de nombre que el registro guarda: el nombre no
    aparece en ninguna nota, cita ni descripción. Con la lista local de quien la tiene, tampoco sus nombres."""
    _modulo()
    datos = json.loads((NORMATIVA / fichero).read_text(encoding='utf-8'))
    texto = json.dumps(datos, ensure_ascii=False)
    assert '"titular":' not in texto and '"instalacion":' not in texto, 'un elemento trae el nombre en claro'
    huellas = _huellas_del_fichero(datos)
    assert huellas, 'el fichero no guarda las huellas de sus nombres'
    sin_claves = re.sub(r'"[0-9a-f]{16}"|\[[0-9a-f]{16}\]', ' ', texto)
    en_claro = sorted({t for t in _trozos(sin_claves) if huella(t) in huellas})
    assert not en_claro, f'{fichero}: {len(en_claro)} nombres en claro con su huella en el registro'
    local = os.environ.get('CSG_NORMATIVA_ELEMENTOS')
    if local and Path(local).is_dir():
        nombres = _modulo().leer_lista_local(local)
        assert not [h for h in nombres if any(huella(t) == h for t in _trozos(sin_claves))]


def test_107_rf11_la_huella_tiene_un_solo_cuerpo_para_la_entrega_y_el_producto():
    """107:RF-11 (PIT-ANON-ELEMENTOS) — la herramienta de la entrega y el registro calculan la huella con la misma
    función: un nombre del registro se busca igual en la comprobación de la entrega."""
    sys.path.insert(0, str(RAIZ / 'tools'))
    try:
        import comprobar_entrega
    finally:
        sys.path.remove(str(RAIZ / 'tools'))
    dominio = _dominio()
    assert comprobar_entrega.huella is dominio.huella and comprobar_entrega.normalizar is dominio.normalizar


def _registro_sintetico(tmp_path, elementos):
    carpeta = tmp_path / 'reg'
    carpeta.mkdir()
    (carpeta / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'SINT-MODIF', 'titulo': 'Modificación sintética', 'estado_juridico': 'vigente_comprobada',
        'sha256': 'd' * 64, 'vigencia_desde': '2041-01-01', 'reglas': [{
            'clave': 'pit.modificacion_2025_2029.elementos', 'pagina': '1', 'cita_literal': '«cuadros sintéticos»',
            'valor': {'area': 99, 'informe': 'IT sintético', 'cuadros': {'6.4 agregan': elementos}}}]}]}),
        encoding='utf-8')
    return cargar_registro(carpeta)


def _fila_base():
    return {'anio': '2042', 'titular_huella': huella('Titular Sintético SAC'), 'elemento': 'Celda de Línea 33kV a {1}',
        'referencias_huella': [huella('Barra Lejana')], 'instalacion_tipo': 'SET',
        'instalacion_huella': huella('SET Norte Sintética')}


def test_107_rf11_casado_por_huella_con_y_sin_lista_local(tmp_path):
    """107:RF-11 (PIT-ANON-ELEMENTOS) — sin lista local, la SET de la red del usuario (con o sin «SET», en mayúsculas o
    no) y su titular casan por huella y se muestra «elemento <huella>»; con la lista local, los nombres y la
    descripción con sus referencias."""
    mod = _modulo()
    FILA = _fila_base()
    registro = _registro_sintetico(tmp_path, [FILA, {**FILA, 'instalacion_huella': huella('SET Otra')}])
    sin = mod.elementos_de_las_modificaciones(registro, '2041-06-01', sets=['NORTE SINTÉTICA'],
                                              titulares=['titular sintetico sac'], lista={})
    assert [e['en_la_red'] for e in sin] == [True, False] and all(e['del_titular'] for e in sin)
    assert sin[0]['instalacion'] == f'elemento {FILA["instalacion_huella"]}'
    assert sin[0]['elemento'] == f'Celda de Línea 33kV a elemento {huella("Barra Lejana")}'
    lista = tmp_path / 'lista'
    lista.mkdir()
    (lista / 'a.json').write_text(json.dumps({'esquema': mod.ESQUEMA_LISTA, 'nombres': [
        'SET Norte Sintética', 'Titular Sintético SAC', 'Barra Lejana']}), encoding='utf-8')
    con = mod.elementos_de_las_modificaciones(registro, '2041-06-01', sets=['SET Norte Sintética'],
                                              lista=mod.leer_lista_local(lista))
    assert con[0]['instalacion'] == 'SET Norte Sintética' and con[0]['titular'] == 'Titular Sintético SAC'
    assert con[0]['elemento'] == 'Celda de Línea 33kV a Barra Lejana' and con[1]['instalacion'].startswith('elemento ')


def test_107_rf11_lista_local_mal_escrita_o_nombre_en_claro_en_el_registro_se_rechazan(tmp_path, monkeypatch):
    """107:RF-11 (PIT-ANON-ELEMENTOS) — una lista local sin su forma se rechaza con su nombre; un elemento del registro
    con el nombre en claro también; y la carpeta de la lista sale de CSG_NORMATIVA_ELEMENTOS."""
    mod = _modulo()
    (tmp_path / 'mala.json').write_text('{"nombres": "no es una lista"}', encoding='utf-8')
    with pytest.raises(PitError, match='mala.json'):
        mod.leer_lista_local(tmp_path)
    monkeypatch.setenv(mod.VARIABLE_LISTA, str(tmp_path / 'otra'))
    assert mod.carpeta_lista_local() == tmp_path / 'otra' and mod.leer_lista_local() == {}
    registro = _registro_sintetico(tmp_path, [{**_fila_base(), 'titular': 'Nombre En Claro'}])
    with pytest.raises(PitError, match='en claro'):
        mod.elementos_de_las_modificaciones(registro, '2041-06-01', lista={})


def test_107_rf11_las_salidas_del_pit_sin_lista_local_no_llevan_ningun_nombre():
    """107:RF-11 (PIT-ANON-ELEMENTOS) — con el registro real y sin lista local, cada titular e instalación que da el PIT
    es «elemento <huella>» y ninguna descripción da la huella de un nombre del registro."""
    mod = _modulo()
    registro = cargar_registro(NORMATIVA)
    salida = mod.elementos_de_las_modificaciones(registro, '2026-11-16', lista={})
    assert len(salida) >= 28 + 1, 'faltan los elementos de las modificaciones vigentes'
    huellas = set().union(*(_huellas_del_fichero(json.loads((NORMATIVA / f).read_text(encoding='utf-8')))
                            for f in CON_ELEMENTOS))
    for e in salida:
        for campo in ('titular', 'instalacion'):
            assert e[campo] is None or e[campo].startswith('elemento '), (campo, e['acto'])
        assert not [t for t in _trozos(re.sub(r'elemento [0-9a-f]{16}', ' ', e['elemento'])) if huella(t) in huellas]
