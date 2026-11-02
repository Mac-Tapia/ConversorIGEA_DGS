"""Spec 063: informe de factibilidad en un paso, para cualquier alimentador.

El caso real es la ampliación de INKA'S BERRIES S.A.C. en SM218 (2026-11-01): el estado actual
ya violaba límites (un cuello de botella al 131 %) y con la carga el punto de diseño bajaba a
0,934 p.u. Aquí las medidas se sortean (``CSG_SCALE_SEED``): ningún alimentador ni valor fijo.
"""
from __future__ import annotations

import os
import random

import pytest

from convertersmartgrid.estudios_pf import Limites
from convertersmartgrid.informes import (
    TRIFASICA,
    Caso,
    Extremo,
    Potencia,
    conclusion_factibilidad,
)

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))


def test_anexo_de_obras_exige_operacion_nativa_persistida(tmp_path):
    """063:RF-36, RF-38: el anexo de aceptación no se fabrica desde un plan propuesto."""
    import json

    from apoyo import cargar_herramienta

    herramienta = cargar_herramienta('informe_casos_guardados.py', 'anexo_operacion_063')
    ruta = tmp_path / 'operacion.json'
    datos = {'project': 'P', 'aceptada': True, 'persistida': False,
             'cargas_previstas_relectura': {'completa': True},
             'estudios_relectura': {'flujo': {'aceptada': True},
                                   'flujo_desequilibrado': {'aceptada': True}}}
    ruta.write_text(json.dumps(datos))
    with pytest.raises(ValueError, match='persistida'):
        herramienta.leer_operacion(ruta, 'P')
    datos['persistida'] = True
    ruta.write_text(json.dumps(datos))
    assert herramienta.leer_operacion(ruta, 'P')['persistida']
    with pytest.raises(ValueError, match='proyecto'):
        herramienta.leer_operacion(ruta, 'OTRO')
LIM = Limites(0.95, 1.05, 100.0)


def test_documentos_de_casos_no_mezclan_proyectos_ni_omiten_ramas(tmp_path):
    """063:RF-6, 063:RF-12: el generador rechaza otro proyecto o cobertura incompleta."""
    import json

    from apoyo import cargar_herramienta

    herramienta = cargar_herramienta('informe_casos_guardados.py', 'informe_casos_063')
    ruta = tmp_path / 'caso.json'
    datos = {'project': 'OTRO', 'caso': 'Sin proyecto', 'estudio': 'flujo',
             'red_proyecto': {'cobertura_completa': True, 'balance_completo': True}}
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(ValueError, match='proyecto'):
        herramienta.leer_caso(ruta, 'P', 'Sin proyecto')
    datos['project'] = 'P'
    datos['red_proyecto']['cobertura_completa'] = False
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(ValueError, match='cobertura'):
        herramienta.leer_caso(ruta, 'P', 'Sin proyecto')


def test_dictamen_incluye_el_peor_de_ambos_flujos():
    """063:RF-38: un desequilibrado correcto no oculta una sobrecarga del equilibrado."""
    from dataclasses import replace

    from apoyo import cargar_herramienta

    herramienta = cargar_herramienta('informe_casos_guardados.py', 'ambos_flujos_063')
    rng = random.Random(SEMILLA)
    bien = _caso(rng, 'Con proyecto', cumple=True)
    mal = replace(bien, cargabilidad_max=Extremo(150, 'L_FALLA'), tramos_sobre=1)
    c = herramienta.caso_conservador(mal, bien)
    assert not c.cumple(LIM)
    assert c.cargabilidad_max == Extremo(150, 'L_FALLA')
    assert herramienta.caso_conservador(bien, bien).cumple(LIM)


def _caso(rng, nombre, *, cumple: bool, converge: bool = True) -> Caso:
    if not converge:
        return Caso(nombre, False)
    nodo, tramo = f'N{rng.randrange(10_000)}', f'L{rng.randrange(10_000)}'
    if cumple:
        u, carga = rng.uniform(0.951, 0.999), rng.uniform(5.0, 99.0)
    elif rng.random() < 0.5:
        u, carga = rng.uniform(0.80, 0.949), rng.uniform(5.0, 99.0)
    else:
        u, carga = rng.uniform(0.951, 0.999), rng.uniform(101.0, 250.0)
    return Caso(nombre, True, fuente=Potencia(rng.uniform(100, 20_000), rng.uniform(0, 5_000)),
                tension_min={TRIFASICA: Extremo(u, nodo)}, tension_max=Extremo(1.0, 'CAB'),
                cargabilidad_max=Extremo(carga, tramo), tramos_sobre=int(carga > 100.0),
                nodos_fuera=int(u < 0.95))


