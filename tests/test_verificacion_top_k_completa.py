"""044:RF-6, RF-7 — la ausencia de medidas nunca equivale a una verificación correcta."""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from convertersmartgrid.digital_twin.evaluacion import Limites
from convertersmartgrid.digital_twin.evolutivo import verificar_top_k
from convertersmartgrid.evaluacion_modelos import validar_medicion_nativa
from convertersmartgrid.experimentos import ContextoExperimento

RAIZ = Path(__file__).resolve().parents[1]
#: Limites holgados: aquí se comprueba la completitud; la norma se prueba con los suyos abajo.
LIMITES = Limites('Norma', 0.5, 1.5, 100.0, None)


def contexto_de(rol: str = 'con_proyecto', **cambios) -> ContextoExperimento:
    base = {'source_run_id': 'r1', 'source_mode': 'txt', 'source_fingerprint': 'a' * 64, 'project': 'P',
            'feeders': ('A1',), 'case_id': f'caso-{rol}', 'case_role': rol, 'year': 2026, 'period': '2026-07',
            'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64, 'topology_hash': 'c' * 64,
            'controls_hash': 'd' * 64, 'scenario_hash': 'e' * 64}
    return ContextoExperimento(**{**base, **cambios})


def flujo_de(v_min: float, perdidas: float, cargabilidad: float = 50.0) -> dict:
    return {'tensiones': {'unidad': 'p.u.', 'valores': {'B1': v_min, 'B2': max(v_min, 1.0)}},
            'perdidas': {'unidad': 'kW', 'valores': {'total': perdidas}},
            'cargabilidad': {'unidad': '%', 'valores': {'lineas': {'L1': cargabilidad}}}}


def medida_nativa(v_min: float, perdidas: float, contexto: ContextoExperimento | None = None, **cambios) -> dict:
    """Una medición completa, con su referencia vinculada, tal como la exige RF-7."""
    contexto = contexto or contexto_de()
    return {'converge': True, 'v_min': v_min, 'perdidas_kw': perdidas, 'contexto': contexto,
            'unidades': {'v_min': 'p.u.', 'perdidas_kw': 'kW'}, 'flujo': flujo_de(v_min, perdidas),
            'reabierto': True, 'revertido': False,
            'referencia': {'contexto': replace(contexto, case_id='caso-sin', case_role='sin_proyecto',
                                               topology_hash='f' * 64, controls_hash='1' * 64, scenario_hash='2' * 64),
                           'flujo': flujo_de(0.9, perdidas * 10 + 1.0), 'reabierto': True}, **cambios}


def _verificar(alternativa, medicion, **kw):
    return verificar_top_k([alternativa], lambda _: medicion, tolerancia_v_pu=0.01,
                           contexto=kw.pop('contexto', contexto_de()), limites=kw.pop('limites', LIMITES), **kw)


ALT = {'v_min': 0.97, 'perdidas_kw': 10.0}


def test_top_k_sin_metricas_rechaza():
    """044:RF-6 — reproduce la aceptación anterior con solo converge=True."""
    resultado = verificar_top_k([{'id': 'x'}], lambda _: {'converge': True},
                               tolerancia_v_pu=0.01)
    assert resultado['verificada'] is False
    assert resultado['elegida'] is None
    assert resultado['descartadas'][0]['motivo']


def test_medicion_completa_verifica_y_trae_su_evaluacion():
    """044:RF-7 — la completa pasa; la elegida lleva lo validado y el juicio nativo, con las claves públicas."""
    r = _verificar(ALT, medida_nativa(0.971, 10.5))
    assert r['verificada'] and r['elegida'] == ALT and r['descartadas'] == []
    assert r['gemelo'] == ALT and r['digsilent']['converge']
    assert r['evaluacion']['clase'] == 'accepted' and r['validacion']['valida']
    assert r['validacion']['diferencias']['perdidas_fraccion'] == pytest.approx(.05)
    assert r['validacion']['unidades'] == {'v_min': 'p.u.', 'perdidas_kw': 'kW'}


@pytest.mark.parametrize('lado', ['prediccion', 'medicion'])
@pytest.mark.parametrize('clave', ['v_min', 'perdidas_kw'])
@pytest.mark.parametrize('valor', [None, float('nan'), float('inf'), -float('inf'), 'invalido', True])
def test_top_k_nan_rechaza(lado, clave, valor):
    """044:RF-6 — validar ambos lados evita ceros ficticios y comparaciones con NaN."""
    alternativa = dict(ALT)
    medicion = medida_nativa(0.97, 10.0)
    (alternativa if lado == 'prediccion' else medicion)[clave] = valor
    resultado = _verificar(alternativa, medicion)
    assert resultado['verificada'] is False
    assert clave in resultado['descartadas'][0]['motivo']


