"""Spec 045, T1: episodio v2, contexto físico y grafo versión 3 (sin DIgSILENT real)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import fake_pf
import jsonschema
import pytest
from apoyo import cargar_herramienta, contexto_nativo, contrato_fisico
from test_digital_twin_episode import H, _payload, _payload_v1

from convertersmartgrid.digital_twin import episode as ep
from convertersmartgrid.digital_twin.buffer import BuferEpisodios, Consulta
from convertersmartgrid.digital_twin.capture import construir_episodio
from convertersmartgrid.digital_twin.contratos_fisicos import (
    REPRESENTACION,
    VERSION_GRAFO,
    contexto_fisico,
    validar_alcance_fisico,
)
from convertersmartgrid.digital_twin.episode import Caso, Clase
from convertersmartgrid.digital_twin.evaluacion import evaluar
from convertersmartgrid.digital_twin.integration import plan_de_lectura
from convertersmartgrid.digital_twin.oraculo import muestra_de_episodio, por_que_no_ensena
from convertersmartgrid.experimentos import ContextoExperimento, clave_contexto
from convertersmartgrid.native_action import build_native_action_context

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMAS = RAIZ / 'src' / 'convertersmartgrid' / 'schemas'


def _grafo(**cambios) -> dict:
    g = {'version': VERSION_GRAFO, **contrato_fisico(),
         'nodos': {'S': {'kv': 10.0, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': True, 'v_pu': 1.02, 'angulo_deg': 0.0},
                   'A': {'kv': 10.0, 'p_mw': 0.3, 'q_mvar': -0.1, 'fuente': False, 'carga_p_mw': 0.5, 'carga_q_mvar': 0.1,
                         'gen_p_mw': 0.2, 'gen_q_mvar': 0.0, 'banco_q_mvar': 0.2,
                         'carga_p_efectiva_mw': 0.5, 'carga_q_efectiva_mvar': 0.1}},
         'ramas': [{'id': 'L1', 'clase': 'ElmLne', 'desde': 'S', 'hasta': 'A', 'cerrada': True, 'r_ohm': 0.4,
                    'x_ohm': 0.3, 'inom_ka': 0.2, 'fases': 3},
                   {'id': 'T1', 'clase': 'ElmTr2', 'desde': 'S', 'hasta': 'A', 'cerrada': False, 'r_ohm': 0.4, 'x_ohm': 2.0,
                    'inom_ka': 0.1, 'toma': {'posicion': 0.0, 'neutra': 0.0, 'paso_pct': 1.25, 'lado': 0.0, 'automatica': False}}],
         'bancos': [{'id': 'B1', 'clase': 'ElmShnt', 'nodo': 'A', 'en_servicio': True, 'q_mvar': 0.2, 'escalones': 1.0,
                     'q_medida_mvar': -0.19}],
         'generadores': [{'id': 'G1', 'clase': 'ElmGenstat', 'nodo': 'A', 'en_servicio': True, 'p_mw': 0.2, 'q_mvar': 0.0,
                          'control': 'constq', 'usetp': 1.0, 'referencia': False, 'p_medida_mw': 0.2, 'q_medida_mvar': 0.0}]}
    g.update(cambios)
    return g


def _lectura(grafo=None, rol='sin_proyecto', **contexto) -> dict:
    return {'project': 'P', 'folder': 'F', 'feeders': ['A1'], 'pf_version': '2024', 'reopen_verified': True,
            'caso_nativo': {'rol': rol, 'nombre': rol, 'id': f'IntCase:Estudios\\{rol}'},
            'contexto': {'year': None, 'period': None, 'criterio_fijas': 'coincidente', **contexto},
            'topologia': {'grafo': grafo or _grafo(), 'variaciones_activas': [], 'escenario': None},
            'flujo': {'balance': {'unidad': 'kW', 'valores': {'cabeceras': {'A1': 100.0}}},
                      'perdidas': {'unidad': 'kW', 'valores': {'total': 1.0}},
                      'cargabilidad': {'unidad': '%', 'valores': {'lineas': {'L1': 40.0}}},
                      'tensiones': {'unidad': 'p.u.', 'valores': {'S': 1.02, 'A': 0.8}},
                      'confiabilidad': {'ausente': 'sin estudio'}}}


def _plan(feeders=('A1',)) -> dict:
    enlace = {'project': 'P', 'source_run_id': 'run-1', 'source_mode': 'txt', 'source_fingerprint': H}
    return {'project': 'P', 'feeders': list(feeders),
            'native_action_context': build_native_action_context(enlace, 'P', feeders, 'gemelo_escenarios')}


def _construir(caso: Caso, lectura=None, **resultado) -> ep.Episodio:
    return construir_episodio(_plan(), {'status': 'OK', 'converged': True, **resultado},
                              lectura or _lectura(rol=caso.value), [], caso=caso, limites=None, referencia=None,
                              calibracion_cuadra=True, creado='2026-11-03T10:00:00+00:00')


def test_v1_lectura_no_cambia_hash(tmp_path):
    """045:RF-2 — un episodio v1 se lee con su esquema y su huella, sin reescribir su fichero ni su contenido."""
    original = ep.leer_episodio(_payload_v1())
    payload = ep.episodio_a_dict(original)
    assert payload['schema'] == ep.ESQUEMA_V1 and 'contexto_fisico' not in payload
    assert ep.huella_episodio(payload) == original.episode_id
    bufer = BuferEpisodios(tmp_path)
    ruta = bufer.guardar(original)
    bytes_antes = ruta.read_bytes()
    leido = bufer.leer(original.episode_id)
    assert leido.esquema == ep.ESQUEMA_V1 and leido.contexto_fisico is None
    assert ep.episodio_a_dict(leido) == payload
    bufer.guardar(leido)
    assert ruta.read_bytes() == bytes_antes
    assert bufer.reconstruir_indice() == 1 and ruta.read_bytes() == bytes_antes


def test_v1_con_el_prefijo_anterior_conserva_su_huella():
    """045:RF-2 — un v1 escrito con el prefijo de esquema anterior a la 058 tampoco cambia de identidad."""
    from convertersmartgrid.util import PREFIJO_ESQUEMA_ANTERIOR

    payload = _payload_v1(schema=PREFIJO_ESQUEMA_ANTERIOR + 'digital-twin-episode-v1')
    e = ep.leer_episodio(payload)
    assert e.esquema == payload['schema']
    assert ep.huella_episodio(ep.episodio_a_dict(e)) == e.episode_id == ep.huella_episodio(payload)


def test_v1_no_conoce_el_cuarto_caso():
    """045:RF-2 — el esquema v1 sigue siendo el que era: «Cargas nuevas» no se le añade al leer."""
    with pytest.raises(ep.EpisodioInvalido) as err:
        ep.leer_episodio(_payload_v1(caso='cargas_nuevas', clase='counterfactual'))
    assert err.value.campo == 'caso'


def test_esquema_v2_publicado_coincide_con_el_contrato():
    """045:RF-1 — el esquema publicado y el contrato de Python declaran lo mismo; el v1 queda como estaba."""
    v2 = json.loads((ESQUEMAS / 'digital_twin_episode_v2.schema.json').read_text(encoding='utf-8'))
    v1 = json.loads((ESQUEMAS / 'digital_twin_episode_v1.schema.json').read_text(encoding='utf-8'))
    assert v2['properties']['schema']['const'] == ep.ESQUEMA
    assert v1['properties']['schema']['const'] == ep.ESQUEMA_V1
    assert v2['properties']['caso']['enum'] == [c.value for c in ep.Caso]
    assert v1['properties']['caso']['enum'] == [c.value for c in ep.CASOS_V1]
    assert set(v2['required']) == set(ep.CAMPOS_V2) and set(v1['required']) == set(ep.CAMPOS)
    jsonschema.validate(ep.episodio_a_dict(ep.leer_episodio(_payload())), v2)
    jsonschema.validate(ep.episodio_a_dict(ep.leer_episodio(_payload_v1())), v1)


@pytest.mark.parametrize('caso', list(Caso))
def test_cuatro_roles_con_su_identidad_nativa(caso):
    """045:RF-1 — cada uno de los cuatro casos se captura con su rol y la identidad del caso de DIgSILENT."""
    e = _construir(caso)
    assert e.esquema == ep.ESQUEMA
    assert e.caso is caso and e.contexto_fisico['case_role'] == caso.value
    assert e.contexto_fisico['case_id'] == f'IntCase:Estudios\\{caso.value}'


def test_una_lectura_de_otro_caso_no_se_mezcla():
    """045:RF-1 — la lectura de «Sin proyecto» no pasa por «Cargas nuevas»: cuarentena, con el motivo."""
    e = _construir(Caso.CARGAS_NUEVAS, _lectura(rol='sin_proyecto'))
    assert e.clase is Clase.QUARANTINE and 'ausente' in e.contexto_fisico
    assert any('sin_proyecto' in b for b in e.aceptacion['bloqueos'])


def test_cargas_nuevas_es_diagnostico():
    """045:RF-1 — «Cargas nuevas» enseña física pero nunca se acepta como obra, tampoco a mano."""
    violacion = evaluar(Caso.CARGAS_NUEVAS, {'tensiones': {'sin_tension': ['B']}}, convergio=True, revertido=False,
                        reabierto=True, limites=None, calibracion_cuadra=None, referencia=None)
    assert violacion.clase is Clase.COUNTERFACTUAL and violacion.diagnostico
    e = _construir(Caso.CARGAS_NUEVAS, obras=[{'alternativa': 'bancos', 'elemento': 'V1'}])
    assert e.clase is Clase.COUNTERFACTUAL and e.obras == ()
    with pytest.raises(ep.EpisodioInvalido) as err:
        ep.leer_episodio(_payload(caso='cargas_nuevas', clase='accepted'))
    assert err.value.campo == 'clase'
    with pytest.raises(ep.EpisodioInvalido) as err:
        ep.leer_episodio(_payload(caso='cargas_nuevas', clase='counterfactual',
                                  obras=[{'alternativa': 'bancos', 'elemento': 'V1'}]))
    assert err.value.campo == 'obras'


def test_aceptado_exige_los_controles():
    """045:RF-3 — un episodio aceptado sin controles ni caso nativo no pasa el contrato."""
    p = _payload(contexto_fisico={'ausente': 'sin lectura'})
    with pytest.raises(ep.EpisodioInvalido) as err:
        ep.leer_episodio(p)
    assert err.value.campo == 'contexto_fisico'
    assert ep.leer_episodio({**p, 'clase': 'quarantine'}).contexto_fisico == {'ausente': 'sin lectura'}
    otro = _payload(contexto_fisico={'case_role': 'con_proyecto', 'case_id': 'IntCase:x', 'topology_hash': H,
                                     'controls_hash': H, 'scenario_hash': H})
    with pytest.raises(ep.EpisodioInvalido) as err:
        ep.leer_episodio(otro)
    assert err.value.campo == 'contexto_fisico.case_role'


def _cambia_toma(g):
    g['ramas'][1]['toma']['posicion'] = 2.0


def _cambia_banco(g):
    g['bancos'][0]['en_servicio'] = False


def _cambia_escalon(g):
    g['bancos'][0]['escalones'] = 2.0


def _cambia_central(g):
    g['generadores'][0]['p_mw'] = 0.4


def _cambia_iopt(g):
    g['controles']['comldf']['iopt_lev'] = 1


@pytest.mark.parametrize('cambio', [_cambia_toma, _cambia_banco, _cambia_escalon, _cambia_central, _cambia_iopt])
def test_controles_y_casos_no_se_mezclan(cambio):
    """045:RF-3 — variar banco, central, toma o ajuste del flujo cambia la huella de controles, y solo esa."""
    base = contexto_fisico(_lectura())
    g = _grafo()
    cambio(g)
    otro = contexto_fisico(_lectura(g))
    assert otro['controls_hash'] != base['controls_hash']
    assert otro['topology_hash'] == base['topology_hash']


def test_criterio_de_fijas_y_caso_cambian_el_contexto():
    """045:RF-3 — el criterio de las fijas y el rol del caso entran en el contexto y en su clave."""
    base = contexto_fisico(_lectura())
    assert contexto_fisico(_lectura(criterio_fijas='maximo_mes'))['controls_hash'] != base['controls_hash']
    assert contexto_fisico(_lectura(rol='cargas_nuevas'))['scenario_hash'] != base['scenario_hash']
    assert contexto_fisico(_lectura(year=2025))['scenario_hash'] != base['scenario_hash']

    def clave(c):
        return clave_contexto(ContextoExperimento(
            source_run_id='r', source_mode='txt', source_fingerprint=H, project='P', feeders=('A1',),
            case_id=c['case_id'], case_role=c['case_role'], year=c['year'], period='2026-07',
            criterio_fijas=c['criterio_fijas'], profile_hash=H, topology_hash=c['topology_hash'],
            controls_hash=c['controls_hash'], scenario_hash=c['scenario_hash']))

    assert clave(contexto_fisico(_lectura(criterio_fijas='maximo_mes'))) != clave(base)
    assert clave(contexto_fisico(_lectura(rol='con_proyecto'))) != clave(base)


def test_consignas_y_efectivos_no_se_sustituyen():
    """045:RF-3 — ComLdf, lo escrito y lo medido quedan los tres; lo que falta es ``None``, no un valor supuesto."""
    c = contexto_fisico(_lectura())
    assert c['comldf']['iopt_net'] == 0
    assert c['consignas']['banco_q_mvar'] == pytest.approx(0.2)
    assert c['efectivos']['banco_q_mvar'] == pytest.approx(-0.19)
    assert c['consignas']['central_p_mw'] == pytest.approx(0.2)
    g = _grafo()
    g['bancos'][0]['q_medida_mvar'] = None
    assert contexto_fisico(_lectura(g))['efectivos']['banco_q_mvar'] is None
    assert contexto_fisico(_lectura(g))['criterio_fijas'] == 'coincidente'
    assert contexto_fisico({**_lectura(), 'contexto': {}})['criterio_fijas'] is None
    assert 'ausente' in contexto_fisico({**_lectura(), 'caso_nativo': None})
    assert 'ausente' in contexto_fisico({'caso_nativo': {'rol': 'x', 'id': 'y'}, 'topologia': {}})


def test_el_plan_de_lectura_lleva_anio_y_criterio_si_los_hay():
    """045:RF-3 — el plan de la lectura pasa el año y el criterio; sin ellos no aparecen supuestos."""
    plan = {'project': 'P', 'feeders': ['A1'], 'native_action_context': {'x': 1}}
    limpio = plan_de_lectura(plan, Caso.SIN_PROYECTO, {})
    assert 'criterio_fijas' not in limpio and 'anio_casos' not in limpio
    con = plan_de_lectura({**plan, 'criterio_fijas': 'maximo_mes', 'anio_casos': 2025}, Caso.SIN_PROYECTO, {})
    assert con['criterio_fijas'] == 'maximo_mes' and con['anio_casos'] == 2025


# ---------------------------------------------------------------- captura con el doble de DIgSILENT
@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('digital_twin_snapshot_pf.py', 'digital_twin_snapshot_045', tools_en_path=True)


def _red_del_doble(caso='Sin proyecto'):
    """Un proyecto del doble con red externa, central, banco y una toma: lo que trae una red real."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    app.carpetas['study'].CreateObject('IntCase', caso)
    red = next(iter(app.proyecto.GetContents('*.ElmNet', 1)), None) or app.proyecto
    barras = app.proyecto.GetContents('*.ElmTerm', 1)
    barra = barras[1]

    def cub(nombre, b):
        return b.CreateObject('StaCubic', nombre)

    x = red.CreateObject('ElmXnet', 'Red')
    object.__setattr__(x, 'bus1', cub('cx', barras[0]))
    object.__setattr__(x, 'usetp', 1.02)
    object.__setattr__(x, 'phiini', 0.0)
    object.__setattr__(x, 'bustp', 'SL')
    sh = red.CreateObject('ElmShnt', 'Banco')
    for k, v in {'bus1': cub('cs', barra), 'qtotn': 0.3, 'ncapa': 1, 'outserv': 0, 'm:Q:bus1': -0.28}.items():
        object.__setattr__(sh, k, v)
    g = red.CreateObject('ElmGenstat', 'Central')
    for k, v in {'bus1': cub('cg', barra), 'pgini': 5.0, 'qgini': -0.4, 'ngnum': 1, 'av_mode': 'constq', 'usetp': 1.0,
                 'ip_ctrl': 0, 'outserv': 0, 'm:P:bus1': 5.0, 'm:Q:bus1': -0.4}.items():
        object.__setattr__(g, k, v)
    for tr in app.proyecto.GetContents('*.ElmTr2', 1):
        object.__setattr__(tr, 'nntap', 0)
        object.__setattr__(tr, 'ntrcn', 0)
        for k, v in {'dutap': 2.5, 'nntap0': 0, 'tap_side': 0}.items():
            object.__setattr__(tr.typ_id, k, v)
    for k in ('iopt_net', 'iopt_lev', 'iopt_pq', 'iopt_at', 'iopt_asht'):
        object.__setattr__(app.ldf, k, 0)
    app.escrituras.clear()
    app.creados.clear()
    return app


