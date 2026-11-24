"""047:RF-89 a RF-91 — lo que la medida del 047h (2026-11-23) dejó ver, corregido sin el LLM.

Falsas alarmas: en propuestas sanas, el LLM dudaba de datos que estaban en la evidencia («cargabilidad_final_pct»),
enfrentaba la tensión de la máxima con la del valle del mismo fragmento, y preguntaba por lo que la propuesta no dice
(«tipo de aislador», «si hacen falta más reconectadores»). Detección casual: la medición de otra SED respaldaba el
cambio de tap y ningún rol lo vio. Aquí no hay LLM: dobles y valores sintéticos, que no copian los casos del 047h.
"""
from __future__ import annotations

from convertersmartgrid.aplicacion.asistente import contradicciones as C
from test_revision_reglas_t13 import _c, _revisar


def comprobar_datos(*a):
    assert hasattr(C, 'comprobar_datos'), 'el código no respalda los datos de la propuesta (RF-89)'
    return C.comprobar_datos(*a)


def comprobar_elementos(*a):
    assert hasattr(C, 'comprobar_elementos'), 'el código no comprueba el elemento de la evidencia (RF-90)'
    return C.comprobar_elementos(*a)


PROPUESTA = {'accion': 'cambiar 5 crucetas de madera de la estructura E41 del ramal R7 por crucetas de concreto', 'crucetas': 5,
             'cargabilidad_final_pct': 58, 'coste_usd': 600, 'restricciones_deterministas': {'plan_completo': True}}
FRAGMENTOS = {'e1': 'Cruceta de concreto, montada: USD 120 cada una.',
              'e2': 'Con el cambio, el ramal R7 queda con cargabilidad 58 %; límite 100 %.'}


def test_047_rf89_los_datos_que_respalda_la_evidencia_o_la_accion():
    """047:RF-89 — la cantidad que fija la acción y la cifra del fragmento quedan respaldadas; la de un límite no."""
    ev = {k: {'fragmento': v} for k, v in FRAGMENTOS.items()}
    hechos = {c['campo']: c['calculo'] for c in comprobar_datos(PROPUESTA, ev)}
    assert hechos == {'crucetas': 'la acción fija la cantidad', 'cargabilidad_final_pct': 'la cifra está en e2'}
    limite = {**PROPUESTA, 'cargabilidad_final_pct': 100}
    assert 'cargabilidad_final_pct' not in {c['campo'] for c in comprobar_datos(limite, ev)}, \
        'la cifra del límite respaldó un dato'
    otra = {**PROPUESTA, 'cargabilidad_final_pct': 61}
    assert 'cargabilidad_final_pct' not in {c['campo'] for c in comprobar_datos(otra, ev)}


def test_047_rf90_la_evidencia_de_otro_elemento_bloquea():
    """047:RF-90 — una medición de otro elemento con el mismo prefijo que el de la acción no la respalda."""
    propuesta = {'accion': 'subir un paso el tap de la SED S-5310', 'tension_actual_pu': 0.93, 'coste_usd': 0}
    ajena = {'e1': {'fragmento': 'Medición en la SED S-5130: 0,93 p.u. en la máxima.'}}
    c = comprobar_elementos(propuesta, ajena)
    assert len(c) == 1 and c[0]['coincide'] is False and 's-5130' in c[0]['calculo']
    propia = {'e1': {'fragmento': 'Medición en la SED S-5310: 0,93 p.u. en la máxima; la SED S-5130 no se midió.'}}
    assert comprobar_elementos(propuesta, propia) == [], 'el fragmento nombra también el elemento de la acción'
    sin_ids = {'e1': {'fragmento': 'Cambio de tap sin coste de materiales.'}}
    assert comprobar_elementos(propuesta, sin_ids) == []


def test_047_rf90_la_revision_no_aprueba_con_la_evidencia_de_otro_elemento(tmp_path):
    propuesta = {'accion': 'subir un paso el tap de la SED S-5310', 'tension_actual_pu': 0.93, 'coste_usd': 0,
                 'restricciones_deterministas': {'plan_completo': True}}
    r, _ = _revisar(tmp_path, {'decision': 'favorable', 'incertidumbres': [], 'contradicciones': []},
                    propuesta=propuesta, fragmentos={'e1': 'Medición en la SED S-5130: 0,93 p.u. en la máxima.',
                                                     'e2': 'El cambio de tap no tiene coste de materiales.'})
    assert not r['aprobada'], 'los roles favorables aprobaron con la medición de otra SED'
    assert any(not c['coincide'] and c['campo'] == 'accion' for c in r['comprobaciones_del_codigo'])


def test_047_rf91_con_todo_respaldado_las_dudas_sueltas_son_observaciones(tmp_path):
    """047:RF-91 — con cada dato respaldado y ninguna comprobación fallida, las dudas y la contradicción sobre un campo
    que la propuesta no tiene se guardan como observaciones; la contradicción sobre un dato sigue contando."""
    dudas = {'decision': 'revisar', 'incertidumbres': ['material de las crucetas', 'si el ramal R7 necesita más crucetas'],
             'contradicciones': [_c('material de la cruceta', 'concreto', 'madera', 'e3')]}
    r, _ = _revisar(tmp_path, dudas, propuesta=PROPUESTA, fragmentos={
        **FRAGMENTOS, 'e3': 'Las crucetas actuales de la E41 son de madera.'})
    assert r['aprobada'], 'con todos los datos respaldados, las dudas sueltas siguen bloqueando'
    d = r['dictamenes'][-1]
    assert 'material de las crucetas' in d['observaciones'] and d['incertidumbres'] == [] and d['contradicciones'] == []


def test_047_rf91_sin_todo_respaldado_las_dudas_siguen_contando(tmp_path):
    sin_respaldo = {**PROPUESTA, 'cargabilidad_final_pct': 61}
    r, _ = _revisar(tmp_path, {'decision': 'revisar', 'incertidumbres': ['cargabilidad_final_pct'], 'contradicciones': []},
                    propuesta=sin_respaldo, fragmentos=FRAGMENTOS)
    assert not r['aprobada'], 'un dato sin respaldo dejó de revisarse'