def test_conclusion_sin_problemas_no_propone_obras():
    """063:RF-8 — estado actual y con la carga dentro de límites: factible sin obras."""
    rng = random.Random(SEMILLA)
    for _ in range(50):
        c = conclusion_factibilidad(_caso(rng, 'actual', cumple=True), _caso(rng, 'carga', cumple=True),
                                    None, LIM)
        assert c.factible and c.clave == 'sin_obras' and not c.violaciones and not c.elementos, SEMILLA


def test_conclusion_con_problemas_y_sin_obras_pide_refuerzo():
    """063:RF-9, 063:RF-10 — una violación en el estado actual o con la carga y ninguna obra: no
    es factible sin refuerzo; se listan las violaciones y los elementos que lo requieren."""
    rng = random.Random(SEMILLA + 1)
    for _ in range(50):
        actual_cumple = rng.random() < 0.5
        actual = _caso(rng, 'actual', cumple=actual_cumple)
        carga = _caso(rng, 'carga', cumple=False)
        c = conclusion_factibilidad(actual, carga, None, LIM)
        assert not c.factible and c.clave == 'requiere_refuerzo', SEMILLA
        assert c.violaciones and c.elementos, SEMILLA
        peor = carga.minima.donde if carga.minima.valor < 0.95 else carga.cargabilidad_max.donde
        assert peor in c.elementos, SEMILLA


def test_conclusion_juzga_con_proyecto_con_obras():
    """063:RF-7, 063:RF-9 — con violaciones y obras, «Con proyecto» decide: factible si cumple;
    si no, las obras no bastan."""
    rng = random.Random(SEMILLA + 2)
    for _ in range(50):
        actual, carga = _caso(rng, 'actual', cumple=False), _caso(rng, 'carga', cumple=False)
        bien = conclusion_factibilidad(actual, carga, _caso(rng, 'con', cumple=True), LIM)
        assert bien.factible and bien.clave == 'con_obras' and bien.violaciones, SEMILLA
        mal = conclusion_factibilidad(actual, carga, _caso(rng, 'con', cumple=False), LIM)
        assert not mal.factible and mal.clave == 'obras_insuficientes' and mal.elementos, SEMILLA


@pytest.mark.parametrize('cual', ['actual', 'carga', 'con'])
def test_conclusion_sin_convergencia_no_es_factible(cual):
    """063:RF-11 — un caso que no converge impide concluir que es factible, y se dice cuál."""
    rng = random.Random(SEMILLA + 3)
    casos = {k: _caso(rng, k, cumple=k != 'actual', converge=k != cual) for k in ('actual', 'carga', 'con')}
    c = conclusion_factibilidad(casos['actual'], casos['carga'], casos['con'], LIM)
    assert not c.factible and c.clave == 'no_converge' and cual in ' '.join(c.violaciones)


def test_referencia_no_convergente_solo_con_estado_final_verificado():
    """063:RF-11, 063:RF-38 — la referencia fallida no inventa una aceptación sin obras."""
    rng = random.Random(743)
    actual, cargas, con = _caso(rng, 'actual', cumple=False), Caso('cargas', False), _caso(rng, 'con', cumple=True)
    assert not conclusion_factibilidad(actual, cargas, con, LIM).factible
    c = conclusion_factibilidad(actual, cargas, con, LIM, con_proyecto_verificado=True)
    assert c.factible and c.clave == 'con_obras_verificadas'
    assert any('no converge' in v for v in c.violaciones)
    for a, f in ((Caso('actual', False), con), (actual, Caso('con', False)),
                 (actual, _caso(rng, 'con', cumple=False))):
        assert not conclusion_factibilidad(a, cargas, f, LIM, con_proyecto_verificado=True).factible


