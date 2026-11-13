"""086:RF-76 — «Con proyecto» sin cargas nuevas: obras solo donde el estado actual viola límites.

Electro Oriente NJA202 (T32, 2026-11-12): calibrado a 0,568 p.u. en la fase A, sin cargas nuevas, y la web respondía
«Ningún alimentador marcado tiene cargas nuevas aplicadas: no hay nada que optimizar». Las obras solo si hay problemas:
aquí los había.
"""
from __future__ import annotations

import pytest


class _Ctx:
    def __init__(self):
        self.textos: list[str] = []

    def log(self, t):
        self.textos.append(t)

    def check_cancel(self):
        pass


def _sin_cargas(monkeypatch, tmp_path, bajas):
    from convertersmartgrid.web import services

    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [])
    monkeypatch.setattr(services, '_obras_a_comparar', lambda *a, **k: {})
    monkeypatch.setattr(services, '_transferencias_como_alternativa', lambda *a, **k: {})
    tocadas = {'reponer': 0, 'oraculo': 0}

    def _reponer(*a, **k):
        tocadas['reponer'] += 1

    def _oraculo(*a, **k):
        tocadas['oraculo'] += 1
        return {}

    monkeypatch.setattr(services, '_reponer_cargas_nuevas', _reponer)
    monkeypatch.setattr(services, '_seleccion_por_oraculo', _oraculo)
    monkeypatch.setattr(services, '_bajas_sin_cargas', lambda ws, ctx, project, feeders, opciones: bajas)
    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})
    llamadas = []

    def escalera(ws, ctx, project, feeders, *, aplicar=False, traspaso=False, previas=None, **k):
        f = feeders[0]
        llamadas.append((f, 'aplica' if aplicar else 'mide', bool(previas)))
        return {'alimentadores': [{'alimentador': f, 'elegida': None if traspaso else 'bancos 2×300 kvar', 'tabla': []}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    return services, llamadas, tocadas


def test_sin_cargas_nuevas_solo_el_que_viola_limites_lleva_obra(monkeypatch, tmp_path):
    """086:RF-76 — NJA202 viola y sube su escalera; NJA203 cumple y queda sin obras; sin reponer cargas ni oráculo."""
    services, llamadas, tocadas = _sin_cargas(monkeypatch, tmp_path, {'NJA202': ['N_7', 'N_5'], 'NJA203': []})
    ctx = _Ctx()
    r = services.escalera_por_alimentador(object(), ctx, 'P', ['NJA202', 'NJA203'])
    assert [x for x in llamadas if x[0] == 'NJA202'][-1] == ('NJA202', 'aplica', True)
    assert not [x for x in llamadas if x[0] == 'NJA203']
    assert r['caben'] == 0 and r['orden'] == [] and r['a_set_nueva'] == []
    assert r['por_alimentador']['NJA202']['barras_bajas'] == ['N_7', 'N_5']
    assert 'NJA203' not in r['por_alimentador']
    assert tocadas == {'reponer': 0, 'oraculo': 0}
    assert any('086:RF-76' in t for t in ctx.textos)


def test_cargas_pedidas_que_no_estan_aplicadas_se_rechazan_diciendo_cuales(monkeypatch, tmp_path):
    """086:RF-76 — pedir SE0001 sin que esté aplicada no se convierte en «corregir el estado actual» a escondidas."""
    services, llamadas, _ = _sin_cargas(monkeypatch, tmp_path, {'F1': ['B1']})
    with pytest.raises(services.UserError, match='SE0001'):
        services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1'], cargas=['SE0001'])
    assert llamadas == []


def test_optimizar_sin_cargas_va_a_la_escalera_por_alimentador(monkeypatch, tmp_path):
    """086:RF-76 — el botón de la web pide «Con proyecto»; sin cargas no hay bisección ni SET nueva que proponer."""
    from convertersmartgrid import perfil_empresa
    from convertersmartgrid.web import services

    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [])
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: {'planificacion': {}})
    monkeypatch.setattr(perfil_empresa, 'completar_planeamiento',
                        lambda perfil, *a, **k: ({'planificacion': {'radio_zona_set_km': None, 'set_nueva_desde_kw': None}}, []))
    monkeypatch.setattr(services, '_registrar_corrida', lambda *a, **k: None)
    vistas = []

    def por_alimentador(ws, ctx, project, feeders, **k):
        vistas.append(feeders)
        return {'project': project, 'orden': [], 'caben': 0, 'por_alimentador': {}, 'escalera': None, 'a_set_nueva': []}

    def no(*a, **k):
        raise AssertionError('sin cargas no se busca cuántas caben ni se propone SET nueva')

    monkeypatch.setattr(services, 'escalera_por_alimentador', por_alimentador)
    monkeypatch.setattr(services, 'optimizar_con_proyecto', no)
    monkeypatch.setattr(services, 'set_nueva_proponer', no)
    ctx = _Ctx()
    r = services.con_proyecto_optimizar(object(), ctx, 'P', ['NJA202'])
    assert vistas == [['NJA202']]
    assert r['escalera_por_cargas']['orden'] == [] and r['set_nueva'] == {'zonas': [], 'avisos': []}
    assert any('086:RF-76' in t for t in ctx.textos)
