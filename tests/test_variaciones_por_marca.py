"""086:RF-87, 086:RF-88 — las variaciones y los casos del conversor se reconocen por su marca, no por el nombre del proyecto.

Copia PRUEBA064_184942 de PA217 (2026-11-12): la calibración creó ``Fichas_PRUEBA064_184942`` junto a la
``Fichas_<original>`` que traía la copia, y «Cargas nuevas» se quedó con la fuente a 1,025 p.u. tras recalibrar a 1,0278.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from apoyo import cargar_herramienta


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'variaciones_por_marca_guion', tools_en_path=True)


@pytest.fixture(scope='module')
def casos():
    return cargar_herramienta('casos_pf.py', 'variaciones_por_marca_casos', tools_en_path=True)


def _variacion(nombre, *, marca=None, etapa=None):
    """Una variación de DIgSILENT: con la marca del conversor en ``desc`` y/o con la etapa que crea el conversor."""
    etapas = [SimpleNamespace(loc_name=etapa)] if etapa else []
    return SimpleNamespace(loc_name=nombre, desc=[marca] if marca else [], GetContents=lambda _f='*': etapas)


def _app(variaciones=(), casos_estudio=()):
    objetos = [v if isinstance(v, SimpleNamespace) else _variacion(v) for v in variaciones]
    carpetas = {'scheme': SimpleNamespace(GetContents=lambda _f, _r=0: objetos),
                'study': SimpleNamespace(GetContents=lambda _f, _r=0: list(casos_estudio))}
    return SimpleNamespace(GetProjectFolder=lambda nombre: carpetas[nombre])


def _del_conversor(casos, prefijo, nombre):
    return _variacion(nombre, marca=f'{casos.MARCA}variacion:{prefijo}')


def test_la_variacion_de_fichas_de_la_copia_se_reutiliza(guion, casos):
    """086:RF-87 — en la copia se graba en la ``Fichas_`` del conversor que trae, por su marca; sin ninguna, la propia."""
    pre = guion.PREFIJO_FICHAS
    marcada = _del_conversor(casos, pre, f'{pre}PA217')
    assert guion.nombre_de_la_propia(_app([marcada, 'Obra_X']), pre, 'PRUEBA064_184942') == f'{pre}PA217'
    assert guion.nombre_de_la_propia(_app([_del_conversor(casos, pre, f'{pre}PA217(1)')]), pre, 'P') == f'{pre}PA217'
    # La del proyecto, si ya existe, gana a la de la copia.
    assert guion.nombre_de_la_propia(_app([marcada, f'{pre}PRUEBA064']), pre, 'PRUEBA064') == f'{pre}PRUEBA064'
    assert guion.nombre_de_la_propia(_app(['Obra_X']), pre, 'PRUEBA064') == f'{pre}PRUEBA064'


def test_la_de_antes_de_la_marca_se_reconoce_por_su_etapa(guion):
    """086:RF-87 — una del conversor creada antes de la marca lleva la etapa ``Etapa_fichas`` que él crea."""
    pre = guion.PREFIJO_FICHAS
    antigua = _variacion(f'{pre}20261112-113130_CSG_TXT_PA217', etapa='Etapa_fichas')
    assert guion.nombre_de_la_propia(_app([antigua]), pre, 'PRUEBA064') == f'{pre}20261112-113130_CSG_TXT_PA217'


def test_la_del_usuario_con_el_mismo_prefijo_no_se_toca(guion):
    """086:RF-87 — ``Fichas_prueba`` hecha a mano no es del conversor: se avisa y no se graba dentro de ella."""
    pre = guion.PREFIJO_FICHAS
    avisos = []
    assert guion.nombre_de_la_propia(_app([f'{pre}prueba']), pre, 'PA217', avisos) == f'{pre}PA217'
    assert len(avisos) == 1 and f'{pre}prueba' in avisos[0] and 'no se toca' in avisos[0]


def test_dos_del_conversor_avisan_y_no_se_elige(guion, casos):
    """086:RF-87 — en una copia de una copia, dos del conversor: el orden alfabético no dice cuál vale; se avisa."""
    pre = guion.PREFIJO_FICHAS
    for dos in ([_del_conversor(casos, pre, f'{pre}A'), _del_conversor(casos, pre, f'{pre}B')],
                [_variacion(f'{pre}A', etapa='Etapa_fichas'), _variacion(f'{pre}B', etapa='Etapa_fichas')]):
        avisos = []
        assert guion.nombre_de_la_propia(_app(dos), pre, 'P', avisos) == f'{pre}P'
        assert len(avisos) == 1 and f'{pre}A' in avisos[0] and f'{pre}B' in avisos[0]
        assert 'no se elige' in avisos[0]


def test_la_marca_se_pone_y_no_falla_si_no_se_acepta(guion, casos):
    """086:RF-87 — la variación del conversor queda marcada; si DIgSILENT rechaza ``desc``, se sigue sin error."""
    pre = guion.PREFIJO_FICHAS
    v = _variacion(f'{pre}PA217')
    guion.marcar_variacion_del_conversor(v, pre)
    assert casos.rol_de(v) == f'variacion:{pre}'

    class SinDesc:
        loc_name = f'{pre}X'

        @property
        def desc(self):
            raise AttributeError('desc')

    guion.marcar_variacion_del_conversor(SinDesc(), pre)


def test_la_de_transformadores_tambien_va_por_su_marca(guion, casos):
    """086:RF-87 — ``SED_NTP_`` sigue la misma regla que ``Fichas_``, con su etapa ``Etapa_sed_ntp``."""
    pre = guion.PREFIJO_SED_NTP
    assert guion.nombre_de_la_propia(_app([_del_conversor(casos, pre, f'{pre}PA217')]), pre, 'P') == f'{pre}PA217'
    assert guion.nombre_de_la_propia(_app([_variacion(f'{pre}PA217', etapa='Etapa_sed_ntp')]), pre, 'P') == f'{pre}PA217'
    assert guion.nombre_de_la_propia(_app([f'{pre}PA217']), pre, 'P') == f'{pre}P'


def test_el_caso_cargas_nuevas_se_halla_por_nombre_y_marca(casos):
    """086:RF-88, 037:RF-4 — el del sistema, nunca uno del operador con el mismo nombre; con año, el de ese año."""
    marca = casos.MARCA
    ajeno = SimpleNamespace(loc_name='Cargas nuevas', desc=[])
    propio = SimpleNamespace(loc_name='Cargas nuevas', desc=[f'{marca}cargas'])
    de_2025 = SimpleNamespace(loc_name='Cargas nuevas 2025', desc=[f'{marca}cargas@2025'])
    app = _app(casos_estudio=[ajeno, propio, de_2025])
    assert casos.caso_cargas_nuevas(app) is propio
    assert casos.caso_cargas_nuevas(app, 2025) is de_2025
    assert casos.caso_cargas_nuevas(_app(casos_estudio=[ajeno])) is None


def test_la_consigna_llega_tambien_a_cargas_nuevas(guion):
    """086:RF-88 — con «Cargas nuevas» en la lista, su red externa toma la consigna; sin ese caso, nada falla."""
    class Caso(SimpleNamespace):
        def Activate(self):
            app.activo = self

    class Esc:
        def Save(self):
            pass

    roles = ('sin', 'con', 'base', 'cargas')
    xnet = {r: SimpleNamespace(loc_name='Red L-PA235', usetp=1.025) for r in roles}
    app = SimpleNamespace(activo=None)
    app.GetCalcRelevantObjects = lambda _f: [xnet[app.activo.rol]]
    app.GetActiveScenario = lambda: Esc()
    guion.fijar_consigna_de_la_fuente(app, 1.0278, [Caso(rol=r) for r in roles])
    assert xnet['cargas'].usetp == 1.0278
    guion.fijar_consigna_de_la_fuente(app, 1.03, [Caso(rol='sin'), None])
    assert xnet['sin'].usetp == 1.03
