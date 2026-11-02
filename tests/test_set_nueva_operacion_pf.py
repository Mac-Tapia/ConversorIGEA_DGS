"""063:RF-6/RF-9; 011:RF-58 — operación aislada, sin aceptación nativa simulada."""
import struct

import fake_pf
import pytest
from apoyo import cargar_herramienta

from convertersmartgrid.native_action import build_native_action_context

g = cargar_herramienta('set_nueva_operacion_pf.py', 'operacion_set_prueba', tools_en_path=True)


def plan(**extra):
    p = {'project': 'P', 'feeders': ['F1'], 'accion': 'diagnostico',
         'nuevas': [{'sed': 'F1_S1', 'alimentador': 'F1', 'variacion': 'Carga_base_prueba',
                     'barra': 'F1_S1_BT', 'kw': 50., 'kvar': 16.434205258943162}]}
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
    for carga in app.GetCalcRelevantObjects('*.ElmLod'):
        carga.outserv = 0
    base = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_base_prueba')
    base.Activate()
    casos['Cargas nuevas'].Activate()
    base.Activate()
    casos['Con proyecto'].Activate()
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
    app, _casos, _linea = red()
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': r'\OTRO.IntPrj\L.ElmLne', 'atributos': {'nlnum': 2}}]))
    assert rc == 2 and out['status'] == 'BLOQUEADO_DATOS'
    assert not any(v.loc_name.startswith('Obra_operacion_SET_') for v in app.carpetas['scheme'].GetContents('*.IntScheme'))


def test_evaluar_restaura_variaciones_y_no_escribe_demanda():
    """011:RF-58 — el ensayo borra solo sus obras y conserva cargas y atributos originales."""
    app, casos, linea = red()
    antes = linea.nlnum
    app.escrituras.clear()
    out, _rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': antes + 1}}]))
    assert 'estudios' in out, out
    assert linea.nlnum == antes
    assert not any(v.loc_name.startswith('Obra_operacion_SET_') for v in app.carpetas['scheme'].GetContents('*.IntScheme'))
    assert not any(o.GetClassName() == 'ElmLod' for o, *_ in app.escrituras)
    assert app.GetActiveStudyCase() is casos['Con proyecto']


def test_aceptacion_falla_cerrada_sin_resultados():
    """063:RF-9 — convergencia sola no acredita cobertura ni abastecimiento."""
    ok, razones = g.validar_resultados({'converged': True}, {}, {}, {})
    assert not ok and razones


def test_evaluacion_restaura_escenario_original_y_carga_nueva(monkeypatch):
    """011:RF-58 — el escenario original y la carga que crea el medio tramo sobreviven."""
    app, _casos, linea = red()
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
    app, _casos, linea = red()
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
    creadas = [v for v in app.carpetas['scheme'].GetContents('*.IntScheme') if v is not previa and not v.loc_name.startswith('Carga_')]
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
    app, casos, _linea = red()
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
    app, _casos, _linea = red()
    p = plan()
    p['project'] = 'Ajeno'
    app.escrituras.clear()
    out, rc = g.ejecutar(app, p)
    assert rc == 2 and out['status'] == 'BLOQUEADO_DATOS'
    assert not app.escrituras


