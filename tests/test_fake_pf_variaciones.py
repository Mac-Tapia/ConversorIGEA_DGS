"""El doble de DIgSILENT con variaciones que se activan y desactivan (spec 007, T1).

Las pruebas del guion de cargas confían en él para comprobar que la carga *i* no ve la
*i−1*: si el doble dejara en la red lo creado en una variación inactiva, esas pruebas
pasarían sin probar nada.
"""
from __future__ import annotations

from fake_pf import proyecto


def _variacion(app, nombre):
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage(f'Etapa_{nombre}', 0, 1)
    return v


def _carga_colgada(app, barra, nombre, p=0.2):
    """Carga nueva con su barra de baja, colgada de ``barra`` por un interruptor."""
    red = barra.GetParent()
    b_bt = red.CreateObject('ElmTerm', f'{nombre}_BT')
    sw = red.CreateObject('ElmCoup', f'SW_{nombre}')
    for term, lado in ((barra, 0), (b_bt, 1)):
        cub = term.CreateObject('StaCubic', f'c{lado}_SW_{nombre}')
        cub.obj_id, cub.obj_bus = sw, lado
    carga = red.CreateObject('ElmLod', nombre)
    carga.plini, carga.coslini = p, 0.95
    cub = b_bt.CreateObject('StaCubic', f'c_{nombre}')
    cub.obj_id, cub.obj_bus = carga, 0
    return carga


def test_lo_creado_en_una_variacion_inactiva_sale_de_la_red():
    """apoyo de 007:RF-11 / 007:RF-12 — desactivar la variación quita sus objetos."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    barra = alim.GetObjs('ElmTerm')[1]
    v = _variacion(app, 'C1')
    carga = _carga_colgada(app, barra, 'NUEVA')
    assert carga in alim.GetObjs('ElmLod')
    assert carga in app.GetCalcRelevantObjects('*.ElmLod')
    v.Deactivate()
    assert carga not in alim.GetObjs('ElmLod')
    assert carga not in app.GetCalcRelevantObjects('*.ElmLod')
    assert app.GetRecordingStage() is None and app.GetActiveNetworkVariations() == []
    v.Activate()
    assert carga in alim.GetObjs('ElmLod') and app.GetActiveNetworkVariations() == [v]


def test_la_carga_i_no_ve_la_anterior():
    """apoyo de 007:RF-12 — con la variación de la anterior desactivada, el flujo no la suma."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2, bt=True, flujo=True)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    barras = [b for b in alim.GetObjs('ElmTerm') if not b.loc_name.endswith('_BT')]

    def cabecera():
        assert app.ldf.Execute() == 0
        return getattr(alim.obj_id.obj_id, f'm_Psum:bus{alim.obj_id.obj_bus + 1}')

    sin = cabecera()
    v1 = _variacion(app, 'C1')
    _carga_colgada(app, barras[1], 'N1', p=0.3)
    con_1 = cabecera()
    v1.Deactivate()
    v2 = _variacion(app, 'C2')
    _carga_colgada(app, barras[2], 'N2', p=0.1)
    con_2 = cabecera()
    assert con_1 > sin and sin < con_2 < con_1
    v2.Deactivate()
    assert abs(cabecera() - sin) < 1e-12


def test_otro_alimentador_no_ve_la_carga():
    """apoyo de 007:RF-25 — la carga colgada de F1 no es de F2."""
    app = proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=2)
    f1, f2 = app.proyecto.GetContents('*.ElmFeeder', 1)
    _variacion(app, 'C1')
    carga = _carga_colgada(app, f1.GetObjs('ElmTerm')[1], 'NUEVA')
    assert carga in f1.GetObjs('ElmLod') and carga not in f2.GetObjs('ElmLod')


# --------------------------------------------------------------------------- spec 011
# Las pruebas de los tres casos confían en que el doble separa lo que DIgSILENT separa:
# si una variación activada en «Con proyecto» se viera en «Sin proyecto», RF-64 (que
# «Sin proyecto» no cambia) pasaría sin probar nada.

