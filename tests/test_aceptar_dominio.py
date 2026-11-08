"""065:RF-21: preaceptación con fuentes reales de disco, sin motor simulado."""
import json
from pathlib import Path

import pytest

from convertersmartgrid.asistente.llm_destilacion import custodiar
from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding
from convertersmartgrid.sources.snapshot import snapshot_from_paths
from tools.aceptar_dominio import preaceptar


@pytest.fixture
def caso(tmp_path):
    root = tmp_path / 'espacio'
    run = '20261102T120000-abcdef012345'
    source = root / 'runs' / run
    source.mkdir(parents=True)
    entrada = source / 'red.txt'
    entrada.write_text('fuente reservada de prueba', encoding='utf-8')
    snapshot = snapshot_from_paths('txt', {'red': entrada}, source, origin='prueba')
    manifest = {'version': 1, 'run_id': run, 'mode': 'txt', 'created_at': 0,
                'fingerprint': snapshot.fingerprint,
                'files': [x.to_dict(source) for x in snapshot.files.values()]}
    (source / 'source_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    binding = PowerFactoryProjectBinding('Proyecto', 'Carpeta', run, 'txt',
        snapshot.fingerprint, ('AL001',), {}, 'inventario', {}).as_dict()
    ws = {'id': 'ejemplo', 'active_run_id': run, 'options': {'input_mode': 'txt'},
          'pf_project_bindings': {'Proyecto': binding}}
    (root / 'workspace.json').write_text(json.dumps(ws), encoding='utf-8')
    report = tmp_path / 'informe.json'
    report.write_text('{"converge": true}', encoding='utf-8')
    evidencia = {'custodia': custodiar(report, localizador='informe guardado'),
                 'contexto': {'project': 'Proyecto', 'caso': 'sin_proyecto',
                    'periodo': '2026-09', 'source_tuple': [run, 'txt', snapshot.fingerprint]}}
    return root, ws, entrada, evidencia


def ejecutar(caso, **kw):
    root, _, _, evidencia = caso
    return preaceptar(root, 'Proyecto', ['AL001'], caso='sin_proyecto',
                     periodo='2026-09', evidencias=[evidencia], **kw)


def test_control_sellado_no_certifica_fisica(caso):
    """065:RF-21: una fuente sellada e informe convergido no aceptan electricidad."""
    resultado = ejecutar(caso)
    assert resultado['listo_diagnostico'] is True
    assert resultado['aceptacion_electrica'] is False
    assert resultado['operaciones_nativas'] == 0
    assert resultado['caso'] == 'sin_proyecto'
    assert resultado['periodo'] == '2026-09'


def test_fuente_modificada_impide_replay(caso):
    """065:RF-21: cambiar bytes conservando manifiesto impide continuar."""
    caso[2].write_text('datos cambiados', encoding='utf-8')
    resultado = ejecutar(caso)
    assert resultado['listo_diagnostico'] is False
    assert 'huella de fuente modificada' in resultado['bloqueos']


def test_run_igual_huella_no_es_replay_exacto(caso):
    """065:RF-21: la preaceptación de replay exige identidad exacta del caso."""
    root, ws, _, _ = caso
    nuevo = '20261102T130000-abcdef012345'
    import shutil
    shutil.copytree(root / 'runs' / ws['active_run_id'], root / 'runs' / nuevo)
    p = root / 'runs' / nuevo / 'source_manifest.json'
    d = json.loads(p.read_text()); d['run_id'] = nuevo; p.write_text(json.dumps(d))
    ws['active_run_id'] = nuevo
    (root / 'workspace.json').write_text(json.dumps(ws), encoding='utf-8')
    resultado = ejecutar(caso)
    assert resultado['listo_diagnostico'] is False
    assert any('replay exige source_run_id exacto' in b for b in resultado['bloqueos'])


def test_vinculo_alterado_impide_replay(caso):
    """065:RF-21: el sello del vínculo vigente es obligatorio."""
    root, ws, _, _ = caso
    ws['pf_project_bindings']['Proyecto']['folder'] = 'Otra'
    (root / 'workspace.json').write_text(json.dumps(ws), encoding='utf-8')
    resultado = ejecutar(caso)
    assert resultado['listo_diagnostico'] is False
    assert any('PROJECT_BINDING_RECORD_MISMATCH' in b for b in resultado['bloqueos'])


def test_artefacto_ausente_impide_replay(caso):
    """065:RF-21: evidencia declarada y desaparecida no constituye aceptación."""
    Path(caso[3]['custodia']['ruta']).unlink()
    assert ejecutar(caso)['listo_diagnostico'] is False


