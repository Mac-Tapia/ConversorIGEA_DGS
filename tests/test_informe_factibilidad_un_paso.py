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



@pytest.fixture(autouse=True)
def _conjunto_que_cumple(monkeypatch):
    """087:RF-45: la confirmación conjunta tiene sus pruebas en test_obras_integrales; aquí, que cumple."""
    from convertersmartgrid.web import services

    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})

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


def test_conclusiones_de_cada_caso_con_sus_cifras():
    """063:RF-54 — cada caso dice sus cifras medidas; sorteadas, nada de valores fijos."""
    from convertersmartgrid.informes import conclusiones_por_caso, numero

    rng = random.Random(SEMILLA)
    for _ in range(30):
        actual, con = _caso(rng, 'Sin proyecto', cumple=False), _caso(rng, 'Con proyecto', cumple=True)
        textos = conclusiones_por_caso(actual, Caso('Cargas nuevas', False), con, LIM,
                                       nominal_kw={'cargas': rng.uniform(100, 9000)})
        assert len(textos) == 4, SEMILLA      # un párrafo por caso y la comparación
        for texto, caso in ((textos[0], actual), (textos[2], con)):
            assert numero(caso.fuente.kw, 0) in texto, SEMILLA
            assert numero(caso.minima.valor, 3) in texto and caso.minima.donde in texto, SEMILLA
            assert numero(caso.cargabilidad_max.valor, 1) in texto and caso.cargabilidad_max.donde in texto, SEMILLA
        assert numero(abs(con.minima.valor - actual.minima.valor), 3) in textos[3], SEMILLA


def test_conclusiones_de_un_caso_sin_flujo_no_inventan_valores():
    """063:RF-54 — sin convergencia solo la demanda nominal, nunca tensiones ni cargabilidades."""
    from convertersmartgrid.informes import conclusiones_por_caso, numero

    rng = random.Random(SEMILLA)
    nominal = rng.uniform(1000, 90_000)
    actual, con = _caso(rng, 'A', cumple=True), _caso(rng, 'C', cumple=True)
    texto = conclusiones_por_caso(actual, Caso('Cargas', False), con, LIM, nominal_kw={'cargas': nominal})[1]
    assert 'no converge' in texto and numero(nominal, 0) in texto, SEMILLA
    assert 'p.u.' not in texto and '%' not in texto, SEMILLA
    assert conclusiones_por_caso(actual, Caso('Cargas', False), con, LIM)[1].count('kW') == 0, SEMILLA


def test_demanda_por_fuente_antes_y_despues():
    """063:RF-55 — variación y total por fuente; la que entra o sale del servicio se nombra."""
    from convertersmartgrid.informes import FuenteMedida, demanda_antes_despues, numero

    rng = random.Random(SEMILLA)
    comun, sale, entra = (f'F{rng.randrange(10_000)}_{n}' for n in 'abc')
    a, b, c, d = (rng.uniform(100, 20_000) for _ in range(4))
    filas, textos = demanda_antes_despues(
        [FuenteMedida(comun, a, 10.0), FuenteMedida(sale, b, 20.0)],
        [FuenteMedida(comun, c, 30.0), FuenteMedida(entra, d, 40.0)])
    assert [f[0] for f in filas] == [comun, sale, entra, 'Total'], SEMILLA
    assert filas[-1][1] == numero(a + b, 0) and filas[-1][3] == numero(c + d, 0), SEMILLA
    assert filas[0][5] == numero(c - a, 0), SEMILLA
    assert any(sale in t and 'deja de' in t for t in textos), SEMILLA
    assert any(entra in t and 'entra' in t for t in textos), SEMILLA


def test_demanda_por_alimentador_suma_cabecera_y_salidas():
    """063:RF-55 — la zona trasladada no desaparece: cabecera más salidas de la SET nueva."""
    from convertersmartgrid.informes import demanda_por_alimentador, numero

    rng = random.Random(SEMILLA)
    antes, cab, sal, nuevas = (rng.uniform(100, 30_000) for _ in range(4))
    nombre = f'AL{rng.randrange(1000)}'
    tabla, textos = demanda_por_alimentador([{'alimentador': nombre, 'antes_kw': antes, 'cabecera_kw': cab,
                                              'salidas_kw': sal, 'nuevas_kw': nuevas}])
    assert tabla[0][0] == nombre and tabla[0][4] == numero(cab + sal, 0), SEMILLA
    assert tabla[0][5] == numero(cab + sal - antes, 0), SEMILLA
    assert nombre in textos[0] and numero(sal, 0) in textos[0] and numero(nuevas, 0) in textos[0], SEMILLA