def _plan_doble(**extra):
    return {'project': 'P', 'feeders': ['F1'], 'case': 'sin_proyecto',
            'native_action_context': contexto_nativo('P', ['F1'], 'ajuste_ejecutar'), **extra}


def test_central_y_bancos_se_conservan_con_su_estado_medido(guion):
    """045:RF-10 — la central y el banco de la red quedan en el grafo con lo escrito y lo medido, sin escribir nada."""
    app = _red_del_doble()
    lectura, rc = guion.ejecutar(app, _plan_doble())
    assert rc == 0, lectura
    assert app.escrituras == [] and app.creados == []
    g = lectura['topologia']['grafo']
    banco = next(b for b in g['bancos'] if b['id'].endswith('Banco.ElmShnt'))
    assert banco['en_servicio'] is True and banco['q_mvar'] == pytest.approx(0.3)
    assert banco['q_medida_mvar'] == pytest.approx(-0.28)
    central = next(c for c in g['generadores'] if c['id'].endswith('Central.ElmGenstat'))
    assert central['p_mw'] == pytest.approx(5.0) and central['p_medida_mw'] == pytest.approx(5.0)
    assert central['control'] == 'constq' and central['en_servicio'] is True
    nodo = g['nodos'][banco['nodo']]
    assert nodo['banco_q_mvar'] == pytest.approx(0.3) and nodo['gen_p_mw'] == pytest.approx(5.0)
    assert nodo['p_mw'] == pytest.approx(nodo['carga_p_mw'] - 5.0)
    assert nodo['q_mvar'] == pytest.approx(nodo['carga_q_mvar'] + 0.4 - 0.3)


