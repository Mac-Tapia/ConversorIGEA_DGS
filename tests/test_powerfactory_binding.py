"""Contrato verificable entre una ejecución fuente y el proyecto PowerFactory nativo."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from apoyo import espacio_txt_custodiado
from convertersmartgrid.dominio.util import sha256_file


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
    from convertersmartgrid.adaptadores.powerfactory_binding import PowerFactoryProjectBinding

    values = {
        'project': 'Oct/IN191',
        'folder': 'Empresa',
        'source_run_id': 'run-active',
        'source_mode': 'txt',
        'source_fingerprint': 'f' * 64,
        'feeders': ('IN191',),
        'dgs_sha256': {'IN191': 'd' * 64},
        'native_inventory_sha256': 'n' * 64,
        'native_reread': {'status': 'VERIFICADO_PERSISTENCIA'},
        'accepted_at': 1_797_000_000.0,
    }
    values.update(overrides)
    return PowerFactoryProjectBinding(**values)


def _workspace(tmp_path):
    from convertersmartgrid.presentacion.web.workspace import Workspace

    ws = Workspace(id='binding', root=tmp_path)
    ws.active_run_id = 'run-active'
    ws.loaded_run_id = 'run-active'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = SimpleNamespace()
    ws.pf_inventory = {
        'folder': 'Empresa',
        'projects': [{
            'name': 'IN191', 'path': 'Oct/IN191', 'feeders': ['IN191'],
            'native_inventory_sha256': 'n' * 64,
        }],
    }
    return ws


def test_native_inventory_hash_is_wrapper_stable_and_excludes_operational_pq():
    from convertersmartgrid.adaptadores.powerfactory_binding import native_inventory_sha256

    term = _Obj('ElmTerm', r'Grid\B1.ElmTerm', ukNom=10.0, **{'p:alimentador': ['IN191']})
    cub = _Obj('StaCubic', r'Grid\B1\C1.StaCubic', cterm=term)
    typ = _Obj('TypLod', r'Library\Load.TypLod')
    load = _Obj(
        'ElmLod', r'Grid\SED1\L1.ElmLod', bus1=cub, typ_id=typ,
        plini=100.0, qlini=30.0, coslini=0.957826, **{'p:alimentador': 'IN191'},
    )
    app = _App([term, load, load])  # wrappers repetidos se colapsan por GetFullName.
    first = native_inventory_sha256(app, ['IN191'])

    load.plini, load.qlini, load.coslini = 140.0, 55.0, 0.91
    assert native_inventory_sha256(app, ['IN191']) == first

    load.bus1 = _Obj('StaCubic', r'Grid\B2\C1.StaCubic', cterm=_Obj('ElmTerm', r'Grid\B2.ElmTerm'))
    assert native_inventory_sha256(app, ['IN191']) != first


def test_native_inventory_hash_changes_with_equipment_or_feeder_label():
    from convertersmartgrid.adaptadores.powerfactory_binding import native_inventory_sha256

    typ = _Obj('TypLne', r'Library\AAAC70.TypLne')
    line = _Obj('ElmLne', r'Grid\L1.ElmLne', typ_id=typ, **{'p:alimentador': ['IN191']})
    app = _App([line])
    first = native_inventory_sha256(app, ['IN191'])
    line.typ_id = _Obj('TypLne', r'Library\AAAC95.TypLne')
    assert native_inventory_sha256(app, ['IN191']) != first
    line.typ_id = typ
    setattr(line, 'p:alimentador', ['OTRO'])
    assert native_inventory_sha256(app, ['IN191']) != first


def test_exact_active_binding_is_persisted_and_accepted(tmp_path):
    from convertersmartgrid.adaptadores.powerfactory_binding import record_project_binding, require_project_binding
    from convertersmartgrid.presentacion.web.workspace import Workspace

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    accepted = require_project_binding(ws, 'Oct/IN191', ['IN191'])
    assert accepted.source_run_id == 'run-active'
    assert accepted.feeders == ('IN191',)

    reopened = Workspace.load(tmp_path)
    reopened.active_run_id = 'run-active'
    reopened.loaded_run_id = 'run-active'
    reopened.loaded_source_mode = 'txt'
    reopened.loaded_source_fingerprint = 'f' * 64
    reopened.dataset = SimpleNamespace()
    assert require_project_binding(reopened, 'Oct/IN191', ['IN191']).binding_sha256


def test_equivalent_source_reload_is_warning_not_blocking(tmp_path):
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        project_binding_warnings, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(source_run_id='run-historical'))
    accepted = require_project_binding(ws, 'Oct/IN191', ['IN191'])
    warnings = project_binding_warnings(ws, 'Oct/IN191', ['IN191'])

    assert accepted.project == 'Oct/IN191'
    assert warnings == [{
        'code': 'PROJECT_BINDING_SOURCE_RUN_CHANGED',
        'message': (
            "La fuente se volvió a cargar como 'run-active'; conserva la misma "
            "huella que 'run-historical'."
        ),
        'elements': [],
    }]


def test_different_source_fingerprint_is_still_rejected(tmp_path):
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(
        source_run_id='run-historical', source_fingerprint='e' * 64,
    ))
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_SOURCE_MISMATCH'):
        require_project_binding(ws, 'Oct/IN191', ['IN191'])


def test_tras_reiniciar_la_web_el_vinculo_usa_el_manifiesto_activo(tmp_path, monkeypatch):
    """014:RF-17 — reiniciar la web no bloquea el proyecto: sin la fuente en memoria, la
    identidad sale del manifiesto persistido de la ejecución activa (CA191, 2026-10-14)."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(source_run_id='run-historical'))
    # Lo que queda tras reiniciar: solo ``active_run_id`` sobrevive en workspace.json.
    ws.loaded_run_id = ws.loaded_source_mode = ws.loaded_source_fingerprint = None
    ws.dataset = None
    manifiesto = SimpleNamespace(run_id='run-active', mode='txt', fingerprint='f' * 64)
    monkeypatch.setattr(ws, 'active_run', lambda: manifiesto)
    assert require_project_binding(ws, 'Oct/IN191', ['IN191']).project == 'Oct/IN191'

    manifiesto.fingerprint = 'e' * 64
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_SOURCE_MISMATCH'):
        require_project_binding(ws, 'Oct/IN191', ['IN191'])