def _cola(rng, *, converge: bool, cumple: bool = False) -> dict:
    a, b = rng.uniform(100, 20_000), rng.uniform(100, 20_000)
    return {'cantidad': rng.randrange(2, 200), 'kw': a + b, 'por_alimentador': {'AL1': a, 'AL2': b},
            'demanda_actual_kw': rng.uniform(100, 30_000), 'converge': converge, 'cumple': cumple,
            'obra': 'la SET nueva'}


def test_cola_que_no_converge_justifica_la_obra():
    """063:RF-56 — cuántas cargas, cuántos kW, que no converge y que por eso se justifica la obra."""
    from convertersmartgrid.informes import conclusion_cola, desarrollo_cola, numero

    rng = random.Random(SEMILLA)
    cola = _cola(rng, converge=False)
    for texto in conclusion_cola(cola), ' '.join(desarrollo_cola(cola)):
        assert str(cola['cantidad']) in texto and numero(cola['kw'], 0) in texto, SEMILLA
        assert 'no converge' in texto and 'no es posible' in texto, SEMILLA
        assert numero(cola['por_alimentador']['AL1'], 0) in texto, SEMILLA
    assert 'justifica' in conclusion_cola(cola) and 'la SET nueva' in conclusion_cola(cola), SEMILLA


def test_cola_que_cumple_no_afirma_que_no_cabe():
    """063:RF-56 — solo se afirma lo medido: si el flujo cumple, no se dice que no se pueda conectar."""
    from convertersmartgrid.informes import conclusion_cola, desarrollo_cola

    rng = random.Random(SEMILLA)
    cola = _cola(rng, converge=True, cumple=True)
    for texto in conclusion_cola(cola), ' '.join(desarrollo_cola(cola)):
        assert 'no converge' not in texto and 'no es posible' not in texto and 'justifica' not in texto, SEMILLA
    medio = _cola(rng, converge=True, cumple=False)
    assert 'incumple' in conclusion_cola(medio) and 'no converge' not in conclusion_cola(medio), SEMILLA


def test_demanda_sin_fuentes_usa_el_alimentador():
    """063:RF-55 — sin datos por fuente, la inyección de cada caso con el nombre del alimentador."""
    from convertersmartgrid.informes import fuentes_del_caso, numero

    rng = random.Random(SEMILLA)
    caso = _caso(rng, 'A', cumple=True)
    nombre = f'AL{rng.randrange(1000)}'
    f = fuentes_del_caso(caso, nombre)
    assert [(x.nombre, numero(x.kw, 2)) for x in f] == [(nombre, numero(caso.fuente.kw, 2))], SEMILLA
    assert fuentes_del_caso(Caso('B', False), nombre) == (), SEMILLA


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
                  'barra': f'N{i}', 'variacion': f'Carga_{i}', 'sola': False,
                  'lat': -13.0, 'lon': -76.0} for i, w in enumerate(pesos)]
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
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)      # 087:RF-54

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


def test_la_escalera_primero_no_salta_a_la_set_nueva(monkeypatch):
    """042:RF-17 — por encima del umbral, si el operador pide la escalera, se busca carga a carga."""
    from convertersmartgrid.web import services

    aplicadas = [{'sed': 'C0', 'alimentador': 'AL1', 'kw': 25_000.0, 'kvar': 0.0, 'barra': 'N0', 'variacion': 'Carga_0', 'sola': False}]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil',
                        lambda: {'planificacion': {'set_nueva_desde_kw': 10_000}})
    vistos = {}
    monkeypatch.setattr(services, 'escalera_por_alimentador',
                        lambda *a, **k: vistos.setdefault('escalera', {'caben': 1, 'a_set_nueva': []}))
    monkeypatch.setattr(services, 'set_nueva_proponer', lambda *a, **k: {'avisos': []})

    class Ctx:
        def log(self, *_a, **_k):
            pass

    services.con_proyecto_optimizar(object(), Ctx(), 'P', ['AL1'], escalera_primero=True)
    assert 'escalera' in vistos