def test_recursos_bajos_bloquean_ml(caso, monkeypatch):
    """065:RF-21: el control comparte el umbral ML vigente, sin cargar pesos."""
    monkeypatch.setattr('convertersmartgrid.training_coordinator._memoria_sistema',
                        lambda: {'fisica_gib': 1., 'commit_gib': 2.})
    resultado = ejecutar(caso, requiere_ml=True)
    assert resultado['listo_diagnostico'] is False
    assert any('Memoria insuficiente' in b for b in resultado['bloqueos'])


def test_informe_de_otro_periodo_no_habilita(caso):
    """065:RF-21: un informe sellado de otro contexto no habilita el diagnóstico."""
    caso[3]['contexto']['periodo'] = '2025-01'
    assert ejecutar(caso)['listo_diagnostico'] is False


def test_slot_repetido_es_fuente_ambigua(caso):
    """065:RF-21: dos entradas del mismo slot no se resuelven tomando la última."""
    root, ws, _, _ = caso
    p = root / 'runs' / ws['active_run_id'] / 'source_manifest.json'
    d = json.loads(p.read_text()); d['files'].append(dict(d['files'][0]))
    p.write_text(json.dumps(d), encoding='utf-8')
    resultado = ejecutar(caso)
    assert resultado['listo_diagnostico'] is False
    assert 'Entrada duplicada o de otra fuente en el manifiesto.' in resultado['bloqueos']


@pytest.mark.parametrize('version', [None, True, 2, '1'])
def test_version_de_manifiesto_no_admitida_bloquea(caso, version):
    """065:RF-21: ausencia, booleano, versión futura o texto no habilitan replay."""
    assert ejecutar(caso)['listo_diagnostico'] is True
    root, ws, _, _ = caso
    p = root / 'runs' / ws['active_run_id'] / 'source_manifest.json'
    d = json.loads(p.read_text(encoding='utf-8'))
    if version is None:
        d.pop('version')
    else:
        d['version'] = version
    p.write_text(json.dumps(d), encoding='utf-8')
    resultado = ejecutar(caso)
    assert resultado['listo_diagnostico'] is False
    assert 'Manifiesto de otra ejecución o versión no admitida.' in resultado['bloqueos']
    assert resultado['aceptacion_electrica'] is False
    assert resultado['operaciones_nativas'] == 0


def test_registro_compartido_tiene_precedencia(caso):
    """065:RF-21: la copia privada no oculta un vínculo compartido alterado."""
    from convertersmartgrid.powerfactory_binding import REGISTRO_SCHEMA
    from convertersmartgrid.web.workspace import REGISTRO_VINCULOS_FILE
    root, ws, _, _ = caso
    vinculo = dict(ws['pf_project_bindings']['Proyecto'])
    vinculo['source_mode'] = 'mdb'
    (root.parent / REGISTRO_VINCULOS_FILE).write_text(
        json.dumps({'schema': REGISTRO_SCHEMA, 'vinculos': {'Proyecto': vinculo}}), encoding='utf-8')
    assert ejecutar(caso)['listo_diagnostico'] is False


@pytest.mark.parametrize(('accion', 'flujos', 'consume'), [
    ('diagnostico', False, False), ('diagnostico', True, True),
    ('evaluar', False, True), ('aplicar', False, True)])
def test_manifiesto_nuevas_solo_en_operaciones_que_lo_consumen(tmp_path, monkeypatch, accion, flujos, consume):
    """065:RF-21: el inventario estructural es independiente de demandas históricas ausentes."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    llamadas, planes = [], []
    def nuevas(*_):
        llamadas.append(True)
        return [{'sed': 'Carga', 'kw': None}]
    def guion(_ws, _ctx, _script, plan, **_kw):
        planes.append(plan)
        return 0, {'aceptada': False}, tmp_path / 'informe.json'
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', nuevas)
    monkeypatch.setattr(services, '_guion_pf', guion)
    monkeypatch.setattr(services, 'native_action_context', lambda *_: {'contexto': 'sellado'})
    ctx = SimpleNamespace(log=lambda _: None)
    resultado = services.set_nueva_operacion(SimpleNamespace(), ctx, 'Proyecto', ['AL001'],
                                            accion=accion, verificar_flujos=flujos)
    assert bool(llamadas) is consume
    assert planes[0]['nuevas'] == ([{'sed': 'Carga', 'kw': None}] if consume else [])
    assert resultado['aceptada'] is False