def test_changed_native_topology_is_reported_but_does_not_block(tmp_path):
    """014:RF-17 — una modificación manual del modelo nativo se lista como aviso y no
    bloquea: el vínculo sigue siendo válido."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
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

    assert require_project_binding(ws, 'Oct/IN191', ['IN191']).project == 'Oct/IN191'
    warnings = project_binding_warnings(ws, 'Oct/IN191', ['IN191'])
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
    assert require_project_binding(ws, 'Oct/IN191', ['IN191']).project == 'Oct/IN191'
    assert project_binding_warnings(ws, 'Oct/IN191', ['IN191']) == []


def test_unbound_project_and_foreign_feeder_are_rejected(tmp_path):
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_MISSING') as missing:
        require_project_binding(ws, 'Oct/IN191', ['IN191'])
    assert missing.value.code == 'PROJECT_BINDING_MISSING'
    record_project_binding(ws, _binding())
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_FEEDER_MISMATCH'):
        require_project_binding(ws, 'Oct/IN191', ['OTRO'])


def test_vinculo_de_otro_espacio_sin_fuente_activa_se_dice_como_tal(tmp_path):
    """018:RF-3 — caso real 2026-10-14: el proyecto se aceptó en un espacio con fuente activa
    y se listó en otro espacio sin fuente activa; el mensaje decía «fuente activa None»."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.active_run_id = None
    ws.loaded_run_id = None
    ws.loaded_source_mode = None
    ws.loaded_source_fingerprint = None
    with pytest.raises(ProjectBindingError) as sin_fuente:
        require_project_binding(ws, 'Oct/IN191', ['IN191'])
    assert sin_fuente.value.code == 'PROJECT_BINDING_NO_ACTIVE_SOURCE'
    assert 'None' not in sin_fuente.value.detail


def test_tampered_persisted_binding_is_rejected(tmp_path):
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.pf_project_bindings['Oct/IN191']['source_fingerprint'] = 'x' * 64
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_RECORD_MISMATCH'):
        require_project_binding(ws, 'Oct/IN191', ['IN191'])


def test_failed_native_reread_is_fail_closed(tmp_path):
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.pf_inventory['projects'][0]['native_inventory_sha256'] = None
    ws.pf_inventory['projects'][0]['native_warning'] = 'API sin relectura'
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_NATIVE_UNREADABLE'):
        require_project_binding(ws, 'Oct/IN191', ['IN191'])


def test_caso_base_verificado_por_alimentador():
    """015:RF-13 — solo se calibra el alimentador cuyo «Caso base» está verificado; un
    vínculo de antes de la spec 015 cuenta como no verificado."""
    from types import SimpleNamespace

    from convertersmartgrid.adaptadores.powerfactory_binding import caso_base_verificado

    ws = SimpleNamespace(pf_project_bindings={
        'P': {'native_reread': {'caso_base': {
            'CA191': {'status': 'VERIFICADO', 'fallos': []},
            'PE194': {'status': 'NO_VERIFICADO', 'fallos': ['flujo']},
        }}},
        'VIEJO': {'native_reread': {'status': 'VERIFICADO_PERSISTENCIA'}},
    })
    assert caso_base_verificado(ws, 'P', ['CA191', 'PE194', 'SI293']) == {
        'PE194': ['flujo'], 'SI293': ['sin verificar']}
    assert caso_base_verificado(ws, 'VIEJO', ['CA191']) == {'CA191': ['sin verificar']}


def _espacio(tmp_path, nombre, registro):
    """Espacio de trabajo con la misma fuente activa que _workspace, en su propia carpeta."""
    ws = _workspace(tmp_path / nombre)
    ws.vinculos_compartidos = registro
    return ws


def test_018_rf1_vinculo_aceptado_en_un_espacio_vale_en_otro_con_la_misma_fuente(tmp_path):
    """018:RF-1 — un vínculo aceptado en un espacio vale en otro con la misma fuente activa."""
    from convertersmartgrid.adaptadores.powerfactory_binding import record_project_binding, require_project_binding

    registro = tmp_path / 'vinculos_pf.json'
    record_project_binding(_espacio(tmp_path, 'origen', registro), _binding())
    destino = _espacio(tmp_path, 'destino', registro)
    assert destino.pf_project_bindings == {}
    assert require_project_binding(destino, 'Oct/IN191', ['IN191']).project == 'Oct/IN191'


def test_018_rf1_otra_fuente_no_reutiliza_el_vinculo_compartido(tmp_path):
    """018:RF-1 — con otra fuente activa el vínculo compartido no se reutiliza."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    registro = tmp_path / 'vinculos_pf.json'
    record_project_binding(_espacio(tmp_path, 'origen', registro), _binding())
    destino = _espacio(tmp_path, 'destino', registro)
    destino.active_run_id = destino.loaded_run_id = 'run-otra'
    destino.loaded_source_fingerprint = 'e' * 64
    with pytest.raises(ProjectBindingError) as otra:
        require_project_binding(destino, 'Oct/IN191', ['IN191'])
    assert otra.value.code == 'PROJECT_BINDING_SOURCE_MISMATCH'


def test_018_rf2_registro_ilegible_bloquea_aunque_el_espacio_tenga_copia(tmp_path):
    """018:RF-2 — fail-closed: con el registro roto no se cae a la copia del espacio, y no se
    sobrescribe."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    registro = tmp_path / 'vinculos_pf.json'
    registro.write_text('{no es json', encoding='utf-8')
    ws = _espacio(tmp_path, 'espacio', registro)
    ws.pf_project_bindings['Oct/IN191'] = _binding().as_dict()
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_REGISTRY_UNREADABLE'):
        require_project_binding(ws, 'Oct/IN191', ['IN191'])
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_REGISTRY_UNREADABLE'):
        record_project_binding(ws, _binding())
    assert registro.read_text(encoding='utf-8') == '{no es json'


