"""Contrato verificable entre una ejecución fuente y el proyecto PowerFactory nativo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Obj:
    def __init__(self, cls, full_name, **attrs):
        self._cls = cls
        self._full_name = full_name
        for name, value in attrs.items():
            setattr(self, name, value)

    def GetClassName(self):
        return self._cls

    def GetFullName(self):
        return self._full_name

    def GetAttribute(self, name):
        return getattr(self, name, None)

    def GetUserAttribute(self, name):
        return getattr(self, name, None)


class _App:
    def __init__(self, objects):
        self.objects = list(objects)

    def GetCalcRelevantObjects(self, pattern):
        cls = pattern.rsplit('.', 1)[-1]
        return [obj for obj in self.objects if obj.GetClassName() == cls]


def _binding(**overrides):
    from igea_dgs.powerfactory_binding import PowerFactoryProjectBinding

    values = {
        'project': 'Oct/IN111',
        'folder': 'Empresa',
        'source_run_id': 'run-active',
        'source_mode': 'txt',
        'source_fingerprint': 'f' * 64,
        'feeders': ('IN111',),
        'dgs_sha256': {'IN111': 'd' * 64},
        'native_inventory_sha256': 'n' * 64,
        'native_reread': {'status': 'VERIFICADO_PERSISTENCIA'},
        'accepted_at': 1_797_000_000.0,
    }
    values.update(overrides)
    return PowerFactoryProjectBinding(**values)


def _workspace(tmp_path):
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='binding', root=tmp_path)
    ws.active_run_id = 'run-active'
    ws.loaded_run_id = 'run-active'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = SimpleNamespace()
    ws.pf_inventory = {
        'folder': 'Empresa',
        'projects': [{
            'name': 'IN111', 'path': 'Oct/IN111', 'feeders': ['IN111'],
            'native_inventory_sha256': 'n' * 64,
        }],
    }
    return ws


def test_native_inventory_hash_is_wrapper_stable_and_excludes_operational_pq():
    from igea_dgs.powerfactory_binding import native_inventory_sha256

    term = _Obj('ElmTerm', r'Grid\B1.ElmTerm', ukNom=10.0, **{'p:alimentador': ['IN111']})
    cub = _Obj('StaCubic', r'Grid\B1\C1.StaCubic', cterm=term)
    typ = _Obj('TypLod', r'Library\Load.TypLod')
    load = _Obj(
        'ElmLod', r'Grid\SED1\L1.ElmLod', bus1=cub, typ_id=typ,
        plini=100.0, qlini=30.0, coslini=0.957826, **{'p:alimentador': 'IN111'},
    )
    app = _App([term, load, load])  # wrappers repetidos se colapsan por GetFullName.
    first = native_inventory_sha256(app, ['IN111'])

    load.plini, load.qlini, load.coslini = 140.0, 55.0, 0.91
    assert native_inventory_sha256(app, ['IN111']) == first

    load.bus1 = _Obj('StaCubic', r'Grid\B2\C1.StaCubic', cterm=_Obj('ElmTerm', r'Grid\B2.ElmTerm'))
    assert native_inventory_sha256(app, ['IN111']) != first


def test_native_inventory_hash_changes_with_equipment_or_feeder_label():
    from igea_dgs.powerfactory_binding import native_inventory_sha256

    typ = _Obj('TypLne', r'Library\AAAC70.TypLne')
    line = _Obj('ElmLne', r'Grid\L1.ElmLne', typ_id=typ, **{'p:alimentador': ['IN111']})
    app = _App([line])
    first = native_inventory_sha256(app, ['IN111'])
    line.typ_id = _Obj('TypLne', r'Library\AAAC95.TypLne')
    assert native_inventory_sha256(app, ['IN111']) != first
    line.typ_id = typ
    setattr(line, 'p:alimentador', ['OTRO'])
    assert native_inventory_sha256(app, ['IN111']) != first


def test_exact_active_binding_is_persisted_and_accepted(tmp_path):
    from igea_dgs.powerfactory_binding import record_project_binding, require_project_binding
    from igea_dgs.web.workspace import Workspace

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    accepted = require_project_binding(ws, 'Oct/IN111', ['IN111'])
    assert accepted.source_run_id == 'run-active'
    assert accepted.feeders == ('IN111',)

    reopened = Workspace.load(tmp_path)
    reopened.active_run_id = 'run-active'
    reopened.loaded_run_id = 'run-active'
    reopened.loaded_source_mode = 'txt'
    reopened.loaded_source_fingerprint = 'f' * 64
    reopened.dataset = SimpleNamespace()
    assert require_project_binding(reopened, 'Oct/IN111', ['IN111']).binding_sha256


def test_equivalent_source_reload_is_warning_not_blocking(tmp_path):
    from igea_dgs.powerfactory_binding import (
        project_binding_warnings, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(source_run_id='run-historical'))
    accepted = require_project_binding(ws, 'Oct/IN111', ['IN111'])
    warnings = project_binding_warnings(ws, 'Oct/IN111', ['IN111'])

    assert accepted.project == 'Oct/IN111'
    assert warnings == [{
        'code': 'PROJECT_BINDING_SOURCE_RUN_CHANGED',
        'message': (
            "La fuente se volvió a cargar como 'run-active'; conserva la misma "
            "huella que 'run-historical'."
        ),
        'elements': [],
    }]


def test_different_source_fingerprint_is_still_rejected(tmp_path):
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(
        source_run_id='run-historical', source_fingerprint='e' * 64,
    ))
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_SOURCE_MISMATCH'):
        require_project_binding(ws, 'Oct/IN111', ['IN111'])


def test_tras_reiniciar_la_web_el_vinculo_usa_el_manifiesto_activo(tmp_path, monkeypatch):
    """014:RF-17 — reiniciar la web no bloquea el proyecto: sin la fuente en memoria, la
    identidad sale del manifiesto persistido de la ejecución activa (CA101, 2026-10-14)."""
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(source_run_id='run-historical'))
    # Lo que queda tras reiniciar: solo ``active_run_id`` sobrevive en workspace.json.
    ws.loaded_run_id = ws.loaded_source_mode = ws.loaded_source_fingerprint = None
    ws.dataset = None
    manifiesto = SimpleNamespace(run_id='run-active', mode='txt', fingerprint='f' * 64)
    monkeypatch.setattr(ws, 'active_run', lambda: manifiesto)
    assert require_project_binding(ws, 'Oct/IN111', ['IN111']).project == 'Oct/IN111'

    manifiesto.fingerprint = 'e' * 64
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_SOURCE_MISMATCH'):
        require_project_binding(ws, 'Oct/IN111', ['IN111'])


def test_changed_native_topology_is_reported_but_does_not_block(tmp_path):
    """014:RF-17 — una modificación manual del modelo nativo se lista como aviso y no
    bloquea: el vínculo sigue siendo válido."""
    from igea_dgs.powerfactory_binding import (
        project_binding_warnings, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    baseline = [
        {'class': 'ElmLne', 'full_name': r'Grid\L1.ElmLne', 'sha256': '1' * 64},
        {'class': 'ElmTerm', 'full_name': r'Grid\B1.ElmTerm', 'sha256': '2' * 64},
    ]
    record_project_binding(ws, _binding(native_reread={
        'status': 'VERIFICADO_PERSISTENCIA', 'inventory_manifest': baseline,
    }))
    ws.pf_inventory['projects'][0]['native_inventory_sha256'] = 'x' * 64
    ws.pf_inventory['projects'][0]['native_inventory_manifest'] = [
        {'class': 'ElmLne', 'full_name': r'Grid\L1.ElmLne', 'sha256': '3' * 64},
        {'class': 'ElmLod', 'full_name': r'Grid\SED1.ElmLod', 'sha256': '4' * 64},
    ]

    assert require_project_binding(ws, 'Oct/IN111', ['IN111']).project == 'Oct/IN111'
    warnings = project_binding_warnings(ws, 'Oct/IN111', ['IN111'])
    assert warnings == [{
        'code': 'PROJECT_BINDING_NATIVE_MODIFIED',
        'message': 'El proyecto contiene modificaciones manuales posteriores a su aceptación.',
        'elements': [
            {'change': 'added', 'class': 'ElmLod', 'full_name': r'Grid\SED1.ElmLod'},
            {'change': 'removed', 'class': 'ElmTerm', 'full_name': r'Grid\B1.ElmTerm'},
            {'change': 'modified', 'class': 'ElmLne', 'full_name': r'Grid\L1.ElmLne'},
        ],
    }]

    # P/Q no forman parte de la huella y por eso no invalidan el contrato.
    ws.pf_inventory['projects'][0]['native_inventory_sha256'] = 'n' * 64
    ws.pf_inventory['projects'][0].pop('native_inventory_manifest')
    ws.pf_inventory['projects'][0]['operational_p_kw'] = 999.0
    ws.pf_inventory['projects'][0]['operational_q_kvar'] = 444.0
    assert require_project_binding(ws, 'Oct/IN111', ['IN111']).project == 'Oct/IN111'
    assert project_binding_warnings(ws, 'Oct/IN111', ['IN111']) == []


def test_unbound_project_and_foreign_feeder_are_rejected(tmp_path):
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_MISSING') as missing:
        require_project_binding(ws, 'Oct/IN111', ['IN111'])
    assert missing.value.code == 'PROJECT_BINDING_MISSING'
    record_project_binding(ws, _binding())
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_FEEDER_MISMATCH'):
        require_project_binding(ws, 'Oct/IN111', ['OTRO'])


def test_vinculo_de_otro_espacio_sin_fuente_activa_se_dice_como_tal(tmp_path):
    """018:RF-3 — caso real 2026-10-14: el proyecto se aceptó en un espacio con fuente activa
    y se listó en otro espacio sin fuente activa; el mensaje decía «fuente activa None»."""
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.active_run_id = None
    ws.loaded_run_id = None
    ws.loaded_source_mode = None
    ws.loaded_source_fingerprint = None
    with pytest.raises(ProjectBindingError) as sin_fuente:
        require_project_binding(ws, 'Oct/IN111', ['IN111'])
    assert sin_fuente.value.code == 'PROJECT_BINDING_NO_ACTIVE_SOURCE'
    assert 'None' not in sin_fuente.value.detail


def test_tampered_persisted_binding_is_rejected(tmp_path):
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.pf_project_bindings['Oct/IN111']['source_fingerprint'] = 'x' * 64
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_RECORD_MISMATCH'):
        require_project_binding(ws, 'Oct/IN111', ['IN111'])


def test_failed_native_reread_is_fail_closed(tmp_path):
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.pf_inventory['projects'][0]['native_inventory_sha256'] = None
    ws.pf_inventory['projects'][0]['native_warning'] = 'API sin relectura'
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_NATIVE_UNREADABLE'):
        require_project_binding(ws, 'Oct/IN111', ['IN111'])


def test_caso_base_verificado_por_alimentador():
    """015:RF-13 — solo se calibra el alimentador cuyo «Caso base» está verificado; un
    vínculo de antes de la spec 015 cuenta como no verificado."""
    from types import SimpleNamespace

    from igea_dgs.powerfactory_binding import caso_base_verificado

    ws = SimpleNamespace(pf_project_bindings={
        'P': {'native_reread': {'caso_base': {
            'CA101': {'status': 'VERIFICADO', 'fallos': []},
            'PE104': {'status': 'NO_VERIFICADO', 'fallos': ['flujo']},
        }}},
        'VIEJO': {'native_reread': {'status': 'VERIFICADO_PERSISTENCIA'}},
    })
    assert caso_base_verificado(ws, 'P', ['CA101', 'PE104', 'SI213']) == {
        'PE104': ['flujo'], 'SI213': ['sin verificar']}
    assert caso_base_verificado(ws, 'VIEJO', ['CA101']) == {'CA101': ['sin verificar']}


def _espacio(tmp_path, nombre, registro):
    """Espacio de trabajo con la misma fuente activa que _workspace, en su propia carpeta."""
    ws = _workspace(tmp_path / nombre)
    ws.vinculos_compartidos = registro
    return ws


def test_018_rf1_vinculo_aceptado_en_un_espacio_vale_en_otro_con_la_misma_fuente(tmp_path):
    """018:RF-1 — un vínculo aceptado en un espacio vale en otro con la misma fuente activa."""
    from igea_dgs.powerfactory_binding import record_project_binding, require_project_binding

    registro = tmp_path / 'vinculos_pf.json'
    record_project_binding(_espacio(tmp_path, 'origen', registro), _binding())
    destino = _espacio(tmp_path, 'destino', registro)
    assert destino.pf_project_bindings == {}
    assert require_project_binding(destino, 'Oct/IN111', ['IN111']).project == 'Oct/IN111'


def test_018_rf1_otra_fuente_no_reutiliza_el_vinculo_compartido(tmp_path):
    """018:RF-1 — con otra fuente activa el vínculo compartido no se reutiliza."""
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    registro = tmp_path / 'vinculos_pf.json'
    record_project_binding(_espacio(tmp_path, 'origen', registro), _binding())
    destino = _espacio(tmp_path, 'destino', registro)
    destino.active_run_id = destino.loaded_run_id = 'run-otra'
    destino.loaded_source_fingerprint = 'e' * 64
    with pytest.raises(ProjectBindingError) as otra:
        require_project_binding(destino, 'Oct/IN111', ['IN111'])
    assert otra.value.code == 'PROJECT_BINDING_SOURCE_MISMATCH'


def test_018_rf2_registro_ilegible_bloquea_aunque_el_espacio_tenga_copia(tmp_path):
    """018:RF-2 — fail-closed: con el registro roto no se cae a la copia del espacio, y no se
    sobrescribe."""
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    registro = tmp_path / 'vinculos_pf.json'
    registro.write_text('{no es json', encoding='utf-8')
    ws = _espacio(tmp_path, 'espacio', registro)
    ws.pf_project_bindings['Oct/IN111'] = _binding().as_dict()
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_REGISTRY_UNREADABLE'):
        require_project_binding(ws, 'Oct/IN111', ['IN111'])
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_REGISTRY_UNREADABLE'):
        record_project_binding(ws, _binding())
    assert registro.read_text(encoding='utf-8') == '{no es json'


def test_018_rf4_mismo_nombre_en_otra_carpeta_no_es_el_mismo_proyecto(tmp_path):
    """018:RF-4 — el mismo nombre de proyecto en otra carpeta de DIgSILENT es otro proyecto."""
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.pf_inventory['folder'] = 'OtraCarpeta'
    with pytest.raises(ProjectBindingError) as otra:
        require_project_binding(ws, 'Oct/IN111', ['IN111'])
    assert otra.value.code == 'PROJECT_BINDING_FOLDER_MISMATCH'


def test_018_rf7_registro_conserva_todos_los_proyectos_sin_fichero_temporal(tmp_path):
    """018:RF-7 — el registro guarda todos los proyectos y no deja ficheros temporales."""
    import json

    from igea_dgs.powerfactory_binding import record_project_binding

    registro = tmp_path / 'vinculos_pf.json'
    ws = _espacio(tmp_path, 'espacio', registro)
    record_project_binding(ws, _binding())
    record_project_binding(ws, _binding(project='Oct/IN222', feeders=('IN222',)))
    datos = json.loads(registro.read_text(encoding='utf-8'))
    assert set(datos['vinculos']) == {'Oct/IN111', 'Oct/IN222'}
    assert not registro.with_name(registro.name + '.tmp').exists()


def test_018_rf8_arranque_siembra_los_vinculos_de_los_espacios_existentes(tmp_path):
    """018:RF-8 — al arrancar, los vínculos de los espacios existentes pasan al registro: un
    conflicto gana el aceptado más tarde, uno alterado se descarta y una segunda siembra no
    cambia nada."""
    import json

    from igea_dgs.web.workspace import REGISTRO_VINCULOS_FILE, WorkspaceStore

    raiz = tmp_path / 'web'
    viejo = _binding(accepted_at=1.0, feeders=('IN111',)).as_dict()
    alterado = _binding(project='Oct/IN222', feeders=('IN222',)).as_dict()
    alterado['source_fingerprint'] = 'x' * 64
    nuevo = _binding(accepted_at=2.0, feeders=('IN111',), native_reread={'status': 'otro'})
    espacio_a = raiz / 'aaaa'
    espacio_a.mkdir(parents=True)
    (espacio_a / 'workspace.json').write_text(json.dumps(
        {'pf_project_bindings': {'Oct/IN111': viejo, 'Oct/IN222': alterado}}), encoding='utf-8')
    espacio_b = raiz / 'bbbb'
    espacio_b.mkdir()
    (espacio_b / 'workspace.json').write_text(json.dumps(
        {'pf_project_bindings': {'Oct/IN111': nuevo.as_dict()}}), encoding='utf-8')

    primera = WorkspaceStore(raiz)
    assert primera.siembra == {'añadidos': 1, 'actualizados': 1, 'iguales': 0, 'descartados': 1}
    registro = raiz / REGISTRO_VINCULOS_FILE
    datos = json.loads(registro.read_text(encoding='utf-8'))['vinculos']
    assert datos['Oct/IN111']['binding_sha256'] == nuevo.binding_sha256
    assert 'Oct/IN222' not in datos

    segunda = WorkspaceStore(raiz)
    assert segunda.siembra['añadidos'] == 0 and segunda.siembra['actualizados'] == 0


class _CtxSinEjecutar:
    """Si el servicio llega a usar el contexto, la exigencia del vínculo ya falló."""

    def __getattr__(self, name):
        raise AssertionError(f'se llegó a {name} sin vínculo')


def test_018_rf5_verificar_caso_base_exige_vinculo_en_el_servidor(tmp_path):
    """018:RF-5 — sin vínculo la API no verifica; la interfaz oculta el botón, pero no basta."""
    from igea_dgs.web import services

    ws = _workspace(tmp_path)
    with pytest.raises(services.UserError, match='PROJECT_BINDING_MISSING'):
        services.pf_verificar_base(ws, _CtxSinEjecutar(), 'Oct/IN111', ['IN111'])


def test_018_rf14_el_nombre_de_la_red_por_sistema_vale_por_sus_alimentadores(tmp_path, monkeypatch):
    """018:RF-14 — verificar el «Caso base» o una acción nativa con ``SISTEMA_NASCA`` pide al
    vínculo sus alimentadores, no el nombre del DGS; un alimentador suelto sigue igual."""
    from igea_dgs import powerfactory_binding
    from igea_dgs.web import services

    ws = _workspace(tmp_path)
    ws.groups = {'SISTEMA_NASCA': {'feeders': ['NA203', 'NA205', 'PU101'], 'status': 'ok'}}
    assert services.alimentadores_pedidos(ws, ['SISTEMA_NASCA', 'NA203', 'IN111', ' ']) == [
        'NA203', 'NA205', 'PU101', 'IN111']
    pedidos = []

    def exigir(ws_, project, feeders):
        pedidos.append(sorted(feeders))
        raise powerfactory_binding.ProjectBindingError('PARADA', 'basta con ver lo pedido')

    monkeypatch.setattr(powerfactory_binding, 'require_project_binding', exigir)
    with pytest.raises(services.UserError, match='PARADA'):
        services.pf_verificar_base(ws, _CtxSinEjecutar(), 'P/SISTEMA_NASCA', ['SISTEMA_NASCA'])
    with pytest.raises(services.UserError, match='PARADA'):
        services.native_action_context(ws, 'P/SISTEMA_NASCA', ['SISTEMA_NASCA'], 'obras')
    assert pedidos == [['NA203', 'NA205', 'PU101']] * 2


@pytest.mark.parametrize('caso, adopta', [
    ('misma fuente, otra ejecución, sin su DGS', True),
    ('otra huella', False),
    ('misma ejecución', False),
    ('con su DGS', False),
])
def test_018_rf15_misma_fuente_sin_el_dgs_aceptado_usa_la_ejecucion_del_vinculo(tmp_path, monkeypatch, caso, adopta):
    """018:RF-15 — la activa es de la misma fuente pero no tiene el DGS aceptado: se usa sola
    la ejecución del vínculo y se dice; con otra huella, la misma ejecución o el DGS, nada."""
    from types import SimpleNamespace

    from igea_dgs.web import services

    ws = _workspace(tmp_path)
    activa = SimpleNamespace(run_id='nueva' if caso != 'misma ejecución' else 'vieja', mode='txt',
                             fingerprint='h' if caso != 'otra huella' else 'otra')
    monkeypatch.setattr(type(ws), 'active_run', lambda self: activa)
    binding = SimpleNamespace(source_run_id='vieja', source_mode='txt', source_fingerprint='h')
    monkeypatch.setattr(services, 'dgs_jobs', lambda ws_, f: ([], [] if caso == 'con su DGS' else ['NA203']))
    adoptados = []
    monkeypatch.setattr(services, 'adoptar_fuente_del_vinculo', lambda ws_, p: adoptados.append(p))
    aviso = services.usar_ejecucion_del_vinculo(ws, 'P/SISTEMA_NASCA', binding, ['NA203'])
    assert (adoptados == ['P/SISTEMA_NASCA']) is adopta
    assert (aviso is not None and '018:RF-15' in aviso) is adopta


def test_018_rf15_las_acciones_nativas_no_cambian_la_ejecucion_activa(tmp_path, monkeypatch):
    """018:RF-15 — una acción nativa trabaja sobre el proyecto ya importado: aunque falte el
    DGS en la ejecución activa, no la cambia (Chincha, 2026-10-24)."""
    from types import SimpleNamespace

    from igea_dgs import powerfactory_binding
    from igea_dgs.web import services

    ws = _workspace(tmp_path)
    binding = SimpleNamespace(dgs_sha256={}, source_run_id='vieja')
    monkeypatch.setattr(powerfactory_binding, 'require_project_binding', lambda *_a: binding)
    monkeypatch.setattr(powerfactory_binding, 'project_binding_warnings', lambda *_a: [])
    monkeypatch.setattr(services, 'comprobar_dgs_vinculados', lambda *_a: None)
    monkeypatch.setattr(services, 'usar_ejecucion_del_vinculo',
                        lambda *_a: pytest.fail('una acción nativa no cambia la ejecución activa'))
    monkeypatch.setattr('igea_dgs.native_action.build_native_action_context',
                        lambda b, p, f, a, warnings: {'feeders': f, 'warnings': warnings})
    assert services.native_action_context(ws, 'P', ['PN107'], 'obras')['feeders'] == ['PN107']


def test_018_rf6_dgs_distinto_del_aceptado_bloquea_y_sin_huella_no_bloquea(tmp_path, monkeypatch):
    """018:RF-6 — un DGS distinto del aceptado bloquea; un alimentador sin huella, no."""
    from igea_dgs.web import services

    dgs = tmp_path / 'IN111.dgs'
    dgs.write_text('dgs', encoding='utf-8')
    (tmp_path / 'IN111_feeder_metadata.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(services, 'dgs_jobs', lambda ws, feeders: ([('IN111', dgs, None)], []))
    monkeypatch.setattr(
        'igea_dgs.feeder_metadata.read_feeder_metadata',
        lambda path, expected_dgs: {'dgs_sha256': 'b' * 64},
    )
    ws = _workspace(tmp_path)
    with pytest.raises(services.UserError, match='PROJECT_BINDING_DGS_MISMATCH'):
        services.comprobar_dgs_vinculados(ws, {'IN111': 'a' * 64}, ['IN111'])
    services.comprobar_dgs_vinculados(ws, {'IN111': 'b' * 64}, ['IN111'])
    services.comprobar_dgs_vinculados(ws, {}, ['IN111'])


_RID = '20261014T205152-71b14f2416a0'


def _espacio_origen_en_disco(raiz, *, huella='f' * 64):
    """Espacio que aceptó el proyecto: su ejecución en disco, calibración y DGS unido."""
    import json

    run = raiz / 'origen' / 'runs' / _RID
    (run / 'salida').mkdir(parents=True)
    (raiz / 'medidores.xlsx').write_bytes(b'')
    (run / 'salida' / 'IN111.dgs').write_text('dgs', encoding='utf-8')
    (run / 'source_manifest.json').write_text(json.dumps({
        'version': 1, 'run_id': _RID, 'mode': 'txt', 'created_at': 1.0,
        'fingerprint': huella, 'files': [],
    }), encoding='utf-8')
    (raiz / 'origen' / 'workspace.json').write_text(json.dumps({
        'id': 'origen',
        'pf_project_bindings': {'Oct/IN111': {'source_run_id': _RID}},
        'calibraciones': {'Oct/IN111': {'IN111': {'kw': 1.0}}},
        'demanda': {'medidores': {'path': str(raiz / 'medidores.xlsx'), 'name': 'medidores.xlsx'},
                    'perdido': {'path': str(raiz / 'no_existe.xlsx'), 'name': 'no_existe.xlsx'}},
        'groups': {'IN111_X': {'name': 'IN111_X', 'status': 'ok',
                               'dgs': str(run / 'salida' / 'IN111_X.dgs')}},
    }), encoding='utf-8')
    return run


def _espacio_sin_fuente(raiz, registro):
    ws = _espacio(raiz, 'nuevo', registro)
    ws.active_run_id = ws.loaded_run_id = None
    ws.loaded_source_mode = ws.loaded_source_fingerprint = None
    return ws


def test_018_rf9_rf10_espacio_nuevo_usa_la_ejecucion_con_la_que_se_acepto(tmp_path):
    """018:RF-9, 018:RF-10 — caso real CA101 (2026-10-15): un espacio nuevo, sin fuente, ve
    disponible la ejecución del vínculo y, al usarla, el proyecto deja de estar bloqueado sin
    volver a abrir DIgSILENT; trae la calibración, el DGS unido de esa ejecución y los libros
    de demanda que siguen en disco."""
    from igea_dgs.powerfactory_binding import record_project_binding
    from igea_dgs.web import services

    raiz = tmp_path / 'web'
    registro = raiz / 'vinculos_pf.json'
    origen = _espacio_origen_en_disco(raiz)
    # El vínculo se graba desde fuera de la raíz: el espacio que trabajó el proyecto es «origen».
    record_project_binding(_espacio(tmp_path, 'fuera', registro), _binding(source_run_id=_RID))
    ws = _espacio_sin_fuente(raiz, registro)

    antes = services.estado_vinculos(ws, [dict(p) for p in ws.pf_inventory['projects']])[0]
    assert antes['binding_blocked_code'] == 'PROJECT_BINDING_NO_ACTIVE_SOURCE'
    assert antes['binding_fuente_disponible'] is True

    inventario = services.adoptar_fuente_del_vinculo(ws, 'Oct/IN111')
    despues = inventario['projects'][0]
    assert despues['binding_blocked_code'] is None
    assert ws.active_run_id == _RID
    assert (ws.root / 'runs' / _RID / 'salida' / 'IN111.dgs').read_text(encoding='utf-8') == 'dgs'
    assert (origen / 'salida' / 'IN111.dgs').is_file()
    assert ws.calibraciones['Oct/IN111'] == {'IN111': {'kw': 1.0}}
    assert list(ws.demanda) == ['medidores']
    assert ws.groups['IN111_X']['dgs'] == str(ws.root / 'runs' / _RID / 'salida' / 'IN111_X.dgs')
    assert not (ws.root / 'runs' / f'{_RID}.copia').exists()
    # Repetirlo no falla, y el contexto sigue saliendo del espacio que trabajó el proyecto
    # aunque la ejecución ya sea la propia.
    ws.demanda = {}
    assert services.adoptar_fuente_del_vinculo(ws, 'Oct/IN111')['projects'][0][
        'binding_blocked_code'] is None
    assert list(ws.demanda) == ['medidores']


def test_018_rf10_ejecucion_con_otra_huella_no_se_usa(tmp_path):
    """018:RF-10 — una carpeta con el mismo identificador pero otra huella no es la fuente
    aceptada: no se ofrece, y pedirla no cambia nada."""
    from igea_dgs.powerfactory_binding import record_project_binding
    from igea_dgs.web import services

    raiz = tmp_path / 'web'
    registro = raiz / 'vinculos_pf.json'
    _espacio_origen_en_disco(raiz, huella='e' * 64)
    record_project_binding(_espacio(raiz, 'aceptó', registro), _binding(source_run_id=_RID))
    ws = _espacio_sin_fuente(raiz, registro)

    estado = services.estado_vinculos(ws, [dict(p) for p in ws.pf_inventory['projects']])[0]
    assert estado['binding_fuente_disponible'] is False
    with pytest.raises(services.UserError, match='PROJECT_BINDING_SOURCE_UNAVAILABLE'):
        services.adoptar_fuente_del_vinculo(ws, 'Oct/IN111')
    assert ws.active_run_id is None
    assert not (ws.root / 'runs').exists()


def test_018_rf12_verificar_compara_con_el_manifiesto_sin_la_red_en_memoria(tmp_path, monkeypatch):
    """018:RF-12 — tras reiniciar la web la red no está en memoria; para leer un proyecto ya
    importado basta el manifiesto en disco. Importar sigue exigiendo la red cargada."""
    from igea_dgs.web import services

    raiz = tmp_path / 'web'
    _espacio_origen_en_disco(raiz)
    ws = _espacio_sin_fuente(raiz, None)
    ws.root = raiz / 'origen'
    ws.active_run_id = _RID
    dgs = ws.out_dir / 'IN111.dgs'
    (ws.out_dir / 'IN111_feeder_metadata.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(
        'igea_dgs.feeder_metadata.read_feeder_metadata',
        lambda path, expected_dgs: {'source_run_id': _RID, 'source_mode': 'txt',
                                    'source_fingerprint': 'f' * 64, 'dgs_sha256': 'd' * 64},
    )
    evidencia = services.check_powerfactory_source_run(ws, ['IN111'], exigir_red_cargada=False)
    assert evidencia['source_run_id'] == _RID and evidencia['targets'][0]['dgs'] == dgs.name
    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.check_powerfactory_source_run(ws, ['IN111'])


def test_alimentador_solo_en_el_rotulo_de_su_barra_de_set(tmp_path):
    """022:RF-52 — el rótulo de la red externa de una barra de SET junta a sus alimentadores
    («PI101 + PI102»); cada uno vale para el vínculo (sistema Pisco, 2026-10-18: PI101 y
    SI114 solo salían ahí y la calibración del sistema se rechazaba)."""
    from igea_dgs.powerfactory_binding import (
        ProjectBindingError, alimentadores_de_rotulos, record_project_binding,
        require_project_binding,
    )

    assert alimentadores_de_rotulos(['PI102', 'PI101 + PI102 + PI116']) == {'PI101', 'PI102', 'PI116'}
    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(feeders=('IN111 + PI101', 'IN111')))
    ws.pf_inventory['projects'][0]['feeders'] = ['IN111 + PI101', 'IN111']
    assert require_project_binding(ws, 'Oct/IN111', ['IN111', 'PI101']).project == 'Oct/IN111'
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_FEEDER_MISMATCH'):
        require_project_binding(ws, 'Oct/IN111', ['PI102'])


def test_caso_base_de_un_alimentador_del_rotulo_de_su_barra(tmp_path):
    """022:RF-52 — un alimentador sin cargas solo está en el rótulo de su barra de SET: toma
    el estado del rótulo (CA103 y TM101 en Chincha, 2026-10-18, salían «sin verificar»)."""
    from igea_dgs.powerfactory_binding import caso_base_verificado, record_project_binding

    ws = _workspace(tmp_path)
    verificado = {'status': 'VERIFICADO', 'fallos': []}
    record_project_binding(ws, _binding(
        feeders=('IN111', 'IN111 + PI101'),
        native_reread={'status': 'VERIFICADO_PERSISTENCIA',
                       'caso_base': {'IN111': verificado, 'IN111 + PI101': verificado}}))
    assert caso_base_verificado(ws, 'Oct/IN111', ['IN111', 'PI101']) == {}
    assert caso_base_verificado(ws, 'Oct/IN111', ['PI102']) == {'PI102': ['sin verificar']}