def _otro_caso(app, nombre):
    return app.carpetas['study'].AddCopy(app.caso, nombre)


def test_las_variaciones_activas_son_de_cada_caso():
    """apoyo de 011:RF-7 / 011:RF-8 — activar otro caso cambia qué red se ve."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    sin, con = app.caso, _otro_caso(app, 'Con proyecto')
    con.Activate()
    v = _variacion(app, 'C1')
    carga = _carga_colgada(app, alim.GetObjs('ElmTerm')[1], 'NUEVA')
    assert carga in alim.GetObjs('ElmLod') and app.GetRecordingStage() is not None
    sin.Activate()
    assert carga not in alim.GetObjs('ElmLod')
    assert app.GetActiveNetworkVariations() == [] and app.GetRecordingStage() is None
    con.Activate()
    assert carga in alim.GetObjs('ElmLod') and app.GetActiveNetworkVariations() == [v]


def test_un_atributo_grabado_se_ve_solo_en_los_casos_de_su_variacion():
    """apoyo de 011:RF-57 / 011:RF-60 — con ``atributos_en_variacion``, el tipo que una obra
    asigna en «Con proyecto» no se ve en «Sin proyecto», y vuelve al activar «Con proyecto».

    Sin esto, una obra activa en un solo caso cambiaba la red de los dos, y la prueba de
    que el tramo conserva su tipo en el otro caso no podía fallar.
    """
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    app.atributos_en_variacion = True
    linea = app.proyecto.GetContents('*.ElmLne', 1)[0]
    original = linea.typ_id
    copia = app.carpetas['equip'].AddCopy(original, 'AAAC_F1_22_9kV')
    sin, con = app.caso, _otro_caso(app, 'Con proyecto')
    con.Activate()
    _variacion(app, 'Obra')
    linea.typ_id = copia
    sin.Activate()
    assert linea.typ_id is original
    con.Activate()
    assert linea.typ_id is copia


def test_copiar_un_caso_copia_sus_variaciones_activas():
    """apoyo de 011:RF-4 / 011:RF-5 — la copia nace con las variaciones del original,
    y activar otra en la copia no la activa en el original."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    base = _variacion(app, 'Ajuste')
    copia = _otro_caso(app, 'Sin proyecto')
    assert copia.loc_name == 'Sin proyecto' and copia.GetParent() is app.carpetas['study']
    original = app.caso
    copia.Activate()
    assert app.GetActiveNetworkVariations() == [base]
    otra = app.carpetas['scheme'].CreateObject('IntScheme', 'Obra')
    otra.Activate()
    original.Activate()
    assert app.GetActiveNetworkVariations() == [base]


def test_el_escenario_es_de_cada_caso():
    """apoyo de 011:RF-46 — el escenario activo de un caso no es el de otro."""
    app = proyecto(alimentadores=('F1',), escenario=True)
    original, esc = app.caso, app.GetActiveScenario()
    copia = _otro_caso(app, 'Sin proyecto')
    copia.Activate()
    assert app.GetActiveScenario() is esc          # la copia nace con él
    propio = esc.GetParent().AddCopy(esc, 'Sin proyecto')
    propio.Activate()
    assert app.GetActiveScenario() is propio
    original.Activate()
    assert app.GetActiveScenario() is esc


def test_la_copia_de_un_tipo_es_independiente():
    """apoyo de 011:RF-59 / 011:RF-60 — cambiar la copia no toca el original."""
    app = proyecto(alimentadores=('F1',))
    original = app.carpetas['equip'].GetContents('*.TypTr2')[0]
    copia = app.carpetas['equip'].AddCopy(original, original.loc_name, '_22_9kV')
    copia.utrn_h = 22.9
    assert copia.loc_name == 'TR100_F1_22_9kV' and copia.GetClassName() == 'TypTr2'
    assert original.utrn_h == 10.0 and copia.utrn_l == original.utrn_l
    assert copia.strn == original.strn