def test_018_rf4_mismo_nombre_en_otra_carpeta_no_es_el_mismo_proyecto(tmp_path):
    """018:RF-4 — el mismo nombre de proyecto en otra carpeta de DIgSILENT es otro proyecto."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding())
    ws.pf_inventory['folder'] = 'OtraCarpeta'
    with pytest.raises(ProjectBindingError) as otra:
        require_project_binding(ws, 'Oct/IN191', ['IN191'])
    assert otra.value.code == 'PROJECT_BINDING_FOLDER_MISMATCH'


def test_018_rf7_registro_conserva_todos_los_proyectos_sin_fichero_temporal(tmp_path):
    """018:RF-7 — el registro guarda todos los proyectos y no deja ficheros temporales."""
    import json

    from convertersmartgrid.adaptadores.powerfactory_binding import record_project_binding

    registro = tmp_path / 'vinculos_pf.json'
    ws = _espacio(tmp_path, 'espacio', registro)
    record_project_binding(ws, _binding())
    record_project_binding(ws, _binding(project='Oct/IN222', feeders=('IN222',)))
    datos = json.loads(registro.read_text(encoding='utf-8'))
    assert set(datos['vinculos']) == {'Oct/IN191', 'Oct/IN222'}
    assert not registro.with_name(registro.name + '.tmp').exists()


def test_018_rf8_arranque_siembra_los_vinculos_de_los_espacios_existentes(tmp_path):
    """018:RF-8 — al arrancar, los vínculos de los espacios existentes pasan al registro: un
    conflicto gana el aceptado más tarde, uno alterado se descarta y una segunda siembra no
    cambia nada."""
    import json

    from convertersmartgrid.presentacion.web.workspace import REGISTRO_VINCULOS_FILE, WorkspaceStore

    raiz = tmp_path / 'web'
    viejo = _binding(accepted_at=1.0, feeders=('IN191',)).as_dict()
    alterado = _binding(project='Oct/IN222', feeders=('IN222',)).as_dict()
    alterado['source_fingerprint'] = 'x' * 64
    nuevo = _binding(accepted_at=2.0, feeders=('IN191',), native_reread={'status': 'otro'})
    espacio_a = raiz / 'aaaa'
    espacio_a.mkdir(parents=True)
    (espacio_a / 'workspace.json').write_text(json.dumps(
        {'pf_project_bindings': {'Oct/IN191': viejo, 'Oct/IN222': alterado}}), encoding='utf-8')
    espacio_b = raiz / 'bbbb'
    espacio_b.mkdir()
    (espacio_b / 'workspace.json').write_text(json.dumps(
        {'pf_project_bindings': {'Oct/IN191': nuevo.as_dict()}}), encoding='utf-8')

    primera = WorkspaceStore(raiz)
    assert primera.siembra == {'añadidos': 1, 'actualizados': 1, 'iguales': 0, 'descartados': 1}
    registro = raiz / REGISTRO_VINCULOS_FILE
    datos = json.loads(registro.read_text(encoding='utf-8'))['vinculos']
    assert datos['Oct/IN191']['binding_sha256'] == nuevo.binding_sha256
    assert 'Oct/IN222' not in datos

    segunda = WorkspaceStore(raiz)
    assert segunda.siembra['añadidos'] == 0 and segunda.siembra['actualizados'] == 0


class _CtxSinEjecutar:
    """Si el servicio llega a usar el contexto, la exigencia del vínculo ya falló."""

    def __getattr__(self, name):
        raise AssertionError(f'se llegó a {name} sin vínculo')


def test_018_rf5_verificar_caso_base_exige_vinculo_en_el_servidor(tmp_path):
    """018:RF-5 — sin vínculo la API no verifica; la interfaz oculta el botón, pero no basta."""
    from convertersmartgrid.presentacion.web import services

    ws = _workspace(tmp_path)
    with pytest.raises(services.UserError, match='PROJECT_BINDING_MISSING'):
        services.pf_verificar_base(ws, _CtxSinEjecutar(), 'Oct/IN191', ['IN191'])


def test_018_rf14_el_nombre_de_la_red_por_sistema_vale_por_sus_alimentadores(tmp_path, monkeypatch):
    """018:RF-14 — verificar el «Caso base» o una acción nativa con el nombre de un sistema eléctrico pide al vínculo
    sus alimentadores, no el nombre del DGS; un alimentador suelto sigue igual. Universal: el sistema y sus alimentadores
    se sortean en cada corrida (cualquier empresa, sistema o alimentador; los reales solo son ensayos)."""
    import random
    import string

    from convertersmartgrid.adaptadores import powerfactory_binding
    from convertersmartgrid.presentacion.web import services

    azar = random.Random()
    codigo = lambda: ''.join(azar.choices(string.ascii_uppercase, k=2)) + str(azar.randint(100, 999))  # noqa: E731
    sistema = 'SISTEMA_' + ''.join(azar.choices(string.ascii_uppercase, k=azar.randint(3, 8)))
    del_sistema = sorted({codigo() for _ in range(azar.randint(2, 6))})
    suelto = next(c for c in iter(codigo, None) if c not in del_sistema)
    ws = _workspace(tmp_path)
    ws.groups = {sistema: {'feeders': list(del_sistema), 'status': 'ok'}}
    assert services.alimentadores_pedidos(ws, [sistema, del_sistema[0], suelto, ' ']) == [*del_sistema, suelto]
    pedidos = []

    def exigir(ws_, project, feeders):
        pedidos.append(sorted(feeders))
        raise powerfactory_binding.ProjectBindingError('PARADA', 'basta con ver lo pedido')

    monkeypatch.setattr(powerfactory_binding, 'require_project_binding', exigir)
    with pytest.raises(services.UserError, match='PARADA'):
        services.pf_verificar_base(ws, _CtxSinEjecutar(), f'P/{sistema}', [sistema])
    # 018:RF-19: la acción nativa ya no se detiene por el vínculo; lo pedido y el contexto, con los alimentadores.
    contexto = services.native_action_context(ws, f'P/{sistema}', [sistema], 'obras')
    assert pedidos == [del_sistema] * 2
    assert contexto['feeders'] == del_sistema


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

    from convertersmartgrid.presentacion.web import services

    ws = _workspace(tmp_path)
    activa = SimpleNamespace(run_id='nueva' if caso != 'misma ejecución' else 'vieja', mode='txt',
                             fingerprint='h' if caso != 'otra huella' else 'otra')
    monkeypatch.setattr(type(ws), 'active_run', lambda self: activa)
    binding = SimpleNamespace(source_run_id='vieja', source_mode='txt', source_fingerprint='h')
    monkeypatch.setattr(services, 'dgs_jobs', lambda ws_, f: ([], [] if caso == 'con su DGS' else ['A1']))
    adoptados = []
    monkeypatch.setattr(services, 'adoptar_fuente_del_vinculo', lambda ws_, p: adoptados.append(p))
    aviso = services.usar_ejecucion_del_vinculo(ws, 'P/RED', binding, ['A1'])
    assert (adoptados == ['P/RED']) is adopta
    assert (aviso is not None and 'no tiene su DGS' in aviso) is adopta


def test_018_rf15_las_acciones_nativas_no_cambian_la_ejecucion_activa(tmp_path, monkeypatch):
    """018:RF-15 — una acción nativa trabaja sobre el proyecto ya importado: aunque falte el
    DGS en la ejecución activa, no la cambia (Chincha, 2026-10-24)."""
    from types import SimpleNamespace

    from convertersmartgrid.adaptadores import powerfactory_binding
    from convertersmartgrid.presentacion.web import services

    ws = _workspace(tmp_path)
    binding = SimpleNamespace(dgs_sha256={}, source_run_id='vieja')
    monkeypatch.setattr(powerfactory_binding, 'require_project_binding', lambda *_a: binding)
    monkeypatch.setattr(powerfactory_binding, 'project_binding_warnings', lambda *_a: [])
    monkeypatch.setattr(services, 'comprobar_dgs_vinculados', lambda *_a: None)
    monkeypatch.setattr(services, 'usar_ejecucion_del_vinculo',
                        lambda *_a: pytest.fail('una acción nativa no cambia la ejecución activa'))
    monkeypatch.setattr('convertersmartgrid.dominio.native_action.build_native_action_context',
                        lambda b, p, f, a, warnings: {'feeders': f, 'warnings': warnings})
    assert services.native_action_context(ws, 'P', ['PN197'], 'obras')['feeders'] == ['PN197']


def test_018_rf6_dgs_distinto_del_aceptado_bloquea_y_sin_huella_no_bloquea(tmp_path, monkeypatch):
    """018:RF-6 — un DGS distinto del aceptado bloquea; un alimentador sin huella, no."""
    from convertersmartgrid.presentacion.web import services

    dgs = tmp_path / 'IN191.dgs'
    dgs.write_text('dgs', encoding='utf-8')
    (tmp_path / 'IN191_feeder_metadata.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(services, 'dgs_jobs', lambda ws, feeders: ([('IN191', dgs, None)], []))
    monkeypatch.setattr(
        'convertersmartgrid.adaptadores.feeder_metadata.read_feeder_metadata',
        lambda path, expected_dgs: {'dgs_sha256': 'b' * 64},
    )
    ws = _workspace(tmp_path)
    with pytest.raises(services.UserError, match='PROJECT_BINDING_DGS_MISMATCH'):
        services.comprobar_dgs_vinculados(ws, {'IN191': 'a' * 64}, ['IN191'])
    services.comprobar_dgs_vinculados(ws, {'IN191': 'b' * 64}, ['IN191'])
    services.comprobar_dgs_vinculados(ws, {}, ['IN191'])


def _espacio_origen_en_disco(raiz, *, seed=7801):
    """Espacio que aceptó el proyecto: su ejecución en disco, calibración y DGS unido."""
    ws = espacio_txt_custodiado(raiz / 'origen', seed=seed, feeder_name='IN191')
    snapshot = ws.active_run()
    run = snapshot.root
    (raiz / 'medidores.xlsx').write_bytes(b'')
    dgs = run / 'salida' / 'IN191.dgs'
    (run / 'salida' / 'IN191_X.dgs').write_bytes(dgs.read_bytes())
    ws.pf_project_bindings['Oct/IN191'] = _binding(
        source_run_id=snapshot.run_id, source_fingerprint=snapshot.fingerprint,
        dgs_sha256={'IN191': sha256_file(dgs)}).as_dict()
    ws.calibraciones = {'Oct/IN191': {'IN191': {'kw': 1.0}}}
    ws.demanda = {'medidores': {'path': str(raiz / 'medidores.xlsx'), 'name': 'medidores.xlsx'},
                  'perdido': {'path': str(raiz / 'no_existe.xlsx'), 'name': 'no_existe.xlsx'}}
    ws.groups = {'IN191_X': {'name': 'IN191_X', 'status': 'ok',
                            'dgs': str(run / 'salida' / 'IN191_X.dgs')}}
    ws.save()
    return ws


def _espacio_sin_fuente(raiz, registro):
    ws = _espacio(raiz, 'nuevo', registro)
    ws.active_run_id = ws.loaded_run_id = None
    ws.loaded_source_mode = ws.loaded_source_fingerprint = None
    return ws


def test_018_rf9_rf10_espacio_nuevo_usa_la_ejecucion_con_la_que_se_acepto(tmp_path):
    """018:RF-9, 018:RF-10 — caso real CA191 (2026-10-15): un espacio nuevo, sin fuente, ve
    disponible la ejecución del vínculo y, al usarla, el proyecto deja de estar bloqueado sin
    volver a abrir DIgSILENT; trae la calibración, el DGS unido de esa ejecución y los libros
    de demanda que siguen en disco."""
    from convertersmartgrid.adaptadores.powerfactory_binding import record_project_binding
    from convertersmartgrid.presentacion.web import services

    raiz = tmp_path / 'web'
    registro = raiz / 'vinculos_pf.json'
    origen = _espacio_origen_en_disco(raiz).active_run()
    # El vínculo se graba desde fuera de la raíz: el espacio que trabajó el proyecto es «origen».
    record_project_binding(_espacio(tmp_path, 'fuera', registro), _binding(
        source_run_id=origen.run_id, source_fingerprint=origen.fingerprint,
        dgs_sha256={'IN191': sha256_file(origen.root / 'salida' / 'IN191.dgs')}))
    ws = _espacio_sin_fuente(raiz, registro)

    antes = services.estado_vinculos(ws, [dict(p) for p in ws.pf_inventory['projects']])[0]
    assert antes['binding_blocked_code'] == 'PROJECT_BINDING_NO_ACTIVE_SOURCE'
    assert antes['binding_fuente_disponible'] is True

    inventario = services.adoptar_fuente_del_vinculo(ws, 'Oct/IN191')
    despues = inventario['projects'][0]
    assert despues['binding_blocked_code'] is None
    assert ws.active_run_id == origen.run_id
    assert (ws.root / 'runs' / origen.run_id / 'salida' / 'IN191.dgs').read_bytes() == (
        origen.root / 'salida' / 'IN191.dgs').read_bytes()
    assert (origen.root / 'salida' / 'IN191.dgs').is_file()
    assert ws.calibraciones['Oct/IN191'] == {'IN191': {'kw': 1.0}}
    assert list(ws.demanda) == ['medidores']
    assert ws.groups['IN191_X']['dgs'] == str(ws.root / 'runs' / origen.run_id / 'salida' / 'IN191_X.dgs')
    assert not (ws.root / 'runs' / f'{origen.run_id}.copia').exists()
    # Repetirlo no falla, y el contexto sigue saliendo del espacio que trabajó el proyecto
    # aunque la ejecución ya sea la propia.
    ws.demanda = {}
    assert services.adoptar_fuente_del_vinculo(ws, 'Oct/IN191')['projects'][0][
        'binding_blocked_code'] is None
    assert list(ws.demanda) == ['medidores']


def test_018_rf10_ejecucion_con_otra_huella_no_se_usa(tmp_path):
    """018:RF-10 — una carpeta con el mismo identificador pero otra huella no es la fuente
    aceptada: no se ofrece, y pedirla no cambia nada."""
    from convertersmartgrid.adaptadores.powerfactory_binding import record_project_binding
    from convertersmartgrid.presentacion.web import services

    raiz = tmp_path / 'web'
    registro = raiz / 'vinculos_pf.json'
    from convertersmartgrid.presentacion.web.source_runs import verify_source_files

    origen = _espacio_origen_en_disco(raiz, seed=7802).active_run()
    referencia = espacio_txt_custodiado(tmp_path / 'referencia', feeder_name='IN191').active_run()
    verify_source_files(origen)
    assert origen.fingerprint != referencia.fingerprint
    record_project_binding(_espacio(raiz, 'aceptó', registro), _binding(
        source_run_id=origen.run_id, source_fingerprint=referencia.fingerprint))
    ws = _espacio_sin_fuente(raiz, registro)

    estado = services.estado_vinculos(ws, [dict(p) for p in ws.pf_inventory['projects']])[0]
    assert estado['binding_fuente_disponible'] is False
    with pytest.raises(services.UserError, match='PROJECT_BINDING_SOURCE_UNAVAILABLE'):
        services.adoptar_fuente_del_vinculo(ws, 'Oct/IN191')
    assert ws.active_run_id is None
    assert not (ws.root / 'runs').exists()


def test_018_rf12_verificar_compara_con_el_manifiesto_sin_la_red_en_memoria(tmp_path, monkeypatch):
    """018:RF-12 — tras reiniciar la web la red no está en memoria; para leer un proyecto ya
    importado basta el manifiesto en disco. Importar sigue exigiendo la red cargada."""
    from convertersmartgrid.presentacion.web import services

    raiz = tmp_path / 'web'
    from convertersmartgrid.presentacion.web.workspace import Workspace

    origen = _espacio_origen_en_disco(raiz).active_run()
    ws = Workspace.load(raiz / 'origen')
    dgs = ws.out_dir / 'IN191.dgs'
    evidencia = services.check_powerfactory_source_run(ws, ['IN191'], exigir_red_cargada=False)
    assert evidencia['source_run_id'] == origen.run_id and evidencia['targets'][0]['dgs'] == dgs.name
    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.check_powerfactory_source_run(ws, ['IN191'])


def test_092_reconstruccion_verificada_con_el_disco_sin_la_red_en_memoria(tmp_path, monkeypatch):
    """092:RF-1 / 092:RF-2 / 092:RF-3 / 092:RF-4 — Pisco (2026-11-05): cargar la red creaba otra ejecución y adoptar la
    del vínculo la invalidaba, y el «Caso base» de la red reconstruida pedía otra vez cargarla. Al leer un proyecto
    importado basta su informe en disco; con el informe cambiado no se verifica; con una reconstrucción propia en la
    sesión se exige que sea la suya; importar sigue pidiendo la red cargada."""
    import json

    from convertersmartgrid.adaptadores.powerfactory_metadata import reconstruction_report_sha256
    from convertersmartgrid.presentacion.web import services

    raiz = tmp_path / 'web'
    from convertersmartgrid.presentacion.web.workspace import Workspace

    origen = _espacio_origen_en_disco(raiz).active_run()
    ws = Workspace.load(raiz / 'origen')
    informe = {'source_run_id': origen.run_id, 'counts': {'catalog_match': 0, 'engineering_assumption': 2},
               'decisions': [{'d': 1}, {'d': 2}]}
    informe['report_sha256'] = reconstruction_report_sha256(informe)
    (ws.out_dir / 'reconstruction_report.json').write_text(json.dumps(informe), encoding='utf-8')
    metadata_path = ws.out_dir / 'IN191_feeder_metadata.json'
    sidecar = json.loads(metadata_path.read_text(encoding='utf-8'))
    sidecar['reconstruction'] = {'report': 'reconstruction_report.json', 'report_sha256': informe['report_sha256'],
                                  'repairs': 2, 'catalog_matches': 0, 'assumptions': 2}
    metadata_path.write_text(json.dumps(sidecar), encoding='utf-8')
    assert ws.loaded_run_id is None and ws.reconstruction_run_id is None
    evidencia = services.check_powerfactory_source_run(ws, ['IN191'], exigir_red_cargada=False)
    assert evidencia['targets'][0]['reconstruction']['status'] == 'VERIFIED_BEFORE_MUTATION'
    # RF-4: importar sigue pidiendo la red cargada.
    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.check_powerfactory_source_run(ws, ['IN191'])
    # RF-3: una reconstrucción propia de la sesión que no es la del DGS no vale.
    ws.reconstruction_run_id, ws.reconstruction_report_hash = 'otra', 'e' * 64
    with pytest.raises(services.UserError, match='POWERFACTORY_RECONSTRUCTION_MISMATCH'):
        services.check_powerfactory_source_run(ws, ['IN191'], exigir_red_cargada=False)
    # RF-2: el informe cambiado en disco no se verifica.
    ws.reconstruction_run_id = ws.reconstruction_report_hash = None
    (ws.out_dir / 'reconstruction_report.json').write_text(json.dumps({**informe, 'decisions': []}), encoding='utf-8')
    with pytest.raises(services.UserError, match='POWERFACTORY_RECONSTRUCTION_MISMATCH'):
        services.check_powerfactory_source_run(ws, ['IN191'], exigir_red_cargada=False)


def test_alimentador_solo_en_el_rotulo_de_su_barra_de_set(tmp_path):
    """022:RF-52 — el rótulo de la red externa de una barra de SET junta a sus alimentadores
    («PI191 + PI192»); cada uno vale para el vínculo (sistema Pisco, 2026-10-18: PI191 y
    SI194 solo salían ahí y la calibración del sistema se rechazaba)."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, alimentadores_de_rotulos, record_project_binding,
        require_project_binding,
    )

    assert alimentadores_de_rotulos(['PI192', 'PI191 + PI192 + PI196']) == {'PI191', 'PI192', 'PI196'}
    ws = _workspace(tmp_path)
    record_project_binding(ws, _binding(feeders=('IN191 + PI191', 'IN191')))
    ws.pf_inventory['projects'][0]['feeders'] = ['IN191 + PI191', 'IN191']
    assert require_project_binding(ws, 'Oct/IN191', ['IN191', 'PI191']).project == 'Oct/IN191'
    # 092 T2 (Pisco, 2026-11-08): el «Caso base» pide los rótulos tal cual, con el de la barra.
    assert require_project_binding(ws, 'Oct/IN191', ['IN191 + PI191', 'IN191']).project == 'Oct/IN191'
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_FEEDER_MISMATCH'):
        require_project_binding(ws, 'Oct/IN191', ['PI192'])
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_FEEDER_MISMATCH'):
        require_project_binding(ws, 'Oct/IN191', ['IN191 + PI192'])