@pytest.mark.parametrize('lado', ['prediccion', 'medicion'])
def test_top_k_perdidas_negativas_rechaza(lado):
    """044:RF-6 — una pérdida negativa no es una medida física admisible."""
    alternativa = dict(ALT)
    medicion = medida_nativa(0.97, 10.0)
    (alternativa if lado == 'prediccion' else medicion)['perdidas_kw'] = -1.0
    assert not _verificar(alternativa, medicion)['verificada']


def test_top_k_descarta_y_continua_con_evidencia():
    """044:RF-6 — descartar no impide encontrar una alternativa completa posterior."""
    alternativas = [{'id': 'mala'}, {'id': 'valida', **ALT}]
    guardados = []
    resultado = verificar_top_k(
        alternativas, lambda _: medida_nativa(0.971, 10.5), tolerancia_v_pu=0.01, contexto=contexto_de(),
        limites=LIMITES, guardar=lambda *args: guardados.append(args))
    assert resultado['verificada']
    assert resultado['elegida']['id'] == 'valida'
    assert len(guardados) == len(resultado['descartadas']) == 1


@pytest.mark.parametrize('clave', ['tolerancia_v_pu', 'tolerancia_perdidas', 'tolerancia_perdidas_kw'])
@pytest.mark.parametrize('valor', [float('nan'), float('inf'), -1, True])
def test_tolerancia_invalida_no_habilita_verificacion(clave, valor):
    """044:RF-6 — NaN en la política tampoco puede convertir diferencias en aceptación."""
    parametros = {'tolerancia_v_pu': 0.01, 'tolerancia_perdidas': 0.2, clave: valor}
    with pytest.raises(ValueError, match='tolerancia'):
        verificar_top_k([], lambda _: None, **parametros)


def test_perdida_cero_no_oculta_error():
    """044:RF-6 — una predicción cero no puede suprimir la comparación de pérdidas."""
    alternativa = {'v_min': 0.97, 'perdidas_kw': 0}
    assert not _verificar(alternativa, medida_nativa(0.97, 10))['verificada']
    # Sin tolerancia absoluta declarada no se sabe cuánto es demasiado: no se acepta.
    motivo = _verificar(alternativa, medida_nativa(0.97, 0.5))['descartadas'][0]['motivo']
    assert 'tolerancia absoluta' in motivo
    assert not _verificar(alternativa, medida_nativa(0.97, 0.5), tolerancia_perdidas_kw=0.1)['verificada']
    assert _verificar(alternativa, medida_nativa(0.97, 0.5), tolerancia_perdidas_kw=1.0)['verificada']
    assert _verificar(alternativa, medida_nativa(0.97, 0.0))['verificada']


@pytest.mark.parametrize('campo,valor', [('year', 2025), ('case_id', 'otro'), ('source_mode', 'mdb'),
                                         ('source_fingerprint', '9' * 64), ('period', '2026-08'),
                                         ('project', 'Q'), ('topology_hash', '8' * 64)])
def test_top_k_contexto_distinto_rechaza(campo, valor):
    """044:RF-7 — una medida de otro año, caso o fuente es correcta, pero de otra cosa."""
    medido = replace(contexto_de(), **{campo: valor})
    r = _verificar(ALT, medida_nativa(0.97, 10.0, contexto=contexto_de()) | {'contexto': medido})
    assert not r['verificada'] and campo in r['descartadas'][0]['motivo']


@pytest.mark.parametrize('contexto', [None, 'texto', {'project': 'P'}])
def test_medicion_sin_contexto_valido_rechaza(contexto):
    """044:RF-7 — sin contexto en la medición no se sabe de qué caso es."""
    r = _verificar(ALT, medida_nativa(0.97, 10.0) | {'contexto': contexto})
    assert not r['verificada'] and 'contexto' in r['descartadas'][0]['motivo']


def test_sin_contexto_del_experimento_no_se_acepta():
    """044:RF-7 — con la medición entera, pero sin contexto contra el que comprobarla, tampoco."""
    r = verificar_top_k([ALT], lambda _: medida_nativa(0.97, 10.0), tolerancia_v_pu=0.01, limites=LIMITES)
    assert not r['verificada'] and 'contexto del experimento' in r['descartadas'][0]['motivo']


@pytest.mark.parametrize('cambios,texto', [
    ({'flujo': None}, 'flujo completo'),
    ({'flujo': {'tensiones': flujo_de(.97, 10.)['tensiones'], 'perdidas': flujo_de(.97, 10.)['perdidas']}}, 'cargabilidad'),
    ({'flujo': flujo_de(.97, 10., cargabilidad=float('nan'))}, 'no finitos'),
    ({'flujo': flujo_de(.97, 10.) | {'perdidas': {'ausente': 'sin calcular'}}}, 'perdidas'),
    ({'reabierto': False}, 'reabrir'),
    ({'reabierto': None}, 'reabrir'),
    ({'revertido': None}, 'siga aplicada'),
    ({'unidades': {'v_min': 'p.u.', 'perdidas_kw': 'MW'}}, 'unidades'),
    ({'unidades': None}, 'unidades'),
    ({'referencia': None}, 'referencia'),
    ({'flujo': flujo_de(.96, 10.)}, 'mínimo de su flujo'),
    ({'flujo': flujo_de(.97, 12.)}, 'total de su flujo'),
])
def test_medicion_incompleta_rechaza(cambios, texto):
    """044:RF-6, 044:RF-7 — converge=True no basta: cada pieza que falte tumba la alternativa."""
    r = _verificar(ALT, medida_nativa(0.97, 10.0) | cambios)
    assert not r['verificada'] and texto in r['descartadas'][0]['motivo']


