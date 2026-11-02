"""Contrato del modelo efectivo y puerta de importación (spec 065)."""

from __future__ import annotations

import json
import random
import threading
from types import SimpleNamespace

import pytest

from convertersmartgrid.web import services
from synthetic_export import ExportSpec, load_export


def _contexto():
    return SimpleNamespace(log=lambda *_: None, progress=lambda *_: None,
                           check_cancel=lambda: None, cancel=threading.Event())


@pytest.mark.parametrize('fallos', [('A',), ('A', 'B')])
def test_grupo_rechaza_cualquier_miembro(tmp_path, monkeypatch, fallos):
    """065:RF-5 — el rechazo por miembro se propaga al DGS unido."""
    from convertersmartgrid.web.workspace import Workspace

    ws = Workspace(id='grupo', root=tmp_path)
    ws.out_dir.mkdir(parents=True)
    ws.groups['G'] = {'feeders': ['A', 'B']}
    monkeypatch.setattr(services, 'dgs_jobs', lambda *_: ([("G", ws.out_dir / 'G.dgs', None)], []))
    monkeypatch.setattr(services, '_script', lambda *_: tmp_path / 'sin_ejecutar.py')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, tmp_path / 'sin_ejecutar.exe'))
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'PRUEBA')
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda *_: {})
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'doble de enrutamiento'})
    monkeypatch.setattr(services, 'pandapower_preflight', lambda *_: {
        'disponible': True, 'no_convergen': {f: 'no converge' for f in fallos}})
    comandos = []
    ctx = _contexto()
    ctx.run_process = lambda cmd, **_: comandos.append(cmd) or 3
    resultado = services.powerfactory_flow(ws, ctx, ['A', 'B'])
    assert comandos == []
    assert resultado['failed'] == 1


@pytest.mark.parametrize('layout', ['reducido', 'completo'])
@pytest.mark.parametrize('unida', [False, True])
def test_snapshot_es_el_modelo_escrito_y_no_reconstruye(tmp_path, monkeypatch, layout, unida):
    """065:RF-6 — el control lee el modelo post-reglas exacto, sin entradas actuales."""
    from convertersmartgrid import batch, preflight_contract
    from convertersmartgrid.estructura import estructura_de_dict
    from convertersmartgrid.naming import feeder_short_name
    from convertersmartgrid.perfil_empresa import PerfilEmpresa
    from convertersmartgrid.reglas import REGLAS_PROYECTO
    from convertersmartgrid.web.workspace import Workspace

    rng = random.Random(6506)
    ds = load_export(ExportSpec(feeders=rng.randint(2, 4), sections_per_feeder=rng.randint(5, 9),
                                loads_per_feeder=3, seed=6506, layout=layout), tmp_path / 'fuente')
    ws = Workspace(id='snapshot', root=tmp_path / 'espacio')
    escritos = {}
    escritor = batch.write_dgs
    perfil = PerfilEmpresa(nombre=f'empresa_{layout}', escala_diagrama=2.7 if layout == 'completo' else 1.9)
    aliases = {'DEFAULT': 'AA05001D'}

    def observar(modelo, *args, **kwargs):
        escritos[modelo.name] = preflight_contract.model_digest(modelo)
        return escritor(modelo, *args, **kwargs)

    monkeypatch.setattr(batch, 'write_dgs', observar)
    if unida:
        estructura = estructura_de_dict({
            'zonales': [{'nombre': 'Zona', 'sets': [{'codigo': 'SET 1', 'nombre': 'Principal',
                         'alimentadores': [{'codigo': feeder_short_name(n), 'sistema': 'S1'}
                                           for n in ds.feeder_ids()]}]}],
            'sistemas': {'S1': {'nombre': 'Sistema', 'norma': 'Norma de prueba'}},
        })
        man = batch.convert_group(ds, ds.feeder_ids(), ws.out_dir, name='G',
                                  include_geography=False, reglas=REGLAS_PROYECTO,
                                  estructura=estructura, aliases=aliases, perfil=perfil)
        assert man['status'] == 'ok', man
        targets = ['G']
        ws.groups['G'] = {'feeders': man['feeders']}
    else:
        man = batch.convert_selection(ds, ds.feeder_ids(), ws.out_dir, include_geography=False,
                                      workers=1, reglas=REGLAS_PROYECTO, aliases=aliases, perfil=perfil)
        assert man['summary']['failed'] == 0
        targets = [f['feeder'] for f in man['feeders']]

    # ARQ02: el original y el perfil/alias vigentes ya no intervienen en el control.
    ws.dataset = object()
    monkeypatch.setattr(services, 'perfil_de', lambda *_: pytest.fail('No releer perfil'))
    monkeypatch.setattr(services, 'reglas_de', lambda *_: pytest.fail('No reaplicar reglas'))
    from convertersmartgrid import model
    monkeypatch.setattr(model, 'build_feeder_model', lambda *_a, **_k: pytest.fail('No reconstruir modelo'))
    monkeypatch.setattr(batch, 'load_aliases', lambda *_: pytest.fail('No releer alias actuales'))
    for target in targets:
        dgs = ws.out_dir / f'{target}.dgs'
        contrato = preflight_contract.load_contract(dgs)
        assert preflight_contract.model_digest(contrato['model']) == escritos[target]
        assert contrato['members']
        assert contrato['context']['aliases'] == aliases
        assert contrato['context']['perfil_empresa'] == perfil.valores()
        if unida:
            assert contrato['model'].combined.barras_set
            assert contrato['model'].combined.sistemas['S1'].nombre == 'Sistema'
    res = services.pandapower_preflight(ws, targets, _contexto())
    assert res['no_convergen'] == {}, res
    assert len(res['targets']) == len(targets)


