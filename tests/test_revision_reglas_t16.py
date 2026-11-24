"""047:RF-85 a RF-88 — lo que la medida del 047g (2026-11-23) dejó ver, corregido de forma general.

Falsas alarmas: el LLM dejaba como duda el coste que el código ya había comprobado y cuadraba, o copiaba la acción
entera como incertidumbre, o enfrentaba una cantidad de elementos con la longitud de cada uno. Perdido: en el modo
equipo ningún rol vio que la evidencia prohíbe hacer la acción. Aquí no hay LLM: dobles y valores sintéticos, que no
copian los casos del 047g.
"""
from __future__ import annotations

from convertersmartgrid.aplicacion.asistente.contradicciones import (
    comprobar_prohibiciones, filtrar_contradicciones, filtrar_incertidumbres)
from test_revision_reglas_t13 import _c, _revisar

PROPUESTA = {'accion': 'tender 4 retenidas nuevas en la estructura E19', 'retenidas': 4, 'coste_usd': 880,
             'restricciones_deterministas': {'plan_completo': True}}
FRAGMENTOS = {'e1': 'Retenida de acero de 7 m, montada: USD 220 cada una.',
              'e2': 'La estructura E19 queda con factor de seguridad 2,1.'}


def test_la_duda_sobre_el_campo_que_comprobo_el_codigo_no_cuenta(tmp_path):
    """047:RF-85 — el coste cuadra (4 × 220): «coste_usd» como incertidumbre no bloquea una propuesta sana."""
    quedan, descartadas = filtrar_incertidumbres(['coste_usd'], PROPUESTA, comprobados={'coste_usd'})
    assert quedan == [] and 'comprobó coste_usd' in descartadas[0]['motivo']
    quedan, _ = filtrar_incertidumbres(['coste_usd'], PROPUESTA)
    assert quedan == ['coste_usd'], 'sin la comprobación del código la duda se mantiene'
    r, _ = _revisar(tmp_path, {'decision': 'revisar', 'incertidumbres': ['coste_usd'], 'contradicciones': []},
                    propuesta=PROPUESTA, fragmentos=FRAGMENTOS)
    assert r['aprobada'], 'la duda sobre un coste que el código comprobó y cuadra sigue bloqueando'


def test_la_accion_copiada_como_incertidumbre_no_cuenta(tmp_path):
    """047:RF-86 — la acción es lo que se revisa (RF-46): repetirla como duda no es un hallazgo."""
    quedan, descartadas = filtrar_incertidumbres(['Tender 4 retenidas nuevas en la estructura E19.'], PROPUESTA)
    assert quedan == [] and 'repite la acción' in descartadas[0]['motivo']
    quedan, _ = filtrar_incertidumbres(['si la estructura E19 admite el tiro de 4 retenidas'], PROPUESTA)
    assert quedan, 'una duda sobre la acción, distinta de la acción, se mantiene'
    ev = {'e1': {'fragmento': 'Retenidas nuevas de acero galvanizado con su ancla de concreto: USD 220 cada una.'}}
    # Un trozo de la acción de tres palabras o más (RF-86); dos palabras sueltas no bastan para decir que la repite.
    quedan, descartadas = filtrar_contradicciones([_c('retenidas nuevas', 'retenidas nuevas en la estructura',
                                                      'Retenidas nuevas de acero galvanizado con su ancla de concreto')],
                                                  PROPUESTA, ev)
    assert quedan == [] and 'repite la acción' in descartadas[0]['motivo'], 'palabras de la acción frente a la evidencia'
    p = {**PROPUESTA, 'accion': 'tender 4 retenidas nuevas desde la estructura E19'}
    ev = {'e1': {'fragmento': 'Las retenidas se tienden desde la estructura E21.'}}
    quedan, _ = filtrar_contradicciones([_c('estructura', 'estructura E19', 'estructura E21')], p, ev)
    assert quedan, 'otro elemento de la red sigue contando como contradicción'


def test_una_cantidad_no_se_enfrenta_a_una_longitud(tmp_path):
    """047:RF-87 — «retenidas 4» frente a los «7 m» de cada retenida son magnitudes distintas."""
    ev = {'e1': {'fragmento': FRAGMENTOS['e1']}}
    for valor_e in ('7 m', '7'):
        quedan, descartadas = filtrar_contradicciones([_c('retenidas', 4, valor_e)], PROPUESTA, ev)
        assert quedan == [] and 'magnitudes distintas' in descartadas[0]['motivo'], valor_e
    # Una cantidad frente a otra cantidad distinta sigue contando.
    ev2 = {'e1': {'fragmento': 'El cálculo mecánico pide 6 retenidas en E19.'}}
    quedan, _ = filtrar_contradicciones([_c('retenidas', 4, '6')], PROPUESTA, ev2)
    assert quedan, 'dos cantidades distintas de retenidas son una contradicción'
    # Un campo con su unidad en el nombre sí se compara con la unidad de la evidencia.
    p = {**PROPUESTA, 'longitud_km': 3}
    ev3 = {'e1': {'fragmento': 'El tramo mide 5 km.'}}
    quedan, _ = filtrar_contradicciones([_c('longitud_km', 3, '5 km')], p, ev3)
    assert quedan, 'una longitud distinta de la del tramo es una contradicción'


def test_la_accion_que_la_evidencia_prohibe_la_detecta_el_codigo(tmp_path):
    """047:RF-88 — «puentear» cuando el procedimiento prohíbe puentearlo: lo halla el código, sin el LLM."""
    p = {'accion': 'puentear el reconectador R7 durante la poda del tramo', 'coste_usd': 0}
    ev = {'e1': {'fragmento': 'El reglamento interno prohíbe puentearlo mientras haya personal en el tramo.'},
          'e2': {'fragmento': 'La poda ocupa 3 h con una cuadrilla.'}}
    c = comprobar_prohibiciones(p, ev)
    assert len(c) == 1 and c[0]['coincide'] is False and c[0]['campo'] == 'accion' and c[0]['fuentes'] == ['e1']
    sana = {'accion': 'instalar un indicador de falla en el tramo', 'coste_usd': 0}
    assert comprobar_prohibiciones(sana, ev) == [], 'otra prohibición de la evidencia no es la de la acción'
    r, _ = _revisar(tmp_path, {'decision': 'favorable', 'incertidumbres': [], 'contradicciones': []},
                    propuesta={**p, 'restricciones_deterministas': {'plan_completo': True}},
                    fragmentos={k: v['fragmento'] for k, v in ev.items()})
    assert not r['aprobada'], 'una acción que la evidencia prohíbe se aprueba porque el revisor no la vio'