def test_tipo_de_otro_proyecto_no_se_resuelve_por_nombre():
    """011:RF-59 — solo una ficha por ruta exacta del catálogo propio es admisible."""
    app, _casos, linea = red()
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {
            'typ_id': r'\Otro.IntPrj\Catalogo.IntPrjfolder\AAAC.TypLne'}}]))
    assert rc == 2 and 'catálogo' in out['error']
    assert not any(v.loc_name.startswith('Obra_operacion_SET_') for v in app.carpetas['scheme'].GetContents('*.IntScheme'))


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
    app, _casos, linea = red()
    def falla(*_):
        raise RuntimeError('fallo del motor')
    monkeypatch.setattr(g, '_estudiar', falla)
    out, rc = g.ejecutar(app, plan(accion='evaluar', ajustes_flujo={'iopt_pq': 1}, cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 2 and 'fallo del motor' in out['error']
    assert linea.nlnum == 1 and app.GetFromStudyCase('ComLdf').iopt_pq == 0
    assert not any(v.loc_name.startswith('Obra_operacion_SET_') for v in app.carpetas['scheme'].GetContents('*.IntScheme'))


@pytest.mark.parametrize('accion', ['evaluar', 'aplicar'])
def test_sincronizacion_copia_nominales_a_escenario_propio_sin_tocar_original(monkeypatch, accion):
    """063:RF-9 — activar la variación no basta cuando la demanda vive en el escenario."""
    app, casos, _linea = red()
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


def test_activar_idempotente_comprueba_identidad_nativa_con_wrappers_distintos(monkeypatch):
    """019:RF-1 — Activate=1 no es error si la ruta ya está activa en el motor."""
    app, casos, _linea = red()
    caso = casos['Con proyecto']
    class OtraReferencia:
        def GetFullName(self):
            return caso.GetFullName()
    monkeypatch.setattr(app, 'GetActiveStudyCase', lambda: OtraReferencia())
    llamadas = []
    monkeypatch.setattr(caso, 'Activate', lambda: llamadas.append('activar') or 1)
    g._activar(app, caso)
    assert not llamadas


def test_activar_uno_sin_identidad_activa_sigue_bloqueado(monkeypatch):
    """019:RF-1 — un retorno 1 con otro caso activo no se convierte en éxito."""
    app, casos, _linea = red()
    otro = casos['Sin proyecto']
    monkeypatch.setattr(otro, 'Activate', lambda: 1)
    with pytest.raises(RuntimeError, match='activar'):
        g._activar(app, otro)


def test_evaluar_soporta_activate_uno_si_caso_ya_activo(monkeypatch):
    """019:RF-1 — reproduce la secuencia nativa tras diagnosticar y volver a Con."""
    app, _casos, _linea = red()
    original = fake_pf.Caso.Activate
    def activar_nativo(self, *args):
        if app.GetActiveStudyCase().GetFullName() == self.GetFullName():
            return 1
        return original(self, *args)
    monkeypatch.setattr(fake_pf.Caso, 'Activate', activar_nativo)
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='evaluar'))
    assert rc == 0, out
    assert not out['restauracion_errores']


def test_aplicar_exige_relectura():
    """063:RF-9 — no se puede declarar persistencia sin releer el candidato."""
    with pytest.raises(ValueError, match='reabrir'):
        g.validar_plan(plan(accion='aplicar', reabrir=False))


@pytest.mark.parametrize('fallo', ['ausente', 'apagada', 'nominal', 'ambigua', 'variacion'])
def test_gate_cargas_previstas_impide_aceptar_inventario_incompleto(monkeypatch, fallo):
    """063:RF-9 — conservar lo presente no demuestra que todas las solicitudes estén."""
    app, _casos, _linea = red()
    obj = app.GetCalcRelevantObjects('*.ElmLod')[0]
    v = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_prevista')
    v.Activate()
    registro = {'sed': obj.loc_name, 'alimentador': 'F1', 'variacion': v.loc_name,
                'barra': obj.bus1.cterm.loc_name, 'kw': obj.plini * 1000, 'kvar': obj.qlini * 1000}
    if fallo == 'ausente':
        registro['sed'] = 'No_existe'
    elif fallo == 'apagada':
        obj.outserv = 1
    elif fallo == 'nominal':
        registro['kw'] *= 2
    elif fallo == 'ambigua':
        copia = obj.GetParent().AddCopy(obj, obj.loc_name + '(1)')
        copia.bus1 = obj.bus1
    else:
        v.Deactivate()
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='aplicar', nuevas=[registro]))
    assert rc == 2 and not out['aceptada'], out
    assert not out['variaciones_creadas']


def test_aplicar_con_wrapper_distinto_conserva_cambios_despues_finally(monkeypatch):
    """063:RF-9 — dos wrappers de la misma ruta nativa son el mismo caso."""
    app, casos, linea = red()
    real = casos['Con proyecto']
    class OtroWrapper:
        def __getattr__(self, nombre):
            return getattr(real, nombre)
    monkeypatch.setattr(g, 'casos_del_proyecto', lambda *_: {'con': OtroWrapper()})
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='aplicar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 0 and out['persistida'], out
    assert linea.nlnum == 2
    assert len(app.GetActiveNetworkVariations()) == 2


