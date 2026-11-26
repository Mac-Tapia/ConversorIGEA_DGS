"""106:RF-25 — cada tanda de la suite nocturna espera a un entrenamiento con la GPU si falta memoria.

La noche del 23 al 24-11, la suite por tandas corrió pytest junto a las redes del 089 T7 con menos de 1,5 GiB libres y
la guardia de la cola de GPU cortó cinco entrenamientos. Sin suite real ni GPU: memoria, dueño y reloj son falsos.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.asistente import vigilancia


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))


def _esperar():
    f = getattr(vigilancia, 'esperar_recursos_de_tanda', None)
    assert f is not None, 'la suite no espera recursos antes de cada tanda'
    return f


class _Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def test_106_rf25_espera_mientras_otro_tiene_la_gpu_y_falta_memoria():
    reloj, memorias, avisos = _Reloj(), iter([1.2, 1.4, 2.0, 6.5]), []
    espera = _esperar()(memoria=lambda: next(memorias), dueno_gpu=lambda: 'PID 7 (pronostico-demanda)', minimo_gib=4.0,
                        plazo_s=3600, pausa_s=60, reloj=reloj, dormir=reloj.dormir, avisar=avisos.append)
    assert espera == 180
    assert any('PID 7' in a for a in avisos), 'no dice quién tiene la GPU'


@pytest.mark.parametrize('memoria, dueno', [(1.0, None), (8.0, 'PID 7 (x)')])
def test_106_rf25_sin_dueno_o_con_memoria_no_espera(memoria, dueno):
    reloj = _Reloj()
    assert _esperar()(memoria=lambda: memoria, dueno_gpu=lambda: dueno, minimo_gib=4.0, reloj=reloj,
                      dormir=reloj.dormir, avisar=lambda _m: None) == 0


def test_106_rf25_al_vencer_el_plazo_la_tanda_corre_igual_y_lo_dice():
    reloj, avisos = _Reloj(), []
    espera = _esperar()(memoria=lambda: 1.0, dueno_gpu=lambda: 'PID 7 (x)', minimo_gib=4.0, plazo_s=300, pausa_s=60,
                        reloj=reloj, dormir=reloj.dormir, avisar=avisos.append)
    assert espera >= 300 and 'vencido' in avisos[-1]


def test_106_rf25_correr_por_tandas_espera_antes_de_cada_tanda(tmp_path):
    orden = []

    def ejecutar(_repo, **k):
        orden.append(('tanda', k['argumentos'][-1]))
        return {'codigo': 0, 'resumen': '1 passed', 'segundos': 1, 'fallidas': [], 'omitidas': 0}

    vigilancia.correr_por_tandas(tmp_path, tandas=[['a'], ['b']], ejecutar=ejecutar,
                                 esperar=lambda: orden.append(('espera', None)) or 0)
    assert orden == [('espera', None), ('tanda', 'a'), ('espera', None), ('tanda', 'b')]


def test_106_rf25_la_herramienta_pasa_la_espera(monkeypatch):
    import signal

    from apoyo import cargar_herramienta
    herramienta = cargar_herramienta('suite_por_tandas.py', 'suite_por_tandas_106')
    # correr() instala sus manejadores de cierre; aquí no deben quedarse en el proceso de pytest.
    monkeypatch.setattr(signal, 'signal', lambda *_a, **_k: None)
    visto = {}

    def falso(_repo, **k):
        visto.update(k)
        return {'codigo': 0, 'resumen': 'ok'}

    monkeypatch.setattr(vigilancia, 'correr_por_tandas', falso)
    assert herramienta.correr() == 0
    assert visto.get('esperar') is getattr(vigilancia, 'esperar_recursos_de_tanda', object())


def test_106_rf16_la_suite_nocturna_no_hereda_los_almacenes_de_la_web(tmp_path):
    """106:RF-16 — la noche del 23 al 24-11, la suite lanzada por la web corría pytest con el runtime y los almacenes del
    usuario (las carpetas pytest-of-… estaban dentro del runtime real). Las salidas de la web no pasan a las tandas; los
    datos de prueba, sí."""
    vistos = []

    def ejecutar(_repo, **k):
        vistos.append(dict(k['env']))
        return {'codigo': 0, 'resumen': '1 passed', 'segundos': 1, 'fallidas': [], 'omitidas': 0}

    web = {'CSG_RUNTIME_HOME': 'D:/runtime_de_la_web', 'CSG_ASISTENTE_DATA': 'D:/web/_asistente',
           'CSG_TWIN_DATA': 'D:/web/_digital_twin', 'CSG_SUITE_DATOS': 'D:/sesion_ajena', 'CSG_RED': 'D:/datos/red.txt'}
    vigilancia.correr_por_tandas(tmp_path, tandas=[['a']], ejecutar=ejecutar, env=web)
    salidas = getattr(vigilancia, 'VARIABLES_DE_SALIDA_DE_LA_WEB', ())
    assert salidas, 'la suite no sabe qué variables son salidas de la web'
    assert not set(salidas) & set(vistos[0]), {k: vistos[0][k] for k in set(salidas) & set(vistos[0])}
    assert vistos[0]['CSG_RED'] == 'D:/datos/red.txt', 'los datos de prueba sí pasan'


def test_106_rf26_la_suite_nocturna_no_hereda_la_temporal_de_la_web(tmp_path):
    """106:RF-26 — la noche del 25-11 (23:24) la web había puesto TEMP, TMP y TMPDIR en <runtime>/tmp (configurar_entorno)
    y las tandas los heredaban: el mkdtemp de tests/conftest.py creaba la sesión dentro del runtime real y fallaron
    test_el_runtime_de_la_suite_es_de_la_sesion y tres pruebas de la web que pasan solas. La temporal vuelve a la del
    sistema; una TEMP que no es la de la web se respeta."""
    vistos = []

    def ejecutar(_repo, **k):
        vistos.append(dict(k['env']))
        return {'codigo': 0, 'resumen': '1 passed', 'segundos': 1, 'fallidas': [], 'omitidas': 0}

    web_tmp = 'D:/runtime_de_la_web/tmp'
    web = {'CSG_TEMP_HOME': web_tmp, 'TEMP': web_tmp, 'TMP': web_tmp + '/', 'TMPDIR': web_tmp,
           'LOCALAPPDATA': 'C:/Users/operador/AppData/Local', 'CSG_RED': 'D:/datos/red.txt'}
    vigilancia.correr_por_tandas(tmp_path, tandas=[['a']], ejecutar=ejecutar, env=web)
    visto = vistos[0]
    assert 'CSG_TEMP_HOME' not in visto
    for nombre in ('TEMP', 'TMP', 'TMPDIR'):
        assert not Path(visto.get(nombre, '')).as_posix().startswith('D:/runtime_de_la_web'), (nombre, visto.get(nombre))
    if os.name == 'nt':
        assert Path(visto['TEMP']).as_posix() == 'C:/Users/operador/AppData/Local/Temp'
    assert visto['CSG_RED'] == 'D:/datos/red.txt'

    vistos.clear()
    vigilancia.correr_por_tandas(tmp_path, tandas=[['a']], ejecutar=ejecutar, env={'TEMP': 'E:/mi_temporal'})
    assert vistos[0]['TEMP'] == 'E:/mi_temporal', 'una temporal que no es la de la web no se toca'

def test_106_rf21_ningun_lanzador_de_tools_toma_el_candado_sin_esperar():
    """106:RF-21 — el 24-11, la 070 T22 cayó en 19 s con «GPU ocupada» porque tools/asistente_entrenar.py tomaba el
    candado con BloqueoGPU, sin esperar su turno; otros tres lanzadores hacían lo mismo. Todos piden el turno con
    turno_gpu, que espera con plazo (CSG_GPU_ESPERA_S) y dice quién lo tiene."""
    import re
    from pathlib import Path
    tools = Path(__file__).resolve().parents[1] / 'tools'
    directos = [p.name for p in tools.rglob('*.py') if re.search(r'with\s+BloqueoGPU\(', p.read_text(encoding='utf-8'))]
    assert directos == [], f'toman el candado sin esperar su turno: {directos}'
