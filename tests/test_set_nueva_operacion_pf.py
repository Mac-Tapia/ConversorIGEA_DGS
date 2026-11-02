"""063:RF-6/RF-9; 011:RF-58 — operación aislada, sin aceptación nativa simulada."""
import pytest

import fake_pf
from apoyo import cargar_herramienta
from convertersmartgrid.native_action import build_native_action_context

g = cargar_herramienta('set_nueva_operacion_pf.py', 'operacion_set_prueba', tools_en_path=True)


def plan(**extra):
    p = {'project': 'P', 'feeders': ['F1'], 'accion': 'diagnostico'}
    p['native_action_context'] = build_native_action_context(
        {'project': 'P', 'source_run_id': 'origen'}, 'P', ['F1'], 'obras')
    return {**p, **extra}


@pytest.mark.parametrize('cambio', [
    {'clase': 'ElmLod', 'elemento': r'\P.IntPrj\L.ElmLod', 'atributos': {'plini': 1}},
    {'clase': 'ElmLne', 'elemento': 'SEC', 'atributos': {'nlnum': 2}},
    {'clase': 'ElmLne', 'elemento': r'\P.IntPrj\L.ElmLne', 'atributos': {'nlnum': True}},
    {'clase': 'ElmTr2', 'elemento': r'\P.IntPrj\T.ElmTr2', 'atributos': {'strn': 2}},
])
def test_rechaza_nominales_rutas_ambiguas_y_enteros_booleanos(cambio):
    """063:RF-6 — el plan no permite reducir demanda ni escribir fichas o rutas ambiguas."""
    with pytest.raises(ValueError):
        g.validar_plan(plan(accion='evaluar', cambios=[cambio]))


def test_no_impone_ajustes_por_defecto():
    """063:RF-6 — iopt_pq y demás opciones solo entran explícitas en el plan."""
    assert g.validar_plan(plan()).get('ajustes_flujo', {}) == {}
    with pytest.raises(ValueError):
        g.validar_plan(plan(ajustes_flujo={'iopt_net': 1}))


def red():
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=2, bt=True, flujo=True)
    app.atributos_en_variacion = True
    study = app.carpetas['study']
    casos = {n: study.CreateObject('IntCase', n) for n in ['Sin proyecto', 'Cargas nuevas', 'Con proyecto']}
    casos['Con proyecto'].Activate()
    app.GetFromStudyCase('ComLdf').iopt_net = 0
    linea = app.GetCalcRelevantObjects('*.ElmLne')[0]
    return app, casos, linea


def test_diagnostico_da_rutas_y_restaura_caso():
    """063:RF-9 — inventario completo por caso, con identidad nativa y catálogo."""
    app, casos, linea = red()
    casos['Sin proyecto'].Activate()
    out, rc = g.ejecutar(app, plan())
    assert rc == 0, out
    assert app.GetActiveStudyCase() is casos['Sin proyecto']
    con = out['casos']['Con proyecto']
    assert any(o['ruta'] == linea.GetFullName() for o in con['objetos']['ElmLne'])
    assert con['catalogo']['TypLne'][0]['ruta'].endswith('.TypLne')
    assert 'iopt_pq' in con['ajustes_flujo']


def test_scope_ajeno_rechazado_sin_escribir_red():
    """011:RF-58 — una referencia de otro proyecto se rechaza antes de crear obras."""
    app, casos, linea = red()
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': r'\OTRO.IntPrj\L.ElmLne', 'atributos': {'nlnum': 2}}]))
    assert rc == 2 and out['status'] == 'BLOQUEADO_DATOS'
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')


def test_evaluar_restaura_variaciones_y_no_escribe_demanda():
    """011:RF-58 — el ensayo borra solo sus obras y conserva cargas y atributos originales."""
    app, casos, linea = red()
    antes = linea.nlnum
    app.escrituras.clear()
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': antes + 1}}]))
    assert 'estudios' in out, out
    assert linea.nlnum == antes
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')
    assert not any(o.GetClassName() == 'ElmLod' for o, *_ in app.escrituras)
    assert app.GetActiveStudyCase() is casos['Con proyecto']


