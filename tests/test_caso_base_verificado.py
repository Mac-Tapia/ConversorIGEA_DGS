"""Verificación del «Caso base» en la aceptación nativa (spec 015, T3 y T3b)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apoyo import cargar_herramienta

tool = cargar_herramienta('powerfactory_acceptance.py', 'pfa_015')


class _Obj:
    """Objeto de DIgSILENT mínimo: atributos, nombre y padre."""

    def __init__(self, nombre, padre=None, **attrs):
        self.loc_name = nombre
        self._padre = padre
        self.__dict__.update(attrs)

    def GetAttribute(self, n):
        return getattr(self, n)

    def SetAttribute(self, n, v):
        setattr(self, n, v)

    def GetParent(self):
        return self._padre


class _Carpeta(_Obj):
    def __init__(self):
        super().__init__('Equipment Type Library')
        self.hijos = []

    def GetContents(self, patron, *_):
        return [h for h in self.hijos if patron.endswith(type(h).__name__) or patron == '*']

    def AddCopy(self, obj, nombre):
        copia = _Obj(nombre, self, **{k: v for k, v in obj.__dict__.items()
                                      if k not in ('loc_name', '_padre')})
        copia.__class__ = type(obj)
        self.hijos.append(copia)
        return copia


class TypTr2(_Obj):
    pass


def _tipo(carpeta, nombre, kv, grupo=('D', 'YN', 5), mva=0.1):
    t = TypTr2(nombre, carpeta, strn=mva, utrn_l=kv, tr2cn_h=grupo[0], tr2cn_l=grupo[1],
               nt2ag=grupo[2])
    carpeta.hijos.append(t)
    return t


def _trafo(nombre, tipo, ntnum=1):
    return _Obj(nombre, typ_id=tipo, ntnum=ntnum)


def test_lee_capacidad_baja_y_grupo_del_tipo():
    """015:RF-6, 015:RF-32, 015:RF-33 — lo que DIgSILENT tiene de cada transformador y línea."""
    lib = _Carpeta()
    tr = _trafo('TR_A', _tipo(lib, 'TR_100kVA', 0.38), ntnum=2)
    sin_tipo = _Obj('TR_B', typ_id=None, ntnum=1)
    ln = _Obj('SEC_1', typ_id=_Obj('C', sline=0.142, InomAir=0.0), nlnum=2, inAir=1)
    eq = tool.leer_equipos_pf([tr, sin_tipo], [ln])
    assert eq['transformadores']['TR_A'].mva == pytest.approx(0.2)
    assert eq['transformadores']['TR_A'].kv_baja == 0.38
    assert eq['transformadores']['TR_A'].grupo == ('D', 'YN', 5)
    assert eq['transformadores']['TR_B'].mva is None
    assert eq['lineas']['SEC_1'].ka == pytest.approx(0.284)


def test_corrige_el_tipo_propio_sin_copiarlo():
    """015:RF-34, 015:RF-35 — si todos los que usan el tipo necesitan la corrección, se corrige el tipo."""
    lib = _Carpeta()
    tipo = _tipo(lib, 'TR_100kVA', 0.22)
    a, b = _trafo('TR_A', tipo), _trafo('TR_B', tipo)
    hechas = tool.corregir_trafos(
        [{'nombre': n, 'kv_baja': {'digsilent': 0.22, 'archivo': 0.38}} for n in ('TR_A', 'TR_B')],
        [a, b], [a, b])
    assert tipo.utrn_l == 0.38
    assert a.typ_id is tipo and b.typ_id is tipo
    assert [h['tipo_copiado'] for h in hechas] == [False, False]
    assert all(h['corregido'] for h in hechas)


def test_tipo_compartido_se_copia_solo_para_los_que_lo_necesitan():
    """015:RF-36 — un tipo de 220 V compartido: la SED de 380 V pasa a una copia corregida."""
    lib = _Carpeta()
    tipo = _tipo(lib, 'TR_100kVA', 0.22)
    bien, mal = _trafo('TR_220', tipo), _trafo('TR_380', tipo)
    hechas = tool.corregir_trafos(
        [{'nombre': 'TR_380', 'kv_baja': {'digsilent': 0.22, 'archivo': 0.38},
          'grupo': {'digsilent': ('Y', 'YN', 0), 'archivo': ('D', 'YN', 5)}}],
        [bien, mal], [bien, mal])
    assert tipo.utrn_l == 0.22 and bien.typ_id is tipo
    assert mal.typ_id is not tipo
    assert (mal.typ_id.utrn_l, mal.typ_id.tr2cn_h, mal.typ_id.nt2ag) == (0.38, 'D', 5)
    assert hechas[0]['tipo_copiado'] is True
    # Volver a verificar no duplica la copia.
    otra = _trafo('TR_380B', tipo)
    tool.corregir_trafos([{'nombre': 'TR_380B', 'kv_baja': {'digsilent': 0.22, 'archivo': 0.38},
                           'grupo': {'digsilent': ('Y', 'YN', 0), 'archivo': ('D', 'YN', 5)}}],
                         [bien, otra], [bien, otra, mal])
    assert otra.typ_id is mal.typ_id
    assert len([h for h in lib.hijos if isinstance(h, TypTr2)]) == 2


def test_sin_tipo_no_se_corrige_y_se_informa():
    """015:RF-35 — un transformador sin tipo no se puede corregir: se dice por qué."""
    hechas = tool.corregir_trafos([{'nombre': 'TR_X', 'kv_baja': {'digsilent': None, 'archivo': 0.38}}],
                                  [_Obj('TR_X', typ_id=None)], [])
    assert hechas == [{'nombre': 'TR_X', 'kv_baja': {'digsilent': None, 'archivo': 0.38},
                       'corregido': False, 'motivo': 'sin tipo asignado'}]


def _report(**cambios):
    base = {'gps': {'coordinate_mismatches': 0, 'invalid_in_manifest': 0,
                    'line_path_mismatches': 0, 'sin_coordenadas_en_archivo': 0},
            'connectivity': {'valid_lines': 3, 'total_lines': 3}, 'connectivity_pass': True,
            'geographic_diagram_pass': True, 'convergence_pass': True,
            'load_flow': {'requested': True}}
    base.update(cambios)
    return base


_SIN_FALLOS = {'sin_capacidad': [], 'capacidad_distinta': [], 'a_corregir': [], 'no_en_archivo': []}


def test_todo_bien_es_verificado():
    """015:RF-9 — cada comprobación por separado, y verificado si pasan todas."""
    r = tool.resumen_caso_base(_report(), _SIN_FALLOS, [], [])
    assert r['status'] == 'VERIFICADO'
    assert set(r['comprobaciones']) == {'gps_barras', 'trazado_lineas', 'conectividad',
                                        'diagrama', 'capacidades', 'flujo'}


@pytest.mark.parametrize('cambio, comprobacion', [
    ({'gps': {'coordinate_mismatches': 2}}, 'gps_barras'),
    ({'gps': {'line_path_mismatches': 1}}, 'trazado_lineas'),
    ({'connectivity_pass': False}, 'conectividad'),
    ({'geographic_diagram_pass': False}, 'diagrama'),
])
def test_cada_fallo_bloquea(cambio, comprobacion):
    """015:RF-2, 015:RF-3, 015:RF-4, 015:RF-5, 015:RF-10 — un fallo físico deja el «Caso base» sin verificar."""
    r = tool.resumen_caso_base(_report(**cambio), _SIN_FALLOS, [], [])
    assert r['status'] == 'NO_VERIFICADO'
    assert r['comprobaciones'][comprobacion]['pass'] is False


def test_sin_capacidad_bloquea_y_distinta_avisa():
    """015:RF-6, 015:RF-10, 015:RF-11 — sin capacidad bloquea; distinta solo se avisa."""
    falta = {**_SIN_FALLOS, 'sin_capacidad': [{'clase': 'ElmTr2', 'nombre': 'TR_A'}]}
    assert tool.resumen_caso_base(_report(), falta, [], [])['status'] == 'NO_VERIFICADO'
    distinta = {**_SIN_FALLOS, 'capacidad_distinta': [{'clase': 'ElmTr2', 'nombre': 'TR_A',
                                                        'magnitud': 'MVA', 'digsilent': 0.25,
                                                        'archivo': 0.2}]}
    r = tool.resumen_caso_base(_report(), distinta, [], [])
    assert r['status'] == 'VERIFICADO'
    assert any('TR_A' in a and '0.25' in a for a in r['avisos'])


def test_correcciones_y_variaciones_no_bloquean():
    """015:RF-12, 015:RF-31, 015:RF-34, 015:RF-35 — se avisan con sus valores y no bloquean."""
    corr = [{'nombre': 'TR_A', 'kv_baja': {'digsilent': 0.22, 'archivo': 0.38}, 'corregido': True}]
    r = tool.resumen_caso_base(_report(gps={'sin_coordenadas_en_archivo': 4}), _SIN_FALLOS, corr,
                               ['Ajuste_CA101_20261013_203247_3'])
    assert r['status'] == 'VERIFICADO'
    assert any('0.22 → 0.38' in a for a in r['avisos'])
    assert any('4 barras sin coordenadas' in a for a in r['avisos'])
    assert any('Ajuste_CA101_20261013_203247_3' in a for a in r['avisos'])



def test_diagrama_dice_su_motivo_y_la_curva_del_unifilar_solo_avisa():
    """015:RF-5, 015:RF-10 — caso real CA101 (2026-10-15): «diagrama» salía ✗ con la lista de
    fallos vacía, por 296 curvas del unifilar distintas del mapa con el GPS perfecto. El
    diagrama que falla dice por qué; la curva del unifilar se avisa y no bloquea."""
    falla = tool.resumen_caso_base(
        _report(geographic_diagram_pass=False,
                diagram={'fallos': ['el diagrama no tiene objetos gráficos']}),
        _SIN_FALLOS, [], [])
    assert falla['comprobaciones']['diagrama']['fallos'] == ['el diagrama no tiene objetos gráficos']
    curvas = {'compared': 488, 'distintas': 296, 'max_m': 642.01, 'muestra': []}
    r = tool.resumen_caso_base(_report(diagram={'curvas_grid_mapa': curvas, 'fallos': []}),
                               _SIN_FALLOS, [], [])
    assert r['status'] == 'VERIFICADO'
    assert any('296 líneas' in a and 'unifilar' in a for a in r['avisos'])


def test_equipos_que_el_archivo_no_trae_se_avisan_con_su_nombre():
    """015:RF-11 — caso real CA101 (2026-10-15): dos tramos partidos y tres condensadores
    dibujados a mano en el «Caso base» se avisan con su nombre y no bloquean."""
    equipos = {**_SIN_FALLOS, 'no_en_archivo': [{'clase': 'ElmLne', 'nombre': 'SEC_1_a'}]}
    reread = {'expected': 0, 'reread': 1, 'banks': [
        {'loc_name': 'Shunt/Filter', 'terminal': 'Terminal', 'catalog_kvar': 300.0}]}
    r = tool.resumen_caso_base(_report(capacitor_reread=reread), equipos, [], [])
    assert r['status'] == 'VERIFICADO'
    assert any('2 equipo(s)' in a and 'SEC_1_a' in a and 'Shunt/Filter' in a for a in r['avisos'])

@pytest.mark.parametrize('converge', [False, None])
def test_el_flujo_no_bloquea(converge):
    """015:RF-8, 015:RF-10, 015:RF-40 — el flujo se informa en su comprobación, pero el
    «Caso base» queda verificado si lo físico pasa."""
    r = tool.resumen_caso_base(_report(convergence_pass=converge), _SIN_FALLOS, [], [])
    assert r['status'] == 'VERIFICADO'
    assert r['comprobaciones']['flujo']['pass'] is False


def test_el_flujo_de_la_importacion_actualiza_el_resumen():
    """015:RF-8, 015:RF-38, 015:RF-39 — el flujo que corrió al importar, y su ajuste, van al
    resumen sin cambiar el estado."""
    r = tool.resumen_caso_base(_report(convergence_pass=None), _SIN_FALLOS, [], [])
    tool.actualizar_flujo_caso_base(r, True, {'pass': True, 'factor': 0.7, 'escenario': 'Operador'})
    assert r['status'] == 'VERIFICADO' and r['comprobaciones']['flujo']['pass'] is True
    assert any('70.0 %' in a and 'RF-38' in a for a in r['avisos'])
    tool.actualizar_flujo_caso_base(r, False, {'omitido': 'sin_proyecto'})
    assert r['status'] == 'VERIFICADO'
    assert any('RF-39' in a for a in r['avisos'])


def _red_que_no_converge(limite):
    import sys

    import fake_pf
    from apoyo import TOOLS

    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True,
                           escenario=True)
    app.escenario_manda = True
    app.escenario.fotografiar()
    app.ldf.limite = limite
    return app


def test_sin_converger_se_reduce_la_demanda_hasta_el_mayor_factor():
    """015:RF-38 — se baja por igual la demanda de todas las cargas hasta el mayor factor con
    que converge, y queda en el escenario del «Caso base»."""
    app = _red_que_no_converge(None)
    # El doble converge si la carga de cada alimentador no pasa del límite.
    mayor = max(sum(c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)
                    if c.loc_name.startswith(f)) for f in ('F1', 'F2'))
    app.ldf.limite = mayor * 0.62
    antes = {c.loc_name: c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)}
    ajuste = tool.converger_caso_base(app)
    assert ajuste['pass'] is True
    assert 0.55 < ajuste['factor'] <= 0.62
    assert app.escenario.guardados >= 1
    for c in app.proyecto.GetContents('*.ElmLod', 1):
        assert c.plini == pytest.approx(antes[c.loc_name] * ajuste['factor'], rel=1e-6)


def test_si_no_converge_ni_al_minimo_vuelve_la_demanda_original():
    """015:RF-40 — sin factor que converja, la demanda vuelve a la del archivo y se avisa."""
    app = _red_que_no_converge(1e-9)
    antes = {c.loc_name: c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)}
    ajuste = tool.converger_caso_base(app)
    assert ajuste['pass'] is False and ajuste['factor'] is None
    assert {c.loc_name: c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)} == pytest.approx(antes)
    r = tool.resumen_caso_base(_report(convergence_pass=False, load_flow={'requested': True, 'ajuste_de_cargas': ajuste}),
                               _SIN_FALLOS, [], [])
    assert r['status'] == 'VERIFICADO' and any('RF-40' in a for a in r['avisos'])


def test_proyecto_existente_exige_manifiesto(tmp_path, capsys):
    """015:RF-1 — sin la geografía del archivo original no se verifica el «Caso base»."""
    dgs = tmp_path / 'CA101.dgs'
    dgs.write_text('', encoding='utf-8')
    rc = tool.main(['--existing-project', 'P', '--source-dgs', str(dgs)])
    assert rc == 1
    assert 'requiere --manifest' in capsys.readouterr().err


def test_proyecto_existente_sin_remedios_del_flujo(tmp_path, capsys):
    """015:RF-8 — el «Caso base» se verifica tal como está, sin escalar cargas."""
    dgs = tmp_path / 'CA101.dgs'
    geo = tmp_path / 'CA101_geography.json'
    dgs.write_text('', encoding='utf-8')
    geo.write_text('{}', encoding='utf-8')
    rc = tool.main(['--existing-project', 'P', '--source-dgs', str(dgs), '--manifest', str(geo),
                    '--fix-until-converge'])
    assert rc == 1
    assert '--fix-until-converge' in capsys.readouterr().err


def test_activa_el_caso_marcado_como_caso_base(monkeypatch):
    """015:RF-1 — con los casos de la spec 011 se verifica «Caso base», no el caso activo."""
    activado = []
    caso = SimpleNamespace(loc_name='Caso base', Activate=lambda: activado.append(True))
    casos = cargar_herramienta('casos_pf.py', tools_en_path=True)
    monkeypatch.setitem(__import__('sys').modules, 'casos_pf', casos)
    monkeypatch.setattr(casos, 'casos_del_proyecto', lambda app: {'base': caso})
    assert tool.activar_caso_base(object()) == 'Caso base'
    assert activado == [True]


def test_calibrar_no_cambia_la_huella_y_un_cambio_fisico_si(monkeypatch):
    """015:RF-19, 015:RF-30 — la huella del inventario no incluye demandas ni la marca fija o
    escalable: calibrar no la cambia; cambiar el tipo de un transformador desde «Sin
    proyecto» sí, y se avisa contra la huella del «Caso base» verificado."""
    import fake_pf
    from test_ajuste_cabecera_guion import _plan

    from igea_dgs.powerfactory_binding import (
        PowerFactoryProjectBinding, native_inventory_evidence, project_binding_warnings,
    )

    ajuste = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_015_t10', tools_en_path=True)
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True,
                           kva=lambda f, i: 50.0 * i)
    huella, manifiesto = native_inventory_evidence(app, ['F1'])
    informe, rc = ajuste.ejecutar(app, _plan())
    assert rc == 0, informe
    assert native_inventory_evidence(app, ['F1'])[0] == huella

    sin = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Sin proyecto')
    sin.Activate()
    trafo = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_F1_S1')
    trafo.typ_id = app.carpetas['equip'].CreateObject('TypTr2', 'TR_250kVA')
    nueva, manifiesto_nuevo = native_inventory_evidence(app, ['F1'])
    assert nueva != huella

    binding = PowerFactoryProjectBinding(
        project='P', folder='F', source_run_id='run', source_mode='txt',
        source_fingerprint='f' * 64, feeders=('F1',), dgs_sha256={'F1': 'd' * 64},
        native_inventory_sha256=huella,
        native_reread={'status': 'VERIFICADO_PERSISTENCIA', 'inventory_manifest': manifiesto,
                       'caso_base': {'F1': {'status': 'VERIFICADO', 'fallos': []}}})
    ws = SimpleNamespace(
        pf_project_bindings={'P': binding.as_dict()}, active_run_id='run',
        loaded_source_mode='txt', loaded_source_fingerprint='f' * 64,
        pf_inventory={'projects': [{'path': 'P', 'feeders': ['F1'],
                                    'native_inventory_sha256': nueva,
                                    'native_inventory_manifest': manifiesto_nuevo}]})
    avisos = project_binding_warnings(ws, 'P', ['F1'])
    (modificado,) = [a for a in avisos if a['code'] == 'PROJECT_BINDING_NATIVE_MODIFIED']
    assert any(e['class'] == 'ElmTr2' and e['change'] == 'modified' for e in modificado['elements'])


def test_con_sin_proyecto_creado_no_se_corrige_el_caso_base():
    """015:RF-19, 015:RF-35 — si «Sin proyecto» ya existe, el grupo o la tensión de baja que
    difieren se informan y no se corrigen: el «Caso base» ya no se toca."""
    lib = _Carpeta()
    tipo = _tipo(lib, 'TR_100kVA', 0.22)
    tr = _trafo('TR_A', tipo)
    item = {'nombre': 'TR_A', 'kv_baja': {'digsilent': 0.22, 'archivo': 0.38}}
    equipos = {**_SIN_FALLOS, 'a_corregir': [item]}
    # Lo que hace run_acceptance con corregir=False, sin red de DIgSILENT.
    corregidas = [{**x, 'corregido': False, 'motivo': '«Sin proyecto» ya existe'}
                  for x in equipos['a_corregir']]
    r = tool.resumen_caso_base(_report(), equipos, corregidas, [])
    assert tipo.utrn_l == 0.22 and tr.typ_id is tipo
    assert any('no se pudo corregir' in a and 'Sin proyecto' in a for a in r['avisos'])
    import inspect
    fuente = inspect.getsource(tool.run_acceptance)
    assert 'if equipos[\'a_corregir\'] and corregir:' in fuente
    assert 'corregir=not sin_proyecto_existe(app)' in inspect.getsource(tool.main)


def test_un_proyecto_ya_importado_se_verifica_sin_flujo(tmp_path, capsys):
    """015:RF-8, 015:RF-39 — la convergencia se prueba al importar el DGS: al verificar un
    proyecto existente no hay comprobación de flujo, y la orden no admite correrlo."""
    r = tool.resumen_caso_base(_report(convergence_pass=None, load_flow={'requested': False}),
                               _SIN_FALLOS, [], [])
    assert 'flujo' not in r['comprobaciones'] and r['status'] == 'VERIFICADO'
    dgs = tmp_path / 'CA101.dgs'
    geo = tmp_path / 'CA101_geography.json'
    dgs.write_text('', encoding='utf-8')
    geo.write_text('{}', encoding='utf-8')
    for opcion in ('--run-load-flow', '--run-studies'):
        rc = tool.main(['--existing-project', 'P', '--source-dgs', str(dgs), '--manifest',
                        str(geo), opcion])
        assert rc == 1 and 'al importar el DGS' in capsys.readouterr().err
