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
        data = lectura(rol, variaciones=_esperadas)
        data.update(project='P', feeders=[feeder])
        data['caso_nativo']['nombre'] = {'caso_base': 'Caso base', 'sin_proyecto': 'Sin proyecto',
                                       'con_proyecto': 'Con proyecto', 'cargas_nuevas': 'Cargas nuevas'}[rol]
        (carpeta/f'{etiqueta}_{rol}.json').write_text(json.dumps(data), encoding='utf-8')
        return {'ruta': f'{etiqueta}_{rol}.json', 'rc': 0, 'pid': 1, 'lectura': data}

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
        proyecto='P', planes=tmp_path, barra='B', q_kvar=300, guion_local=True)
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


@pytest.mark.parametrize('rol_malo', ['caso_base', 'sin_proyecto'])
@pytest.mark.parametrize('defecto', ['rc', 'pid', 'ausente', 'json', 'lista', 'vacio', 'version',
                                    'reapertura', 'proyecto', 'carpeta', 'alimentadores',
                                    'caso', 'nombre_caso', 'id_caso', 'flujo', 'nan'])
def test_preflight_fallido_no_llama_escritor_y_conserva_motivos(
        guion, tmp_path, monkeypatch, rol_malo, defecto):
    """044:RF-9 — una referencia no válida no autoriza crear obra, caso ni variación."""
    import json
    from pathlib import Path

    base = {'project': 'PROYECTO-ENSAYO', 'folder': 'CARPETA-ENSAYO', 'feeders': ['ALIM-A']}
    monkeypatch.setattr(guion, 'plan_firmado', lambda *_: dict(base))
    monkeypatch.setattr(guion, '_web', lambda *_: object())
    writers = []

    def correr(cmd, _log):
        if cmd[0] == str(guion.OBRAS):
            writers.append(cmd)
            raise AssertionError('No debe alcanzarse el escritor')
        assert cmd[0] == str(guion.LECTURA)
        plan = json.loads(Path(cmd[cmd.index('--plan') + 1]).read_text(encoding='utf-8'))
        rol = plan['case']
        data = lectura(rol)
        data.update(base)
        data['caso_nativo'].update(nombre={'caso_base': 'Caso base', 'sin_proyecto': 'Sin proyecto'}[rol])
        output = Path(cmd[cmd.index('--output-json') + 1])
        rc = 0
        if rol == rol_malo:
            if defecto == 'ausente':
                return 0, 123
            if defecto == 'json':
                output.write_text('{JSON no valido', encoding='utf-8')
                return 0, 123
            if defecto == 'rc': rc = 2
            elif defecto == 'lista': data = []
            elif defecto == 'vacio': data = {}
            elif defecto == 'version': data['pf_version'] = None
            elif defecto == 'reapertura': data['reopen_verified'] = False
            elif defecto == 'proyecto': data['project'] = 'OTRO-PROYECTO'
            elif defecto == 'carpeta': data['folder'] = 'OTRA-CARPETA'
            elif defecto == 'alimentadores': data['feeders'] = ['OTRO-ALIM']
            elif defecto == 'caso': data['caso_nativo']['rol'] = 'con_proyecto'
            elif defecto == 'nombre_caso': data['caso_nativo']['nombre'] = 'Otro caso'
            elif defecto == 'id_caso': data['caso_nativo']['id'] = ''
            elif defecto == 'flujo': data['flujo'] = {}
            elif defecto == 'nan': data['flujo']['tensiones']['valores']['ElmTerm:B2'] = float('nan')
        output.write_text(json.dumps(data), encoding='utf-8')
        return rc, None if rol == rol_malo and defecto == 'pid' else 123

    monkeypatch.setattr(guion, '_correr', correr)
    evidence = tmp_path / 'evidencia'
    rc = guion.main(['--espacio', 'ENSAYO', '--proyecto', base['project'], '--alimentador', 'ALIM-A',
                     '--planes', str(tmp_path), '--evidencia', str(evidence),
                     'obras', '--barra', 'B2', '--q-kvar', '300', '--guion-local'])
    report = json.loads((evidence / guion.MANIFIESTO).read_text(encoding='utf-8'))
    assert writers == []
    assert rc == 2 and report['errores']
    preflight = report['obras']['preflight']
    assert preflight['ok'] is False and preflight['motivos']
    assert rol_malo in preflight['referencias']
    assert not report['obras']['obra'].get('variacion')
    assert not (evidence / 'plan_aplicar.json').exists()
    assert any('preflight' in error for error in report['errores'])


