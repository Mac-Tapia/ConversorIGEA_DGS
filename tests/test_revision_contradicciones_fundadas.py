"""047:RF-52 a RF-56 — una contradicción cuenta solo si sus valores, leídos como cifras, son distintos, están en la
propuesta y en la fuente citada y se refieren a la misma base.

La medida T8d (2026-11-21) dio 5 falsas alarmas de 6 sanos en los dos modos: cifras escritas con marcas («>$14500»,
«_3_», «/^3$/i»), una cifra dentro de una frase, valores que no estaban en ningún sitio («user», «kOhm») y un total
frente a un precio por unidad. Aquí no hay LLM: dobles y valores sintéticos, sin mirar las respuestas de ningún conjunto.
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from convertersmartgrid.aplicacion.asistente import revision_roles
from convertersmartgrid.aplicacion.asistente.revision_roles import revisar_propuesta
from test_asistente_revision_roles import _cliente, _dictamen_llm

PROPUESTA = {'accion': 'cambiar 4 aisladores del vano V18 por aisladores de 450 kvar de prueba', 'aisladores': 4,
             'coste_usd': 520, 'demanda_kw': 1450, 'tension_pu': 0.97,
             'restricciones_deterministas': {'plan_completo': True}}
FRAGMENTOS = {'e1': 'Medición del vano V18: demanda máxima 1,25 MW; tensión mínima 0,97 p.u.',
              'e2': 'Aislador polimérico de 25 kV, instalado: 130 USD por unidad.',
              'e3': 'El vano V18 requiere 4 aisladores; banco de prueba de 300 kvar.'}


def _paquete(tmp_path, fragmentos=FRAGMENTOS):
    contexto = SimpleNamespace(project='P1', source_fingerprint='abc')
    evidencia = {}
    for clave, texto in fragmentos.items():
        ruta = tmp_path / f'{clave}.txt'
        ruta.write_text(texto, encoding='utf-8')
        evidencia[clave] = {'archivo': str(ruta), 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest(),
                            'proyecto': 'P1', 'fuente': 'abc', 'localizador': 'texto', 'fragmento': texto}
    return contexto, evidencia


def _c(campo, propuesta, evidencia, fuente, base=None):
    dato = {'campo': campo, 'valor_propuesta': propuesta, 'valor_evidencia': evidencia, 'fuente': fuente}
    return {**dato, 'base': base} if base else dato


def _dictamen(tmp_path, contradicciones, propuesta=PROPUESTA, fragmentos=FRAGMENTOS):
    contexto, evidencia = _paquete(tmp_path, fragmentos)
    dictamen = {'decision': 'bloqueada', 'evidencia_ids': sorted(evidencia), 'incertidumbres': [],
                'contradicciones': contradicciones}
    r = revisar_propuesta(propuesta, evidencia, contexto=contexto, max_rondas=1, roles=('unico',),
                          revisor=lambda *_a: json.loads(json.dumps(dictamen)))
    return r, r['dictamenes'][0]


def _motivos(d):
    return [x['motivo'] for x in d.get('contradicciones_descartadas', [])]


@pytest.mark.parametrize('a, b', [
    ('>$14500', '14 500 USD'), ('_3_', '3'), ('/^3$/i', '3'), ('$12.400', '12 400 USD'), ('>$12,400', '12 400 USD'),
    ('Cargabilidad máxima de A71 74 %', '74 %'), ('≈62', '62%'), ('k340', '340'), ('12 400', '12400'),
    ('f.p. 0,98', 'factor de potencia en cabecera 0,98'), ('9 × 210', '1890'), ('2,5 x 12 600', '31500'),
])
def test_cifras_con_marcas_prefijos_o_dentro_de_una_frase_se_leen(a, b):
    """047:RF-52 — «>$14500» es 14 500 USD, «_3_» es 3 y «Cargabilidad máxima de A71 74 %» es 74 %."""
    assert revision_roles.valores_coinciden(a, b) and revision_roles.valores_coinciden(b, a)


@pytest.mark.parametrize('a, b', [
    ('54 kW antes y 42 kW después', '42 kW'), ('A71 74 %', 'A71 78 %'), ('9 × 210', '1260'), ('$12.400', '12 500 USD'),
])
def test_una_frase_con_varias_cifras_o_una_cifra_distinta_no_coincide(a, b):
    """047:RF-52 — conservador: con varias cifras no se elige una; otra cifra sigue siendo otra."""
    assert not revision_roles.valores_coinciden(a, b)


def test_lo_que_no_esta_en_la_propuesta_o_en_la_fuente_no_cuenta(tmp_path):
    """047:RF-53 — «user», «kOhm» o una cifra que la fuente no da no son contradicciones: se descartan con su motivo."""
    r, d = _dictamen(tmp_path, [_c('zz_campo', 'user', '1,25 MW', 'e1'), _c('tension_pu', '0,97', '0,91', 'e1'),
                                _c('demanda_kw', '1450', '1,25 MW', 'e9')])
    assert r['aprobada'], 'contradicciones sin fundamento siguen bloqueando'
    assert d['contradicciones'] == [] and d['decision'] == 'favorable' and d['decision_devuelta'] == 'bloqueada'
    motivos = _motivos(d)
    assert len(motivos) == 3 and all(m.startswith('no fundada') for m in motivos), motivos


def test_sin_texto_de_la_fuente_se_mantiene(tmp_path):
    """047:RF-53 — si la evidencia no trae su fragmento, el código no puede comprobarla: la contradicción queda."""
    contexto, evidencia = _paquete(tmp_path)
    for registro in evidencia.values():
        registro.pop('fragmento')
    real = _c('tension_pu', '0,97', '0,91', 'e1')
    dictamen = {'decision': 'bloqueada', 'evidencia_ids': ['e1'], 'incertidumbres': [], 'contradicciones': [real]}
    r = revisar_propuesta(PROPUESTA, evidencia, contexto=contexto, max_rondas=1, roles=('unico',),
                          revisor=lambda *_a: json.loads(json.dumps(dictamen)))
    assert not r['aprobada'] and r['dictamenes'][0]['contradicciones'] == [real]


def test_el_valor_de_un_campo_de_la_propuesta_lo_pone_el_codigo(tmp_path):
    """047:RF-54 — el modelo escribía «Shekels» o «N/A» como valor de la propuesta: si el campo es suyo, vale el suyo."""
    r, d = _dictamen(tmp_path, [_c('demanda_kw', 'Shekels', '1,25 MW', 'e1'), _c('aisladores', 'N/A', '4', 'e3')])
    assert not r['aprobada'], 'una contradicción real con el valor de la propuesta mal copiado se pierde'
    assert d['contradicciones'] == [{**_c('demanda_kw', 1450, '1,25 MW', 'e1'), 'valor_propuesta_devuelto': 'Shekels'}]
    assert _motivos(d) and _motivos(d)[0].startswith('valores iguales')


def test_un_total_no_se_compara_con_un_precio_por_unidad(tmp_path):
    """047:RF-55 / RF-76 — «520» frente a «130 USD por unidad» no se compara tal cual: con los 4 aisladores anclados en
    la propuesta es 520 (MEJ24d convierte en vez de descartar); la cuenta del total también se compara."""
    r, d = _dictamen(tmp_path, [_c('coste_usd', '520', '130', 'e2')])
    assert r['aprobada'] and _motivos(d)[0].startswith('valores iguales tras convertir')
    r, d = _dictamen(tmp_path, [_c('coste_usd', '520', '4 × 130', 'e2', 'total')])
    assert r['aprobada'] and _motivos(d)[0].startswith('valores iguales')
    r, d = _dictamen(tmp_path, [_c('coste_usd', '520', '5 × 130', 'e2', 'total')])
    assert r['aprobada'] and _motivos(d)[0].startswith('no fundada'), 'una cantidad que no está en ningún sitio cuenta'
    r, d = _dictamen(tmp_path, [_c('coste_usd', '520', '4 × 130', 'e2')], propuesta={**PROPUESTA, 'coste_usd': 390})
    assert not r['aprobada'] and d['contradicciones'][0]['valor_evidencia'] == '4 × 130'


def test_la_base_la_dice_la_fuente_no_el_modelo(tmp_path):
    """047:RF-55 / RF-76 — el esquema pide la base, pero solo se guarda: en la T8e el modelo declaraba «unidad» en
    «0,92 p.u.» o «124 %» y eso descartaba defectos reales. Cuenta la marca del texto («por unidad», «c/u», «/km»)."""
    items = revision_roles.esquema_dictamen()['properties']['contradicciones']['items']
    assert items['properties'].get('base') == {'enum': ['total', 'unidad']} and 'base' in items['required']
    r, d = _dictamen(tmp_path, [_c('tension_pu', '0,97', '0,97 p.u.', 'e1', 'unidad')])
    assert r['aprobada'] and _motivos(d)[0].startswith('valores iguales')
    fragmentos = {**FRAGMENTOS, 'e1': 'Medición del vano V18: demanda máxima 1,25 MW; tensión mínima 0,91 p.u.'}
    r, d = _dictamen(tmp_path, [_c('tension_pu', '0,97', '0,91', 'e1', 'unidad')], fragmentos=fragmentos)
    assert not r['aprobada'] and d['contradicciones'], 'la base que declara el modelo descarta un defecto real'


def test_el_texto_de_la_accion_no_es_una_contradiccion(tmp_path):
    """047:RF-56 — la acción frente a una frase de la evidencia no es un dato; una cifra suya distinta, sí."""
    r, d = _dictamen(tmp_path, [_c('accion', PROPUESTA['accion'], FRAGMENTOS['e3'], 'e3')])
    assert r['aprobada'] and _motivos(d)[0].startswith('la acción no es un dato')
    r, d = _dictamen(tmp_path, [_c('accion', '450 kvar', '300 kvar', 'e3')])
    assert not r['aprobada'] and d['contradicciones'] == [_c('accion', '450 kvar', '300 kvar', 'e3')]


def test_el_encargo_pide_la_base_y_la_cuenta_del_total(tmp_path):
    """047:RF-55 — cada rol recibe que compare el mismo concepto y escriba la cuenta del total."""
    contexto, evidencia = _paquete(tmp_path)
    peticiones = []
    revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1, roles=('unico',),
                      revisor=revision_roles.revisor_ollama(_cliente(_dictamen_llm(
                          {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                           'contradicciones': []}), peticiones)))
    sistema = peticiones[0][1]['messages'][0]['content']
    assert 'base (total o unidad)' in sistema and 'cantidad × precio' in sistema
    assert 'copiado de la propuesta' in sistema and 'copiado de la fuente' in sistema
