"""047:RF-79 a RF-83 — lo que la medida del 047f (2026-11-22) dejó ver, corregido de forma general, sin mirar sus casos.

Falsas alarmas: el LLM comparaba el coste total con cada partida aunque el código ya había comprobado ese coste, y
dejaba como duda una cantidad que fija la acción. Sin respuesta: un rol bloqueó sin hallazgo y no hubo otra ronda.
Perdido: nadie vio una prohibición de la evidencia. Aquí no hay LLM: dobles y valores sintéticos.
"""
from __future__ import annotations

import json

from convertersmartgrid.aplicacion.asistente import revision_roles
from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision, revisar_propuesta
from test_asistente_revision_roles import _cliente, _dictamen_llm
from test_revision_cuentas_y_coste import _paquete

PROPUESTA = {'accion': 'montar 3 crucetas nuevas en el vano V44', 'crucetas': 3, 'coste_usd': 1500,
             'tension_final_pu': 0.98, 'restricciones_deterministas': {'plan_completo': True}}
FRAGMENTOS = {'e1': 'Partidas: crucetas 1 200 USD; montaje 300 USD.',
              'e2': 'Flujo en máxima tras el cambio: tensión mínima 0,98 p.u.'}


def _c(campo, propuesta, evidencia, fuente='e1'):
    return {'campo': campo, 'valor_propuesta': propuesta, 'valor_evidencia': evidencia, 'fuente': fuente,
            'base': 'total'}


def _revisar(tmp_path, dictamen, propuesta=PROPUESTA, fragmentos=FRAGMENTOS, rondas=1, roles=('unico',)):
    contexto, evidencia = _paquete(tmp_path, fragmentos)
    llamadas = []

    def revisor(rol, p, ev, ctx, ronda):
        llamadas.append((rol, ronda, p))
        d = dictamen(ronda) if callable(dictamen) else dictamen
        return json.loads(json.dumps({**d, 'evidencia_ids': sorted(ev)}))
    r = revisar_propuesta(propuesta, evidencia, contexto=contexto, max_rondas=rondas, roles=roles, revisor=revisor)
    return r, llamadas


def test_el_campo_que_comprobo_el_codigo_no_lo_decide_el_llm(tmp_path):
    """047:RF-79 — el coste cuadra con la suma de las partidas: «1500 frente a 1 200» no bloquea."""
    r, _ = _revisar(tmp_path, {'decision': 'bloqueada', 'incertidumbres': [],
                               'contradicciones': [_c('coste_usd', '1500', '1 200 USD')]})
    assert r['aprobada'], 'el LLM vuelve a decidir un coste que el código ya comprobó y cuadra'
    d = r['dictamenes'][0]
    assert d['contradicciones'] == [] and d['decision_devuelta'] == 'bloqueada'
    assert d['contradicciones_descartadas'][0]['motivo'].startswith('el código comprobó coste_usd')
    r, _ = _revisar(tmp_path, {'decision': 'bloqueada', 'incertidumbres': [],
                               'contradicciones': [_c('tension_final_pu', '0,98', '0,91 p.u.', 'e2')]},
                    fragmentos={**FRAGMENTOS, 'e2': 'Flujo en máxima tras el cambio: tensión mínima 0,91 p.u.'})
    assert not r['aprobada'] and r['dictamenes'][0]['contradicciones'], 'otro campo sigue decidiéndolo el dictamen'


def test_con_el_coste_que_no_cuadra_la_contradiccion_cuenta(tmp_path):
    """047:RF-79 — solo un campo que cuadra se lo queda el código; si no cuadra, la revisión ya no se aprueba."""
    r, _ = _revisar(tmp_path, {'decision': 'bloqueada', 'incertidumbres': [],
                               'contradicciones': [_c('coste_usd', '1400', '1 200 USD + 300 USD')]},
                    propuesta={**PROPUESTA, 'coste_usd': 1400})
    assert not r['aprobada'] and r['dictamenes'][0]['contradicciones']


def test_una_cantidad_que_fija_la_accion_no_es_una_duda(tmp_path):
    """047:RF-80 — «crucetas» como incertidumbre, con «montar 3 crucetas» en la acción, se descarta."""
    r, _ = _revisar(tmp_path, {'decision': 'revisar', 'incertidumbres': ['crucetas'], 'contradicciones': []})
    assert r['aprobada'], 'una cantidad de la acción como duda sigue impidiendo aprobar'
    d = r['dictamenes'][0]
    assert d['incertidumbres'] == [] and d['decision'] == 'favorable' and d['decision_devuelta'] == 'revisar'
    assert d['incertidumbres_descartadas'][0]['entrada'] == 'crucetas'


def test_una_duda_cuyo_valor_no_fija_la_accion_se_mantiene(tmp_path):
    """047:RF-80 — conservador: un campo cuyo valor solo está en una evidencia (que puede ser de otro elemento), o una
    frase, siguen siendo dudas mientras el código no respalde todos los datos; con todos respaldados (RF-89), RF-91 las
    deja como observaciones."""
    sin_tension = {**FRAGMENTOS, 'e2': 'Flujo en máxima tras el cambio: sin violaciones en el vano.'}
    for duda in ('tension_final_pu', 'el procedimiento de seguridad de e2 prohíbe el trabajo'):
        r, _ = _revisar(tmp_path, {'decision': 'revisar', 'incertidumbres': [duda], 'contradicciones': []},
                        fragmentos=sin_tension)
        assert not r['aprobada'] and r['dictamenes'][0]['incertidumbres'] == [duda]
        r, _ = _revisar(tmp_path, {'decision': 'revisar', 'incertidumbres': [duda], 'contradicciones': []})
        d = r['dictamenes'][0]
        # El campo que el código respaldó se descarta (RF-85); la frase queda como observación (RF-91).
        guardadas = d.get('observaciones', []) + [x['entrada'] for x in d.get('incertidumbres_descartadas', [])]
        assert d['incertidumbres'] == [] and duda in guardadas, 'RF-91: con todo respaldado la duda no bloquea'