def test_banco_y_central_fuera_de_servicio_no_suman_pero_quedan(guion):
    """045:RF-10 — fuera de servicio siguen en el grafo con su estado: el hueco no parece que no existan."""
    app = _red_del_doble()
    for o in app.proyecto.GetContents('*.ElmShnt', 1) + app.proyecto.GetContents('*.ElmGenstat', 1):
        object.__setattr__(o, 'outserv', 1)
    lectura, _rc = guion.ejecutar(app, _plan_doble())
    g = lectura['topologia']['grafo']
    assert [b['en_servicio'] for b in g['bancos']] == [False]
    assert [c['en_servicio'] for c in g['generadores']] == [False]
    assert all(not d['banco_q_mvar'] and not d['gen_p_mw'] for d in g['nodos'].values())


def test_el_grafo_declara_equipos_unidades_controles_y_alcance(guion):
    """045:RF-3 — el grafo registra equipos, unidades, controles efectivos y lo que representa su física."""
    lectura, _rc = guion.ejecutar(_red_del_doble(), _plan_doble())
    g = lectura['topologia']['grafo']
    assert g['version'] == VERSION_GRAFO == 3
    assert g['unidades']['r_ohm'] == 'ohm' and g['unidades']['v_pu'] == 'p.u.'
    assert g['alcance_fisico']['representacion'] == REPRESENTACION and g['alcance_fisico']['aproximaciones']
    assert g['alcance_fisico']['equipos']['ElmShnt'] == 1 and g['alcance_fisico']['equipos']['central'] == 1
    assert g['controles']['comldf'] == {'iopt_net': 0, 'iopt_lev': 0, 'iopt_pq': 0, 'iopt_at': 0, 'iopt_asht': 0}
    trafo = next(r for r in g['ramas'] if r['clase'] == 'ElmTr2')
    assert trafo['toma']['paso_pct'] == pytest.approx(2.5) and trafo['toma']['automatica'] is False
    assert 'unidades' in trafo
    assert validar_alcance_fisico(g) == (), validar_alcance_fisico(g)