def test_aceptacion_falla_cerrada_sin_resultados():
    """063:RF-9 — convergencia sola no acredita cobertura ni abastecimiento."""
    ok, razones = g.validar_resultados({'converged': True}, {}, {}, {})
    assert not ok and razones


def test_evaluacion_restaura_escenario_original_y_carga_nueva(monkeypatch):
    """011:RF-58 — el escenario original y la carga que crea el medio tramo sobreviven."""
    app, casos, linea = red()
    origen = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Aprobado')
    origen.Activate()
    carga = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_Parte')
    carga.NewStage('Etapa_carga', -100, 1)
    app.GetRecordingStage().Deactivate()
    # El objeto solo existe cuando su carga está activa: mismo contrato de SplitLine.
    app.grabando = carga.GetContents('*.IntSstage')[0]
    medio = linea.GetParent().CreateObject('ElmLne', 'Medio_creado_por_carga')
    medio.nlnum, medio.dline, medio.typ_id = 1, .1, linea.typ_id
    app.grabando = None
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': medio.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 0, out
    assert app.GetActiveScenario() is origen
    assert carga in app.GetActiveNetworkVariations()
    assert medio in app.GetCalcRelevantObjects('*.ElmLne') and medio.nlnum == 1
    assert app.carpetas['scen'].GetContents('*.IntScenario') == [origen]


def test_aplicar_no_aceptada_conserva_obras_previas_y_desactiva_nuevas(monkeypatch):
    """063:RF-9 — el fallo eléctrico no elimina ni altera una obra preexistente."""
    app, casos, linea = red()
    previa = app.carpetas['scheme'].CreateObject('IntScheme', 'Obra_anterior')
    previa.NewStage('Etapa_previa', -100, 1)
    app.GetRecordingStage().Deactivate()
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': False}})
    out, rc = g.ejecutar(app, plan(accion='aplicar', desactivar_variaciones=['Obra_anterior'],
        ajustes_flujo={'iopt_lev': 1}, cambios=[{
            'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 2 and not out['aceptada']
    assert previa in app.GetActiveNetworkVariations()
    assert linea.nlnum == 1 and app.GetFromStudyCase('ComLdf').iopt_lev == 0
    creadas = [v for v in app.carpetas['scheme'].GetContents('*.IntScheme') if v is not previa]
    assert len(creadas) == 1 and creadas[0] not in app.GetActiveNetworkVariations()


def test_aplicar_aceptada_aisla_variacion_y_escenario(monkeypatch):
    """011:RF-58 — el candidato estructural y operativo solo permanece en Con proyecto."""
    app, casos, linea = red()
    origen = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Aprobado')
    origen.Activate()
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='aplicar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 0 and out['persistida'], out
    assert linea.nlnum == 2 and app.GetActiveScenario() is not origen
    casos['Sin proyecto'].Activate()
    assert linea.nlnum == 1 and not app.GetActiveNetworkVariations()


def test_limites_no_permiten_disimular_incumplimiento():
    """063:RF-9 — un plan no puede relajar la aceptación solicitada."""
    for limites in [{'tension_min_pu': .9}, {'tension_max_pu': 1.1}, {'cargabilidad_max_pct': 110}]:
        with pytest.raises(ValueError):
            g.validar_plan(plan(limites=limites))


@pytest.mark.parametrize('accion', ['evaluar', 'aplicar'])
def test_sincronizar_cargas_persiste_solo_al_aplicar(monkeypatch, accion):
    """063:RF-9 — sincronizar conserva cargas y solo persiste en una aplicación aceptada."""
    app, casos, linea = red()
    v = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_individual')
    v.NewStage('Etapa', -100, 1)
    app.grabando = None
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion=accion, sincronizar_cargas=True))
    assert rc == 0, out
    assert v in app.GetActiveNetworkVariations()
    casos['Cargas nuevas'].Activate()
    assert (v in app.GetActiveNetworkVariations()) is (accion == 'aplicar')


def test_firma_invalida_bloquea_antes_de_activar_proyecto():
    """018:RF-15 — el contexto fuente/proyecto se valida también dentro del guion."""
    app, casos, linea = red()
    p = plan()
    p['project'] = 'Ajeno'
    app.escrituras.clear()
    out, rc = g.ejecutar(app, p)
    assert rc == 2 and out['status'] == 'BLOQUEADO_DATOS'
    assert not app.escrituras


def test_tipo_de_otro_proyecto_no_se_resuelve_por_nombre():
    """011:RF-59 — solo una ficha por ruta exacta del catálogo propio es admisible."""
    app, casos, linea = red()
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {
            'typ_id': r'\Otro.IntPrj\Catalogo.IntPrjfolder\AAAC.TypLne'}}]))
    assert rc == 2 and 'catálogo' in out['error']
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')