def test_copiar_desde_la_biblioteca_global():
    """apoyo de 011:RF-90 / 011:RF-92 — ``PasteCopy`` deja la copia en el proyecto."""
    app = proyecto(alimentadores=('F1',))
    glob = app.GetGlobalLibrary('TypLne').CreateObject('TypLne', 'AAAC_120')
    glob.uline, glob.sline = 22.9, 120.0
    error, copia = app.GetLocalLibrary('TypLne').PasteCopy(glob)
    assert error == 0 and copia.GetParent() is app.carpetas['equip']
    assert copia is not glob and copia.sline == 120.0


def test_copiar_una_carga_conserva_su_demanda():
    """apoyo de 011:RF-4 — la copia lleva P y cos φ, que la carga guarda aparte."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=1)
    carga = app.proyecto.GetContents('*.ElmLod', 1)[0]
    copia = carga.GetParent().AddCopy(carga, 'copia')
    assert copia.plini == carga.plini and copia.coslini == carga.coslini


def test_maniobrar_un_interruptor():
    """apoyo de 011:RF-109 / 011:RF-119 — ``Open``, ``Close`` e ``IsClosed``."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=1)
    red = app.proyecto.GetContents('*.ElmNet')[0]
    for clase in ('StaSwitch', 'ElmCoup'):
        sw = red.CreateObject(clase, f'SW_{clase}')
        sw.on_off = 1
        assert sw.IsClosed() == 1
        sw.Open()
        assert sw.IsClosed() == 0 and sw.on_off == 0
        sw.Close()
        assert sw.IsClosed() == 1


def test_mover_un_cubiculo_cambia_su_barra():
    """apoyo de 011:RF-75 — el regulador se intercala moviendo el cubículo del tramo."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=1)
    red = app.proyecto.GetContents('*.ElmNet')[0]
    b0 = red.GetContents('*.ElmTerm')[0]
    cub = b0.GetContents('*.StaCubic')[0]
    nueva = red.CreateObject('ElmTerm', 'F1_B0_REG')
    assert nueva.Move(cub) == 0
    assert cub.cterm is nueva and cub not in b0.GetContents('*.StaCubic')


# --------------------------------------------------------------------------- spec 012
# Las pruebas de los guiones de confiabilidad y capacidad confían en que el doble se
# comporta como DIgSILENT en las sondas del 2026-10-12: si el doble despejara fallas sin
# interruptor de cabecera, RF-69 pasaría sin probar nada.

def _con_modelos(app, dnfr=0.1, repmu=4.0):
    equip = app.carpetas['equip']
    sl = equip.CreateObject('StoTyplne', 'lineas')
    sl.DnFr, sl.RepMu = dnfr, repmu
    for ln in app.proyecto.GetContents('*.ElmLne', 1):
        ln.pStoch = sl
    return sl


def _cabecera(alim):
    """Interruptor automático con protección en el cubículo del primer tramo."""
    barra = alim.GetObjs('ElmTerm')[0]
    cub = next(c for c in barra.GetContents('*.StaCubic') if c.obj_id._clase == 'ElmLne')
    sw = cub.CreateObject('StaSwitch', 'cabecera')
    sw.aUsage, sw.rel_hasProt, sw.on_off = 'cbk', 1, 1
    return sw


def test_sin_interruptor_de_cabecera_no_se_despeja_ninguna_falla_de_linea():
    """apoyo de 012:RF-69 — como DIgSILENT: índices a cero y el error en la salida."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=3)
    _con_modelos(app)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    rel = app.caso.CreateObject('ComRel3', 'rel')
    assert rel.Execute() == 0
    assert alim.GetAttribute('c:SAIFI') == 0.0
    assert any('No protection devices' in x for x in app.salida)
    _cabecera(alim)
    app.salida.clear()
    rel.Execute()
    assert not any('No protection devices' in x for x in app.salida)
    assert abs(alim.GetAttribute('c:SAIFI') - 0.1 * 3) < 1e-9