def test_la_escalera_va_por_alimentador(monkeypatch, tmp_path):
    """042:RF-24, 042:RF-29 — cada alimentador sube la escalera con sus cargas; el que no cumple pasa sus cargas a la obra siguiente."""
    from convertersmartgrid.web import services

    aplicadas = [{'sed': 'A', 'alimentador': 'F1', 'kw': 900.0, 'variacion': 'Carga_A'},
                 {'sed': 'B', 'alimentador': 'F2', 'kw': 4000.0, 'variacion': 'Carga_B'},
                 {'sed': 'C', 'alimentador': 'F2', 'kw': 500.0, 'variacion': 'Carga_C'}]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    llamadas = []

    vistos_solo = []

    def escalera(ws, ctx, project, feeders, *, cargas_activas=None, aplicar=True, **k):
        llamadas.append((tuple(feeders), tuple(cargas_activas or ()), aplicar))
        if aplicar:
            vistos_solo.append(k.get('solo'))
        return {'alimentadores': [{'feeder': feeders[0], 'elegida': 'bancos' if feeders == ['F1'] else None}]}
    monkeypatch.setattr(services, 'obras_escalera', escalera)
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {})
    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)

    class Ctx:
        def log(self, *_a, **_k):
            pass

        def check_cancel(self):
            pass

    r = services.escalera_por_alimentador(object(), Ctx(), 'P', ['F1', 'F2'])
    assert (('F1',), ('Carga_A',), False) in llamadas and (('F2',), ('Carga_B', 'Carga_C'), False) in llamadas
    assert (('F1',), ('Carga_A',), True) in llamadas
    assert vistos_solo == [{'F1': 'bancos'}], '042:RF-29: al aplicar, solo la obra elegida'
    assert r['caben'] == 1 and {c['sed'] for c in r['a_set_nueva']} == {'B', 'C'}
    assert r['por_alimentador']['F2']['cumple'] is False


