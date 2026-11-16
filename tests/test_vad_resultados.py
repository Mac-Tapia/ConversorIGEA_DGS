"""Spec 108 T16 — cargo fijo, VAD por nivel, variantes, FEE y reajuste desde el registro (108:RF-16, RF-9, RF-13).

Los registros son sintéticos: conceptos, variantes y fórmulas inventados para la prueba, con nombres que no son los del
TdR 2026 (las variantes son «publica» y «privada», no «_SER»), para comprobar que nada de eso está en el código. Los
valores esperados se calculan a mano en cada prueba. El registro real se usa solo para comprobar que sus fórmulas
transcritas se evalúan con las variables que define el TdR.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import jsonschema
import pytest

from convertersmartgrid.registro_normativo import RegistroError, cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.formulas import FormulaError, evaluar, variables
from convertersmartgrid.vad.resultados_vad import (DatosSistema, ambitos, calcular_fee, calcular_sistema,
                                                   calcular_vad, conceptos, factores_reajuste)

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_VAD = RAIZ / 'config' / 'vad'
RESULTADOS = CONFIG_VAD / 'tdr_vad_2026_resultados.json'
ESQUEMA = RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json'


def _r(clave, valor, **kw):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave}»', 'lineas': '1', **kw}


def _registro(tmp_path, estado='vigente_comprobada', sin=(), extra=()):
    reglas = [
        _r('vad.conceptos.alfa', ['CF', 'VADX', 'VADY']),
        _r('vad.conceptos.beta', ['CF', 'VADX_R']),
        _r('vad.variantes.VADX_R', ['publica', 'privada']),
        _r('vad.formula.CF', 'Ccom / Ncli', unidad='por cliente.año'),
        _r('vad.formula.VADX', '(Ax + Ox) / Px', unidad='por kW.año'),
        _r('vad.formula.VADY', '(Ay + Oy) / Py'),
        _r('vad.formula.VADX_R.publica', '(Ax * F + Ox) / Px'),
        _r('vad.formula.VADX_R.privada', '(Ax + Ox) / Px'),
        _r('vad.ponderacion', {'CF': 'Ncli', 'VADX': 'Px', 'VADY': 'Py', 'VADX_R': 'Px'}),
        _r('vad.formula.FEE', '(Pfc + (1 + tc) * Pvc) / (1 + tc)'),
        _r('vad.reajuste.factores', {'alfa': ['FA1', 'FA2'], 'beta': ['FA1']}),
        _r('vad.reajuste.parametros', ['p1', 'p2']),
        *extra,
    ]
    reglas = [r for r in reglas if r['clave'] not in sin]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': estado, 'sha256': 'b' * 64,
        'version': 'v9', 'vigencia_desde': '2001-01-01', 'reglas': reglas}]}
    ruta = tmp_path / 'reg' / 'tdr.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(ruta.parent)


#: Dos empresas sintéticas, con sus sistemas y valores; los esperados se calculan a mano debajo.
EMPRESAS = {
    'norte': [DatosSistema('S1', 'alfa', 'XUS', {'Ccom': 1200, 'Ncli': 100, 'Ax': 50, 'Ox': 30, 'Px': 4,
                                                 'Ay': 10, 'Oy': 6, 'Py': 2}),
              DatosSistema('S2', 'alfa', 'XUS', {'Ccom': 900, 'Ncli': 300, 'Ax': 20, 'Ox': 10, 'Px': 6,
                                                 'Ay': 9, 'Oy': 3, 'Py': 6})],
    'sur': [DatosSistema('R1', 'alfa', 'XUS', {'Ccom': 500, 'Ncli': 50, 'Ax': 7, 'Ox': 3, 'Px': 1,
                                               'Ay': 4, 'Oy': 4, 'Py': 1})],
}
ESPERADO = {
    # CF por sistema = Ccom/Ncli; empresa: Σ CF·Ncli / Σ Ncli = Σ Ccom / Σ Ncli.
    'norte': {'S1': {'CF': 12.0, 'VADX': 20.0, 'VADY': 8.0}, 'S2': {'CF': 3.0, 'VADX': 5.0, 'VADY': 2.0},
              'empresa': {'CF': 2100 / 400, 'VADX': (20 * 4 + 5 * 6) / 10, 'VADY': (8 * 2 + 2 * 6) / 8}},
    'sur': {'R1': {'CF': 10.0, 'VADX': 10.0, 'VADY': 8.0}, 'empresa': {'CF': 10.0, 'VADX': 10.0, 'VADY': 8.0}},
}


@pytest.mark.parametrize('empresa', sorted(EMPRESAS))
def test_caso_calculado_a_mano_por_sistema_y_ponderado(tmp_path, empresa):
    """108:RF-16 — el cargo fijo y el VAD de cada nivel salen de las fórmulas del registro, por sistema y ponderados
    a nivel empresa con la variable que dice el registro; coinciden con el cálculo a mano."""
    resultado = calcular_vad(_registro(tmp_path), EMPRESAS[empresa])
    assert resultado.estado == 'conforme', resultado.motivos
    for sistema in resultado.sistemas:
        for concepto, esperado in ESPERADO[empresa][sistema.sistema].items():
            assert sistema.valor(concepto).valor == pytest.approx(esperado)
    empresa_valores = {v.concepto: v.valor for v in resultado.empresa}
    assert empresa_valores == pytest.approx(ESPERADO[empresa]['empresa'])


def test_cada_valor_lleva_su_regla_norma_y_huella(tmp_path):
    """108:RF-9 — cada valor dice qué regla y qué norma lo dieron, si obliga y su huella."""
    valor = calcular_sistema(_registro(tmp_path), EMPRESAS['norte'][0]).valor('VADX')
    assert (valor.regla, valor.acto, valor.obligatoria, valor.moneda) == ('vad.formula.VADX', 'tdr-sintetico', True,
                                                                         'XUS')
    assert len(valor.huella) == 64 and valor.unidad == 'por kW.año'


def test_las_variantes_salen_del_registro_no_del_codigo(tmp_path):
    """108:RF-16, 108:RF-13 — un ámbito con variantes inventadas («publica», «privada») calcula la que declara cada
    sistema; sin declararla es un hueco que nombra las opciones; una variante que el registro no tiene se rechaza."""
    reg = _registro(tmp_path)
    datos = {'Ccom': 10, 'Ncli': 5, 'Ax': 10, 'Ox': 2, 'Px': 2, 'F': 0.4}
    publica = calcular_sistema(reg, DatosSistema('P', 'beta', 'XUS', datos, {'VADX_R': 'publica'}))
    privada = calcular_sistema(reg, DatosSistema('Q', 'beta', 'XUS', datos, {'VADX_R': 'privada'}))
    assert publica.valor('VADX_R').valor == pytest.approx((10 * 0.4 + 2) / 2)
    assert privada.valor('VADX_R').valor == pytest.approx((10 + 2) / 2)
    assert publica.valor('VADX_R').variante == 'publica'
    sin = calcular_sistema(reg, DatosSistema('R', 'beta', 'XUS', datos)).valor('VADX_R')
    assert sin.hueco and 'publica' in sin.motivo and 'privada' in sin.motivo
    with pytest.raises(VadError, match='otra'):
        calcular_sistema(reg, DatosSistema('T', 'beta', 'XUS', datos, {'VADX_R': 'otra'}))
    with pytest.raises(VadError, match='VADX'):
        calcular_sistema(reg, DatosSistema('U', 'alfa', 'XUS', datos, {'VADX': 'publica'}))


def test_variable_que_falta_y_division_entre_cero_son_huecos_nombrados(tmp_path):
    """108:RF-16 — una variable que falta o una demanda 0 dejan un hueco que lo dice, nunca un 0, y el resultado
    queda incompleto; la empresa no pondera un concepto con un sistema en hueco."""
    reg = _registro(tmp_path)
    sistemas = [DatosSistema('S1', 'alfa', 'XUS', {'Ccom': 1, 'Ncli': 1, 'Ax': 1, 'Ox': 1, 'Px': 0, 'Ay': 1, 'Py': 1}),
                DatosSistema('S2', 'alfa', 'XUS', {'Ccom': 1, 'Ncli': 1, 'Ax': 1, 'Ox': 1, 'Px': 1, 'Ay': 1, 'Oy': 1,
                                                   'Py': 1})]
    resultado = calcular_vad(reg, sistemas)
    vadx, vady = resultado.sistemas[0].valor('VADX'), resultado.sistemas[0].valor('VADY')
    assert vadx.hueco and 'cero' in vadx.motivo
    assert vady.hueco and 'Oy' in vady.motivo
    empresa = {v.concepto: v for v in resultado.empresa}
    assert empresa['VADX'].hueco and 'S1' in empresa['VADX'].motivo
    assert empresa['CF'].valor == pytest.approx(1.0)
    assert resultado.estado == 'incompleto' and any('Oy' in m for m in resultado.motivos)


def test_regla_que_no_obliga_deja_no_conforme(tmp_path):
    """108:RF-10, 108:RF-16 — con el TdR sin comprobar, los valores salen pero el resultado es no_conforme."""
    reg = _registro(tmp_path, estado='prepublicada')
    resultado = calcular_vad(reg, EMPRESAS['sur'])
    assert resultado.estado == 'no_conforme'
    assert any('no obliga' in m for m in resultado.motivos)


def test_formula_que_falta_en_el_registro_es_hueco(tmp_path):
    """108:RF-16 — si el registro no trae la fórmula de un concepto, el concepto es un hueco con la clave."""
    reg = _registro(tmp_path, sin=('vad.formula.VADY',))
    valor = calcular_sistema(reg, EMPRESAS['sur'][0]).valor('VADY')
    assert valor.hueco and 'vad.formula.VADY' in valor.motivo


def test_entradas_invalidas_se_rechazan_con_mensaje(tmp_path):
    """108:RF-16 — ámbito desconocido, sistemas repetidos, lista vacía y datos sin moneda se rechazan."""
    reg = _registro(tmp_path)
    with pytest.raises(VadError, match='alfa, beta'):
        conceptos(reg, 'gamma')
    with pytest.raises(VadError, match='repetidos'):
        calcular_vad(reg, [EMPRESAS['sur'][0], EMPRESAS['sur'][0]])
    with pytest.raises(VadError, match='ningún sistema'):
        calcular_vad(reg, [])
    with pytest.raises(VadError, match='moneda'):
        DatosSistema('S', 'alfa', '')


def test_dos_monedas_no_se_ponderan_juntas(tmp_path):
    """108:RF-16, 108:RF-9 — dos sistemas en monedas distintas no dan un VAD de empresa mezclado."""
    a = EMPRESAS['norte'][0]
    b = DatosSistema('S9', 'alfa', 'XPE', dict(EMPRESAS['norte'][1].valores))
    empresa = {v.concepto: v for v in calcular_vad(_registro(tmp_path), [a, b]).empresa}
    assert empresa['VADX'].hueco and 'XPE' in empresa['VADX'].motivo


def test_fee_con_la_formula_registrada_y_sus_limites(tmp_path):
    """108:RF-16 — el FEE se calcula con la fórmula registrada; proporciones que no suman 1 o fuera de [0, 1] y una
    tasa de crecimiento ≤ -1 se rechazan."""
    reg = _registro(tmp_path)
    fee = calcular_fee(reg, 'VADX', proporcion_fija=0.3, proporcion_variable=0.7, crecimiento=0.05)
    assert fee.valor == pytest.approx((0.3 + 1.05 * 0.7) / 1.05) and fee.regla == 'vad.formula.FEE'
    with pytest.raises(VadError, match='suman'):
        calcular_fee(reg, 'VADX', proporcion_fija=0.3, proporcion_variable=0.6, crecimiento=0.05)
    with pytest.raises(VadError, match='proporción'):
        calcular_fee(reg, 'VADX', proporcion_fija=1.2, proporcion_variable=-0.2, crecimiento=0.05)
    with pytest.raises(VadError, match='mayor que -1'):
        calcular_fee(reg, 'VADX', proporcion_fija=0.3, proporcion_variable=0.7, crecimiento=-1)


def test_reajuste_sin_formula_registrada_es_hueco_con_cita(tmp_path):
    """108:RF-16 — sin fórmula de reajuste en el registro, cada factor queda como hueco que cita las líneas, y las
    incidencias se validan contra los parámetros registrados."""
    reg = _registro(tmp_path)
    reajuste = factores_reajuste(reg, 'alfa', {'FA1': {'p1': 0.25, 'p2': 0.75}})
    fa1, fa2 = reajuste.factores
    assert fa1.hueco and 'forma cerrada' in fa1.motivo and 'líneas 1' in fa1.motivo
    assert fa2.hueco and 'FA2' in fa2.motivo
    assert reajuste.incidencias == {'FA1': {'p1': 0.25, 'p2': 0.75}}
    with pytest.raises(VadError, match='suman'):
        factores_reajuste(reg, 'alfa', {'FA1': {'p1': 0.5, 'p2': 0.6}})
    with pytest.raises(VadError, match='faltan: p2'):
        factores_reajuste(reg, 'alfa', {'FA1': {'p1': 1.0}})
    with pytest.raises(VadError, match='FA9'):
        factores_reajuste(reg, 'alfa', {'FA9': {'p1': 0.5, 'p2': 0.5}})
    with pytest.raises(VadError, match='delta'):
        factores_reajuste(reg, 'delta', {})


def test_reajuste_con_formula_registrada(tmp_path):
    """108:RF-16 — si el registro trae la fórmula de reajuste, se evalúa con las incidencias y los índices."""
    reg = _registro(tmp_path, extra=(_r('vad.formula.reajuste', 'suma(k, a * I / I0)'),))
    reajuste = factores_reajuste(reg, 'beta', {'FA1': {'p1': 0.4, 'p2': 0.6}},
                                 indices={'p1': (100.0, 110.0), 'p2': (50.0, 45.0)})
    assert reajuste.factores[0].valor == pytest.approx(0.4 * 1.1 + 0.6 * 0.9)
    sin_indices = factores_reajuste(reg, 'beta', {'FA1': {'p1': 0.4, 'p2': 0.6}}, indices={'p1': (1.0, 1.0)})
    assert sin_indices.factores[0].hueco and 'p2' in sin_indices.factores[0].motivo


def test_interprete_cerrado():
    """108:RF-13 — las fórmulas del registro se evalúan sin eval: solo aritmética, variables y suma(n, …)."""
    assert evaluar('suma(n, x / (1 + i) ** (n - 1))', {'x': [1.0, 1.1], 'i': 0.1}) == pytest.approx(2.0)
    assert variables('(a + suma(n, b * n)) / c') == {'a', 'b', 'c'}
    for mala, valores in (('__import__("os").system("x")', {}), ('a % b', {'a': 1, 'b': 2}), ('a.b', {'a': 1}),
                          ('', {}), ('a', {'a': [1.0]}), ('suma(n, a)', {'a': [1.0], 'n': 1}),
                          ('suma(n, a + b)', {'a': [1.0], 'b': [1.0, 2.0]}), ('(-1) ** 0.5', {}),
                          ('a', {'a': float('nan')}), ('a', {'a': True}), ('x' * 3000, {})):
        with pytest.raises(FormulaError):
            evaluar(mala, valores)


def test_registro_real_cumple_el_esquema_y_esta_citado():
    """108:RF-9, 108:RF-16 — la ampliación del TdR real valida contra el esquema y cada regla está citada."""
    esquema = json.loads(ESQUEMA.read_text(encoding='utf-8'))
    jsonschema.validate(json.loads(RESULTADOS.read_text(encoding='utf-8')), esquema)
    registro = cargar_registro(CONFIG_VAD)
    reglas = [r for n in registro.normas.values() for r in n.reglas if r.clave.startswith(('vad.formula.',
                                                                                            'vad.conceptos.'))]
    assert reglas and all(r.citada for r in reglas)
    # 108:RF-9, 108:RF-16 — los ámbitos que calcula el módulo son los de las reglas citadas, y cada concepto que
    # el módulo lee de un ámbito está en esa regla citada.
    citadas = {r.clave: r for r in reglas}
    declarados = sorted(c.removeprefix('vad.conceptos.') for c in citadas if c.startswith('vad.conceptos.'))
    assert declarados and ambitos(registro) == declarados
    for ambito in declarados:
        assert conceptos(registro, ambito) == citadas[f'vad.conceptos.{ambito}'].valor


def test_formulas_reales_se_evaluan_con_sus_variables():
    """108:RF-16 — cada concepto de cada ámbito del TdR registrado tiene su fórmula (o la de cada variante) y se
    evalúa con valores sintéticos; un caso del ámbito con variantes coincide con el cálculo a mano."""
    registro = cargar_registro(CONFIG_VAD)
    for ambito in ('lce', 'lger'):
        for concepto in conceptos(registro, ambito):
            try:
                opciones = registro.regla(f'vad.variantes.{concepto}').regla.valor
                claves = [f'vad.formula.{concepto}.{v}' for v in opciones]
            except RegistroError:  # sin variantes en el registro
                claves = [f'vad.formula.{concepto}']
            for clave in claves:
                formula = registro.regla(clave).regla.valor
                valor = evaluar(formula, dict.fromkeys(variables(formula), 2.0))
                assert math.isfinite(valor), clave
    variantes = registro.regla('vad.variantes.VADMT_SER').regla.valor
    datos = DatosSistema('S', 'lger', 'XUS', {'CCCL': 600, 'NCL': 60, 'aVNRMT': 100, 'OyMMT': 20, 'MWMT': 4,
                                              'FFR': 0.5, 'aVNRSED': 30, 'OyMSED': 6, 'MWBT': 3, 'aVNRBT': 60,
                                              'OyMBT': 15},
                         {c: variantes[0] for c in ('VADMT_SER', 'VADSED_SER', 'VADBT_SER')})
    resultado = calcular_sistema(registro, datos)
    assert resultado.valor('CF').valor == pytest.approx(10.0)
    assert resultado.valor('VADMT_SER').valor == pytest.approx((100 * 0.5 + 20) / 4)
    assert resultado.valor('VADBT_SER').valor == pytest.approx((60 * 0.5 + 15) / 3)


def test_reajuste_real_queda_como_hueco_con_cita():
    """108:RF-16 — el TdR registrado no da la fórmula de reajuste: los factores quedan como hueco con su cita."""
    registro = cargar_registro(CONFIG_VAD)
    parametros = registro.regla('vad.reajuste.parametros').regla.valor
    reparto = {p: 1 / len(parametros) for p in parametros}
    factor = registro.regla('vad.reajuste.factores').regla.valor['lce'][0]
    reajuste = factores_reajuste(registro, 'lce', {factor: reparto})
    assert reajuste.factores[0].hueco and 'forma cerrada' in reajuste.factores[0].motivo
