"""Spec 044, T4: el diseño confirmado se relee en DIgSILENT tras una sesión nueva (044:RF-9).

Las de arriba prueban las comprobaciones de ``tools/aceptacion_nativa.py`` con lecturas mínimas; la última
relee la evidencia nativa de ``CSG_EVIDENCIA_NATIVA`` (DIgSILENT real, fuera de pytest por 084:RF-21) y vuelve
a decidir con ella. Ningún doble cierra la tarea.
"""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta, evidencia_nativa


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('aceptacion_nativa.py', 'aceptacion_nativa_044', tools_en_path=True)


def lectura(rol: str, *, bancos=(), variaciones=(), version='24.0.2', reabierta=True, u=1.0) -> dict:
    """Una lectura nativa mínima: dos barras, un tramo, sus bancos y el flujo."""
    barras = {'ElmTerm:B1': {'nombre': 'B1', 'kv': 10.0}, 'ElmTerm:B2': {'nombre': 'B2', 'kv': 10.0}}
    nodos = {k: {'kv': 10.0, 'carga_p_mw': 0.5 if k.endswith('2') else 0.0, 'fuente': k.endswith('1'), 'v_pu': 1.0}
             for k in barras}
    return {'pf_version': version, 'reopen_verified': reabierta,
            'caso_nativo': {'rol': rol, 'nombre': rol, 'id': f'IntCase:{rol}'},
            'topologia': {'variaciones_activas': list(variaciones), 'barras': barras, 'grafo': {
                'version': 3, 'nodos': nodos, 'generadores': [],
                'ramas': [{'id': 'ElmLne:L1', 'desde': 'ElmTerm:B1', 'hasta': 'ElmTerm:B2', 'cerrada': True,
                           'r_ohm': 0.5, 'x_ohm': 0.5}],
                'bancos': [{'id': f'ElmShnt:{n}', 'nodo': 'ElmTerm:B2', 'q_mvar': q, 'en_servicio': True,
                            'escalones': 1.0} for n, q in bancos]}},
            'flujo': {'tensiones': {'valores': {'ElmTerm:B1': 1.0, 'ElmTerm:B2': u}},
                      'balance': {'valores': {'cabeceras': {'F1': 500.0}}}}}


def test_la_relectura_exige_version_reapertura_caso_y_variacion(guion):
    """044:RF-9 — una lectura sin versión de DIgSILENT, sin reabrir, de otro caso o sin la variación de la obra
    no confirma nada."""
    assert guion.releida(lectura('con_proyecto', variaciones=['V1']), 'con_proyecto', ['V1'])['ok']
    for mala, motivo in ((lectura('con_proyecto', variaciones=['V1'], version=None), 'versión'),
                         (lectura('con_proyecto', variaciones=['V1'], reabierta=False), 'reapertura'),
                         (lectura('sin_proyecto', variaciones=['V1']), 'caso'),
                         (lectura('con_proyecto'), 'activas')):
        r = guion.releida(mala, 'con_proyecto', ['V1'])
        assert not r['ok'] and any(motivo in m for m in r['motivos']), r


def test_la_obra_que_no_esta_tras_reabrir_no_se_confirma(guion):
    """044:RF-9 — el banco de la obra tiene que estar tras reabrir, en su barra y con su potencia."""
    sin = lectura('sin_proyecto', bancos=[('BC1', 0.3)])
    con = lectura('con_proyecto', bancos=[('BC1', 0.3), ('BC_OBRA', 0.3)])
    assert guion.obra_presente(sin, con, 'B2', 300.0)['ok']
    assert not guion.obra_presente(sin, sin, 'B2', 300.0)['ok']
    assert not guion.obra_presente(sin, con, 'B2', 450.0)['ok']
    otro = lectura('con_proyecto', bancos=[('BC1', 0.45), ('BC_OBRA', 0.3)])
    assert any('existentes' in m for m in guion.obra_presente(sin, otro, 'B2', 300.0)['motivos'])


