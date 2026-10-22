"""Spec 024, T1: contrato del episodio del gemelo digital (sin DIgSILENT)."""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from igea_dgs.digital_twin import episode as ep

RAIZ = Path(__file__).resolve().parents[1]
H = 'a' * 64


def _payload(**cambios) -> dict:
    """Episodio mínimo válido de «Sin proyecto» con dos alimentadores."""
    base = {
        'schema': ep.ESQUEMA,
        'clase': 'accepted',
        'caso': 'sin_proyecto',
        'creado': '2026-10-21T10:00:00+00:00',
        'fuente': {'source_run_id': 'run-1', 'source_mode': 'txt', 'source_fingerprint': H},
        'nativo': {'project': 'P', 'folder': 'F', 'feeders': ['A1', 'A2'],
                   'pf_version': '2024', 'reopen_verified': True},
        'accion': {'tipo': 'ajuste_ejecutar', 'aplicada': True},
        'topologia': {'frontera': ['SEC_1']},
        'flujo': {
            'balance': {'unidad': 'kW', 'valores': {'cabecera': 1000.0}},
            'perdidas': {'unidad': 'kW', 'valores': {'total': 25.0}},
            'cargabilidad': {'unidad': '%', 'valores': {'L1': 40.0}},
            'tensiones': {'unidad': 'p.u.', 'valores': {'B1': 0.98}},
            'confiabilidad': {'ausente': 'la spec 012 no se ejecutó'},
        },
        'aceptacion': {'bloqueos': [], 'diagnostico': []},
        'obras': [],
        'artefactos': [{'rol': 'resultado', 'ruta': 'r.json', 'sha256': H, 'bytes': 10}],
    }
    base.update(cambios)
    return base


def _campo_que_falla(payload) -> str:
    with pytest.raises(ep.EpisodioInvalido) as err:
        ep.leer_episodio(payload)
    return err.value.campo


def test_la_huella_no_depende_del_orden_de_las_claves():
    """024:RF-6 — el mismo contenido da la misma huella, sea cual sea el orden de las claves."""
    a = _payload()
    b = json.loads(json.dumps(a))
    b['fuente'] = dict(reversed(list(b['fuente'].items())))
    b = dict(reversed(list(b.items())))
    assert ep.huella_episodio(a) == ep.huella_episodio(b)


def test_el_orden_de_los_alimentadores_cuenta():
    """024:RF-2 — el orden de los alimentadores expresa la orientación: otra huella."""
    a = _payload()
    b = copy.deepcopy(a)
    b['nativo']['feeders'] = ['A2', 'A1']
    assert ep.huella_episodio(a) != ep.huella_episodio(b)


def test_la_huella_ignora_el_identificador_y_cambia_con_el_contenido():
    """024:RF-6 — ``episode_id`` no entra en su propia huella; un dato distinto, sí."""
    a = _payload()
    con_id = dict(a, episode_id=ep.huella_episodio(a))
    assert ep.huella_episodio(con_id) == ep.huella_episodio(a)
    b = copy.deepcopy(a)
    b['flujo']['perdidas']['valores']['total'] = 26.0
    assert ep.huella_episodio(b) != ep.huella_episodio(a)


def test_episodio_valido_se_lee_con_su_huella():
    """024:RF-1 / 024:RF-28 — un episodio completo se lee, liga fuente y proyecto y conserva
    los resultados del flujo."""
    leido = ep.leer_episodio(_payload())
    assert leido.episode_id == ep.huella_episodio(_payload())
    assert leido.clase is ep.Clase.ACCEPTED and leido.caso is ep.Caso.SIN_PROYECTO
    assert leido.fuente['source_fingerprint'] == H
    assert leido.nativo['feeders'] == ['A1', 'A2']
    assert set(leido.flujo) == set(ep.RESULTADOS_FLUJO)
    assert leido.artefactos[0] == ep.Artefacto('resultado', 'r.json', H, 10)
    assert ep.episodio_a_dict(leido) == dict(_payload(), episode_id=leido.episode_id)


def test_un_identificador_que_no_es_su_huella_se_rechaza():
    """024:RF-6 — un ``episode_id`` que no corresponde al contenido es una colisión."""
    assert _campo_que_falla(_payload(episode_id='b' * 64)) == 'episode_id'