def test_la_escalera_repone_antes_las_cargas_apartadas(monkeypatch, tmp_path):
    """042:RF-32 — Pisco: tras una caída, 6 de 14 cargas seguían apartadas y AL209 se medía sin ellas."""
    from convertersmartgrid.web import services

    orden = []
    aplicadas = [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'},
                 {'sed': 'B', 'alimentador': 'F1', 'kw': 90.0, 'variacion': 'Carga_B'}]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr(services, '_reponer_cargas_nuevas',
                        lambda ws, ctx, project, feeders, anio, variaciones: orden.append(('reponer', tuple(variaciones))))

    def escalera(ws, ctx, project, feeders, **k):
        orden.append(('escalera', tuple(feeders)))
        return {'alimentadores': [{'ya_cumple': True}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)

    class Ctx:
        def log(self, *_a, **_k):
            pass

        def check_cancel(self):
            pass

    services.escalera_por_alimentador(object(), Ctx(), 'P', ['F1'])
    assert orden[0] == ('reponer', ('Carga_A', 'Carga_B')) and orden[1] == ('escalera', ('F1',))


def test_cada_alimentador_aplica_su_obra_antes_de_evaluar_el_siguiente(monkeypatch):
    """042:RF-48 — al elegir la obra de F1 se aplica ya; F2 se evalúa después, y el que no cumple no aplica nada."""
    from convertersmartgrid.web import services

    # 042 sin el oráculo de la 087 (087:RF-30): aquí se mira el orden de la escalera de siempre.
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {})

    orden = []
    aplicadas = [{'sed': f'S{f}', 'alimentador': f, 'kw': 10.0, 'variacion': f'Carga_{f}'} for f in ('F1', 'F2', 'F3')]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)

    def escalera(ws, ctx, project, feeders, *, aplicar=False, solo=None, **k):
        f = feeders[0]
        orden.append(('aplica' if aplicar else 'evalua', f))
        if aplicar:
            return {'alimentadores': [{'alimentador': f, 'aplicada': [f'Obra_{f}']}]}
        return {'alimentadores': [{'alimentador': f, 'elegida': None if f == 'F2' else f'obra de {f}'}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)

    class Ctx:
        def log(self, *_a, **_k):
            pass

        def check_cancel(self):
            pass

    r = services.escalera_por_alimentador(object(), Ctx(), 'P', ['F1', 'F2', 'F3'])
    # 087:RF-31: el que no cumple prueba además transferir o trasladar a un vecino antes de ir a la SET nueva.
    assert orden == [('evalua', 'F1'), ('aplica', 'F1'), ('evalua', 'F2'), ('evalua', 'F2'), ('evalua', 'F3'),
                     ('aplica', 'F3')]
    assert [a['alimentador'] for a in r['escalera']['alimentadores']] == ['F1', 'F3']


def test_rehacer_retira_antes_de_evaluar_y_olvida_lo_aplicado(monkeypatch):
    """042:RF-60 — retira, repone y evalúa, en ese orden; sin pedirlo no se retira nada."""
    from convertersmartgrid.web import services

    # 042 sin el oráculo de la 087 (087:RF-30): aquí se mira el orden de la escalera de siempre.
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {})

    orden = []
    aplicadas = [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'}]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: orden.append('reponer'))
    monkeypatch.setattr(services, 'carpeta_de', lambda *a: 'C')
    monkeypatch.setattr(services, 'native_action_context', lambda *a: {})

    def guion(ws, ctx, guion_py, plan, **k):
        orden.append(k['nombre'])
        return 0, {'retiradas': ['Obra_terna_F1']}, None

    monkeypatch.setattr(services, '_guion_pf', guion)

    def escalera(ws, ctx, project, feeders, **k):
        orden.append('escalera')
        return {'alimentadores': [{'ya_cumple': True}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)

    class Ctx:
        def log(self, *_a, **_k):
            pass

        def check_cancel(self):
            pass

    class Ws:
        obras_aplicadas = [{'project': 'P', 'variacion': 'Obra_terna_F1'}, {'project': 'P', 'variacion': 'Obra_terna_F2'}]

    ws = Ws()
    services.escalera_por_alimentador(ws, Ctx(), 'P', ['F1'], rehacer_obras=True)
    assert orden == ['retirar_obras', 'reponer', 'escalera']
    assert [o['variacion'] for o in ws.obras_aplicadas] == ['Obra_terna_F2']
    orden.clear()
    services.escalera_por_alimentador(ws, Ctx(), 'P', ['F1'])
    assert orden == ['reponer', 'escalera']


def test_una_barra_que_ya_estaba_baja_lleva_su_obra_aparte(monkeypatch):
    """042:RF-64 — con obra para la carga y sin ella: segunda escalera con las barras previas; ninguna obra si no las hay."""
    from convertersmartgrid.web import services

    baja = {'previo': [{'barra': 'B2', 'u': 0.94}, {'barra': 'B1', 'u': 0.93}], 'causado': [], 'sin_comparacion': [{'barra': 'B3', 'u': 0.945}]}
    filas = {'F1': {'alimentador': 'F1', 'elegida': 'obra', 'bajo_limite': baja},
             'F2': {'alimentador': 'F2', 'ya_cumple': True, 'bajo_limite': baja},
             'F3': {'alimentador': 'F3', 'ya_cumple': True, 'bajo_limite': {'causado': [{'barra': 'B9', 'u': 0.9}]}}}
    aplicadas = [{'sed': f, 'alimentador': f, 'kw': 10.0, 'variacion': f'Carga_{f}'} for f in filas]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    pedidas = {}

    def escalera(ws, ctx, project, feeders, *, previas=None, **k):
        f = feeders[0]
        if previas:
            pedidas[(f, k['etiqueta_previas'])] = (previas[f], k['aplicar'])
            return {'alimentadores': [{'alimentador': f, 'alternativas': [{'numero': 1, 'nombre': 'x', 'costo_anual': 5.0}]}]}
        return {'alimentadores': [filas[f]]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)

    class Ctx:
        def log(self, *_a, **_k):
            pass

        def check_cancel(self):
            pass

    r = services.escalera_por_alimentador(object(), Ctx(), 'P', list(filas))
    assert pedidas == {(f, e): (b, False) for f in ('F1', 'F2')
                       for e, b in (('déficit previo', ['B1', 'B2']), ('sin comparación', ['B3']))}   # 042:RF-68
    assert r['por_alimentador']['F2']['deficit_previo']['alternativas'][0]['nombre'] == 'x'
    assert r['por_alimentador']['F2']['sin_comparacion']['barras'] == ['B3']
    assert r['por_alimentador']['F3']['deficit_previo'] is None


def test_la_web_recibe_las_alternativas_de_cada_alimentador(monkeypatch):
    """042:RF-76, 042:RF-77, 042:RF-78 — el resultado trae las alternativas por alimentador, y no trae pruebas por tandas."""
    from convertersmartgrid.web import services

    aplicadas = [{'sed': 'A', 'alimentador': 'F1', 'kw': 10.0, 'variacion': 'Carga_A'}]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    alternativas = [{'numero': 1, 'nombre': 'x', 'costo_anual': 5.0, 'elegida': False}]
    monkeypatch.setattr(services, 'obras_escalera', lambda *a, **k: {
        'alimentadores': [{'alimentador': 'F1', 'ya_cumple': True, 'alternativas': alternativas}]})

    class Ctx:
        def log(self, *_a, **_k):
            pass

        def check_cancel(self):
            pass

    r = services.escalera_por_alimentador(object(), Ctx(), 'P', ['F1'])
    assert r['por_alimentador']['F1']['alternativas'] == alternativas and 'pruebas' not in r
