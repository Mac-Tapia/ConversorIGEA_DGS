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
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_MISSING'):
        require_project_binding(ws, 'Oct/IN111', ['IN111'])
    record_project_binding(ws, _binding())
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_FEEDER_MISMATCH'):
        require_project_binding(ws, 'Oct/IN111', ['OTRO'])


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