def test_caso_base_de_un_alimentador_del_rotulo_de_su_barra(tmp_path):
    """022:RF-52 — un alimentador sin cargas solo está en el rótulo de su barra de SET: toma
    el estado del rótulo (CA193 y TM191 en Chincha, 2026-10-18, salían «sin verificar»)."""
    from convertersmartgrid.adaptadores.powerfactory_binding import caso_base_verificado, record_project_binding

    ws = _workspace(tmp_path)
    verificado = {'status': 'VERIFICADO', 'fallos': []}
    record_project_binding(ws, _binding(
        feeders=('IN191', 'IN191 + PI191'),
        native_reread={'status': 'VERIFICADO_PERSISTENCIA',
                       'caso_base': {'IN191': verificado, 'IN191 + PI191': verificado}}))
    assert caso_base_verificado(ws, 'Oct/IN191', ['IN191', 'PI191']) == {}
    assert caso_base_verificado(ws, 'Oct/IN191', ['PI192']) == {'PI192': ['sin verificar']}


def test_081_rf75_relectura_anterior_a_la_importacion_no_cuenta_como_otro_proyecto(tmp_path):
    """081:RF-75 — la relectura guardada es de antes de importar: no puede conocer el proyecto nuevo.

    Caso real del 2026-11-05 (005 T12): el operador leyó los proyectos, reimportó PRUEBA_005 y el
    «Caso base» falló con PROJECT_BINDING_PROJECT_MISMATCH porque la lista era de antes.
    """
    from convertersmartgrid.adaptadores.powerfactory_binding import record_project_binding, require_project_binding

    ws = _workspace(tmp_path)
    ws.pf_inventory['projects'][0]['native_reread_at'] = 1_796_999_000.0       # antes de importar
    record_project_binding(ws, _binding(project='Oct/NUEVO', accepted_at=1_797_000_000.0))
    assert require_project_binding(ws, 'Oct/NUEVO', ['IN191']).project == 'Oct/NUEVO'


