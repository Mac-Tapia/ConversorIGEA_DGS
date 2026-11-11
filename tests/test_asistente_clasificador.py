"""Spec 026, T7: informes desde la consola y su clasificación en dos niveles."""
from __future__ import annotations

import os

import pytest

torch = pytest.importorskip('torch')

from convertersmartgrid.asistente import almacen
from convertersmartgrid.asistente import clasificador as cl
from convertersmartgrid.asistente.ejecutor import pasos
from convertersmartgrid.asistente.sinteticos import SUBTIPOS_ESTUDIO
from convertersmartgrid.asistente.tareas import TAREAS
from convertersmartgrid.asistente.transformer import Configuracion


@pytest.fixture(scope='module')
def entrenado(tmp_path_factory):
    raiz = tmp_path_factory.mktemp('asistente_inf')
    os.environ['CSG_ASISTENTE_DATA'] = str(raiz)
    try:
        yield raiz, cl.entrenar_y_promover(cfg=Configuracion(epocas=8), minimo_subtipo=0.8)
    finally:
        os.environ.pop('CSG_ASISTENTE_DATA', None)


def test_los_dos_informes_desde_la_consola():
    """026:RF-13 — los informes de estudio y de factibilidad son tareas de la consola y van por
    sus rutas de la web, con el formulario guardado en 4.4."""
    assert {'informe_estudio', 'informe_factibilidad'} <= set(TAREAS)
    p = pasos('informe_factibilidad', {'proyecto': 'P', 'alimentadores': ['A1'], 'sed': 'SE1'},
              {'formulario': {'lugar': 'Ica', 'solicitud': {'potencia_kw': 500}}})
    assert p[0].ruta == '/informes/factibilidad'
    assert p[0].cuerpo == {'lugar': 'Ica', 'solicitud': {'potencia_kw': 500}, 'project': 'P', 'alimentador': 'A1',
                           'sed': 'SE1'}
    assert pasos('informe_estudio', {'proyecto': 'P', 'alimentadores': ['A1']}, {})[0].ruta == '/informes/estudio'


def test_clasifica_tipo_y_subtipo(entrenado, monkeypatch):
    """026:RF-14 — clasifica un pedido o un informe en su tipo y su subtipo de estudio."""
    raiz, r = entrenado
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    assert r['promovido'] and r['acierto_subtipo'] >= 0.8, r
    c = cl.cargar()
    x = c.clasificar('informe de factibilidad: solicitud de suministro para 800 kW en el fundo Santa Rosa')
    assert x['tipo'] == 'factibilidad' and x['subtipo'] == 'alimentación de carga nueva'
    assert c.clasificar('migración del alimentador XY123 de 10 kV a 22,9 kV')['subtipo'] == 'migración de tensión'


def test_aprende_de_las_correcciones(entrenado, monkeypatch):
    """026:RF-15 — cada corrección queda como ejemplo y entra al siguiente entrenamiento."""
    raiz, _ = entrenado
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(raiz))
    for i in range(5):
        cl.registrar(f'estudio de coordinación de protecciones número {i}', 'estudio', 'mejora de tensión', 'corregido')
    ent, prueba = cl.reales()
    assert len(ent) + len(prueba) == 5 and len(prueba) == 1
    assert almacen.leer('informes')[-1]['origen'] == 'corregido'


def test_subtipos_del_perfil(monkeypatch):
    """026:RF-16 — dos niveles; los subtipos salen del perfil y, sin él, de la spec."""
    import convertersmartgrid.perfil_empresa as pe

    monkeypatch.setattr(pe, 'datos_perfil', lambda: {'asistente': {'subtipos_estudio': ['a', 'b']}})
    assert cl.subtipos_del_perfil() == ['a', 'b']
    monkeypatch.setattr(pe, 'datos_perfil', lambda: {})
    assert cl.subtipos_del_perfil() == list(SUBTIPOS_ESTUDIO) and cl.TIPOS_INFORME == ('estudio', 'factibilidad')
    datos = cl.generar(['otro subtipo'], por_subtipo=3)
    assert all(s == 'otro subtipo' for _, _, s in datos)


def test_026_rf33_reales_por_grupo_y_estratificados(tmp_path, monkeypatch):
    """026:RF-33 — las versiones de un informe no se reparten; cada subtipo con dos o más grupos tiene uno en prueba."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    for v in range(4):
        cl.registrar(f'version {v} del estudio de caida de tension de AB101', 'estudio', 'mejora de tensión', 'generado',
                     grupo='AB101')
    for g in ('CD202', 'EF303'):
        cl.registrar(f'estudio de caida de tension de {g}', 'estudio', 'mejora de tensión', 'generado', grupo=g)
    for g in ('GH404', 'IJ505'):
        cl.registrar(f'factibilidad de suministro en {g}', 'factibilidad', 'alimentación de carga nueva', 'maestro', grupo=g)
    ent, prueba = cl.reales()
    lados = {('AB101' in t) for t, _tp, _s in prueba}
    assert not ({t for t, *_ in ent if 'AB101' in t} and {t for t, *_ in prueba if 'AB101' in t}), lados
    assert {tp for _t, tp, _s in prueba} == {'estudio', 'factibilidad'}
    assert len(ent) + len(prueba) == 8 and cl.reales() == (ent, prueba)


def test_026_rf34_informes_desde_un_manifiesto(tmp_path, monkeypatch):
    """026:RF-34 — anota con su grupo, no repite y dice lo que no pudo anotar."""
    import importlib.util
    from pathlib import Path

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    ruta = Path(__file__).resolve().parents[1] / 'tools/asistente_informes_reales.py'
    spec = importlib.util.spec_from_file_location('asistente_informes_reales', ruta)
    herramienta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(herramienta)
    filas = [{'texto': 'ASUNTO : transferencia de carga entre AB101 y CD202', 'tipo': 'estudio', 'subtipo': 'transferencia',
              'grupo': 'g1'},
             {'texto': 'ASUNTO :  transferencia de carga  entre AB101 y CD202', 'tipo': 'estudio', 'subtipo': 'transferencia',
              'grupo': 'g1'},
             {'texto': 'sin grupo', 'tipo': 'estudio', 'subtipo': 'transferencia'}]
    r = herramienta.registrar_manifiesto(filas, 'maestro')
    assert len(r['anotados']) == 1 and len(r['repetidos']) == 1 and len(r['errores']) == 1
    fila = almacen.leer('informes')[-1]
    assert fila['grupo'] == 'g1' and fila['origen'] == 'maestro'