def test_guarda_copia_antes_aislar_y_la_reactiva_para_flujo(monkeypatch):
    """063:RF-9 — cambiar caso puede restaurar el escenario anterior en PowerFactory."""
    app, _casos, linea = red()
    carpeta = app.GetProjectFolder('scen', 1)
    original = carpeta.CreateObject('IntScenario', 'Aprobado')
    original.Activate()
    original_activar = fake_pf.Caso.Activate
    original_save = fake_pf.Escenario.Save
    eventos = []
    def cambiar_caso(self, *args):
        resultado = original_activar(self, *args)
        if self.loc_name == 'Con proyecto':
            original.Activate()
        return resultado
    def guardar(self):
        eventos.append(('guardar', self.GetFullName(), app.GetActiveScenario().GetFullName()))
        if app.GetActiveScenario().GetFullName() != self.GetFullName():
            return 1
        return original_save(self)
    def flujo(*_):
        actual = app.GetActiveScenario()
        assert actual.loc_name.startswith('Operacion_SET_')
        assert actual.guardados >= 1
        eventos.append(('flujo', actual.GetFullName()))
        return {'flujo': {'aceptada': True}}
    monkeypatch.setattr(fake_pf.Caso, 'Activate', cambiar_caso)
    monkeypatch.setattr(fake_pf.Escenario, 'Save', guardar)
    monkeypatch.setattr(g, '_estudiar', flujo)
    out, rc = g.ejecutar(app, plan(accion='evaluar', reabrir=False, cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 0, out
    assert eventos[0][0] == 'guardar' and eventos[-1][0] == 'guardar'


def test_save_fallido_expone_contexto_y_retorno(monkeypatch):
    """063:RF-9 — un Save=1 no se oculta ni se convierte en aceptación."""
    app, _casos, _linea = red()
    monkeypatch.setattr(fake_pf.Escenario, 'Save', lambda _: 1)
    out, rc = g.ejecutar(app, plan(accion='evaluar'))
    assert rc == 2 and not out['aceptada']
    assert out['guardados_escenarios'][-1]['retorno'] == 1
    assert out['contexto_error']['escenario_activo']
    assert 'salida_nativa' in out['contexto_error']


@pytest.mark.parametrize('db_correcta', [True, False])
def test_save_uno_exige_lectura_bd_y_reactivacion_identica(monkeypatch, db_correcta):
    """063:RF-9 — Save=1 sin modificación solo pasa con evidencia de BD y reapertura."""
    app, _casos, _linea = red()
    app.proyecto.Activate()
    esc = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Copia_propia')
    esc.Activate()
    monkeypatch.setattr(fake_pf.Escenario, 'Save', lambda _: 1)
    def valor_bd(_esc, obj, atributo, from_object):
        assert from_object == 0
        valor = obj.GetAttribute(atributo)
        if not db_correcta and atributo == 'plini':
            valor += 1
        return [0, valor]
    monkeypatch.setattr(fake_pf.Escenario, 'GetOperationValue', valor_bd, raising=False)
    informe = {}
    if db_correcta:
        g._guardar_escenario(app, esc, informe, 'prueba no modificado')
        evidencia = informe['guardados_escenarios'][-1]
        assert evidencia['retorno'] == 1
        assert evidencia['persistencia_verificada']['lectura_bd']
        assert evidencia['persistencia_verificada']['reactivacion_identica']
    else:
        with pytest.raises(RuntimeError, match='BD'):
            g._guardar_escenario(app, esc, informe, 'prueba datos distintos')


def test_operacion_se_graba_en_variacion_sin_escenario_y_en_copia(monkeypatch):
    """011:RF-58 — no se declara una obra propia si outserv solo quedó en escenario."""
    app, _casos, linea = red()
    original_set = fake_pf.Obj.SetAttribute
    def escribir_nativo(self, atributo, valor):
        # Los operacionales con escenario activo NO quedan en IntSstage.
        if atributo == 'outserv' and app.GetActiveScenario() is not None:
            object.__setattr__(self, atributo, valor)
            return None
        return original_set(self, atributo, valor)
    monkeypatch.setattr(fake_pf.Obj, 'SetAttribute', escribir_nativo)
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='aplicar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'outserv': 1}}]))
    assert rc == 0 and out['persistida'], out
    registro = out['variaciones_creadas'][0]['registro_etapa']
    assert registro['verificado'] and registro['atributos']['outserv'] == 1
    assert linea.outserv == 1


def test_save_no_modificado_usa_save_cero_previo_y_reapertura_completa(monkeypatch):
    """063:RF-9 — el subconjunto puede omitir coslini; no invalida un guardado ya confirmado."""
    app, _casos, _linea = red()
    app.proyecto.Activate()
    esc = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Copia_propia')
    esc.Activate()
    retornos = iter((0, 1))
    monkeypatch.setattr(fake_pf.Escenario, 'Save', lambda _: next(retornos))
    def no_es_operacional(*_):
        raise AssertionError('no consultar campos ausentes del subconjunto tras un Save=0 acreditado')
    monkeypatch.setattr(fake_pf.Escenario, 'GetOperationValue', no_es_operacional, raising=False)
    out = {}
    g._guardar_escenario(app, esc, out, 'primer guardado')
    g._guardar_escenario(app, esc, out, 'sin cambios')
    evidencia = out['guardados_escenarios'][-1]['persistencia_verificada']
    assert evidencia['guardado_previo_confirmado'] and evidencia['reactivacion_identica']


def test_save_cero_previo_no_oculta_diferencia_al_reabrir(monkeypatch):
    """063:RF-9 — el antecedente Save=0 nunca sustituye la igualdad completa después de reabrir."""
    app, _casos, _linea = red()
    app.proyecto.Activate()
    esc = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Copia_propia')
    esc.Activate()
    retornos, firmas = iter((0, 1)), iter(({'x': 1}, {'x': 1}, {'x': 2}))
    monkeypatch.setattr(fake_pf.Escenario, 'Save', lambda _: next(retornos))
    monkeypatch.setattr(g, '_firma_modelo', lambda _: next(firmas))
    out = {}
    g._guardar_escenario(app, esc, out, 'primer guardado')
    with pytest.raises(RuntimeError, match='reapertura'):
        g._guardar_escenario(app, esc, out, 'dato perdido')


def test_aplicar_captura_referencias_sin_usarlas_como_gate_de_con(monkeypatch):
    """063:RF-9 — se entregan los seis flujos, aunque las referencias no converjan."""
    app, casos, _linea = red()
    llamadas = []
    def flujo_referencia(app, *_):
        nombre = app.GetActiveStudyCase().loc_name
        llamadas.append(nombre)
        converge = nombre == 'Con proyecto'
        return {tipo: {'aceptada': converge, 'flujo': {'converged': converge}}
                for tipo in ('flujo', 'flujo_desequilibrado')}
    monkeypatch.setattr(g, '_estudiar', flujo_referencia)
    out, rc = g.ejecutar(app, plan(accion='aplicar', sincronizar_cargas=True))
    assert rc == 0 and out['persistida'], out
    assert llamadas[:2] == ['Sin proyecto', 'Cargas nuevas']
    for rol, esperado in [('sin', 'Sin proyecto'), ('cargas', 'Cargas nuevas')]:
        referencia = out['estudios_referencia'][rol]
        assert referencia['nombre_caso'] == esperado
        assert 'ajustes_flujo' in referencia
        assert not referencia['estudios']['flujo']['flujo']['converged']
    assert app.GetActiveStudyCase() is casos['Con proyecto']


def test_conciliar_fases_preserva_totales_y_reparto_en_copia():
    """063:RF-9 — corrige entradas de fase; la demanda calibrada sigue siendo la autoridad."""
    app, _casos, _linea = red()
    app.proyecto.Activate()
    esc = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Copia_fases')
    esc.Activate()
    carga = app.GetCalcRelevantObjects('*.ElmLod')[0]
    carga.i_sym = 1
    for f, p, q in zip('rst', (.06, .03, .01), (.03, .015, .005)):
        setattr(carga, 'plini' + f, p)
        setattr(carga, 'qlini' + f, q)
    antes = {a: carga.GetAttribute(a) for a in ('plini', 'qlini', 'scale0', 'mode_inp', 'i_sym', 'outserv')}
    audit = g._conciliar_fases(app, app.proyecto, esc)
    assert audit['cantidad'] == 1
    assert sum(getattr(carga, 'plini' + f) for f in 'rst') == pytest.approx(antes['plini'])
    assert sum(getattr(carga, 'qlini' + f) for f in 'rst') == pytest.approx(antes['qlini'])
    assert carga.plinir / carga.plinis == pytest.approx(2)
    assert {a: carga.GetAttribute(a) for a in antes} == antes


def test_conciliar_fases_exige_copia_activa_y_no_inventa_repartos():
    """063:RF-9 — no se interviene un escenario ajeno ni se inventa una distribución."""
    app, _casos, _linea = red()
    app.proyecto.Activate()
    copia = app.GetProjectFolder('scen', 1).CreateObject('IntScenario', 'Copia_fases')
    with pytest.raises(ValueError, match='copia'):
        g._conciliar_fases(app, app.proyecto, copia)

    copia.Activate()
    carga = app.GetCalcRelevantObjects('*.ElmLod')[0]
    carga.i_sym = 1
    for f in 'rst':
        setattr(carga, 'plini' + f, 0.)
        setattr(carga, 'qlini' + f, 0.)
    with pytest.raises(ValueError, match='reparto'):
        g._conciliar_fases(app, app.proyecto, copia)


def salida_de(linea, nombre='Salida_E'):
    origen, destino = linea.bus1.cterm, linea.bus2.cterm
    linea.typ_id.uline = origen.uknom
    return {'origen': origen.GetFullName(), 'destino': destino.GetFullName(),
            'tipo': linea.typ_id.GetFullName(), 'nombre': nombre, 'circuitos': 2,
            'ruta': [[origen.GPSlat, origen.GPSlon], [destino.GPSlat, destino.GPSlon]]}


@pytest.mark.parametrize('accion', ['evaluar', 'aplicar'])
def test_salidas_existente_cada_una_en_variacion_y_rollback_propio(monkeypatch, accion):
    """063:RF-36/RF-38 — la salida es nueva y la SET y los terminales existentes permanecen."""
    app, _casos, linea = red()
    oferta = salida_de(linea)
    gps = [(b.GPSlat, b.GPSlon) for b in (linea.bus1.cterm, linea.bus2.cterm)]
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion=accion, salidas=[oferta]))
    assert rc == 0, out
    creada = out['salidas_creadas'][0]
    assert len(creada['cubiculos']) == 2
    assert out['variaciones_creadas'][0]['registro_etapa']['verificado']
    halladas = [o for o in app.GetCalcRelevantObjects('*.ElmLne') if o.loc_name == oferta['nombre']]
    assert bool(halladas) is (accion == 'aplicar')
    if accion == 'aplicar':
        assert out['salidas_relectura'][0]['verificada']
        assert halladas[0].nlnum == 2
    assert [(b.GPSlat, b.GPSlon) for b in (linea.bus1.cterm, linea.bus2.cterm)] == gps