def test_081_rf75_relectura_posterior_sin_el_proyecto_sigue_fallando(tmp_path):
    """081:RF-75 — si la lista se leyó después de importar y el proyecto no está, ya no existe."""
    from convertersmartgrid.adaptadores.powerfactory_binding import (
        ProjectBindingError, record_project_binding, require_project_binding,
    )

    ws = _workspace(tmp_path)
    ws.pf_inventory['projects'][0]['native_reread_at'] = 1_797_000_500.0       # después de importar
    record_project_binding(ws, _binding(project='Oct/NUEVO', accepted_at=1_797_000_000.0))
    with pytest.raises(ProjectBindingError, match='PROJECT_BINDING_PROJECT_MISMATCH'):
        require_project_binding(ws, 'Oct/NUEVO', ['IN191'])


def _registro_heredado(tmp_path, monkeypatch, vinculos):
    """Un registro de una carpeta de datos anterior, con el formato de siempre, que la web nueva no conocía."""
    from convertersmartgrid.adaptadores import powerfactory_binding as pb

    ruta = tmp_path / 'heredado' / 'output' / 'web' / 'vinculos_pf.json'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({'schema': pb.REGISTRO_SCHEMA, 'vinculos': vinculos}), encoding='utf-8')
    monkeypatch.setattr(pb, 'registros_heredados', lambda: [ruta])
    return ruta