@pytest.mark.parametrize('falla', ['ausente', 'dgs_modificado', 'modelo_modificado', 'calculo', 'indisponible'])
def test_control_requerido_falla_cerrado(tmp_path, monkeypatch, falla):
    """065:RF-7 — ausencias, corrupción o cálculo fallido bloquean el target."""
    from convertersmartgrid import batch, oraculo
    from convertersmartgrid.web.workspace import Workspace

    ds = load_export(ExportSpec(feeders=1, sections_per_feeder=5, loads_per_feeder=2, seed=6507),
                     tmp_path / 'fuente')
    ws = Workspace(id='cerrado', root=tmp_path / 'espacio')
    man = batch.convert_selection(ds, ds.feeder_ids(), ws.out_dir, include_geography=False, workers=1)
    target = man['feeders'][0]['feeder']
    dgs = ws.out_dir / f'{target}.dgs'
    sidecar = dgs.with_name(f'{target}_preflight.json')
    if falla == 'ausente':
        if sidecar.exists():
            sidecar.unlink()
    elif falla == 'dgs_modificado':
        dgs.write_bytes(dgs.read_bytes() + b'\nMODIFICADO')
    elif falla == 'modelo_modificado':
        dato = json.loads(sidecar.read_text(encoding='utf-8'))
        dato['model'] = {'falso': True}
        sidecar.write_text(json.dumps(dato), encoding='utf-8')
    elif falla == 'calculo':
        monkeypatch.setattr(oraculo, 'validar', lambda *_: (_ for _ in ()).throw(ValueError('fallo deliberado')))
    else:
        monkeypatch.setattr(oraculo, 'disponible', lambda: False)
    res = services.pandapower_preflight(ws, [target], _contexto())
    assert target in res['no_convergen'], res
    assert res['import_continued'] is False


@pytest.mark.parametrize('estado', ['converge', 'miembro', 'ambos', 'unida', 'calculo', 'cambio_miembros'])
def test_grupo_calcula_miembros_y_union_publicada(tmp_path, monkeypatch, estado):
    """065:RF-5, 065:RF-6, 065:RF-7 — cada miembro y el unido deben superar el control."""
    from convertersmartgrid import batch, oraculo
    from convertersmartgrid.web.workspace import Workspace

    ds = load_export(ExportSpec(feeders=3, sections_per_feeder=5, loads_per_feeder=2, seed=6515),
                     tmp_path / 'fuente')
    ws = Workspace(id='grupo-real', root=tmp_path / 'espacio')
    man = batch.convert_group(ds, ds.feeder_ids(), ws.out_dir, name='G', include_geography=False)
    assert man['status'] == 'ok', man
    ws.groups['G'] = {'feeders': man['feeders']}
    if estado == 'cambio_miembros':
        ws.groups['G']['feeders'] = man['feeders'][:-1]
    calculados = []

    def informe(nombre, converge):
        return SimpleNamespace(disponible=True, convergio=converge, errores=[],
                               as_dict=lambda: {'convergio': converge},
                               resumen=lambda: f'{nombre}: convergencia={converge}')

    def miembro(m):
        calculados.append(m.name)
        if estado == 'calculo':
            raise ValueError('cálculo requerido fallido')
        malo = estado == 'ambos' or estado == 'miembro' and m.name == man['feeders'][0]
        return informe(m.name, not malo)

    def union(m):
        calculados.append(m.name)
        general = informe(m.name, estado != 'unida')
        return SimpleNamespace(general=general, as_dict=lambda: {'general': general.as_dict()})

    monkeypatch.setattr(oraculo, 'validar', miembro)
    monkeypatch.setattr(oraculo, 'validar_unida', union)
    res = services.pandapower_preflight(ws, ['G'], _contexto())
    assert ('G' in res['no_convergen']) is (estado != 'converge'), res
    if estado not in {'calculo', 'cambio_miembros'}:
        assert calculados == man['feeders'] + ['G']