def test_esquema_referencia_solo_usa_topologia_y_gps_propios():
    """063:RF-35, 063:RF-38 — nunca reutiliza tensiones parciales de un flujo inválido."""
    from apoyo import cargar_herramienta
    h = cargar_herramienta('informe_casos_guardados.py', 'esquema_fallido_063')
    objetos = {'ElmTerm': [
        {'ruta': 'P/B1', 'nombre': 'B1', 'GPSlat': -14., 'GPSlon': -75., 'uknom': 10, 'outserv': 0, 'm:u': .5},
        {'ruta': 'P/B2', 'nombre': 'B2', 'GPSlat': -14.01, 'GPSlon': -75.01, 'uknom': 10, 'outserv': 0, 'm:u': .2}],
        'ElmLne': [{'nombre': 'L1', 'outserv': 0, 'c:loading': 300,
                    'referencias': {'bus1': {'terminal': 'P/B1'}, 'bus2': {'terminal': 'P/B2'}}}],
        'ElmLod': [{'nombre': 'Cliente', 'outserv': 0, 'plini': .1, 'qlini': .02, 'scale0': 1}]}
    geo = h.geografia_topologica(objetos)
    assert geo['barras'] == [['B1', -14., -75., None, 10], ['B2', -14.01, -75.01, None, 10]]
    assert geo['tramos'][0][:3] == ['L1', [[-14., -75.], [-14.01, -75.01]], None]
    assert geo['sin_resultados_electricos'] is True


def _operacion_certificada_referencia():
    import copy
    objetos = {'ElmTerm': [{'outserv': 0, 'm:u': 1.0}], 'ElmSym': [{'outserv': 1}],
               'ElmLod': [{'outserv': 0, 'plini': .1, 'qlini': .02, 'scale0': 1,
                           'm:Psum:bus1': .1, 'm:Qsum:bus1': .02}]}
    estudio = {'aceptada': True, 'incumplimientos': [],
               'flujo': {'converged': True, 'return_code': 0, 'ldf_valid': True},
               'red_proyecto': {'cobertura_completa': True, 'balance_completo': True,
                                'cantidad_barras': 1, 'medida': {'converge': True}}, 'objetos': objetos}
    return {'project': 'P', 'accion': 'aplicar', 'status': 'OK', 'aceptada': True, 'persistida': True,
            'verificacion_final': {'modelo_identico': True, 'cargas_sin_obras_verificadas': True},
            'cargas_previstas_relectura': {'completa': True},
            'estudios_relectura': {m: copy.deepcopy(estudio) for m in ('flujo', 'flujo_desequilibrado')},
            'estudios_referencia': {'sin': {'estudios': {m: copy.deepcopy(estudio) for m in ('flujo', 'flujo_desequilibrado')}}}}


@pytest.mark.parametrize('fallo', ['modelo', 'persistencia', 'con', 'sin', 'cobertura', 'pq', 'tension'])
def test_excepcion_referencia_rechaza_certificacion_incompleta(fallo):
    """063:RF-11, 063:RF-38 — no relaja el estado final, P/Q ni la cobertura nativa."""
    from apoyo import cargar_herramienta
    h = cargar_herramienta('informe_casos_guardados.py', 'gate_referencia_063')
    op = _operacion_certificada_referencia()
    if fallo == 'modelo':
        op['verificacion_final']['modelo_identico'] = False
    elif fallo == 'persistencia':
        op['persistida'] = False
    elif fallo == 'con':
        op['estudios_relectura']['flujo']['aceptada'] = False
    elif fallo == 'sin':
        op['estudios_referencia']['sin']['estudios']['flujo']['flujo']['converged'] = False
    elif fallo == 'cobertura':
        op['estudios_relectura']['flujo']['red_proyecto']['cobertura_completa'] = False
    elif fallo == 'pq':
        op['estudios_relectura']['flujo']['objetos']['ElmLod'][0]['m:Psum:bus1'] = .01
    else:
        op['estudios_relectura']['flujo']['objetos']['ElmTerm'][0]['m:u'] = .8
    with pytest.raises(ValueError):
        h.validar_referencia_certificada(op)


def test_referencia_no_convergente_requiere_huella_y_objetos_del_mismo_caso(tmp_path):
    """063:RF-11, 063:RF-35, 063:RF-38 — excepción cerrada y ligada al caso nativo."""
    import json

    from apoyo import cargar_herramienta
    h = cargar_herramienta('informe_casos_guardados.py', 'lectura_referencia_063')
    op = _operacion_certificada_referencia()
    objetos = {'ElmTerm': [{'ruta': 'B', 'nombre': 'B', 'GPSlat': -14., 'GPSlon': -75., 'uknom': 10., 'outserv': 0}],
               'ElmLne': [], 'ElmLod': []}
    e = {'flujo': {'converged': False, 'return_code': 1, 'ldf_valid': False}, 'objetos': objetos}
    op['estudios_referencia']['cargas'] = {'estudios': {'flujo': e}}
    wrapper = {'project': 'P', 'caso': 'Cargas nuevas', 'estudio': 'flujo', 'error': 'no converge',
               'referencia_no_convergente': True, 'source_operacion_sha256': 'SHA', 'objetos_nativos': objetos}
    ruta = tmp_path / 'referencia.json'
    ruta.write_text(json.dumps(wrapper))
    with pytest.raises(ValueError):
        h.leer_caso(ruta, 'P', 'Cargas nuevas')
    datos = h.leer_caso(ruta, 'P', 'Cargas nuevas', operacion=op, sha_operacion='SHA')
    assert datos['red_proyecto'] == {'medida': {'converge': False}}
    assert datos['geo_proyecto']['barras'][0][3] is None
    with pytest.raises(ValueError):
        h.leer_caso(ruta, 'P', 'Cargas nuevas', operacion=op, sha_operacion='OTRA')


