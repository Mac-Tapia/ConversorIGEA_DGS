"""Spec 026, T7: informes desde la consola y su clasificación en dos niveles."""
from __future__ import annotations

import os

import pytest

torch = pytest.importorskip('torch')

from igea_dgs.asistente import almacen
from igea_dgs.asistente import clasificador as cl
from igea_dgs.asistente.ejecutor import pasos
from igea_dgs.asistente.sinteticos import SUBTIPOS_ESTUDIO
from igea_dgs.asistente.tareas import TAREAS
from igea_dgs.asistente.transformer import Configuracion


@pytest.fixture(scope='module')
def entrenado(tmp_path_factory):
    raiz = tmp_path_factory.mktemp('asistente_inf')
    os.environ['IGEA_ASISTENTE_DATA'] = str(raiz)
    try:
        yield raiz, cl.entrenar_y_promover(cfg=Configuracion(epocas=8), minimo_subtipo=0.8)
    finally:
        os.environ.pop('IGEA_ASISTENTE_DATA', None)


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
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    assert r['promovido'] and r['acierto_subtipo'] >= 0.8, r
    c = cl.cargar()
    x = c.clasificar('informe de factibilidad: solicitud de suministro para 800 kW en el fundo Santa Rosa')
    assert x['tipo'] == 'factibilidad' and x['subtipo'] == 'alimentación de carga nueva'
    assert c.clasificar('migración del alimentador XY123 de 10 kV a 22,9 kV')['subtipo'] == 'migración de tensión'


def test_aprende_de_las_correcciones(entrenado, monkeypatch):
    """026:RF-15 — cada corrección queda como ejemplo y entra al siguiente entrenamiento."""
    raiz, _ = entrenado
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    for i in range(5):
        cl.registrar(f'estudio de coordinación de protecciones número {i}', 'estudio', 'mejora de tensión', 'corregido')
    ent, prueba = cl.reales()
    assert len(ent) + len(prueba) == 5 and len(prueba) == 1
    assert almacen.leer('informes')[-1]['origen'] == 'corregido'


def test_subtipos_del_perfil(monkeypatch):
    """026:RF-16 — dos niveles; los subtipos salen del perfil y, sin él, de la spec."""
    import igea_dgs.perfil_empresa as pe

    monkeypatch.setattr(pe, 'datos_perfil', lambda: {'asistente': {'subtipos_estudio': ['a', 'b']}})
    assert cl.subtipos_del_perfil() == ['a', 'b']
    monkeypatch.setattr(pe, 'datos_perfil', lambda: {})
    assert cl.subtipos_del_perfil() == list(SUBTIPOS_ESTUDIO) and cl.TIPOS_INFORME == ('estudio', 'factibilidad')
    datos = cl.generar(['otro subtipo'], por_subtipo=3)
    assert all(s == 'otro subtipo' for _, _, s in datos)