@pytest.mark.parametrize('rol_retiro', ['caso_base', 'sin_proyecto'])
@pytest.mark.parametrize('cambio', ['intacta', 'banco', 'tension', 'caso', 'ausente'])
def test_retiro_relee_y_contrasta_ambas_referencias(
        guion, tmp_path, monkeypatch, rol_retiro, cambio):
    """048:RF-9 — ni retiro exitoso ni Con intacto ocultan cambios posteriores en Base/Sin."""
    import json
    from pathlib import Path
    from types import SimpleNamespace
    base = {'project': 'PROYECTO-ENSAYO', 'folder': 'CARPETA-ENSAYO', 'feeders': ['ALIM-A']}
    monkeypatch.setattr(guion, 'plan_firmado', lambda *_: dict(base))
    monkeypatch.setattr(guion, '_web', lambda *_: object())
    writers = []
    lecturas_finales = []

    def correr(cmd, _log):
        output = Path(cmd[cmd.index('--output-json') + 1])
        if cmd[0] == str(guion.OBRAS):
            writers.append(cmd)
            data = ({'retiradas': ['Obra_condensador_ALIM-A']}
                    if '--retirar-obras' in cmd else {'obras': [{'variacion': 'Obra_condensador_ALIM-A'}]})
        else:
            plan = json.loads(Path(cmd[cmd.index('--plan') + 1]).read_text(encoding='utf-8'))
            rol = plan['case']
            data = lectura(rol, bancos=[('BC_PREVIO', 0.3)],
                           variaciones=plan.get('variaciones_esperadas') or [])
            data.update(base)
            data['caso_nativo']['nombre'] = {'caso_base': 'Caso base', 'sin_proyecto': 'Sin proyecto',
                                           'con_proyecto': 'Con proyecto', 'cargas_nuevas': 'Cargas nuevas'}[rol]
            if output.name.startswith('lectura_retirada_'):
                lecturas_finales.append(rol)
                if rol == rol_retiro:
                    if cambio == 'ausente': return 0, 123
                    if cambio == 'banco': data['topologia']['grafo']['bancos'][0]['q_mvar'] = 0.45
                    elif cambio == 'tension': data['flujo']['tensiones']['valores']['ElmTerm:B2'] = 0.8
                    elif cambio == 'caso': data['caso_nativo']['rol'] = 'con_proyecto'
        output.write_text(json.dumps(data), encoding='utf-8')
        return 0, 123

    monkeypatch.setattr(guion, '_correr', correr)
    args = SimpleNamespace(url='http://127.0.0.1:1', espacio='ENSAYO', proyecto=base['project'],
                           alimentador='ALIM-A', planes=tmp_path, barra='B2', q_kvar=300, guion_local=True)
    r = guion.etapa_obras(args, tmp_path)
    assert len(writers) == 2  # Únicamente aplicar y retirar la variación propia.
    assert {'caso_base', 'sin_proyecto'} <= set(lecturas_finales)
    assert r['retiro']['ok'] is (cambio == 'intacta')
    for rol in ('caso_base', 'sin_proyecto'):
        check = r['retiro']['referencias'][rol]
        assert check['ok'] is (cambio == 'intacta' or rol != rol_retiro)
        if not check['ok']:
            assert check['motivos']


def test_preflight_rechazado_no_inventa_veredictos_y_conserva_049(guion, tmp_path):
    """044/049:RF-9 — el fallo de obras no fabrica44/45/48 ni oculta otro bloqueo leído."""
    import json
    (tmp_path / 'protecciones_capacidades.json').write_text(
        json.dumps({'informe': {'version': '24.0.2'}}), encoding='utf-8')
    (tmp_path / 'protecciones_estado.json').write_text(
        json.dumps({'disponibilidad': {'disponible': False, 'faltan': ['fichas']}}), encoding='utf-8')
    preflight = {'ok': False, 'motivos': ['caso_base: lectura ausente'], 'referencias': {}}
    v = guion.veredictos(tmp_path, {'obras': {'preflight': preflight}, 'protecciones': {'trabajo': 'done'}})
    assert v['preflight']['cerrable'] is False
    assert not {'044', '045', '048'} & set(v)
    assert v['049']['cerrable'] is False and v['049']['bloqueo'] == ['fichas']


