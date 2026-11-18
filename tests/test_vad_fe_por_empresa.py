"""Tarjeta VAD-FE26 (specs 107 y 108): los factores de expansión de pérdidas (FE), los porcentajes y las fórmulas de
reajuste del VAD 2026-2030, grupo 1 (RCD 185-2026-OS/CD), y la elección de la tabla de FE de una EMPRESA cuando dos
fijaciones se solapan (la 223-2023 del grupo 2 rige hasta el 2027-10-31; la 185-2026, del 2026-11-01 al 2030-10-31).

Los ayudantes devuelven None ante RegistroError: así cada prueba falla en el rojo por su propia aserción.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from convertersmartgrid.adaptadores.pit import expediente
from convertersmartgrid.dominio.registro_normativo import RegistroError, cargar_registro
from convertersmartgrid.aplicacion.vad import estudio

RAIZ = Path(__file__).resolve().parents[1]
NORMATIVA = RAIZ / 'config' / 'normativa'
FE = 'vad.perdidas.factores_expansion'
R185 = 'RCD 185-2026-OS/CD'
R223 = 'RCD 223-2023-OS/CD'
H = 'b' * 64


def _de_empresa(registro, clave, empresa, fecha):
    try:
        return registro.regla_de_empresa(clave, empresa, fecha)
    except RegistroError:
        return None


def _regla(registro, clave, fecha):
    try:
        return registro.regla(clave, fecha)
    except RegistroError:
        return None


def _acto(rv):
    return rv.norma.acto if rv is not None else None


@pytest.fixture(scope='module')
def registro():
    return cargar_registro(NORMATIVA)


def _empresas_de_norma(registro, acto, clave=FE):
    """Las empresas que trae la tabla ``clave`` de la norma ``acto``: el grupo sale del registro, no del código."""
    try:
        norma = registro.norma(acto)
    except RegistroError:
        return set()
    return {e for r in norma.reglas if r.clave == clave for e in r.valor['empresas']}


def _una_de_cada_grupo(registro):
    """Una empresa que solo está en la 185-2026 (grupo 1) y otra que solo está en la 223-2023 (grupo 2)."""
    g1, g2 = _empresas_de_norma(registro, R185), _empresas_de_norma(registro, R223)
    return min(g1 - g2, default=None), min(g2 - g1, default=None)


# --------------------------------------------------------------------------- la tabla de cada empresa, por fecha
def test_el_2026_11_01_cada_empresa_toma_la_tabla_de_su_fijacion(registro):
    """107:RF-7, 108:RF-8, 108:RF-13 — el 2026-11-01 una empresa del grupo 1 toma la 185-2026 y una del grupo 2 la
    223-2023, las dos obligatorias; el grupo de cada una lo dice el registro."""
    e1, e2 = _una_de_cada_grupo(registro)
    uno = _de_empresa(registro, FE, e1, '2026-11-01')
    dos = _de_empresa(registro, FE, e2, '2026-11-01')
    assert _acto(uno) == R185 and uno.obligatoria
    assert _acto(dos) == R223 and dos.obligatoria
    assert e1 in uno.regla.valor['empresas'] and e2 in dos.regla.valor['empresas']


def test_la_223_rige_su_ultimo_dia_y_no_el_siguiente(registro):
    """107:RF-7, 108:RF-8 — la 223-2023 rige el 2027-10-31, su último día (incluido), y el 2027-11-01 ya no: la
    empresa del grupo 2 se queda sin tabla y el error lo dice."""
    e1, e2 = _una_de_cada_grupo(registro)
    assert _acto(_de_empresa(registro, FE, e2, '2027-10-31')) == R223
    assert e2 is not None and _de_empresa(registro, FE, e2, '2027-11-01') is None
    assert _acto(_de_empresa(registro, FE, e1, '2027-11-01')) == R185


def test_la_185_rige_su_ultimo_dia(registro):
    """107:RF-7, 108:RF-8 — la 185-2026 rige el 2030-10-31, su último día (incluido), y el 2030-11-01 ya no."""
    e1, _ = _una_de_cada_grupo(registro)
    assert _acto(_de_empresa(registro, FE, e1, '2030-10-31')) == R185
    assert _de_empresa(registro, FE, e1, '2030-11-01') is None
    norma = registro.norma(R185)
    assert (norma.vigencia_desde, norma.vigencia_hasta, norma.vigencia_hasta_motivo) == ('2026-11-01', '2030-10-31',
                                                                                         '')


def test_vigencia_de_la_fijacion_2023_2027_con_su_motivo(registro):
    """107:RF-7 — la 187-2023 dice su vigencia (art. 8); la 223-2023 no la dice y la hereda: «fin deducido» citado."""
    r187, r223 = registro.norma('RCD 187-2023-OS/CD'), registro.norma(R223)
    assert (r187.vigencia_desde, r187.vigencia_hasta, r187.vigencia_hasta_motivo) == ('2023-11-01', '2027-10-31', '')
    assert (r223.vigencia_desde, r223.vigencia_hasta) == ('2023-11-01', '2027-10-31')
    assert r223.vigencia_hasta_motivo.startswith('fin deducido: modifica numerales de la RCD 187-2023-OS/CD')
    assert '31 de octubre de 2027' in r223.vigencia_hasta_motivo and 'Artículo 8' in r187.nota


def test_empresa_que_no_esta_en_ninguna_fijacion_da_un_error_que_la_nombra(registro):
    """107:RF-7, 108:RF-13 — una empresa que no está en ninguna tabla vigente no toma la de otra: RegistroError con la
    empresa, la clave y la fecha."""
    try:
        registro.regla_de_empresa(FE, 'EMPRESA-INEXISTENTE', '2026-11-01')
        mensaje = None
    except RegistroError as exc:
        mensaje = str(exc)
    assert mensaje is not None and 'EMPRESA-INEXISTENTE' in mensaje and FE in mensaje and '2026-11-01' in mensaje
    assert 'sin implementar' not in mensaje


def test_regla_sin_empresa_sobre_fijaciones_distintas_pide_la_empresa(registro):
    """107:RF-7, 108:RF-13 — ``regla()`` sin empresa, el 2026-11-01, no devuelve en silencio una tabla sin la empresa
    que se busca: lanza un RegistroError que pide ``regla_de_empresa``. El 2026-10-31, con una sola fijación, sigue."""
    with pytest.raises(RegistroError, match='va por empresa.*regla_de_empresa'):
        registro.regla(FE, '2026-11-01')
    with pytest.raises(RegistroError, match='va por empresa.*regla_de_empresa'):
        registro.regla(FE)
    assert _acto(_regla(registro, FE, '2026-10-31')) == R223


def _sintetico(tmp_path, empresas_a, empresas_b):
    def norma(acto, desde, empresas):
        return {'acto': acto, 'titulo': acto, 'estado_juridico': 'vigente_comprobada', 'sha256': H,
                'vigencia_desde': desde,
                'reglas': [{'clave': 'x.por_empresa', 'valor': {'empresas': {e: {'v': 1} for e in empresas}},
                            'cita_literal': '«x»', 'pagina': '1'}]}
    datos = {'esquema': 'registro_normativo_v1',
             'normas': [norma('SINT-A', '2020-01-01', empresas_a), norma('SINT-B', '2021-01-01', empresas_b)]}
    (tmp_path / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(tmp_path)


def test_regla_sin_empresa_falla_solo_si_las_fijaciones_cubren_empresas_distintas(tmp_path):
    """107:RF-7 — con las mismas empresas en las dos normas vigentes, ``regla()`` sigue dando la más reciente; con
    empresas distintas lanza, y ``regla_de_empresa`` da a cada empresa la suya."""
    iguales = _sintetico(tmp_path, ['E1', 'E2'], ['E2', 'E1'])
    assert _acto(_regla(iguales, 'x.por_empresa', '2022-01-01')) == 'SINT-B'
    distintas = _sintetico(tmp_path, ['E1'], ['E2'])
    with pytest.raises(RegistroError, match='va por empresa'):
        distintas.regla('x.por_empresa', '2022-01-01')
    assert _acto(_de_empresa(distintas, 'x.por_empresa', 'E1', '2022-01-01')) == 'SINT-A'
    assert _acto(_de_empresa(distintas, 'x.por_empresa', 'E2', '2022-01-01')) == 'SINT-B'


# --------------------------------------------------------------------------- los datos de la 185-2026


def test_las_15_empresas_de_la_185_cumplen_fe_y_coeficientes(registro):
    """108:RF-8, 108:RF-9 — las 15 empresas de la 185-2026 traen los 8 FE con su porcentaje (FE = 1/(1−p), que
    comprueba el cargador) y, en cada nivel (MT, BT y SED), A+B+C+D = 1; las mismas en el IT 607."""
    e1, _ = _una_de_cada_grupo(registro)
    fe = _de_empresa(registro, FE, e1, '2026-11-01')
    assert fe is not None and _acto(fe) == R185 and len(fe.regla.valor['empresas']) == 15
    it607 = _de_empresa(registro, 'vad.perdidas.factores_expansion_it607', e1, '2026-11-01')
    assert it607 is not None and it607.regla.valor['empresas'] == fe.regla.valor['empresas']
    for empresa, fila in fe.regla.valor['empresas'].items():
        assert set(fila['fe']) == set(fila['porcentaje']) and len(fila['fe']) == 8, empresa
        for k, f in fila['fe'].items():
            assert abs(f - 1 / (1 - fila['porcentaje'][k] / 100)) <= 1.5e-4, (empresa, k)
    coef = _de_empresa(registro, 'vad.reajuste.coeficientes', e1, '2026-11-01')
    assert coef is not None and set(coef.regla.valor['empresas']) == set(fe.regla.valor['empresas'])
    assert coef.obligatoria
    for empresa, fila in coef.regla.valor['empresas'].items():
        for nivel in ('MT', 'BT', 'SED'):
            assert round(sum(fila[letra + nivel] for letra in 'ABCD'), 4) == 1, (empresa, nivel)


def test_formulas_y_valores_base_de_la_185_con_su_cita(registro):
    """108:RF-9 — las fórmulas (8) a (12) y los valores base de la 185-2026 vienen de ella, citados y obligatorios."""
    formulas = _regla(registro, 'vad.reajuste.formulas', '2026-11-01')
    base = _regla(registro, 'vad.reajuste.valores_base', '2026-11-01')
    aplicacion = _regla(registro, 'vad.reajuste.aplicacion', '2026-11-01')
    for rv in (formulas, base, aplicacion):
        assert _acto(rv) == R185 and rv.obligatoria and rv.regla.citada and rv.regla.articulo_o_anexo
    f = formulas.regla.valor
    assert f['numeracion'] == {'FAVADMT': '(8)', 'FAVADBT': '(9)', 'FAVADSED': '(10)', 'FACF': '(11)',
                               'FACER': '(12)'}
    assert f['FAVADMT'].startswith('AMT × IPM/IPM0 + BMT × TC/TC0') and f['FACF'] == 'IPM/IPM0'
    assert f['FACER'] == 'TC/TC0'
    v = base.regla.valor
    assert (v['TC0']['valor'], v['IPM0']['valor'], v['IPCu0']['valor'], v['IPAl0']['valor']) == (
        3.368, 125.999904, 448.92, 2625.27)


# --------------------------------------------------------------------------- quien usa la clave por empresa
def test_el_expediente_del_pit_fija_la_huella_de_cada_fijacion(registro):
    """107:RF-7 — el expediente del PIT no es de una empresa: la huella de una clave por empresa junta la regla de
    cada empresa, y no se cae al abrirlo con dos fijaciones a la vez."""
    empresas = registro.empresas_de(FE)
    assert set(empresas) == _empresas_de_norma(registro, R185) | _empresas_de_norma(registro, R223)
    assert set(_una_de_cada_grupo(registro)) <= set(empresas)
    partes = {}
    for e in empresas:
        rv = _de_empresa(registro, FE, e, None)
        partes[e] = rv.huella() if rv is not None else None
    esperada = hashlib.sha256(json.dumps(partes, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    assert expediente._huellas(registro)[FE] == esperada


def test_el_estudio_vad_toma_la_regla_de_su_empresa(registro):
    """108:RF-9, 108:RF-13 — la huella que guarda el estudio de una clave por empresa es la de la fijación de su
    empresa (la 185-2026 para una del grupo 1; la 223-2023 para una del grupo 2)."""
    e1, e2 = _una_de_cada_grupo(registro)
    uno = _de_empresa(registro, FE, e1, None)
    dos = _de_empresa(registro, FE, e2, None)
    assert uno is not None and dos is not None
    assert estudio._huella(registro, FE, e1) == uno.huella()
    assert estudio._huella(registro, FE, e2) == dos.huella() != uno.huella()


# --------------------------------------------------------------- v2 (orden de 28): la tabla previa, solo referencia
def test_la_tabla_previa_a_la_reconsideracion_es_solo_referencia(registro):
    """107:RF-8, 108:RF-10 (VAD-FE26 v2) — la fijación previa a la reconsideración (RCD 187-2023, IT 716) se conserva
    para comparar, pero no obliga aunque esté vigente; el factor de expansión de cada empresa del grupo 2 sale siempre
    de la 223-2023, nunca de la tabla previa."""
    previa = _regla(registro, 'vad.perdidas.factores_expansion_it716', '2025-06-01')
    assert previa is not None and previa.norma.acto == 'RCD 187-2023-OS/CD'
    assert previa.obligatoria is False, 'la tabla previa a la reconsideración no obliga'
    assert getattr(previa.norma, 'solo_referencia', '').startswith('referencia: tabla previa a la reconsideración')
    grupo2 = sorted(_empresas_de_norma(registro, R223))
    assert grupo2, 'el grupo 2 sale del registro'
    actos = {_acto(_de_empresa(registro, FE, e, '2025-06-01')) for e in grupo2}
    assert actos == {R223}, actos