def test_un_dictamen_no_valido_se_pide_de_nuevo(tmp_path):
    """047:RF-81 — «bloqueada» sin hallazgo en la primera ronda: la segunda se lo pide otra vez con el motivo."""
    def dictamen(ronda):
        if ronda == 1:
            return {'decision': 'bloqueada', 'incertidumbres': [], 'contradicciones': []}
        return {'decision': 'favorable', 'incertidumbres': [], 'contradicciones': []}
    r, llamadas = _revisar(tmp_path, dictamen, rondas=2)
    assert [(rol, ronda) for rol, ronda, _p in llamadas] == [('unico', 1), ('unico', 2)], \
        'un dictamen no válido no se vuelve a pedir'
    anterior = llamadas[1][2]['dictamenes_ronda_anterior'][0]
    assert 'sin hallazgo' in anterior['incertidumbres'][0]
    assert r['aprobada'] and r['dictamenes'][0]['fallo_revisor'] and not r['dictamenes'][1].get('fallo_revisor')


def test_un_revisor_que_no_responde_no_se_repite(tmp_path):
    """047:RF-81 — solo se pide de nuevo a quien respondió: un fallo sin respuesta no gasta otra ronda."""
    contexto, evidencia = _paquete(tmp_path, FRAGMENTOS)
    llamadas = []

    def revisor(*a):
        llamadas.append(a[4])
        raise TimeoutError('sin respuesta')
    r = revisar_propuesta(PROPUESTA, evidencia, contexto=contexto, max_rondas=2, roles=('unico',), revisor=revisor)
    assert llamadas == [1] and not r['aprobada']


def test_el_encargo_de_riesgo_incluye_las_prohibiciones(tmp_path):
    """047:RF-82 — el riesgo también es que la evidencia prohíba o limite cómo hacer la acción, y va en incertidumbres."""
    for rol in ('riesgo', 'unico'):
        encargo = revision_roles._ENCARGO[rol]
        assert 'prohíbe o limita' in encargo or 'prohibición o límite' in encargo, rol
        assert 'incertidumbres, con el ID y la frase de la evidencia' in encargo, rol
    contexto, evidencia = _paquete(tmp_path, FRAGMENTOS)
    peticiones = []
    revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1, roles=('riesgo',),
                      revisor=revision_roles.revisor_ollama(_cliente(_dictamen_llm(
                          {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                           'contradicciones': []}), peticiones)))
    assert 'trabajo en caliente' in peticiones[0][1]['messages'][0]['content']


def test_la_frase_de_la_accion_no_se_lee_como_cifra(tmp_path):
    """047:RF-83 — «montar 3 crucetas nuevas en el vano V44» frente a una frase con «0,98 p.u.» no es una cifra."""
    r, _ = _revisar(tmp_path, {'decision': 'bloqueada', 'incertidumbres': [],
                               'contradicciones': [_c('accion', PROPUESTA['accion'], FRAGMENTOS['e2'], 'e2')]})
    assert r['aprobada'], 'la frase de la acción se compara como cifra'
    assert r['dictamenes'][0]['contradicciones_descartadas'][0]['motivo'].startswith('la acción no es un dato')
    propuesta = {**PROPUESTA, 'accion': 'montar 3 crucetas de 450 kvar'}
    r, _ = _revisar(tmp_path, {'decision': 'bloqueada', 'incertidumbres': [],
                               'contradicciones': [_c('accion', '450 kvar', '300 kvar', 'e3')]},
                    propuesta=propuesta, fragmentos={**FRAGMENTOS, 'e3': 'Banco de prueba de 300 kvar.'})
    assert not r['aprobada'] and r['dictamenes'][0]['contradicciones']


def test_el_informe_cuenta_las_dudas_descartadas(tmp_path):
    """047:RF-80 — la medida dice cuántas incertidumbres descartó el código, y las guarda por dictamen."""
    contexto, evidencia = _paquete(tmp_path, FRAGMENTOS)
    casos = [{'id': 'x1', 'defecto': None, 'contexto': contexto, 'evidencia': evidencia, 'propuesta': PROPUESTA}]
    r = comparar_revision(casos, lambda medir: (lambda rol, p, ev, ctx, ronda: {
        'decision': 'revisar', 'evidencia_ids': sorted(ev), 'incertidumbres': ['crucetas'], 'contradicciones': []}),
        rondas=1)
    for modo in ('rol_unico', 'equipo'):
        assert r[modo].get('incertidumbres_descartadas') == r[modo]['intervenciones']
        assert r[modo]['falsas_alarmas'] == 0
        assert r[modo]['por_caso'][0]['dictamenes'][0]['incertidumbres_descartadas'][0]['entrada'] == 'crucetas'