@pytest.mark.parametrize(('cambio', 'campo'), [
    (lambda p: p['fuente'].pop('source_fingerprint'), 'fuente.source_fingerprint'),
    (lambda p: p['fuente'].update(source_fingerprint='xyz'), 'fuente.source_fingerprint'),
    (lambda p: p['fuente'].pop('source_run_id'), 'fuente.source_run_id'),
    (lambda p: p['nativo'].pop('project'), 'nativo.project'),
    (lambda p: p['nativo'].update(feeders=[]), 'nativo.feeders'),
    (lambda p: p.update(schema='otro-v9'), 'schema'),
    (lambda p: p.update(clase='quizas'), 'clase'),
    (lambda p: p.update(caso='caso_raro'), 'caso'),
    (lambda p: p['flujo'].pop('confiabilidad'), 'flujo.confiabilidad'),
    (lambda p: p['flujo']['tensiones'].pop('unidad'), 'flujo.tensiones.unidad'),
    (lambda p: p['flujo'].update(perdidas={'ausente': ''}), 'flujo.perdidas.ausente'),
    (lambda p: p['artefactos'].append(dict(p['artefactos'][0])), 'artefactos[1].rol'),
    (lambda p: p['artefactos'][0].update(sha256='corto'), 'artefactos[0].sha256'),
])
def test_validacion_nombra_el_campo_que_falla(cambio, campo):
    """024:RF-7 / 024:RF-9 — huella, unidades, procedencia o identidad que faltan o no
    encajan se rechazan con la ruta del campo."""
    p = _payload()
    cambio(p)
    assert _campo_que_falla(p) == campo


def test_aceptado_sin_reapertura_se_rechaza():
    """024:RF-4 — sin reapertura y relectura no hay episodio ``accepted``."""
    p = _payload()
    p['nativo']['reopen_verified'] = False
    assert _campo_que_falla(p) == 'nativo.reopen_verified'
    p['clase'] = 'quarantine'
    assert ep.leer_episodio(p).clase is ep.Clase.QUARANTINE


def test_obras_con_su_alternativa_del_pide():
    """024:RF-32 — cada obra lleva su alternativa del PIDE, su tramo o equipo, su coste y
    los indicadores del Anexo N.º 6 (VAN, TIR y período de retorno), que pueden faltar."""
    obra = {'alternativa': 'cambio_seccion', 'elemento': 'L_3091_3092', 'coste': 1500.0,
            'van': 320.5, 'tir': 0.14, 'retorno_anios': 6.2}
    p = _payload(caso='con_proyecto', obras=[obra, {'alternativa': 'bancos', 'elemento': 'B1',
                                                       'coste': None, 'van': None, 'tir': None,
                                                       'retorno_anios': None}])
    leido = ep.leer_episodio(p)
    assert [o['alternativa'] for o in leido.obras] == ['cambio_seccion', 'bancos']
    assert set(ep.ALTERNATIVAS_PIDE) >= {'bancos', 'reguladores', 'cambio_seccion', 'nueva_terna',
                                         'nueva_sed', 'nuevo_alimentador', 'nueva_set'}


@pytest.mark.parametrize(('obra', 'campo'), [
    ({'alternativa': 'pintar_postes', 'elemento': 'X'}, 'obras[0].alternativa'),
    ({'alternativa': 'bancos'}, 'obras[0].elemento'),
    ({'alternativa': 'bancos', 'elemento': 'B', 'coste': 'caro'}, 'obras[0].coste'),
])
def test_obra_mal_formada(obra, campo):
    """024:RF-32 — una obra sin alternativa conocida, sin elemento o con un indicador que no
    es un número se rechaza."""
    assert _campo_que_falla(_payload(caso='con_proyecto', obras=[obra])) == campo


def test_el_caso_base_no_lleva_obras():
    """024:RF-28 / 024:RF-29 — el «Caso base» es la red tal como está: sin obras."""
    obra = {'alternativa': 'bancos', 'elemento': 'B1'}
    assert _campo_que_falla(_payload(caso='caso_base', obras=[obra])) == 'obras'


def test_sorteo_de_clases_casos_y_alimentadores():
    """024:RF-2 / 024:RF-6 — con clases, casos y número de alimentadores sorteados, cada
    episodio válido se lee y su huella es estable al reordenar las claves."""
    semilla = random.randrange(1 << 30)
    rnd = random.Random(semilla)
    for _ in range(25):
        p = _payload(clase=rnd.choice([c.value for c in ep.Clase]),
                     caso=rnd.choice([c.value for c in ep.Caso]))
        p['nativo']['feeders'] = [f'F{i}' for i in range(rnd.randint(1, 40))]
        mezclado = dict(rnd.sample(list(p.items()), len(p)))
        assert ep.huella_episodio(mezclado) == ep.leer_episodio(p).episode_id, f'semilla {semilla}'


def test_el_esquema_json_coincide_con_el_contrato():
    """024:RF-7 — el esquema publicado y el contrato de Python declaran lo mismo."""
    esquema = json.loads((RAIZ / 'src' / 'igea_dgs' / 'schemas'
                          / 'digital_twin_episode_v1.schema.json').read_text(encoding='utf-8'))
    props = esquema['properties']
    assert props['schema']['const'] == ep.ESQUEMA
    assert props['clase']['enum'] == [c.value for c in ep.Clase]
    assert props['caso']['enum'] == [c.value for c in ep.Caso]
    assert props['flujo']['required'] == list(ep.RESULTADOS_FLUJO)
    assert esquema['$defs']['obra']['properties']['alternativa']['enum'] == list(ep.ALTERNATIVAS_PIDE)
    assert set(esquema['required']) == set(ep.CAMPOS)