def test_reconstruccion_real_conserva_snapshot_tras_cambiar_la_fuente(tmp_path, monkeypatch):
    """065:RF-6 — la reparación automática se captura; nunca se valida el original incompleto."""
    from convertersmartgrid.preflight_contract import load_contract
    from test_web_reconstruction import _workspace

    ws = _workspace(tmp_path)
    ws.options.update({'include_geography': False, 'workers': 1, 'export_xlsx': False,
                       'export_tsv': False, 'write_preview': False})
    resultado = services.convert(ws, _contexto(), ['F-A'], False)
    assert resultado['summary']['ok'] == 1
    assert 'N1' not in ws.dataset.nodes
    from convertersmartgrid.naming import feeder_short_name
    target = feeder_short_name('F-A')
    contrato = load_contract(ws.out_dir / f'{target}.dgs')
    assert 'N1' in contrato['model'].nodes
    assert contrato['model'].lines[0].source_type_code == 'UNKNOWN-50'
    ws.reconstructed_dataset = None
    ws.dataset = object()
    ws.options['strict'] = False
    monkeypatch.setattr(services, 'perfil_de', lambda *_: pytest.fail('perfil actual no corresponde al DGS'))
    res = services.pandapower_preflight(ws, [target], _contexto())
    assert res['no_convergen'] == {}, res


def test_cancelacion_del_control_no_se_convierte_en_aviso(tmp_path, monkeypatch):
    """065:RF-7 — una cancelación interrumpe antes de autorizar una importación."""
    from convertersmartgrid import batch
    from convertersmartgrid.web.jobs import JobCancelled
    from convertersmartgrid.web.workspace import Workspace

    ds = load_export(ExportSpec(feeders=1, sections_per_feeder=5, loads_per_feeder=2, seed=6527),
                     tmp_path / 'fuente')
    ws = Workspace(id='cancelar', root=tmp_path / 'espacio')
    man = batch.convert_selection(ds, ds.feeder_ids(), ws.out_dir, include_geography=False, workers=1)
    llamadas = []
    ctx = _contexto()

    def cancelar_en_miembro():
        llamadas.append(True)
        if len(llamadas) == 2:
            raise JobCancelled()

    ctx.check_cancel = cancelar_en_miembro
    with pytest.raises(JobCancelled):
        services.pandapower_preflight(ws, [man['feeders'][0]['feeder']], ctx)


