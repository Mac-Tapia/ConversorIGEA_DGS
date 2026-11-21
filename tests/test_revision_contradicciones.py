"""047:RF-48 a RF-51 — las contradicciones del dictamen son estructuradas y las decide el código, no el texto del LLM.

La medida del 047c (2026-11-21) falló porque qwen3:8b escribía en «contradicciones» comprobaciones cuyos dos valores
coinciden: anulaban favorables correctos y bloqueaban propuestas sanas. Aquí no hay LLM: los revisores son dobles y los
valores, sintéticos; nada se ajusta a las respuestas esperadas de ningún conjunto.
"""
from __future__ import annotations

import json

import pytest

from convertersmartgrid.aplicacion.asistente import revision_roles
from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision, revisar_propuesta
from test_asistente_revision_roles import _cliente, _dictamen_llm, _herramienta_comparar, paquete

CAMPOS = ['campo', 'valor_propuesta', 'valor_evidencia', 'fuente', 'base']
#: 047:RF-53 (MEJ24c): una contradicción solo cuenta si su valor está en la propuesta; esta los tiene.
SANA = {'restricciones_deterministas': {'plan_completo': True}, 'coste_usd': 4300, 'carga_pct': 71,
        'tension_pu': 0.98, 'corriente_a': 118, 'p_kw': 2100, 'x_pct': 3}


def _contradiccion(campo, propuesta, evidencia, fuente='e1'):
    return {'campo': campo, 'valor_propuesta': propuesta, 'valor_evidencia': evidencia, 'fuente': fuente}


def _revisar(tmp_path, dictamen, propuesta=SANA):
    contexto, evidencia = paquete(tmp_path)
    return revisar_propuesta(propuesta, evidencia, contexto=contexto, max_rondas=1,
                             revisor=lambda *_a: json.loads(json.dumps(dictamen)))


def _coinciden(a, b) -> bool:
    funcion = getattr(revision_roles, 'valores_coinciden', None)
    assert funcion is not None, 'el código no compara los dos valores de una contradicción'
    return funcion(a, b)


def test_el_esquema_pide_cada_contradiccion_con_sus_dos_valores_y_su_fuente():
    """047:RF-48 — una lista de textos no dejaba al código ver qué se comparaba."""
    esquema = revision_roles.esquema_dictamen()
    items = esquema['properties']['contradicciones']['items']
    assert items.get('type') == 'object', 'las contradicciones siguen siendo texto libre'
    assert list(items['properties']) == CAMPOS and items['required'] == CAMPOS
    assert items['additionalProperties'] is False
    assert list(esquema['properties'])[-1] == 'decision'