def test_indices_del_alimentador_iguales_a_la_suma_de_sus_cargas():
    """apoyo de 012:RF-30 — SAIFI = ΣTCIF/ΣN, SAIDI = ΣTCIT/ΣN, ENS = ΣLPENS."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=4)
    _con_modelos(app)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    _cabecera(alim)
    for i, c in enumerate(alim.GetObjs('ElmLod')):
        c.NrCust = 10 * (i + 1)
    app.caso.CreateObject('ComRel3', 'rel').Execute()
    cargas = alim.GetObjs('ElmLod')
    n = sum(c.NrCust for c in cargas)
    assert abs(alim.GetAttribute('c:SAIFI') - sum(c.GetAttribute('c:TCIF') for c in cargas) / n) < 1e-12
    assert abs(alim.GetAttribute('c:SAIDI') - sum(c.GetAttribute('c:TCIT') for c in cargas) / n) < 1e-12
    assert abs(alim.GetAttribute('c:ENS') - sum(c.GetAttribute('c:LPENS') for c in cargas)) < 1e-12
    aportes = sum(ln.GetAttribute('c:CpENS') for ln in alim.GetObjs('ElmLne'))
    assert abs(aportes - 100.0) < 1e-9


def test_alimentador_sin_tension_da_ceros():
    """apoyo de 012:RF-71 — fuente fuera de servicio: índices cero, como en la sonda."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    _con_modelos(app)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    _cabecera(alim)
    object.__setattr__(alim, 'sin_tension', 1)
    app.caso.CreateObject('ComRel3', 'rel').Execute()
    assert alim.GetAttribute('c:ENS') == 0.0


def test_reconectadores_en_su_variacion_y_cambian_la_hora_de_estudio():
    """apoyo de 012:RF-35 / 012:RF-38 / 012:RF-60 — candidatos filtrados; desactivar la
    variación quita la marca; la hora de estudio cambia y el guion tendrá que restituirla."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=3)
    app.atributos_en_variacion = True
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    red = app.proyecto.GetContents('*.ElmNet')[0]
    bueno, fusible, sed = (red.CreateObject('ElmCoup', n) for n in ('EQ1', 'FUS1', 'SW_SED'))
    for sw, mejora in ((bueno, 50.0), (fusible, 80.0), (sed, 90.0)):
        sw.aUsage, sw.rel_hasProt, sw.on_off, sw.mejora_ens = 'cbk', 1, 1, mejora
        alim._objs.append(sw)
    excl = app.caso.CreateObject('SetSelect', 'excluidos')
    excl.AddRef([fusible, sed])
    op = app.caso.CreateObject('ComOpri', 'opri')
    op.excludedSwts, op.recResults, op.variationName, op.locations = excl, 2, 'tmp', 1
    hora = app.caso.iStudyTime
    assert op.Execute() == 0
    assert bueno.rel_hasRecl == 1 and getattr(fusible, 'rel_hasRecl', 0) == 0
    assert app.caso.iStudyTime != hora
    var = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme') if v.loc_name == 'tmp')
    assert app.GetRecordingStage() is not None
    var.Deactivate()
    assert not getattr(bueno, 'rel_hasRecl', None)
    assert any('The ENS is reduced by' in x for x in app.salida)


def test_alojamiento_nodo_sin_carga_no_se_calcula():
    """apoyo de 012:RF-44 / 012:RF-72 — en carga nueva, sin carga conectada, ``[1, 0, 0, None]``."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2, bt=True)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    hc = app.caso.CreateObject('ComHostcap', 'hc')
    media = [b for b in alim.GetObjs('ElmTerm') if b.uknom > 1.0]
    hc.objective = 1
    assert hc.CalcMaxHostedPower(media[0]) == [1, 0.0, 0.0, None]     # cabecera, sin SED
    codigo, p, _q, elem = hc.CalcMaxHostedPower(media[1])
    assert codigo == 2 and p > 0 and elem is not None
    hc.objective = 0
    assert hc.CalcMaxHostedPower(media[0])[0] == 2