@pytest.mark.parametrize('alteracion', ['huella', 'resultado', 'geografia'])
def test_dictamen_certificado_no_admite_captura_con_proyecto_de_otra_lectura(alteracion):
    """063:RF-12, 063:RF-38 — el certificado no legitima un wrapper antiguo del mismo proyecto."""
    import copy

    from apoyo import cargar_herramienta
    h = cargar_herramienta('informe_casos_guardados.py', 'vinculo_capturas_063')
    op = _operacion_certificada_referencia()
    e = op['estudios_relectura']['flujo']
    d = {'source_operacion_sha256': 'SHA', 'red_proyecto': copy.deepcopy(e['red_proyecto']),
         'geo_proyecto': {}}
    if alteracion == 'huella':
        d['source_operacion_sha256'] = 'ANTERIOR'
    elif alteracion == 'resultado':
        d['red_proyecto']['cantidad_barras'] = 999
    else:
        d['geo_proyecto'] = {'barras': [['ANTERIOR', -14, -75, .97, 10]]}
    with pytest.raises(ValueError):
        h.vincular_capturas_certificadas([('con', 'flujo', d)], op, 'SHA')


def test_conclusion_usa_los_limites_que_recibe():
    """063:RF-13 — la misma medida cumple o no según la banda del perfil (rural ±7,5 %)."""
    rng = random.Random(SEMILLA + 4)
    actual = _caso(rng, 'actual', cumple=True)
    carga = Caso('carga', True, fuente=Potencia(1000, 200), tension_min={TRIFASICA: Extremo(0.934, 'P')},
                 tension_max=Extremo(1.0, 'CAB'), cargabilidad_max=Extremo(60.0, 'L1'), nodos_fuera=0)
    assert not conclusion_factibilidad(actual, carga, None, LIM).factible
    assert conclusion_factibilidad(actual, carga, None, Limites(0.925, 1.075, 100.0)).factible