def test_segunda_salida_invalida_bloquea_lote_antes_de_cualquier_obra(monkeypatch):
    """063:RF-36 — todo el lote se valida por rutas antes de crear la primera etapa."""
    app, _casos, linea = red()
    primera, segunda = salida_de(linea), salida_de(linea, 'Salida_F')
    segunda['destino'] = r'\Ajeno.IntPrj\Barra.ElmTerm'
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='evaluar', salidas=[primera, segunda], cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 3}}]))
    assert rc == 2 and not out['variaciones_creadas']
    assert out['escenario_candidato'] is None and linea.nlnum == 1


def test_registro_etapa_admite_float32_sin_relajar_enteros_ni_referencias():
    """063:RF-38 — PowerFactory puede almacenar longitudes físicas en precisión simple."""
    app, _casos, linea = red()
    _v, etapa = g.crear_variacion(app, 'Obra_precision', 'Precision')
    pedida = 3.8959525026
    linea.dline = struct.unpack('f', struct.pack('f', pedida))[0]
    linea.nlnum = 2
    registro = g._verificar_registro_etapa(etapa, linea, {'dline': pedida, 'nlnum': 2, 'typ_id': linea.typ_id})
    assert registro['verificado']
    with pytest.raises(RuntimeError, match='no coinciden'):
        g._verificar_registro_etapa(etapa, linea, {'nlnum': 3})
    with pytest.raises(RuntimeError, match='no coinciden'):
        g._verificar_registro_etapa(etapa, linea, {'typ_id': 'otro_tipo.TypLne'})