def test_018_rf18_el_vinculo_del_registro_anterior_se_reconoce_sin_escribir_en_el(tmp_path, monkeypatch):
    """018:RF-18 — un proyecto aceptado con la carpeta de datos anterior deja de salir como «no aceptado»; el registro
    anterior se lee y no se toca. (2026-11-13: un proyecto aceptado el día 9 salía como «importado a mano».)"""
    from convertersmartgrid.adaptadores.powerfactory_binding import vinculo_guardado

    ws = _workspace(tmp_path)
    ws.vinculos_compartidos = tmp_path / 'nuevo' / 'vinculos_pf.json'
    vinculo = _binding().as_dict()
    ruta = _registro_heredado(tmp_path, monkeypatch, {'Oct/IN191': vinculo})
    antes = ruta.read_bytes()
    hallado = vinculo_guardado(ws, 'Oct/IN191')
    assert hallado and hallado['binding_sha256'] == vinculo['binding_sha256']
    assert hallado['registro_heredado'] == str(ruta) and hallado['feeders'] == ['IN191']
    assert ruta.read_bytes() == antes and not ws.vinculos_compartidos.exists()


@pytest.mark.parametrize('cambio', ['huella', 'carpeta'])
def test_018_rf18_del_registro_anterior_solo_vale_un_vinculo_integro_y_de_esta_carpeta(tmp_path, monkeypatch, cambio):
    """018:RF-18 — un vínculo heredado cuya huella no cuadra con su contenido, o de otra carpeta de DIgSILENT, no se
    acepta a ciegas."""
    from convertersmartgrid.adaptadores.powerfactory_binding import vinculo_guardado

    ws = _workspace(tmp_path)
    ws.vinculos_compartidos = tmp_path / 'nuevo' / 'vinculos_pf.json'
    vinculo = _binding().as_dict() if cambio == 'huella' else _binding(folder='OtraEmpresa').as_dict()
    if cambio == 'huella':
        vinculo['feeders'] = ['IN191', 'IN999']               # contenido cambiado tras firmarlo
    _registro_heredado(tmp_path, monkeypatch, {'Oct/IN191': vinculo})
    assert vinculo_guardado(ws, 'Oct/IN191') is None


