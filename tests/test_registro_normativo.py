"""Registro normativo común (tarjeta RN; dueña la 108, lo usan la 107 y la 108): las pruebas genéricas del módulo con
registros sintéticos (107:RF-7, 107:RF-8, 107:RF-11). Actos, valores y fechas inventados para la prueba, sin ninguna
empresa ni periodo real.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from convertersmartgrid.registro_normativo import (
    ESTADOS,
    RegistroError,
    ReglaAmbigua,
    cargar_registro,
)

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = json.loads((RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json')
                     .read_text(encoding='utf-8'))
H = 'b' * 64


def _regla(clave, valor, **kw):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave} es {valor}»', 'pagina': '3', **kw}


def _registro_uno():
    """Una norma en cada estado, cada una con su regla de prueba."""
    return {'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'N-VC', 'titulo': 'Comprobada', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
         'vigencia_desde': '2001-01-01', 'reglas': [_regla('pit.tasa', 0.1)]},
        {'acto': 'N-PRE', 'titulo': 'Proyecto', 'estado_juridico': 'prepublicada',
         'reglas': [_regla('pit.coym', 0.03)]},
        {'acto': 'N-NV', 'titulo': 'Sin leer', 'estado_juridico': 'no_verificada',
         'reglas': [_regla('pit.vida', 30)]},
        {'acto': 'N-DER', 'titulo': 'Derogada', 'estado_juridico': 'derogada', 'vigencia_hasta': '2002-01-01',
         'reglas': [_regla('pit.viejo', 1)]},
    ]}


def _registro_dos():
    """Una norma modificada por otra posterior: la regla vigente cambia con la fecha."""
    return {'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'M-BASE', 'titulo': 'Base', 'estado_juridico': 'modificada', 'sha256': H,
         'vigencia_desde': '2010-01-01', 'vigencia_hasta': '2019-12-31', 'modificada_por': ['M-MOD'],
         'reglas': [_regla('pit.limite', 100)]},
        {'acto': 'M-MOD', 'titulo': 'Modificatoria', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
         'vigencia_desde': '2020-01-01', 'modifica': ['M-BASE'], 'reglas': [_regla('pit.limite', 90)]},
    ]}


def _escribir(tmp_path, nombre, datos):
    carpeta = tmp_path / nombre
    carpeta.mkdir()
    (carpeta / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    return carpeta


@pytest.mark.parametrize('datos', (_registro_uno(), _registro_dos()), ids=('estados', 'modificatoria'))
def test_registros_sinteticos_validan_contra_el_esquema(datos):
    """107:RF-7 — cada norma con su estado jurídico y su vigencia, según el esquema común."""
    jsonschema.validate(datos, ESQUEMA)


def test_los_cinco_estados():
    """107:RF-7 — el registro distingue vigente comprobada, modificada, prepublicada, no verificada y derogada."""
    assert set(ESTADOS) == {'vigente_comprobada', 'modificada', 'prepublicada', 'no_verificada', 'derogada'}


def test_prepublicada_y_no_verificada_no_obligan(tmp_path):
    """107:RF-8 — una regla prepublicada o no verificada sale como no obligatoria, con su estado."""
    registro = cargar_registro(_escribir(tmp_path, 'uno', _registro_uno()))
    assert registro.regla('pit.tasa', '2030-01-01').obligatoria
    for clave, estado in (('pit.coym', 'prepublicada'), ('pit.vida', 'no_verificada')):
        r = registro.regla(clave, '2030-01-01')
        assert r.estado == estado and not r.obligatoria
        assert r.norma.acto and r.regla.pagina and r.regla.cita_literal


def test_modificatoria_por_fecha(tmp_path):
    """107:RF-7 — la regla de cada fecha es la de la norma vigente entonces, con su acto."""
    registro = cargar_registro(_escribir(tmp_path, 'dos', _registro_dos()))
    antes, despues = registro.regla('pit.limite', '2015-06-01'), registro.regla('pit.limite', '2025-06-01')
    assert (antes.regla.valor, antes.norma.acto, antes.obligatoria) == (100, 'M-BASE', True)
    assert (despues.regla.valor, despues.norma.acto, despues.obligatoria) == (90, 'M-MOD', True)
    assert antes.huella() != despues.huella()


def test_instantanea_cambia_con_una_modificatoria_y_no_con_el_orden(tmp_path):
    """107:RF-7 — la huella del registro fija lo que se usó; una norma nueva la cambia."""
    datos = _registro_dos()
    a = cargar_registro(_escribir(tmp_path, 'a', datos)).instantanea()
    datos['normas'].reverse()
    assert cargar_registro(_escribir(tmp_path, 'b', datos)).instantanea() == a
    datos['normas'].append({'acto': 'M-NUEVA', 'titulo': 'Posterior', 'estado_juridico': 'no_verificada'})
    assert cargar_registro(_escribir(tmp_path, 'c', datos)).instantanea() != a


def test_sin_regla_es_un_error_que_la_nombra(tmp_path):
    """107:RF-11 — un valor que no está en el registro no se supone: el error nombra la clave."""
    registro = cargar_registro(_escribir(tmp_path, 'uno', _registro_uno()))
    with pytest.raises(RegistroError, match='pit.inexistente'):
        registro.regla('pit.inexistente')



def _vigente(registro, clave, fecha):
    """La regla vigente en la fecha, o None si el registro no la da (para que la prueba falle por su aserción)."""
    try:
        return registro.regla(clave, fecha)
    except RegistroError:
        return None


def test_vigencia_hasta_es_el_ultimo_dia_incluido(tmp_path):
    """107:RF-7 (RN-VIG) — ``vigencia_hasta`` es el último día de vigencia, incluido, como lo escribe todo el registro:
    ese día rige la norma que termina y al día siguiente la que empieza; de un instante cuenta su fecha."""
    registro = cargar_registro(_escribir(tmp_path, 'dos', _registro_dos()))
    assert getattr(getattr(_vigente(registro, 'pit.limite', '2019-12-31'), 'norma', None), 'acto', None) == 'M-BASE'
    assert getattr(getattr(_vigente(registro, 'pit.limite', '2019-12-31T23:30'), 'norma', None), 'acto', None) == 'M-BASE'
    assert getattr(getattr(_vigente(registro, 'pit.limite', '2020-01-01'), 'norma', None), 'acto', None) == 'M-MOD'


def test_horas_punta_el_ultimo_dia_de_cada_rm_y_el_fin_deducido():
    """107:RF-7 (RN-VIG, orden de 28) — el 2025-05-31 rige todavía la RM 153-2021 (17-23 h) y el 2029-05-31, la RM
    189-2025 (18-23 h). El fin de la 153-2021 es una deducción (la 189-2025 no la deroga expresamente) y lo dice."""
    registro = cargar_registro(RAIZ / 'config' / 'normativa')
    ultimo_153 = _vigente(registro, 'sein.horas_punta', '2025-05-31')
    assert ultimo_153 is not None, 'el 2025-05-31 tiene que tener regla'
    assert (ultimo_153.norma.acto, ultimo_153.regla.valor) == ('RM 153-2021-MINEM/DM', {'desde': '17:00', 'hasta': '23:00'})
    assert getattr(ultimo_153.norma, 'vigencia_hasta_motivo', '').startswith('fin deducido: inicio de la RM 189-2025')
    assert 'sin derogación expresa' in getattr(ultimo_153.norma, 'vigencia_hasta_motivo', '')
    ultimo_189 = _vigente(registro, 'sein.horas_punta', '2029-05-31')
    assert ultimo_189 is not None, 'el 2029-05-31 tiene que tener regla'
    assert (ultimo_189.norma.acto, ultimo_189.regla.valor) == ('RM 189-2025-MINEM/DM', {'desde': '18:00', 'hasta': '23:00'})
    assert getattr(ultimo_189.norma, 'vigencia_hasta_motivo', None) == ''


# --------------------------------------------------------------------------- RN-AMB: normas que se suman


def _norma_suma(acto, desde, valor, hasta='', **kw):
    return {'acto': acto, 'titulo': acto, 'estado_juridico': 'vigente_comprobada', 'sha256': H,
            'vigencia_desde': desde, 'vigencia_hasta': hasta, 'reglas': [_regla('x.suma', valor)], **kw}


def _sumas(tmp_path, nombre, *normas):
    return cargar_registro(_escribir(tmp_path, nombre, {'esquema': 'registro_normativo_v1', 'normas': list(normas)}))


def _ambigua(registro, clave, fecha=None):
    """El mensaje de ReglaAmbigua, o None si ``regla()`` devuelve una (para que la prueba falle por su aserción)."""
    try:
        registro.regla(clave, fecha)
    except ReglaAmbigua as exc:
        return str(exc)
    return None


def test_normas_independientes_con_la_misma_clave_son_ambiguas(tmp_path):
    """107:RF-7, 107:RF-8 (RN-AMB) — dos normas vigentes a la vez que traen la misma clave sin que una modifique a la
    otra se suman: ``regla()`` no elige en silencio la más reciente, lanza ReglaAmbigua, que nombra las dos y remite a
    ``reglas_vigentes``. Antes de que empiece la segunda, la primera sola no es ambigua."""
    registro = _sumas(tmp_path, 'indep', _norma_suma('IND-A', '2020-01-01', [1]),
                      _norma_suma('IND-B', '2021-01-01', [2]))
    mensaje = _ambigua(registro, 'x.suma', '2022-01-01')
    assert mensaje is not None, 'dos normas independientes no pueden dar una sola regla'
    assert 'IND-A' in mensaje and 'IND-B' in mensaje and 'x.suma' in mensaje and 'reglas_vigentes' in mensaje
    assert isinstance(ReglaAmbigua(''), RegistroError), 'quien ya captura RegistroError la sigue capturando'
    assert registro.regla('x.suma', '2020-06-01').norma.acto == 'IND-A'


def test_una_cadena_de_modificatorias_no_es_ambigua(tmp_path):
    """107:RF-7, 107:RF-8 (RN-AMB) — si la más reciente modifica a las demás, directa o encadenadamente (C-3 modifica a
    C-2, que modifica a C-1; un enlace basta con estar en ``modificada_por`` de la modificada), ``regla()`` da la más
    reciente, como siempre, y ``reglas_vigentes`` solo esa."""
    registro = _sumas(tmp_path, 'cadena',
                      _norma_suma('C-1', '2010-01-01', [1], modificada_por=['C-2']),
                      _norma_suma('C-2', '2015-01-01', [2]),
                      _norma_suma('C-3', '2020-01-01', [3], modifica=['C-2']))
    assert _ambigua(registro, 'x.suma', '2022-01-01') is None
    assert registro.regla('x.suma', '2022-01-01').norma.acto == 'C-3'
    assert [v.norma.acto for v in registro.reglas_vigentes('x.suma', '2022-01-01')] == ['C-3']


def test_reglas_vigentes_devuelve_todas_sin_las_modificadas(tmp_path):
    """107:RF-7, 107:RF-8 (RN-AMB) — ``reglas_vigentes`` da todas las vigentes en la fecha, cada una con su norma y
    ordenadas por vigencia, sin la que otra vigente modifica ni la que ya no rige."""
    registro = _sumas(tmp_path, 'todas',
                      _norma_suma('T-B', '2021-01-01', [2]),
                      _norma_suma('T-A0', '2019-01-01', [0], modificada_por=['T-A']),
                      _norma_suma('T-A', '2020-01-01', [1]),
                      _norma_suma('T-VIEJA', '2018-01-01', [7], hasta='2020-12-31'))
    vigentes = registro.reglas_vigentes('x.suma', '2022-01-01')
    assert [(v.norma.acto, v.regla.valor, v.obligatoria) for v in vigentes] == [('T-A', [1], True), ('T-B', [2], True)]
    assert [v.norma.acto for v in registro.reglas_vigentes('x.suma', '2020-06-01')] == ['T-VIEJA', 'T-A']


def test_sin_fecha_solo_es_ambigua_si_las_vigencias_se_solapan(tmp_path):
    """107:RF-7 (RN-AMB) — sin fecha, una norma que sucede a otra sin solaparse (como las RM de horas punta) no es
    ambigua y sale la más reciente; dos que rigen a la vez sí lo son."""
    sucesion = _sumas(tmp_path, 'sucesion', _norma_suma('S-1', '2010-01-01', [1], hasta='2014-12-31'),
                      _norma_suma('S-2', '2015-01-01', [2]))
    assert _ambigua(sucesion, 'x.suma') is None and sucesion.regla('x.suma').norma.acto == 'S-2'
    solape = _sumas(tmp_path, 'solape', _norma_suma('S-1', '2010-01-01', [1], hasta='2015-12-31'),
                    _norma_suma('S-2', '2015-01-01', [2]))
    mensaje = _ambigua(solape, 'x.suma')
    assert mensaje is not None and 'S-1' in mensaje and 'S-2' in mensaje