def test_consumo_reducido_impide_aceptar_aunque_tension_y_corriente_cumplan():
    """063:RF-9 — una adaptación numérica no sustituye el abastecimiento de demanda."""
    barras = {'ruta': 'B', 'outserv': 0, 'm:u': 1.0}
    carga = {'ruta': 'L', 'outserv': 0, 'plini': 1., 'qlini': .1,
             'scale0': 1., 'm:Psum:bus1': .5, 'm:Qsum:bus1': .1}
    resumen = {'cobertura_completa': True, 'balance_completo': True, 'cantidad_barras': 1}
    objetos = {'ElmTerm': [barras], 'ElmLod': [carga]}
    ok, razones = g.validar_resultados({'converged': True}, resumen, objetos, {})
    assert not ok and any('demanda escrita' in r for r in razones)
    carga['m:Psum:bus1'] = 1.
    assert g.validar_resultados({'converged': True}, resumen, objetos, {}) == (True, [])


def test_fallo_intermedio_restaura_datos_y_conserva_solo_variaciones_propias(monkeypatch):
    """011:RF-58 — una excepción del motor no deja aplicada la primera mejora."""
    app, casos, linea = red()
    def falla(*_):
        raise RuntimeError('fallo del motor')
    monkeypatch.setattr(g, '_estudiar', falla)
    out, rc = g.ejecutar(app, plan(accion='evaluar', ajustes_flujo={'iopt_pq': 1}, cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 2 and 'fallo del motor' in out['error']
    assert linea.nlnum == 1 and app.GetFromStudyCase('ComLdf').iopt_pq == 0
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')


@pytest.mark.parametrize('accion', ['evaluar', 'aplicar'])
def test_sincronizacion_copia_nominales_a_escenario_propio_sin_tocar_original(monkeypatch, accion):
    """063:RF-9 — activar la variación no basta cuando la demanda vive en el escenario."""
    app, casos, linea = red()
    app.escenario_manda = True
    cargas = app.GetCalcRelevantObjects('*.ElmLod')
    for carga in cargas:
        carga.scale0, carga.i_scale = 1., 1
    carpeta = app.GetProjectFolder('scen', 1)
    con = carpeta.CreateObject('IntScenario', 'Con_aprobado')
    con.fotografiar()
    con.Activate()
    esperado = cargas[0].plini
    casos['Cargas nuevas'].Activate()
    sinobras = carpeta.CreateObject('IntScenario', 'Sin_obras_aprobado')
    sinobras.fotografiar()
    sinobras.Activate()
    cargas[0].plini = esperado / 2
    datos_originales = {k: dict(v) for k, v in sinobras._datos.items()}
    casos['Con proyecto'].Activate()
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion=accion, sincronizar_cargas=True))
    assert rc == 0, out
    assert out['sincronizacion_nominales']['verificada']
    assert sinobras._datos == datos_originales
    casos['Cargas nuevas'].Activate()
    if accion == 'aplicar':
        assert cargas[0].plini == pytest.approx(esperado)
        assert app.GetActiveScenario() is not sinobras
    else:
        assert cargas[0].plini == pytest.approx(esperado / 2)
        assert app.GetActiveScenario() is sinobras