@pytest.mark.parametrize('mutada', [False, True])
def test_veredictos_recalculan_conservacion_sin_confiar_en_resumen(guion, tmp_path, monkeypatch, mutada):
    """048:RF-9 — un resumen guardado «ok» no puede ocultar el banco cambiado tras retirar."""
    import json
    from copy import deepcopy
    base = {'project': 'P', 'folder': 'CARPETA', 'feeders': ['F1']}
    lecturas = {}
    metadata = {}
    for etapa, roles in [('antes', ('caso_base', 'sin_proyecto')),
                         ('despues', guion.ROLES), ('retirada', ('caso_base', 'sin_proyecto', 'con_proyecto'))]:
        for rol in roles:
            d = lectura(rol, bancos=[('BC_PREVIO', 0.3)])
            d.update(base)
            d['caso_nativo']['nombre'] = {'caso_base': 'Caso base', 'sin_proyecto': 'Sin proyecto',
                                        'con_proyecto': 'Con proyecto', 'cargas_nuevas': 'Cargas nuevas'}[rol]
            lecturas[f'{etapa}/{rol}'] = d
            metadata[f'{etapa}/{rol}'] = {'ruta': f'{etapa}_{rol}.json', 'pid': 123, 'rc': 0}
    if mutada:
        lecturas['retirada/caso_base']['topologia']['grafo']['bancos'][0]['q_mvar'] = 0.45
    for label, d in lecturas.items():
        (tmp_path / metadata[label]['ruta']).write_text(json.dumps(d), encoding='utf-8')
    (tmp_path / 'plan_antes_caso_base.json').write_text(json.dumps(base), encoding='utf-8')
    (tmp_path / 'obras_retirar.json').write_text(json.dumps({'retiradas': ['V']}), encoding='utf-8')
    (tmp_path / 'obras_aplicar.json').write_text(json.dumps({'result': {'informe': {}}}), encoding='utf-8')
    contexto = {'lecturas': lecturas, 'con': lecturas['despues/con_proyecto'], 'base': {},
                'limites': None, 'tolerancias': {'tolerancia_v_pu': .01, 'tolerancia_perdidas': .1}}
    monkeypatch.setattr(guion, 'contexto_de_aceptacion', lambda *_: contexto)
    # Solo se aísla el cálculo eléctrico ajeno a esta prueba del agregador.
    monkeypatch.setattr(guion, 'veredicto_044', lambda *a, **k: {'juicio': {'clase': 'accepted'}})
    check = {r + '_intacto': {'ok': True, 'motivos': []} for r in ('caso_base', 'sin_proyecto')}
    monkeypatch.setattr(guion, 'veredicto_048', lambda *a, **k: {
        'checks': deepcopy(check), 'persiste': True, 'admisible': True, 'cerrable': True})
    monkeypatch.setattr(guion, 'veredicto_045', lambda *a, **k: {})
    manifiesto = {'obras': {'obra': {'variacion': 'V', 'barra': 'B2', 'q_kvar': 300},
                            'lecturas': metadata, 'retiro': {'ok': True, 'rc': 0}}}
    v = guion.veredictos(tmp_path, manifiesto)
    assert v['retiro']['ok'] is (not mutada)
    assert v['048']['checks']['caso_base_intacto']['ok'] is (not mutada)
    assert v['048']['persiste'] is v['048']['cerrable'] is (not mutada)


def _custodia_sintetica(guion, carpeta):
    import json
    carpeta.mkdir(exist_ok=True)
    (carpeta / 'testigo.txt').write_text('captura original\n', encoding='utf-8')
    manifiesto = {'schema': guion.ESQUEMA, 'proyecto': 'P', 'alimentador': 'F', 'espacio': 'E',
                  'commit': 'a' * 40, 'escrito': '2026-01-01T00:00:00+00:00',
                  'sha256': guion.huellas(carpeta)}
    (carpeta / guion.MANIFIESTO).write_text(json.dumps(manifiesto), encoding='utf-8')
    return manifiesto


def _argv_custodia(carpeta, etapa='veredictos'):
    return ['--espacio', 'E', '--proyecto', 'P', '--alimentador', 'F',
            '--planes', str(carpeta), '--evidencia', str(carpeta), etapa]


@pytest.mark.parametrize('defecto', ['cambiado', 'ausente', 'extra', 'sin_huellas', 'vacio',
                                    'schema', 'ruta', 'hash', 'json', 'lista'])