def test_la_lectura_identifica_el_caso_y_el_de_su_anio(guion):
    """045:RF-1 — la lectura trae la identidad del caso activo, también el del año (spec 025) o «Cargas nuevas»."""
    lectura, _rc = guion.ejecutar(_red_del_doble('Cargas nuevas'), _plan_doble(case='cargas_nuevas'))
    assert lectura['caso_nativo']['rol'] == 'cargas_nuevas' and lectura['caso_nativo']['id'].endswith('Cargas nuevas.IntCase')
    lectura, _rc = guion.ejecutar(_red_del_doble('Sin proyecto 2025'), _plan_doble(anio_casos=2025, criterio_fijas='maximo_mes'))
    assert lectura['caso_nativo']['nombre'] == 'Sin proyecto 2025'
    assert lectura['contexto'] == {'year': 2025, 'period': None, 'criterio_fijas': 'maximo_mes'}
    lectura, rc = guion.ejecutar(_red_del_doble('Sin proyecto 2025'), _plan_doble())
    assert rc == 2 and 'Sin proyecto' in lectura['error'], 'sin año no se cae en el caso de otro año'


def test_un_episodio_del_doble_ensena_y_se_consulta_por_su_caso(guion, tmp_path):
    """045:RF-1, 045:RF-3 — lectura → episodio v2 → búfer → muestra: el camino entero con el cuarto caso."""
    lectura, rc = guion.ejecutar(_red_del_doble('Cargas nuevas'), _plan_doble(case='cargas_nuevas'))
    assert rc == 0
    e = construir_episodio(_plan(('F1',)), {'status': 'OK', 'converged': True}, lectura, [], caso=Caso.CARGAS_NUEVAS, limites=None,
                           referencia=None, calibracion_cuadra=None, creado='2026-11-03T10:00:00+00:00')
    assert e.clase is Clase.COUNTERFACTUAL, e.aceptacion
    bufer = BuferEpisodios(tmp_path)
    bufer.guardar(e)
    leido = bufer.consultar(Consulta(caso='cargas_nuevas'))
    assert [x.episode_id for x in leido] == [e.episode_id]
    assert por_que_no_ensena(leido[0]) is None, por_que_no_ensena(leido[0])
    assert muestra_de_episodio(leido[0]).mascara.any()


def test_un_episodio_viejo_no_se_mezcla_en_silencio(tmp_path):
    """045:RF-2 — un grafo versión 2 se conserva y se lee, pero no enseña, y se dice por qué."""
    viejo = copy.deepcopy(_payload_v1())
    viejo['topologia'] = {'grafo': {'version': 2, 'nodos': {'S': {'kv': 10.0, 'fuente': True}}, 'ramas': []}}
    viejo['flujo']['tensiones'] = {'unidad': 'p.u.', 'valores': {'S': 1.0}}
    e = ep.leer_episodio(viejo)
    assert muestra_de_episodio(e) is None
    assert 'versión 2' in por_que_no_ensena(e)