def test_toma_fija_validada_con_tipo_real_y_persistida_en_copia(monkeypatch):
    """063:RF-38 — una toma fija conserva la potencia, las tensiones y la ubicación de la SET."""
    app, _casos, _linea = red()
    trafo = app.GetCalcRelevantObjects('*.ElmTr2')[0]
    trafo.typ_id.itapch, trafo.typ_id.dutap = 1, 1.25
    trafo.typ_id.ntpmn, trafo.typ_id.ntpmx = -8, 8
    trafo.nntap = 0
    parametros = {a: trafo.typ_id.GetAttribute(a) for a in ('strn', 'utrn_h', 'utrn_l')}
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion='aplicar', cambios=[{
        'clase': 'ElmTr2', 'elemento': trafo.GetFullName(), 'atributos': {'nntap': -2}}]))
    assert rc == 0 and out['persistida'], out
    assert trafo.nntap == -2
    assert out['variaciones_creadas'][0]['registro_etapa']['atributos']['nntap'] == -2
    assert {a: trafo.typ_id.GetAttribute(a) for a in parametros} == parametros


@pytest.mark.parametrize('atributo,valor', [('ntpmn', None), ('ntpmx', 1), ('itapch', 0), ('dutap', 0)])
def test_toma_no_admite_limites_inventados_ni_regulador_ausente(atributo, valor):
    """063:RF-38 — el rango de API no sustituye la capacidad física del cambiador."""
    app, _casos, _linea = red()
    trafo = app.GetCalcRelevantObjects('*.ElmTr2')[0]
    for a, v in {'itapch': 1, 'dutap': 1.25, 'ntpmn': -8, 'ntpmx': 8}.items():
        setattr(trafo.typ_id, a, v)
    setattr(trafo.typ_id, atributo, valor)
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmTr2', 'elemento': trafo.GetFullName(), 'atributos': {'nntap': 2}}]))
    assert rc == 2 and not out['variaciones_creadas']
    assert out['escenario_candidato'] is None
    assert 'cambiador' in out['error']