@pytest.mark.parametrize('no_retiro', [False, True])
def test_ensayo_retira_solo_la_variacion_que_acaba_de_crear(guion, tmp_path, monkeypatch, no_retiro):
    """044:RF-9; 098:RF-36 — el arnés pide retiro exacto al escritor real y conserva las demás obras."""
    import json
    import random
    from types import SimpleNamespace
    from test_obras_pf_guion import _calibrada_con_escenario, guion as obras

    app, feeders = _calibrada_con_escenario(random.Random(3))
    feeder = feeders[0]
    scheme = app.GetProjectFolder('scheme')
    own = f'Obra_condensador_{feeder}'
    previous = f'{own}_2'
    scheme.CreateObject('IntScheme', previous)
    base = {'project': 'P', 'feeders': [feeder]}
    monkeypatch.setattr(guion, '_web', lambda *a: object())
    monkeypatch.setattr(guion, 'plan_firmado', lambda *a: dict(base))
    monkeypatch.setattr(obras, 'restituir_flujo_original', lambda *a: 0)

    def leer(_base, rol, _esperadas, carpeta, etiqueta):
        (carpeta/f'plan_{etiqueta}_{rol}.json').write_text('{}', encoding='utf-8')
        return {'ruta': f'{etiqueta}_{rol}.json', 'rc': 0, 'pid': 1, 'lectura': {}}

    def correr(cmd, _log):
        assert cmd[0] == str(guion.OBRAS)
        plan = json.loads(Path(cmd[cmd.index('--plan')+1]).read_text(encoding='utf-8'))
        if '--retirar-obras' in cmd:
            if no_retiro:
                plan = {**plan, 'variaciones': ['variacion_ya_no_encontrada']}
            result, rc = obras.retirar_obras(app, plan)
        else:
            scheme.CreateObject('IntScheme', own)
            result, rc = {'obras': [{'variacion': own}]}, 0
        Path(cmd[cmd.index('--output-json')+1]).write_text(json.dumps(result), encoding='utf-8')
        return rc, 1

    from pathlib import Path
    monkeypatch.setattr(guion, 'leer', leer)
    monkeypatch.setattr(guion, '_correr', correr)
    args = SimpleNamespace(url='http://127.0.0.1:1', espacio='sintetico', alimentador=feeder,
        proyecto='P', planes=tmp_path, barra='B', q_kvar=30, guion_local=True)
    result = guion.etapa_obras(args, tmp_path)
    remaining = {v.loc_name for v in scheme.GetContents('*.IntScheme', 1)}
    assert (own in remaining) is no_retiro
    assert previous in remaining
    assert result['retiro']['ok'] is (not no_retiro)
    assert json.loads((tmp_path/result['retiro']['ruta']).read_text(encoding='utf-8'))['retiradas'] == ([] if no_retiro else [own])


def test_retiro_no_confirmado_conserva_evidencia_y_falla_el_arnes(guion, tmp_path, monkeypatch):
    """044:RF-9; 098:RF-36 — un exit cero sin el retiro pedido no completa el ensayo."""
    import json
    monkeypatch.setattr(guion, 'etapa_obras', lambda *a: {'obra': {}, 'retiro': {'rc': 0, 'ok': False}})
    monkeypatch.setattr(guion, 'veredictos', lambda *a: {})
    evidence = tmp_path/'evidencia'
    rc = guion.main(['--espacio', 'sintetico', '--proyecto', 'P', '--alimentador', 'F',
        '--planes', str(tmp_path), '--evidencia', str(evidence), 'obras',
        '--barra', 'B', '--q-kvar', '30', '--guion-local'])
    report = json.loads((evidence/guion.MANIFIESTO).read_text(encoding='utf-8'))
    assert rc == 2
    assert report['obras']['retiro']['ok'] is False
    assert any('retiro' in error for error in report['errores'])


def test_top_k_nativo_reabre_y_relee():
    """044:RF-9 — con DIgSILENT real: tras una sesión nueva se releen los controles (la variación activa y el
    banco en su barra) y los resultados (tensión mínima y pérdidas no negativas), y la decisión de
    ``verificar_top_k`` sale de esa relectura: un caso que converge con violaciones se rechaza por la evaluación
    eléctrica, no por converger."""
    _g, _c, manifiesto, veredictos = evidencia_nativa('obras')
    v = veredictos['044']
    lecturas = manifiesto['obras']['lecturas']
    # Cada relectura es un proceso propio: una sesión nueva de DIgSILENT, no la que escribió.
    assert len({x['pid'] for x in lecturas.values()}) == len(lecturas)
    assert v['reabierto']['ok'], v['reabierto']
    assert v['obra_presente']['ok'], v['obra_presente']
    assert v['resultados']['ok'], v['resultados']
    assert v['aceptada'] or v['rechazo_electrico'], v
    if v['rechazo_electrico']:
        assert not v['top_k']['verificada'] and v['juicio']['violaciones']
    assert v['cerrable']