def test_018_rf18_el_registro_actual_gana_al_anterior(tmp_path, monkeypatch):
    """018:RF-18 — si el registro de la carpeta de datos en uso ya tiene el proyecto, el anterior ni se mira."""
    from convertersmartgrid.adaptadores import powerfactory_binding as pb

    ws = _workspace(tmp_path)
    ws.vinculos_compartidos = tmp_path / 'nuevo' / 'vinculos_pf.json'
    ws.vinculos_compartidos.parent.mkdir(parents=True)
    actual = _binding(source_run_id='run-nuevo').as_dict()
    ws.vinculos_compartidos.write_text(json.dumps({'schema': pb.REGISTRO_SCHEMA, 'vinculos': {'Oct/IN191': actual}}),
                                       encoding='utf-8')
    _registro_heredado(tmp_path, monkeypatch, {'Oct/IN191': _binding(source_run_id='run-viejo').as_dict()})
    hallado = pb.vinculo_guardado(ws, 'Oct/IN191')
    assert hallado['source_run_id'] == 'run-nuevo' and 'registro_heredado' not in hallado


def test_018_rf19_con_vinculo_heredado_la_calibracion_usa_su_caso_base(tmp_path, monkeypatch):
    """018:RF-19 — con el vínculo en el registro anterior, el contexto nativo lo usa (no uno armado) aunque la fuente
    activa del espacio no sea la suya, y el aviso lo dice sin «se importó a mano»."""
    from convertersmartgrid.presentacion.web import services

    ws = _workspace(tmp_path)
    ws.vinculos_compartidos = tmp_path / 'nuevo' / 'vinculos_pf.json'
    _registro_heredado(tmp_path, monkeypatch, {'Oct/IN191': _binding(source_run_id='run-de-otra-carpeta').as_dict()})
    contexto = services.native_action_context(ws, 'Oct/IN191', ['IN191'], 'ajuste')
    assert contexto['binding']['source_run_id'] == 'run-de-otra-carpeta'
    assert contexto['binding'].get('origen', 'conversion') == 'conversion'
    assert all('a mano' not in a['message'] for a in contexto['binding_warnings'])


class _CtxVerificacion:
    """Contexto de trabajo que anota el registro y las órdenes al guion, sin abrir DIgSILENT."""

    def __init__(self):
        self.registro: list[str] = []
        self.ordenes: list[list[str]] = []

    def log(self, texto):
        self.registro.append(str(texto))

    def progress(self, *_a):
        pass

    def check_cancel(self):
        pass

    def run_process(self, cmd, **_kw):
        self.ordenes.append([str(c) for c in cmd])
        return 0                     # sin informe: el resultado dice NO_VERIFICADO, que aquí no importa


def _con_geografia(ws):
    """Los DGS sintéticos se convierten sin geografía; la verificación la pide para comparar el GPS."""
    for dgs in ws.out_dir.glob('*.dgs'):
        dgs.with_name(f'{dgs.stem}_geography.json').write_text('{}', encoding='utf-8')


def _huellas(carpeta):
    return {p.relative_to(carpeta).as_posix(): sha256_file(p) for p in sorted(carpeta.rglob('*')) if p.is_file()}