def test_toma_rechaza_booleanos_y_fuera_de_rango_schema():
    """063:RF-38 — las tomas siempre son posiciones enteras explícitas."""
    for posicion in (True, -101, 101, 1.5):
        with pytest.raises(ValueError):
            g.validar_plan(plan(accion='evaluar', cambios=[{
                'clase': 'ElmTr2', 'elemento': r'\P.IntPrj\T.ElmTr2', 'atributos': {'nntap': posicion}}]))


def test_toma_no_se_valida_con_tipo_anterior_si_se_pide_reemplazo():
    """063:RF-38 — una toma no hereda límites de un tipo que la misma obra sustituiría."""
    app, _casos, _linea = red()
    trafo = app.GetCalcRelevantObjects('*.ElmTr2')[0]
    out, rc = g.ejecutar(app, plan(accion='evaluar', cambios=[{
        'clase': 'ElmTr2', 'elemento': trafo.GetFullName(),
        'atributos': {'nntap': -2, 'typ_id': trafo.typ_id.GetFullName()}}]))
    assert rc == 2 and 'no se combina' in out['error']
    assert not out['variaciones_creadas'] and out['escenario_candidato'] is None


@pytest.mark.parametrize('accion', ['evaluar', 'aplicar'])
def test_finally_no_rebobina_fecha_ni_oculta_toma_y_salida(monkeypatch, accion):
    """063:RF-38 — IntSstage.Activate cambia la fecha; la persistencia se juzga después de finally."""
    app, casos, linea = red()
    oferta = salida_de(linea)
    vieja = app.GetProjectFolder('scheme').CreateObject('IntScheme', 'Obra_original')
    vieja.NewStage('Etapa_original', 100, 1)
    etapa_vieja = app.GetRecordingStage()
    casos['Con proyecto'].iStudyTime = 1000
    trafo = app.GetCalcRelevantObjects('*.ElmTr2')[0]
    trafo.nntap = 0
    for a, v in {'itapch': 1, 'dutap': 1.25, 'ntpmn': -8, 'ntpmx': 8}.items():
        setattr(trafo.typ_id, a, v)
    activar_original, visible_original = fake_pf.Obj.Activate, fake_pf.Obj.en_red.fget
    def activar_fecha(self, *args):
        self._app.GetActiveStudyCase().iStudyTime = self.tAcTime
        return activar_original(self, *args)
    def visible_fecha(self):
        if not visible_original(self):
            return False
        etapa = self.etapa_creacion
        return (etapa is None or not self._clase.startswith(('Elm', 'Sta'))
                or etapa.tAcTime <= self._app.GetActiveStudyCase().iStudyTime)
    monkeypatch.setattr(fake_pf.Etapa, 'Activate', activar_fecha)
    monkeypatch.setattr(fake_pf.Obj, 'en_red', property(visible_fecha))
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    out, rc = g.ejecutar(app, plan(accion=accion, sincronizar_cargas=True, salidas=[oferta], cambios=[{
        'clase': 'ElmTr2', 'elemento': trafo.GetFullName(), 'atributos': {'nntap': -2}}]))
    assert rc == 0, out
    assert casos['Con proyecto'].iStudyTime == 1000
    nuevas = [o for o in app.GetCalcRelevantObjects('*.ElmLne') if o.loc_name == oferta['nombre']]
    if accion == 'aplicar':
        assert nuevas and trafo.nntap == -2
        assert app.GetActiveScenario().loc_name.startswith('Operacion_SET_')
        assert out['verificacion_final']['modelo_identico']
        assert out['verificacion_final']['fecha'] >= out['verificacion_final']['ultima_etapa_nueva']
    else:
        assert not nuevas and trafo.nntap == 0
        assert app.GetRecordingStage().GetFullName() == etapa_vieja.GetFullName()