@pytest.mark.parametrize('terminacion', ['normal', 'error', 'cancelacion', 'cambio_fuente'])
def test_importacion_fija_entrada_por_trabajo_y_limpia_solo_su_copia(tmp_path, monkeypatch, terminacion):
    """065:RF-6, 065:RF-7 — una reconversión tras el control nunca sustituye la entrada nativa."""
    from pathlib import Path
    from convertersmartgrid import batch
    from convertersmartgrid.web.jobs import JobCancelled
    from convertersmartgrid.web.workspace import Workspace

    ds = load_export(ExportSpec(feeders=1, sections_per_feeder=6, loads_per_feeder=3, seed=6536),
                     tmp_path / 'fuente')
    ws = Workspace(id='fijado', root=tmp_path / 'espacio')
    ws.active_run_id = 'ejecucion-fijada'
    man = batch.convert_selection(ds, ds.feeder_ids(), ws.out_dir, include_geography=False, workers=1)
    target = man['feeders'][0]['feeder']
    salida_original = ws.out_dir
    publicado = ws.out_dir / f'{target}.dgs'
    original = publicado.read_bytes()
    metadata = publicado.with_name(f'{target}_feeder_metadata.json')
    metadata_original = metadata.read_bytes()
    geo = publicado.with_name(f'{target}_geography.json')
    geo.write_text('{"version": "original"}', encoding='utf-8')
    informe = ws.out_dir / 'reconstruction_report.json'
    informe.write_text('{"version": "original"}', encoding='utf-8')
    import hashlib
    monkeypatch.setattr(services, 'check_powerfactory_source_run', lambda *_: {
        'source_run_id': 'ejecucion-fijada', 'source_mode': 'txt', 'source_fingerprint': 'f' * 64,
        'targets': [{'target': target, 'dgs_sha256': hashlib.sha256(original).hexdigest(),
                     'reconstruction': {'report': informe.name, 'report_sha256': 'a' * 64}}],
    })
    copia = []
    informes = []
    control_real = services.pandapower_preflight
    monkeypatch.setenv('CSG_TEMP_HOME', str(tmp_path / 'temporales'))
    monkeypatch.setattr(services, '_script', lambda *_: tmp_path / 'sin_ejecutar.py')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, tmp_path / 'sin_ejecutar.exe'))
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'PRUEBA')
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda *_: {})
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'prueba de custodia'})
    ctx = _contexto()
    ctx.job = SimpleNamespace(id='trabajo-fijado')

    def controlar(entrada, targets, contexto):
        resultado = control_real(entrada, targets, contexto)
        assert not resultado['no_convergen'], resultado
        copia.append(entrada.out_dir / f'{target}.dgs')
        assert copia[-1] != publicado
        assert copia[-1].read_bytes() == original
        owner = json.loads((entrada.out_dir / 'owner.json').read_text(encoding='utf-8'))
        assert owner['propietario'] == 'trabajo-fijado'
        publicado.write_bytes(b'NUEVA CONVERSION PUBLICADA')
        metadata.write_text('{"version": "posterior"}', encoding='utf-8')
        geo.write_text('{"version": "posterior"}', encoding='utf-8')
        informe.write_text('{"version": "posterior"}', encoding='utf-8')
        if terminacion == 'cambio_fuente':
            ws.active_run_id = 'otra-ejecucion'
        if terminacion == 'cancelacion':
            ctx.check_cancel = lambda: (_ for _ in ()).throw(JobCancelled())
        return resultado

    def importar(cmd, **_):
        fijado = Path(cmd[cmd.index('--import-dgs') + 1])
        assert fijado == copia[-1]
        assert fijado.read_bytes() == original
        metadatos_fijados = Path(cmd[cmd.index('--feeder-metadata') + 1])
        assert metadatos_fijados.parent == fijado.parent
        assert metadatos_fijados.read_bytes() == metadata_original
        for bandera in ('--manifest', '--reconstruction-report'):
            acompanante = Path(cmd[cmd.index(bandera) + 1])
            assert acompanante.parent == fijado.parent
            assert json.loads(acompanante.read_text(encoding='utf-8'))['version'] == 'original'
        durable = Path(cmd[cmd.index('--output-json') + 1])
        assert durable.parent.parent.parent == salida_original
        informes.append(durable)
        datos_metadata = json.loads(metadatos_fijados.read_text(encoding='utf-8'))
        feeders = sorted({a['feeder'] for a in datos_metadata['assignments'] if a.get('feeder')})
        # Emisión unitaria del borde nativo; nunca se presenta como aceptación eléctrica.
        reporte = {'feeder': target, 'powerfactory_runtime_pass': True,
                   'import': {'ok': True, 'dgs': str(fijado), 'project_path': 'UNITARIO',
                              'project_folder': 'PRUEBA'},
                   'source_verification': {'status': 'VERIFIED_BEFORE_MUTATION',
                                           'source_run_id': 'ejecucion-fijada', 'source_mode': 'txt',
                                           'source_fingerprint': 'f' * 64,
                                           'dgs_sha256': hashlib.sha256(original).hexdigest(),
                                           'metadata_file': metadatos_fijados.name, 'feeders': feeders}}
        durable.write_text(json.dumps(reporte), encoding='utf-8')
        if terminacion == 'error':
            raise RuntimeError('Fallo de proceso deliberado')
        return 0

    monkeypatch.setattr(services, 'pandapower_preflight', controlar)
    ctx.run_process = importar
    if terminacion in {'normal', 'cambio_fuente'}:
        resultado = services.powerfactory_flow(ws, ctx, [target])
        assert resultado['ok'] == 1
    else:
        with pytest.raises(JobCancelled if terminacion == 'cancelacion' else RuntimeError):
            services.powerfactory_flow(ws, ctx, [target])
    assert copia and not copia[-1].parent.exists()
    assert publicado.read_bytes() == b'NUEVA CONVERSION PUBLICADA'
    if terminacion != 'cancelacion':
        assert informes and informes[-1].is_file()
        assert (salida_original / f'{target}_powerfactory_acceptance.json').is_file() is (terminacion != 'error')