def test_curvas_pv_escalan_solo_la_seleccion_y_no_cambian_demandas():
    """apoyo de 012:RF-51 / 012:RF-52 — resumen en la salida con coma decimal."""
    app = proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=2)
    f1 = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    sel = app.caso.CreateObject('SetSelect', 'pv')
    sel.AddRef(f1.GetObjs('ElmLod'))
    pv = app.caso.CreateObject('ComPvcurves', 'pv')
    pv.frLoads, pv.pSel_Load = 1, sel
    antes = [c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)]
    assert pv.Execute() == 0
    assert 'info - Scaling 2 load(s).' in app.salida
    assert any('Initial scalable demand for this case: 0,10 MW' in x for x in app.salida)
    assert [c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)] == antes
    pv.calcCont = 1
    app.licencia_pv_contingencias = False
    assert pv.Execute() == 1


def test_condensadores_instalados_en_una_variacion_temporal_desaparecen():
    """apoyo de 012:RF-55 — ``iopt_con=1`` instala; desactivar la variación los quita."""
    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    barra = alim.GetObjs('ElmTerm')[-1].loc_name
    app.capo_propuestas = [(barra, 1, 2)]
    var = app.carpetas['scheme'].CreateObject('IntScheme', 'tmp')
    var.NewStage('tmp', 0, 1)
    cp = app.caso.CreateObject('ComCapo', 'capo')
    cp.feeder, cp.iopt_con, cp.shntqstep = alim, 1, [0.15, 0.3]
    assert cp.TotalLossCost() == 100.0
    assert cp.Execute() == 0
    nuevos = app.GetCalcRelevantObjects('*.ElmShnt')
    assert len(nuevos) == 1 and nuevos[0].qcapn == 0.3 and nuevos[0].ncapa == 2
    assert cp.TotalLossCost() == 90.0
    var.Deactivate()
    assert app.GetCalcRelevantObjects('*.ElmShnt') == []


def test_la_etapa_lista_lo_que_creo_y_la_copia_de_lo_que_cambio():
    """apoyo de 014 (T1) — una etapa da sus objetos nuevos y, de los que ya existían, sus
    valores grabados, aunque después mande otro valor o la variación esté inactiva."""
    from fake_pf import variacion_del_operador

    app = proyecto(alimentadores=('F1',), cargas_por_alim=2)
    carga = next(o for o in app.proyecto.GetContents('*.ElmLod', 1))
    trafo = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1))
    v = _variacion(app, 'Ajuste_F1_1')
    carga.plini = 0.30
    nueva = trafo.GetParent().CreateObject('ElmLod', 'Nueva')
    etapa = v.GetContents('*.IntSstage')[0]

    assert {o.loc_name for o in etapa.GetContents('*.ElmLod')} == {carga.loc_name, 'Nueva'}
    copia = next(o for o in etapa.GetContents('*.ElmLod') if o.loc_name == carga.loc_name)
    assert copia is not carga and copia.GetAttribute('plini') == 0.30
    assert next(o for o in etapa.GetContents('*.ElmLod') if o.loc_name == 'Nueva') is nueva

    v.Deactivate()
    carga.plini = 0.10                    # lo escribe otro, ya sin la etapa grabando
    assert copia.plini == 0.30 and len(etapa.GetContents('*')) == 2

    tipo = app.carpetas['equip'].CreateObject('TypTr2', 'TR_250kVA')
    op = variacion_del_operador(app, 'Ajuste_F1_2', [(trafo, 'typ_id', tipo)])
    clases = {o.GetClassName() for s in op.GetContents('*.IntSstage') for o in s.GetContents('*')}
    assert clases == {'ElmTr2'} and op in app.GetActiveNetworkVariations()
    assert trafo.typ_id is tipo and app.grabando is None