def test_verificacion_posterior_finally_fallida_revierte_candidato(monkeypatch):
    """063:RF-38 — un éxito anterior no se conserva si el estado físico final cambió."""
    app, _casos, linea = red()
    monkeypatch.setattr(g, '_estudiar', lambda *_: {'flujo': {'aceptada': True}})
    def fallar(*_):
        raise RuntimeError('modelo final distinto')
    monkeypatch.setattr(g, '_verificar_final', fallar)
    out, rc = g.ejecutar(app, plan(accion='aplicar', cambios=[{
        'clase': 'ElmLne', 'elemento': linea.GetFullName(), 'atributos': {'nlnum': 2}}]))
    assert rc == 2 and not out['persistida'] and not out['aceptada']
    assert out['status'] == 'BLOQUEADO_PERSISTENCIA'
    assert linea.nlnum == 1
    assert not any(v.loc_name.startswith('Obra_operacion_SET_') for v in app.GetActiveNetworkVariations())


def test_diagnostico_verifica_flujos_preexistentes_sin_recrear_ni_guardar(monkeypatch):
    """063:RF-38 — verifica un modelo reabierto conservando obra y escenario existentes."""
    app, casos, _linea = red()
    llamadas = []
    def estudiar(app, *_):
        llamadas.append(app.GetActiveStudyCase().GetFullName())
        return {n: {'aceptada': True} for n in ('flujo', 'flujo_desequilibrado')}
    monkeypatch.setattr(g, '_estudiar', estudiar)
    monkeypatch.setattr(fake_pf.Escenario, 'Save', lambda _: pytest.fail('diagnóstico no guarda escenarios'))
    casos['Sin proyecto'].Activate()
    app.creados.clear()
    out, rc = g.ejecutar(app, plan(verificar_flujos=True))
    assert rc == 0 and out['aceptada'] and out['operacion_preexistente_verificada'], out
    assert llamadas == [casos['Con proyecto'].GetFullName()]
    assert len(out['estudios']) == 2 and 'relectura' in out
    assert not out['variaciones_creadas'] and out['escenario_candidato'] is None
    assert not out.get('persistida') and not app.creados
    assert app.GetActiveStudyCase() is casos['Sin proyecto']


def test_verificar_flujos_rechaza_modificadores_y_exige_manifiesto():
    """063:RF-38 — el diagnóstico fresco no admite aplicar ajustes ni una cobertura implícita."""
    for extra in ({'accion': 'evaluar'}, {'nuevas': []}, {'ajustes_flujo': {'iopt_at': 0}},
                  {'conciliar_fases': True}, {'sincronizar_cargas': True}):
        with pytest.raises(ValueError):
            g.validar_plan(plan(verificar_flujos=True, **extra))