def _dos_espacios(tmp_path, monkeypatch):
    """El espacio que convirtió el proyecto y el del operador, con otra conversión activa y su propio proyecto.

    Caso real (2026-11-27): un proyecto convertido en un espacio se recalibraba desde el del operador, que tiene
    activa otra conversión de los TXT y otros proyectos convertidos con ella. Los alimentadores se sortean: vale para
    cualquier empresa.
    """
    import random
    import string

    from convertersmartgrid.presentacion.web import services
    from convertersmartgrid.presentacion.web.workspace import Workspace

    azar = random.Random()
    ajeno, propio = azar.sample([''.join(azar.choices(string.ascii_uppercase, k=2)) + str(n)
                                 for n in range(100, 999)], 2)
    raiz = tmp_path / 'web'
    origen_ws = espacio_txt_custodiado(raiz / 'origen', seed=7803, feeder_name=ajeno)
    operador = espacio_txt_custodiado(raiz / 'operador', seed=7804, feeder_name=propio)
    for ws in (origen_ws, operador):
        _con_geografia(ws)
    origen, activa = origen_ws.active_run(), operador.active_run()
    assert origen.fingerprint != activa.fingerprint
    p_ajeno, p_propio = f'Oct/{ajeno}', f'Oct/{propio}'
    v_ajeno = _binding(project=p_ajeno, feeders=(ajeno,), source_run_id=origen.run_id,
                       source_fingerprint=origen.fingerprint,
                       dgs_sha256={ajeno: sha256_file(origen.root / 'salida' / f'{ajeno}.dgs')}).as_dict()
    v_propio = _binding(project=p_propio, feeders=(propio,), source_run_id=activa.run_id,
                        source_fingerprint=activa.fingerprint,
                        dgs_sha256={propio: sha256_file(activa.root / 'salida' / f'{propio}.dgs')}).as_dict()
    origen_ws.pf_project_bindings[p_ajeno] = v_ajeno
    origen_ws.save()
    operador = Workspace.load(raiz / 'operador')            # tras reiniciar la web: sin la red en memoria
    operador.pf_project_bindings.update({p_ajeno: v_ajeno, p_propio: v_propio})
    operador.pf_inventory = {'folder': 'Empresa', 'projects': [
        {'name': p.split('/')[-1], 'path': p, 'feeders': [f], 'native_inventory_sha256': 'n' * 64}
        for p, f in ((p_ajeno, ajeno), (p_propio, propio))]}
    operador.save()
    monkeypatch.setattr(services, '_require_pf', lambda: (None, tmp_path / 'python_de_pf.exe'))
    monkeypatch.setattr(services, '_gemelo', lambda *_a, **_k: None)
    return SimpleNamespace(operador=operador, origen=origen, activa=activa, ajeno=ajeno, propio=propio,
                           p_ajeno=p_ajeno, p_propio=p_propio)


def _verificar(ws, ctx, project, feeders):
    from convertersmartgrid.presentacion.web import services

    try:
        return services.pf_verificar_base(ws, ctx, project, feeders)
    except services.UserError as exc:
        return exc


def _argumento(orden, nombre):
    return orden[orden.index(nombre) + 1]


def test_018_rf20_caso_base_de_otra_fuente_con_la_ejecucion_del_vinculo_sin_cambiar_la_activa(tmp_path, monkeypatch):
    """018:RF-20 — el «Caso base» de un proyecto cuya ejecución del vínculo es de otra fuente y de otro espacio se
    verifica con los DGS y la geografía de esa ejecución, solo leyéndola: la ejecución activa del espacio no cambia,
    no se copia nada al espacio y el registro del trabajo lo dice. El otro proyecto del espacio, convertido con la
    fuente activa, se sigue verificando con ella, como antes."""
    caso = _dos_espacios(tmp_path, monkeypatch)
    ws, origen = caso.operador, caso.origen
    antes = _huellas(origen.root)
    ctx = _CtxVerificacion()
    resultado = _verificar(ws, ctx, caso.p_ajeno, [caso.ajeno])
    assert not isinstance(resultado, Exception), f'la verificación falló: {resultado}'
    assert ws.active_run_id == caso.activa.run_id
    assert not (ws.root / 'runs' / origen.run_id).exists()
    orden, = ctx.ordenes
    assert _argumento(orden, '--source-dgs') == str(origen.root / 'salida' / f'{caso.ajeno}.dgs')
    assert _argumento(orden, '--manifest') == str(origen.root / 'salida' / f'{caso.ajeno}_geography.json')
    assert _argumento(orden, '--source-run-id') == origen.run_id
    assert _argumento(orden, '--source-fingerprint') == origen.fingerprint
    # El informe va al espacio que verifica; la ejecución del otro espacio no se escribe.
    assert _argumento(orden, '--output-json') == str(ws.out_dir / f'{caso.ajeno}_caso_base.json')
    assert _huellas(origen.root) == antes
    assert any(origen.run_id in linea and 'activa' in linea for linea in ctx.registro), ctx.registro

    ctx = _CtxVerificacion()
    resultado = _verificar(ws, ctx, caso.p_propio, [caso.propio])
    assert not isinstance(resultado, Exception), f'la verificación falló: {resultado}'
    orden, = ctx.ordenes
    assert _argumento(orden, '--source-dgs') == str(ws.out_dir / f'{caso.propio}.dgs')
    assert _argumento(orden, '--source-run-id') == caso.activa.run_id
    assert not any(origen.run_id in linea for linea in ctx.registro)


@pytest.mark.parametrize('falta', ['carpeta', 'huella del manifiesto'])
def test_018_rf21_sin_la_ejecucion_del_vinculo_se_dice_que_hacer_sin_abrir_digsilent(tmp_path, monkeypatch, falta):
    """018:RF-21 — si la ejecución del vínculo ya no está en disco, o su manifiesto no es íntegro, la verificación se
    rechaza antes de abrir DIgSILENT con un mensaje que nombra la ejecución y dice qué hacer, y la activa no cambia."""
    import shutil

    caso = _dos_espacios(tmp_path, monkeypatch)
    ws, origen = caso.operador, caso.origen
    if falta == 'carpeta':
        shutil.rmtree(origen.root)
    else:
        manifiesto = origen.root / 'source_manifest.json'
        datos = json.loads(manifiesto.read_text(encoding='utf-8'))
        datos['files'][0]['sha256'] = '0' * 64             # la huella del manifiesto ya no cuadra con sus entradas
        manifiesto.write_text(json.dumps(datos), encoding='utf-8')
    ctx = _CtxVerificacion()
    resultado = _verificar(ws, ctx, caso.p_ajeno, [caso.ajeno])
    assert isinstance(resultado, Exception)
    mensaje = str(resultado)
    assert 'PROJECT_BINDING_SOURCE_UNAVAILABLE' in mensaje, mensaje
    assert origen.run_id in mensaje and 'vuelva a convertir' in mensaje.lower(), mensaje
    assert ctx.ordenes == []
    assert ws.active_run_id == caso.activa.run_id
