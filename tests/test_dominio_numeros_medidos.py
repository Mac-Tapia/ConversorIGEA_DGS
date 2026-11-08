"""002:RF-1/2/3/21: U1 extrae únicamente números puros y elimina tres dependencias."""
from __future__ import annotations

import ast
from datetime import date, datetime, time
from decimal import Decimal
import importlib
import json
from pathlib import Path
import pickle
import subprocess
import sys

import pytest

from convertersmartgrid import demanda_medida as dm

RAIZ = Path(__file__).resolve().parents[1]
ARISTAS = {
    'capa|convertersmartgrid.ajuste_cabecera|convertersmartgrid.demanda_medida',
    'capa|convertersmartgrid.perfil_empresa|convertersmartgrid.powerfactory_env',
    'capa|convertersmartgrid.reglas|convertersmartgrid.powerfactory_env',
}


def test_u1_architectura_sin_las_tres_dependencias_historicas():
    """002:RF-2/3: la guarda real debe medir dependencias retiradas, sin dispensarlas."""
    from test_capas import herramienta

    informe = herramienta().comprobar(RAIZ)
    assert not (ARISTAS & informe.violaciones)
    assert not informe.errores, informe.errores


def test_helpers_unicos_con_api_anterior_y_pickle_conservados():
    """002:RF-1/21: un solo cuerpo canónico; los dos consumidores comparten objeto."""
    from convertersmartgrid import ajuste_cabecera

    puros = importlib.import_module('convertersmartgrid.dominio.numeros_medidos')
    for nombre in ('clave_codigo', 'numero'):
        fn = getattr(puros, nombre)
        assert fn is getattr(dm, nombre) is getattr(ajuste_cabecera, nombre)
        assert fn.__module__ == puros.__name__
        assert pickle.loads(pickle.dumps(fn)) is fn
        antiguo = ('cconvertersmartgrid.demanda_medida\n' + nombre + '\n.').encode('ascii')
        assert pickle.loads(antiguo) is fn
    arbol = ast.parse(Path(dm.__file__).read_text(encoding='utf-8'))
    assert not any(isinstance(n, ast.FunctionDef) and n.name in ('clave_codigo', 'numero')
                   for n in arbol.body)


def test_importar_numeros_puros_no_arrastra_adaptadores_ni_librerias_externas():
    """002:RF-3: proceso sin site-packages, sin importar medición/PF para normalizar."""
    codigo = '''
import sys
sys.path.insert(0, sys.argv[1])
from convertersmartgrid.dominio.numeros_medidos import clave_codigo, numero
assert clave_codigo(' 001234 ') == '1234' and numero('1,5') == 1.5
prohibidos = ('convertersmartgrid.demanda_medida', 'convertersmartgrid.powerfactory_env',
              'openpyxl', 'pandas', 'powerfactory')
assert not any(m in sys.modules for m in prohibidos)
'''
    r = subprocess.run([sys.executable, '-B', '-S', '-c', codigo, str(RAIZ / 'src')],
                       capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stdout + r.stderr


def test_configuracion_no_importa_powerfactory_y_conserva_alias_publico():
    """002:RF-3: las raíces canónicas no pasan por un adaptador del motor nativo."""
    from convertersmartgrid import perfil_empresa, reglas, runtime_paths

    assert reglas.project_root is runtime_paths.raiz_programa
    for modulo in (perfil_empresa, reglas):
        tree = ast.parse(Path(modulo.__file__).read_text(encoding='utf-8'))
        assert not any(isinstance(n, ast.ImportFrom) and n.module == 'powerfactory_env'
                       for n in ast.walk(tree))


@pytest.mark.parametrize('valor,esperado', [
    (None, ''), (True, ''), (False, ''), (1234.0, '1234'), (' 001234 ', '1234'),
    ('X-AB_12', 'xab12'), (float('nan'), ''), (float('inf'), ''), (-0.0, '0'),
    ('Straße-02', 'strasse02'), ('ÑÁ-01', 'ñá01'), (Decimal('1234.0'), '12340'),
    (date(2024, 2, 29), '20240229'), (datetime(2026, 11, 8, 9, 30, 15), '2026110809:30:15'),
    (time(23, 59), '23:59:00'),
])
def test_clave_codigo_conserva_contrato_de_los_libros(valor, esperado):
    """004:RF-31; 002:RF-1: identificadores, fechas y bools conservan su semántica."""
    assert dm.clave_codigo(valor) == esperado


@pytest.mark.parametrize('valor,esperado', [
    (None, None), (True, None), (False, None), (float('nan'), None),
    (float('inf'), None), (-float('inf'), None), (0, 0.0), (-2, -2.0),
    (' 1,5 ', 1.5), ('1.234,56', None), ('1e309', None), ('-1e309', None),
    ('NaN', None), ('INF', None), ('1_000', 1000.0), ('+2.5e2', 250.0),
    (Decimal('2.5'), 2.5), (date(2024, 2, 29), None), (time(23, 59), None),
])
def test_numero_finito_conserva_su_contrato(valor, esperado):
    """004:RF-31; 002:RF-1: el traslado no cambia la política decimal o de finitud."""
    assert dm.numero(valor) == esperado


@pytest.mark.parametrize('instalado', [False, True])
def test_configuracion_conserva_programa_datos_y_empresas(tmp_path, monkeypatch, instalado):
    """002:RF-31/35; 086:RF-36/38: configuraciones de lectura y datos locales separados."""
    from convertersmartgrid import perfil_empresa as pe, reglas, runtime_paths as rp

    paquete = (tmp_path / 'site' / 'convertersmartgrid' if instalado
               else tmp_path / 'repo' / 'src' / 'convertersmartgrid')
    programa = paquete / '_programa' if instalado else tmp_path / 'repo'
    datos = tmp_path / 'datos' if instalado else programa
    perfiles = programa / 'config' / 'perfiles'
    perfiles.mkdir(parents=True)
    activo = datos / 'config' / 'perfil_empresa.json'
    activo.parent.mkdir(parents=True, exist_ok=True)
    (perfiles / 'empresa_a.json').write_text(json.dumps({'crs_origen': 'EPSG:3857'}), encoding='utf-8')
    (perfiles / 'empresa_b.json').write_text(json.dumps({'crs_origen': 'EPSG:4326'}), encoding='utf-8')
    activo.write_text(json.dumps({'perfil': 'empresa_a', 'escala_diagrama': 1.25}), encoding='utf-8')
    monkeypatch.setattr(rp, '__file__', str(paquete / 'runtime_paths.py'))
    monkeypatch.setenv(rp.VARIABLE_DATOS, str(datos))
    monkeypatch.delenv(pe.VARIABLE_RUTA, raising=False)
    assert pe._raiz() == reglas.project_root() == programa
    assert pe.carpeta_perfiles() == perfiles and pe.ruta_perfil_activo() == activo
    assert pe.perfiles_disponibles() == ['empresa_a', 'empresa_b']
    assert pe.cargar_perfil().crs_origen == 'EPSG:3857'
    assert pe.cargar_perfil().escala_diagrama == 1.25
    alterno = datos / 'config' / 'otro.json'
    monkeypatch.setenv(pe.VARIABLE_RUTA, str(alterno))
    assert pe.ruta_perfil_activo() == alterno