def test_veredictos_rechazan_custodia_danada_sin_recertificar(
        guion, tmp_path, monkeypatch, defecto, capsys):
    """044:RF-9; 081:RF-47 — alterar una evidencia no la vuelve nueva al recalcular."""
    import json
    m = _custodia_sintetica(guion, tmp_path)
    ruta = tmp_path / guion.MANIFIESTO
    if defecto == 'cambiado': (tmp_path / 'testigo.txt').write_text('otra captura', encoding='utf-8')
    elif defecto == 'ausente': (tmp_path / 'testigo.txt').unlink()
    elif defecto == 'extra': (tmp_path / 'no_custodiado.json').write_text('{}', encoding='utf-8')
    elif defecto == 'sin_huellas': m.pop('sha256')
    elif defecto == 'vacio': m['sha256'] = {}
    elif defecto == 'schema': m['schema'] = 'otro'
    elif defecto == 'ruta': m['sha256'] = {'../fuera.txt': 'a' * 64}
    elif defecto == 'hash': m['sha256']['testigo.txt'] = 'sin-huella'
    if defecto not in ('cambiado', 'ausente', 'extra'):
        ruta.write_text('{no-json' if defecto == 'json' else json.dumps([] if defecto == 'lista' else m),
                        encoding='utf-8')
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    calls = []
    monkeypatch.setattr(guion, 'veredictos', lambda *a: calls.append(a) or {})
    rc = guion.main(_argv_custodia(tmp_path))
    assert rc == 2 and calls == []
    mensaje = capsys.readouterr().out.lower()
    assert 'custodia' in mensaje
    motivo = {'cambiado': 'testigo.txt', 'ausente': 'testigo.txt', 'extra': 'sin custodia',
              'sin_huellas': 'faltan huellas', 'vacio': 'faltan huellas', 'schema': 'esquema',
              'ruta': 'ruta no válida', 'hash': 'huella no válida', 'json': 'expecting',
              'lista': 'esquema'}[defecto]
    assert motivo in mensaje
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == antes


def test_recalcular_con_otra_revision_conserva_procedencia_de_captura(guion, tmp_path, monkeypatch):
    """044:RF-9; 081:RF-47 — revisión del cálculo y captura son procedencias diferentes."""
    import json
    inicial = _custodia_sintetica(guion, tmp_path)
    monkeypatch.setattr(guion, '_commit', lambda: 'b' * 40)
    assert guion.main(_argv_custodia(tmp_path)) == 0
    despues = json.loads((tmp_path / guion.MANIFIESTO).read_text(encoding='utf-8'))
    for clave in ('commit', 'escrito', 'sha256'):
        assert despues[clave] == inicial[clave]
    assert despues['revision_veredictos']['commit'] == 'b' * 40
    assert despues['revision_veredictos']['manifiesto_origen_sha256']
    assert guion.comprobar_huellas(tmp_path, despues) == []


def test_veredictos_sin_manifiesto_no_inventan_primera_captura(guion, tmp_path):
    """044:RF-9 — el recalculador requiere una captura anterior custodiada."""
    assert guion.main(_argv_custodia(tmp_path)) == 2
    assert list(tmp_path.iterdir()) == []


def test_captura_previa_danada_bloquea_otra_etapa(guion, tmp_path, monkeypatch):
    """044:RF-9 — no se llama al productor ni se sella de nuevo una custodia corrupta."""
    _custodia_sintetica(guion, tmp_path)
    (tmp_path / 'testigo.txt').write_text('cambiado', encoding='utf-8')
    antes = (tmp_path / guion.MANIFIESTO).read_bytes()
    calls = []
    monkeypatch.setattr(guion, 'etapa_protecciones', lambda *a: calls.append(a) or {})
    assert guion.main(_argv_custodia(tmp_path, 'protecciones')) == 2
    assert calls == [] and (tmp_path / guion.MANIFIESTO).read_bytes() == antes


def test_primera_captura_y_etapa_posterior_preservan_origen(guion, tmp_path, monkeypatch):
    """044:RF-9 — primera captura legítima y nueva etapa conservan cada procedencia."""
    import json
    def etapa(_args, carpeta):
        (carpeta / 'protecciones_capacidades.json').write_text('{}', encoding='utf-8')
        return {'trabajo': 'done'}
    monkeypatch.setattr(guion, 'etapa_protecciones', etapa)
    monkeypatch.setattr(guion, 'veredictos', lambda *a: {})
    monkeypatch.setattr(guion, '_commit', lambda: 'a' * 40)
    assert guion.main(_argv_custodia(tmp_path, 'protecciones')) == 0
    primera = json.loads((tmp_path / guion.MANIFIESTO).read_text(encoding='utf-8'))
    assert guion.main(_argv_custodia(tmp_path)) == 0
    monkeypatch.setattr(guion, '_commit', lambda: 'b' * 40)
    # El productor de la segunda etapa es sintético; no abre ningún motor.
    def obras(_args, carpeta):
        (carpeta / 'obras.json').write_text('{}', encoding='utf-8')
        return {'obra': {}}
    monkeypatch.setattr(guion, 'etapa_obras', obras)
    args = _argv_custodia(tmp_path, 'obras') + ['--barra', 'B', '--q-kvar', '300']
    assert guion.main(args) == 0
    segunda = json.loads((tmp_path / guion.MANIFIESTO).read_text(encoding='utf-8'))
    assert segunda['commit'] == primera['commit'] == 'a' * 40
    assert segunda['escrito'] == primera['escrito']
    assert segunda['capturas']['protecciones']['commit'] == 'a' * 40
    assert segunda['capturas']['obras']['commit'] == 'b' * 40
    assert segunda['revision_veredictos']['commit'] == 'b' * 40
    assert guion.comprobar_huellas(tmp_path, segunda) == []