def test_optimiza_solo_con_las_cargas_pedidas(monkeypatch, tmp_path):
    """063:RF-23, 063:RF-24 — SM218 (2026-11-01): con INKA y tres cargas del bloque aplicadas, la
    optimización de «Con proyecto» para INKA cuenta solo INKA; un nombre que no está se rechaza."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.services import UserError

    rng = random.Random(SEMILLA + 5)
    feeders = [f'AL{rng.randrange(100, 999)}' for _ in range(rng.randint(1, 3))]
    aplicadas = [{'sed': f'Cliente {i}', 'alimentador': rng.choice(feeders), 'kw': rng.uniform(50, 2000),
                  'kvar': 0.0, 'barra': f'N{i}', 'variacion': f'Carga_{i}', 'sola': i == 0}
                 for i in range(rng.randint(2, 8))]
    pedida = rng.choice(aplicadas)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    vistas = {}

    def oraculo(ws, ctx, project, feeders_, orden, opciones, memo):
        vistas['orden'] = [c['sed'] for c in orden]
        return {'caben': len(orden)}
    monkeypatch.setattr(services, '_optimizar_con_oraculo', oraculo)
    r = services.optimizar_con_proyecto(None, None, 'P', feeders, cargas=[pedida['sed']])
    assert vistas['orden'] == [pedida['sed']] and r['caben'] == 1, SEMILLA
    with pytest.raises(UserError, match='No existe'):
        services.optimizar_con_proyecto(None, None, 'P', feeders, cargas=['No existe'])


def test_banco_en_la_barra_existente_de_la_troncal():
    """063:RF-25 — INKA en SM218 (2026-11-01): su barra NODE_T_ la crea su variación; el banco va
    en la barra existente del tramo que partió, y la carga sigue con su tramo de la troncal. Una
    barra que existe sin la carga se queda; una sin barra existente cercana no da banco."""
    from convertersmartgrid.web.services import _carga_para_escalera

    rng = random.Random(SEMILLA + 6)
    for _ in range(30):
        i = rng.randrange(50)
        nodo, aguas_arriba = f'NODE_T_C{i}', f'B{i}'
        datos = {'indices': {nodo: i, aguas_arriba: i}, 'banco_en': {nodo: aguas_arriba}}
        c = _carga_para_escalera(nodo, {aguas_arriba}, datos)
        assert c == {'barra': aguas_arriba, 'existe': True, 'indice_troncal': i, 'barra_carga': nodo, 'camino': []}
        assert _carga_para_escalera(aguas_arriba, {aguas_arriba}, datos)['barra'] == aguas_arriba
        assert _carga_para_escalera(f'NODE_T_X{i}', set(), {'indices': {}})['existe'] is False


@pytest.mark.parametrize('encima', [True, False])
def test_umbral_de_carga_nueva_lleva_a_set_nueva(monkeypatch, encima):
    """063:RF-34 — NA203 + NA205 (2026-11-01): con cargas nuevas que suman más que el umbral del
    perfil (10 MW en Electro Dunas) la solución es una SET nueva directa; por debajo, la escalera."""
    from convertersmartgrid.web import services

    rng = random.Random(SEMILLA + 7 + int(encima))
    umbral = rng.uniform(5_000, 20_000)
    objetivo = umbral * (1.3 if encima else 0.7)
    n = rng.randint(2, 12)
    pesos = [rng.random() for _ in range(n)]
    aplicadas = [{'sed': f'C{i}', 'alimentador': 'AL1', 'kw': objetivo * w / sum(pesos), 'kvar': 0.0,
                  'barra': f'N{i}', 'variacion': f'Carga_{i}', 'sola': False} for i, w in enumerate(pesos)]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil',
                        lambda: {'planificacion': {'set_nueva_desde_kw': umbral}})
    vistos = {}
    monkeypatch.setattr(services, 'optimizar_con_proyecto',
                        lambda *a, **k: vistos.setdefault('escalera', {'caben': 0, 'a_set_nueva': []}))

    def set_nueva(ws, ctx, project, feeders, a_set_nueva, **k):
        vistos['a_set'] = len(a_set_nueva)
        return {'avisos': []}
    monkeypatch.setattr(services, 'set_nueva_proponer', set_nueva)

    class Ctx:
        def log(self, *_a, **_k):
            pass
    try:
        services.con_proyecto_optimizar(None, Ctx(), 'P', ['AL1'])
    except Exception:  # noqa: BLE001 - lo que sigue a la SET nueva no interesa aquí
        pass
    if encima:
        assert vistos.get('a_set') == n and 'escalera' not in vistos, SEMILLA
    else:
        assert 'escalera' in vistos, SEMILLA


@pytest.mark.parametrize('k', range(4))
def test_el_informe_prepara_solo_su_alimentador_sin_pasar_por_4_2(monkeypatch, tmp_path, k):
    """063:RF-1, 063:RF-3, 063:RF-6, 063:RF-12 — con alimentadores sorteados (nombre y número de
    alimentadores del proyecto variables), la preparación del informe es el paso 4.2 entero solo
    para el alimentador del informe: el último ajuste aplicado como base, flujo equilibrado y
    desequilibrado, y la ejecución del mismo plan; ningún alimentador fijo."""
    from convertersmartgrid.web import services

    rng = random.Random(SEMILLA + k)
    alims = [f"{rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{rng.choice('ABCDEFGHJK')}{rng.randint(100, 999)}"
             for _ in range(rng.randint(1, 12))]
    elegido = rng.choice(alims)
    vistos = []

    def plan(ws, project, feeders, estudios, ajuste, *a, **kw):
        vistos.append(('plan', project, list(feeders), list(estudios), ajuste))
        return {'token': f't{k}'}

    monkeypatch.setattr(services, 'estudios_plan', plan)
    monkeypatch.setattr(services, 'estudios_ejecutar',
                        lambda ws, ctx, token: vistos.append(('ejecutar', token)) or {'resultados': []})
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco',
                        lambda ws, project, *a: {'id': f'disco:{project}', 'feeders': alims})

    class Ctx:
        def log(self, _t):
            pass

    services.preparar_flujos_del_informe(object(), Ctx(), f'PRY{k}', elegido)
    assert vistos == [('plan', f'PRY{k}', [elegido], list(services.ESTUDIOS_DEL_INFORME),
                       {'id': f'disco:PRY{k}', 'feeders': alims}), ('ejecutar', f't{k}')]
    assert set(services.ESTUDIOS_DEL_INFORME) == {'flujo', 'flujo_desequilibrado'}
