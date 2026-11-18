"""Guardas de la migración 002; las excepciones son deuda, no conformidad."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def herramienta():
    spec = importlib.util.spec_from_file_location('guarda_arquitectura', RAIZ / 'tools/arquitectura.py')
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def fuentes(raiz, contenido):
    for nombre, texto in contenido.items():
        archivo = raiz / (nombre.replace('.', '/') + '.py')
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(texto, encoding='utf-8')


def test_inventario_real_y_deuda_sin_deriva():
    """065:RF-16; 002:RF-2, 002:RF-3 — todos los módulos y VNR se analizan sin importarlos."""
    h = herramienta()
    informe = h.comprobar(RAIZ)
    assert len(informe.modulos) >= 150
    assert any(m.startswith('convertersmartgrid.adaptadores.entrada.vnr.') for m in informe.modulos)
    assert not informe.errores, '\n'.join(informe.errores)


@pytest.mark.parametrize('contenido,capas,esperado', [
    ({'p.puro': 'from p.web import servicio', 'p.web': 'servicio = 1'},
     {'p.puro': 'dominio', 'p.web': 'presentacion'}, 'capa|p.puro|p.web'),
    ({'p.a': 'from .b import valor', 'p.b': 'from .a import valor'},
     {'p.a': 'dominio', 'p.b': 'dominio'}, 'ciclo|p.a|p.b'),
    ({'p.a': 'from .b import _interno', 'p.b': '_interno = 1'},
     {'p.a': 'dominio', 'p.b': 'dominio'}, 'privado|p.a|p.b|_interno'),
    ({'p.a': 'from .b import __interno', 'p.b': '__interno = 1'},
     {'p.a': 'dominio', 'p.b': 'dominio'}, 'privado|p.a|p.b|__interno'),
    ({'p.a': 'import p.b as otro\nvalor = otro._interno', 'p.b': '_interno = 1'},
     {'p.a': 'dominio', 'p.b': 'dominio'}, 'privado|p.a|p.b|_interno'),
    ({'p.a': 'from . import b\nvalor = b._interno', 'p.b': '_interno = 1'},
     {'p.a': 'dominio', 'p.b': 'dominio'}, 'privado|p.a|p.b|_interno'),
    ({'p.a': 'from .b import *', 'p.b': 'valor = 1'},
     {'p.a': 'dominio', 'p.b': 'dominio'}, 'comodin|p.a|p.b'),
])
def test_violacion_deliberada_en_modulos_arbitrarios(tmp_path, contenido, capas, esperado):
    """065:RF-16; 002:RF-2, 002:RF-4, 002:RF-5 — el AST detecta violaciones nuevas reales."""
    h = herramienta()
    fuentes(tmp_path, contenido)
    assert esperado in h.analizar(tmp_path, capas).violaciones


def test_ciclo_nuevo_dentro_de_componente_preexistente(tmp_path):
    """065:RF-16; 002:RF-4 — permitir un ciclo no permite todas las aristas del componente."""
    h = herramienta()
    capas = dict.fromkeys(('p.a', 'p.b', 'p.c'), 'dominio')
    fuentes(tmp_path, {'p.a': 'import p.b', 'p.b': 'import p.c', 'p.c': 'import p.a'})
    anteriores = h.analizar(tmp_path, capas).violaciones
    fuentes(tmp_path, {'p.a': 'import p.b\nimport p.c'})
    actuales = h.analizar(tmp_path, capas).violaciones
    errores = h.comparar_deuda(actuales, {v: 'migración pendiente' for v in anteriores})
    assert any('ciclo|p.a|p.c' in e for e in errores)


def test_excepcion_retirada_debe_desaparecer():
    """065:RF-16 — una excepción resuelta falla hasta reducir la lista, nunca se recicla."""
    h = herramienta()
    assert 'retirada' in h.comparar_deuda(set(), {'ciclo|p.a|p.b': 'T3 pendiente'})[0]


def test_excepcion_sin_justificacion_no_puede_autorizar_deuda():
    """065:RF-16 — las excepciones requieren motivo y revisión explícita."""
    h = herramienta()
    assert h.comparar_deuda({'capa|p.a|p.b'}, {'capa|p.a|p.b': ''})


def test_modulo_nuevo_y_clasificacion_obsoleta_fallan(tmp_path):
    """065:RF-16; 002:RF-3 — ni un módulo nuevo ni una clasificación fantasma quedan ocultos."""
    h = herramienta()
    fuentes(tmp_path, {'p.nuevo': 'valor = 1'})
    informe = h.analizar(tmp_path, {'p.retirado': 'dominio'})
    assert 'sin_capa|p.nuevo' in informe.violaciones
    assert 'sin_modulo|p.retirado' in informe.violaciones


def test_importacion_relativa_y_dunder_publico_no_son_privados(tmp_path):
    """002:RF-5 — la versión pública y los imports del mismo módulo no son deuda privada."""
    h = herramienta()
    fuentes(tmp_path, {'p.a': 'from .b import __version__, publico',
                       'p.b': '__version__ = "1"\npublico = 1'})
    assert not h.analizar(tmp_path, dict.fromkeys(('p.a', 'p.b'), 'dominio')).violaciones


def test_importacion_absoluta_sin_alias_detecta_privado(tmp_path):
    """002:RF-5 — import p.b conserva el nombre completo al acceder al privado."""
    h = herramienta()
    fuentes(tmp_path, {'p.a': 'import p.b\nvalor = p.b._interno', 'p.b': '_interno = 1'})
    assert 'privado|p.a|p.b|_interno' in h.analizar(
        tmp_path, dict.fromkeys(('p.a', 'p.b'), 'dominio')).violaciones


@pytest.mark.parametrize('dependencia', ['fastapi', 'tkinter', 'powerfactory', 'pyodbc', 'pymssql'])
def test_dominio_no_importa_borde_ni_driver(tmp_path, dependencia):
    """002:RF-3; 065:RF-16 — el aislamiento también se aplica a dependencias externas."""
    h = herramienta()
    fuentes(tmp_path, {'p.puro': f'import {dependencia}'})
    assert f'dominio_externo|p.puro|{dependencia}' in h.analizar(
        tmp_path, {'p.puro': 'dominio'}).violaciones


def test_no_quedan_nombres_privados_entre_modulos():
    """002:RF-5 — T4: la lista de privados permitidos está vacía y no vuelve a crecer."""
    h = herramienta()
    informe = h.comprobar(RAIZ)
    assert not [v for v in informe.violaciones if v.startswith('privado|')]


def test_no_quedan_ciclos_entre_modulos():
    """002:RF-4 — T3: la lista de ciclos permitidos está vacía y no vuelve a crecer."""
    h = herramienta()
    informe = h.comprobar(RAIZ)
    assert not [v for v in informe.violaciones if v.startswith('ciclo|')]


def test_002_rf1_cada_modulo_vive_en_el_paquete_de_su_capa():
    """002:RF-1 — cada módulo de la tabla de capas está bajo ``convertersmartgrid.<su capa>``, y su fichero existe.

    002:RF-6: el paquete VNR-GIS entra entero como adaptador de entrada; dentro de él, su CLI, su web y sus reglas
    conservan la capa que declaran, sin salir de ``adaptadores``."""
    import tomllib

    tabla = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['convertersmartgrid']['capas']['modulos']
    vnr = 'convertersmartgrid.adaptadores.entrada.vnr'
    fuera = [m for m, c in tabla.items() if m.startswith('convertersmartgrid.') and m.split('.')[1] != c
             and not (m == vnr or m.startswith(vnr + '.'))]
    assert not fuera, fuera
    src = RAIZ / 'src'
    sin_fichero = [m for m in tabla if m.startswith('convertersmartgrid.') and not (
        (src / Path(*m.split('.'))).with_suffix('.py').is_file() or (src / Path(*m.split('.')) / '__init__.py').is_file())]
    assert not sin_fichero, sin_fichero


def test_002_rf21_las_rutas_de_antes_se_leen_con_las_de_hoy():
    """002:RF-21 — los conjuntos sellados no se reescriben: sus rutas viejas se traducen al leerlas."""
    from convertersmartgrid.aplicacion.asistente.rutas_historicas import ruta_vigente

    assert ruta_vigente('src/convertersmartgrid/web/app.py:343') == 'src/convertersmartgrid/presentacion/web/app.py:343'
    assert ruta_vigente('docs/otra.md') == 'docs/otra.md'