def test_primera_captura_no_sella_ficheros_previos_sin_custodia(guion, tmp_path, monkeypatch):
    """044:RF-9 — una carpeta antigua sin manifiesto no es una primera captura vacía."""
    previo = tmp_path / 'lectura_previa.json'
    previo.write_text('{}', encoding='utf-8')
    calls = []
    monkeypatch.setattr(guion, 'etapa_protecciones', lambda *a: calls.append(a) or {})
    assert guion.main(_argv_custodia(tmp_path, 'protecciones')) == 2
    assert calls == [] and list(tmp_path.iterdir()) == [previo]


def test_revision_no_publica_si_la_lectura_cambia_durante_el_calculo(guion, tmp_path, monkeypatch):
    """044:RF-9 — la validación inicial no autoriza un cálculo sobre bytes sustituidos."""
    _custodia_sintetica(guion, tmp_path)
    antes = (tmp_path / guion.MANIFIESTO).read_bytes()
    def calcular(*_):
        (tmp_path / 'testigo.txt').write_text('cambiado en el cálculo', encoding='utf-8')
        return {}
    monkeypatch.setattr(guion, 'veredictos', calcular)
    assert guion.main(_argv_custodia(tmp_path)) == 2
    assert (tmp_path / guion.MANIFIESTO).read_bytes() == antes


def test_fallo_publicacion_conserva_manifiesto_y_no_deja_temporal(guion, tmp_path, monkeypatch):
    """044:RF-9; 081:RF-47 — un error de disco no destruye la custodia anterior."""
    _custodia_sintetica(guion, tmp_path)
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    def fallar(*_):
        raise OSError('disco de prueba no disponible')
    monkeypatch.setattr(guion.os, 'replace', fallar)
    assert guion.main(_argv_custodia(tmp_path)) == 2
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == antes


def test_el_perfil_de_la_captura_queda_anotado_y_no_cambia(guion, tmp_path, monkeypatch):
    """044:RF-9 — PE10 de prueba (2026-11-10): sin ``--perfil`` no quedaba cuál era el activo y la prueba juzgaba
    sin los límites de tensión de la empresa; ahora se anota, y otro perfil no puede juzgar la misma captura."""
    import json
    from pathlib import Path

    from convertersmartgrid.perfil_empresa import VARIABLE_RUTA
    perfil = tmp_path.parent / f'{tmp_path.name}_perfil.json'
    perfil.write_text('{}', encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))
    assert guion.perfil_de_la_captura(None, {}) == perfil
    assert guion.perfil_de_la_captura(None, {'perfil': 'otro.json'}) == Path('otro.json')
    _custodia_sintetica(guion, tmp_path)
    usados = []
    monkeypatch.setattr(guion, 'veredictos', lambda _c, _m, p=None: usados.append(p) or {})
    assert guion.main(_argv_custodia(tmp_path)) == 0
    assert json.loads((tmp_path / guion.MANIFIESTO).read_text(encoding='utf-8'))['perfil'] == str(perfil)
    assert usados == [perfil]
    otro = tmp_path.parent / f'{tmp_path.name}_otro.json'
    otro.write_text('{}', encoding='utf-8')
    assert guion.main([*_argv_custodia(tmp_path)[:-1], '--perfil', str(otro), 'veredictos']) == 2


def test_captura_existente_no_se_sobrescribe(guion, tmp_path, monkeypatch):
    """044:RF-9 — repetir una captura requiere carpeta nueva, no reemplazar sus pruebas."""
    import json
    m = _custodia_sintetica(guion, tmp_path)
    m['protecciones'] = {'trabajo': 'done'}
    (tmp_path / guion.MANIFIESTO).write_text(json.dumps(m), encoding='utf-8')
    antes = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    calls = []
    monkeypatch.setattr(guion, 'etapa_protecciones', lambda *a: calls.append(a) or {})
    assert guion.main(_argv_custodia(tmp_path, 'protecciones')) == 2
    assert calls == [] and {p.name: p.read_bytes() for p in tmp_path.iterdir()} == antes


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
