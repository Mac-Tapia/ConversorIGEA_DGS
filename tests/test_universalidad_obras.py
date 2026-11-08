"""042:RF-39/50: las muestras no deciden capacidades ni tensiones del usuario."""
from copy import deepcopy

import pytest

from convertersmartgrid import escalera_optima as eo, perfil_empresa as pe


def _perfil(esc=None):
    perfil, _ = pe.completar_planeamiento({})
    perfil['escalera'].update(esc or {})
    return perfil


def test_sin_par_de_tensiones_se_omite_solo_nivel_con_motivo():
    """042:RF-50 — no decidir una migración de muestra; conservar otras obras."""
    p = eo.parametros(_perfil())
    troncal = [{'nombre': 'T1', 'largo_m': 1000, 'corriente_a': 100}]
    vs, avisos = eo.variantes('ALIM-UNIVERSAL', 10, troncal,
                            [{'barra': 'B1', 'existe': True}], [], p,
                            banco_kvar=200, nivel={'km': 1, 'seds': 1})
    assert not [v for v in vs if 'nivel' in v.escalones]
    assert any('bancos' in v.escalones for v in vs)
    assert any('migrar_desde_kv' in a and 'migrar_a_kv' in a for a in avisos)
    assert p.migrar_desde_kv is p.migrar_a_kv is None


@pytest.mark.parametrize('desde,hasta', [(10, 22.9), (20, 33), (13.8, 24.9)])
def test_par_explicito_conserva_propuesta_sin_geografia_fija(desde, hasta):
    """042:RF-50 — toda elección válida conserva su destino literal."""
    p = eo.parametros(_perfil({'migrar_desde_kv': desde, 'migrar_a_kv': hasta}))
    avisos = []
    (v,) = eo._escalon_nivel('ALIM-UNIVERSAL', desde, {'km': 1, 'seds': 1}, p, avisos)
    assert v.obras == [{'alimentador': 'ALIM-UNIVERSAL', 'casos': ['Con proyecto'],
                        'kv_destino': hasta, 'clase': 'tension'}]
    assert not avisos


@pytest.mark.parametrize('esc', [{'migrar_desde_kv': 20}, {'migrar_a_kv': 33}])
def test_par_incompleto_no_se_completa_con_muestras(esc):
    """042:RF-50 — un único valor no autoriza inventar el otro."""
    p = eo.parametros(_perfil(esc))
    avisos = []
    assert eo._escalon_nivel('ALIM-UNIVERSAL', 10, {'km': 1}, p, avisos) == []
    assert avisos and p.migrar_desde_kv is p.migrar_a_kv is None


@pytest.mark.parametrize('valor', [0, -1, True, float('nan'), float('inf'), 'no-numero'])
def test_tension_explicita_invalida_se_rechaza(valor):
    """042:RF-50 — no sustituir un valor inválido por un destino de muestra."""
    with pytest.raises(eo.EscaleraError, match='migrar_'):
        eo.parametros(_perfil({'migrar_desde_kv': 20, 'migrar_a_kv': valor}))


@pytest.mark.parametrize('config', [{'10': float('inf')}, {'inf': 300}, {True: 300},
                                   {'NaN': 300}, {'10': 10 ** 400}])
def test_bancos_no_admiten_capacidad_o_tension_no_finita(config):
    """042:RF-39 — las capacidades elegidas deben ser números finitos positivos."""
    with pytest.raises(pe.PerfilError, match='bancos_kvar_por_tension'):
        pe.bancos_kvar_por_tension({'calibracion': {'bancos_kvar_por_tension': config}})


def test_servicio_sin_bancos_no_activa_modulos_de_muestra(tmp_path, monkeypatch):
    """042:RF-39 — continuar el cálculo posible con ausencia explícita y aviso."""
    from test_casos_por_anio import _escalera_falsa
    lector_real = pe.bancos_kvar_por_tension
    services, ws, ctx, _, _, _ = _escalera_falsa(tmp_path, monkeypatch, lambda _: {}, {})
    monkeypatch.setattr(pe, 'bancos_kvar_por_tension', lector_real)
    r = services.obras_escalera(ws, ctx, 'PROYECTO-UNIVERSAL', ['F1'], solo_comun=True)
    assert r['kvar'] is None
    assert any('banco' in a.lower() and 'omit' in a.lower() for a in r['avisos'])


def test_servicio_rechaza_banco_invalido_antes_de_leer_proyecto(tmp_path, monkeypatch):
    """042:RF-39 — un perfil defectuoso no dispara acciones ni fallback silencioso."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace
    perfil = _perfil()
    perfil['calibracion'] = {'bancos_kvar_por_tension': {'10': -1}}
    original = deepcopy(perfil)
    monkeypatch.setattr(pe, 'datos_perfil', lambda: perfil)
    llamadas = []
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_: llamadas.append('proyecto'))
    with pytest.raises(services.UserError, match='bancos_kvar_por_tension'):
        services.obras_escalera(Workspace(id='universal', root=tmp_path), object(),
                               'PROYECTO-UNIVERSAL', ['ALIM-UNIVERSAL'])
    assert llamadas == [] and perfil == original


def test_memo_no_reintroduce_bancos_de_un_perfil_anterior(tmp_path, monkeypatch):
    """042:RF-39 — una ausencia nueva no hereda capacidad de otra parametrización."""
    from test_casos_por_anio import _escalera_falsa
    lector_real = pe.bancos_kvar_por_tension
    services, ws, ctx, _, _, _ = _escalera_falsa(tmp_path, monkeypatch, lambda _: {}, {})
    monkeypatch.setattr(pe, 'bancos_kvar_por_tension', lector_real)
    perfil = pe.datos_perfil()
    perfil['calibracion'] = {'bancos_kvar_por_tension': {'13.8': 200}}
    monkeypatch.setattr(pe, 'datos_perfil', lambda: deepcopy(perfil))
    memo = {}
    primero = services.obras_escalera(ws, ctx, 'PROYECTO-UNIVERSAL', ['F1'], solo_comun=True, memo=memo)
    assert primero['kvar'] == {13.8: 200}
    perfil.pop('calibracion')
    segundo = services.obras_escalera(ws, ctx, 'PROYECTO-UNIVERSAL', ['F1'], solo_comun=True, memo=memo)
    assert segundo['kvar'] is None
    assert any('banco' in a.lower() and 'omit' in a.lower() for a in segundo['avisos'])