@pytest.mark.parametrize('cambios,texto', [
    ({'flujo': None}, 'flujo completo'),
    ({'reabierto': False}, 'referencia sin reabrir'),
    ({'contexto': None}, 'referencia sin contexto'),
    ({'contexto': replace(contexto_de(), year=2025, case_role='sin_proyecto')}, 'year'),
    ({'contexto': contexto_de('caso_base')}, 'caso caso_base'),
])
def test_referencia_no_vinculada_rechaza(cambios, texto):
    """044:RF-7 — la referencia también es nativa, completa, reabierta y del mismo caso de partida."""
    medida = medida_nativa(0.97, 10.0)
    medida['referencia'] = {**medida['referencia'], **cambios}
    r = _verificar(ALT, medida)
    assert not r['verificada'] and texto in r['descartadas'][0]['motivo']


def test_convergente_con_sobrecarga_se_rechaza_por_la_norma():
    """044:RF-7 — todo completo y cerca de lo predicho, con una línea al 120 %: no se acepta."""
    medida = medida_nativa(0.97, 10.0) | {'flujo': flujo_de(.97, 10., cargabilidad=120.)}
    r = _verificar(ALT, medida)
    assert not r['verificada'] and 'converged_with_violations' in r['descartadas'][0]['motivo']
    assert 'cargabilidad' in r['descartadas'][0]['motivo']


def test_sin_limites_de_la_norma_queda_sin_aceptar():
    """044:RF-7 — sin los límites del sistema no se puede decir que cumple."""
    r = _verificar(ALT, medida_nativa(0.97, 10.0), limites=None)
    assert not r['verificada'] and 'quarantine' in r['descartadas'][0]['motivo']


def test_peor_que_la_referencia_se_rechaza():
    """044:RF-7 — la comparación con «Sin proyecto» decide: más pérdidas que sin la obra no se aceptan."""
    medida = medida_nativa(0.97, 10.0)
    medida['referencia']['flujo'] = flujo_de(0.9, 5.0)
    r = _verificar(ALT, medida)
    assert not r['verificada'] and 'pérdidas' in r['descartadas'][0]['motivo']


def test_rol_sin_criterio_no_se_acepta_por_omision():
    """044:RF-7 — «cargas_nuevas» no se acepta como obra: no se juzga con el criterio de otro caso.

    Desde la 045 (045:RF-1) ``evaluar`` tiene su caso y lo da por contrafactual; antes no tenía criterio. En los
    dos, lo que importa es que no se verifica y el motivo dice por qué.
    """
    contexto = contexto_de('cargas_nuevas')
    r = _verificar(ALT, medida_nativa(0.97, 10.0, contexto=contexto), contexto=contexto)
    motivo = r['descartadas'][0]['motivo']
    assert not r['verificada'] and ('criterio de evaluación' in motivo or 'counterfactual' in motivo), motivo


def test_validar_reune_todos_los_motivos():
    """044:RF-6 — el informe dice todo lo que falta, no solo lo primero."""
    v = validar_medicion_nativa({}, {'converge': True}, contexto_de(), politica={
        'tolerancia_v_pu': .01, 'tolerancia_perdidas': .2})
    assert not v['valida'] and v['diferencias'] is None and len(v['motivos']) >= 7
    assert validar_medicion_nativa(ALT, medida_nativa(.97, 10.), contexto_de(), politica={
        'tolerancia_v_pu': .01, 'tolerancia_perdidas': .2})['valida']


def test_ningun_llamador_verifica_sin_contexto():
    """044:RF-7 — quien llame a ``verificar_top_k`` en producción le pasa contexto y límites.

    Desde la T5 la llama la aceptación de lo aplicado en la 052 (``web/services._aceptar_con_medicion_nativa``).
    Esto vigila a ese llamador y a los siguientes: sin los dos, todo se descartaría sin saber por qué.
    """
    for carpeta in ('src', 'tools'):
        for ruta in (RAIZ / carpeta).rglob('*.py'):
            texto = ruta.read_text(encoding='utf-8')
            if 'verificar_top_k' not in texto:
                continue
            for nodo in ast.walk(ast.parse(texto)):
                if isinstance(nodo, ast.Call) and getattr(nodo.func, 'attr', getattr(nodo.func, 'id', '')) == 'verificar_top_k':
                    nombres = {k.arg for k in nodo.keywords}
                    assert {'contexto', 'limites'} <= nombres, f'{ruta}:{nodo.lineno}'