@pytest.mark.parametrize('mala', [
    {'campo': 'coste_usd', 'valor_propuesta': '100', 'valor_evidencia': '120'},
    {**_contradiccion('coste_usd', '100', '120'), 'nota': 'otra clave'},
    _contradiccion('coste_usd', '', '120'),
    _contradiccion('coste_usd', True, '120'),
    {**_contradiccion('coste_usd', '100', '120'), 'base': 'parcial'},
    7,
])
def test_una_contradiccion_con_otra_forma_hace_el_dictamen_no_valido(tmp_path, mala):
    """047:RF-48 — sin los cuatro campos, el código no puede decidir: no vale, y bloquea sin contar como hallazgo."""
    r = _revisar(tmp_path, {'decision': 'bloqueada', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': [mala]})
    assert not r['aprobada']
    assert all(d.get('fallo_revisor') for d in r['dictamenes'])


@pytest.mark.parametrize('a, b', [
    ('11200', '11200'), ('11200', '11 200 USD'), ('62', '62 %'), ('62%', '62 %'), ('38 kW', '38 kW'),
    ('0,97 p.u.', '0.97'), ('1,8 MW', '1800 kW'), ('US$ 3 900', '3900 USD'), ('250 kvar', '0,25 Mvar'),
    ('100', '100,4'), ('A21', 'a21'), (125, '125 A'), ('2,5 km', '2500 m'),
    # 047:RF-52 (MEJ24c): una cifra ambigua coincide si una de sus lecturas es la del otro valor.
    ('11.200', '11200'), ('1,250', '1.25'),
])
def test_los_mismos_valores_con_otro_formato_o_unidad_coinciden(a, b):
    """047:RF-49 — separador de miles, coma decimal, unidad escrita o no y su múltiplo: el mismo valor."""
    assert _coinciden(a, b) and _coinciden(b, a)


@pytest.mark.parametrize('a, b', [
    ('62', '65'), ('100', '101'), ('1,25 MW', '1450 kW'), ('5 A', '5 kA'), ('38 kW', '38 kvar'),
    ('A21', 'A22'), ('1.07 p.u.', '1,04 p.u.'), ('0', '0,5'),
    ('62 %', '62 kW'), ('sin respaldo', 'con respaldo'),
])
def test_los_valores_distintos_o_que_no_se_saben_leer_no_coinciden(a, b):
    """047:RF-49 — conservador: otra cifra fuera del 0,5 %, otra magnitud o un texto distinto."""
    assert not _coinciden(a, b) and not _coinciden(b, a)


def test_la_tolerancia_es_relativa_y_esta_documentada():
    """047:RF-49 — 0,5 % de la mayor: absorbe el redondeo de la cifra impresa, no un error de ingeniería."""
    assert getattr(revision_roles, 'TOLERANCIA_RELATIVA', None) == 0.005
    assert _coinciden('200', '200,9') and not _coinciden('200', '201,1')


def test_las_que_coinciden_se_descartan_con_registro_y_no_cuentan(tmp_path):
    """047:RF-49 / RF-50 — un favorable con comprobaciones que coinciden era anulado por RF-40 («sin respuesta»)."""
    iguales = [_contradiccion('coste_usd', '4300', '4 300 USD'), _contradiccion('carga_pct', '71', '71 %')]
    r = _revisar(tmp_path, {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': iguales})
    assert r['aprobada'], 'unas contradicciones cuyos valores coinciden siguen anulando el dictamen favorable'
    for d in r['dictamenes']:
        assert not d.get('fallo_revisor') and d['contradicciones'] == [] and d['decision'] == 'favorable'
        assert [x['entrada'] for x in d['contradicciones_descartadas']] == iguales
        assert all('iguales' in x['motivo'] for x in d['contradicciones_descartadas'])
        assert 'decision_devuelta' not in d


def test_con_algo_descartado_la_decision_sale_de_lo_que_queda(tmp_path):
    """047:RF-50 — un bloqueo cuyas únicas contradicciones coinciden era una falsa alarma; la decisión devuelta queda."""
    iguales = [_contradiccion('tension_pu', '0,98', '0.98 p.u.')]
    r = _revisar(tmp_path, {'decision': 'bloqueada', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': iguales})
    assert r['aprobada'], 'un bloqueo sin ninguna contradicción que cuente sigue bloqueando'
    assert all(d['decision'] == 'favorable' and d['decision_devuelta'] == 'bloqueada' for d in r['dictamenes'])
    real = _contradiccion('corriente_a', '118', '141 A')
    r = _revisar(tmp_path, {'decision': 'revisar', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': [*iguales, real]})
    assert not r['aprobada']
    for d in r['dictamenes']:
        assert d['decision'] == 'bloqueada' and d['decision_devuelta'] == 'revisar' and d['contradicciones'] == [real]
    r = _revisar(tmp_path, {'decision': 'bloqueada', 'evidencia_ids': ['e1'], 'incertidumbres': ['horas: sin dato'],
                            'contradicciones': iguales})
    assert all(d['decision'] == 'revisar' for d in r['dictamenes']) and not r['aprobada']


def test_sin_nada_descartado_decide_el_modelo(tmp_path):
    """047:RF-50 — el código no reescribe una decisión cuyas listas no tocó."""
    real = _contradiccion('corriente_a', '118', '141 A')
    r = _revisar(tmp_path, {'decision': 'revisar', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': [real]})
    assert all(d['decision'] == 'revisar' and 'decision_devuelta' not in d and
               'contradicciones_descartadas' not in d and d['contradicciones'] == [real] for d in r['dictamenes'])
    r = _revisar(tmp_path, {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': [real]})
    assert not r['aprobada'] and all(d.get('fallo_revisor') for d in r['dictamenes'])


def test_el_texto_libre_se_interpreta_o_se_mantiene(tmp_path):
    """047:RF-49 — formato anterior: «campo: X vs Y» se lee; lo que no se lee sigue siendo contradicción."""
    iguales = ['coste_usd: 4300 (propuesta) vs 4 300 (e2)', 'e1: carga_pct: 71 vs 71%', 'p_kw: 2,1 MW frente a 2100 kW',
               'coste_usd: 4.300 vs 4300']
    quedan = ['x_pct: 3 vs 4', 'e1 da 0,95 p.u. y la propuesta 1,01', 'a vs b vs c']
    r = _revisar(tmp_path, {'decision': 'bloqueada', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                            'contradicciones': iguales + quedan})
    for d in r['dictamenes']:
        assert d['contradicciones'] == quedan and d['decision'] == 'bloqueada'
        assert [x['entrada'] for x in d.get('contradicciones_descartadas', [])] == iguales


def test_el_informe_cuenta_las_descartadas_y_las_recalculadas(tmp_path):
    """047:RF-50 — la medida dice cuántas contradicciones descartó el código y cuántas decisiones recalculó."""
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)[:2]
    def fabrica(medir):
        return lambda rol, p, ev, ctx, ronda: {'decision': 'bloqueada', 'evidencia_ids': sorted(ev),
                                               'incertidumbres': [],
                                               'contradicciones': [_contradiccion('coste_usd', '10', '10 USD')]}
    r = comparar_revision(casos, fabrica, rondas=1)
    for modo in ('rol_unico', 'equipo'):
        informe = r[modo]
        assert informe.get('contradicciones_descartadas') == informe['intervenciones']
        assert informe.get('decisiones_recalculadas') == informe['intervenciones']
        assert informe['falsas_alarmas'] == 0 and informe['sin_respuesta'] == 0
        d = informe['por_caso'][0]['dictamenes'][0]
        assert d['decision'] == 'favorable' and d['decision_devuelta'] == 'bloqueada'
        assert d['contradicciones_descartadas'][0]['entrada']['campo'] == 'coste_usd'


def test_el_encargo_pide_anotar_solo_los_valores_distintos(tmp_path):
    """047:RF-51 / RF-48 — cada rol recibe la forma de la contradicción y que lo que coincide no se escribe."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import revisor_ollama
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1,
                      revisor=revisor_ollama(_cliente(_dictamen_llm({'decision': 'favorable', 'evidencia_ids': ['e1'],
                                                                     'incertidumbres': [], 'contradicciones': []}),
                                                      peticiones)))
    assert len(peticiones) == 4
    for _u, cuerpo in peticiones:
        sistema = cuerpo['messages'][0]['content']
        assert 'Anota solo los valores distintos' in sistema
        assert all(c in sistema for c in CAMPOS)
        assert cuerpo['format']['properties']['contradicciones']['items'].get('type') == 'object'
