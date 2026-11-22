"""047:RF-75 a RF-78 — cuentas evaluadas por el código, precios por unidad pasados a total y coste comprobado sin LLM.

La medida T8e (2026-11-21) dio 0 falsas alarmas pero perdió 3 de 6 (rol único) y 2 de 6 (equipo): lo que el modelo sí
vio acababa descartado («14 × 52 = 728» con la fuente de la cantidad y no la del precio, «21 000 USD/km» como «bases
distintas», una base «unidad» declarada en «0,92 p.u.»). Aquí no hay LLM: dobles y valores sintéticos.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.aplicacion.asistente import contradicciones, revision_roles
from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision, revisar_propuesta
from test_asistente_revision_roles import _cliente, _dictamen_llm

PROPUESTA = {'accion': 'instalar 8 separadores en el vano V31 y tender 1,5 km de cable de guarda', 'separadores': 8,
             'coste_usd': 7040, 'restricciones_deterministas': {'plan_completo': True}}
FRAGMENTOS = {'e1': 'El vano V31 necesita 8 separadores de fase.',
              'e2': 'Separador de fase instalado: 80 USD por unidad.',
              'e3': 'Cable de guarda tendido: 4 000 USD/km.'}
FAVORABLE = {'decision': 'favorable', 'incertidumbres': [], 'contradicciones': []}


def _paquete(tmp_path, fragmentos):
    contexto = SimpleNamespace(project='P1', source_fingerprint='abc')
    evidencia = {}
    for clave, texto in fragmentos.items():
        ruta = tmp_path / f'{clave}.txt'
        ruta.write_text(texto, encoding='utf-8')
        evidencia[clave] = {'archivo': str(ruta), 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest(),
                            'proyecto': 'P1', 'fuente': 'abc', 'localizador': 'texto', 'fragmento': texto}
    return contexto, evidencia


def _revisar(tmp_path, contradicciones_llm=(), propuesta=PROPUESTA, fragmentos=FRAGMENTOS):
    contexto, evidencia = _paquete(tmp_path, fragmentos)
    dictamen = {'decision': 'bloqueada' if contradicciones_llm else 'favorable', 'evidencia_ids': sorted(evidencia),
                'incertidumbres': [], 'contradicciones': list(contradicciones_llm)}
    r = revisar_propuesta(propuesta, evidencia, contexto=contexto, max_rondas=1, roles=('unico',),
                          revisor=lambda *_a: json.loads(json.dumps(dictamen)))
    return r, r['dictamenes'][0]


def _c(campo, propuesta, evidencia, fuente):
    return {'campo': campo, 'valor_propuesta': propuesta, 'valor_evidencia': evidencia, 'fuente': fuente,
            'base': 'total'}


def _comprobar(propuesta, evidencia):
    funcion = getattr(revision_roles, 'comprobar_coste', None)
    assert funcion is not None, 'el código no comprueba el coste de la propuesta sin el LLM'
    return funcion(propuesta, evidencia)


def _evaluar(texto):
    funcion = getattr(revision_roles, 'evaluar_cuenta', None)
    assert funcion is not None, 'el código no evalúa cuentas con + − × / y paréntesis'
    return funcion(texto)


@pytest.mark.parametrize('texto, resultado', [
    ('14 × 52', 728), ('14 × $52 = $728', 728), ('(2 + 3) × 4', 20), ('2,5 x 12 600', 31500), ('10 / 4', 2.5),
    ('100 − 20 - 5', 75), ('8 · 80 + 1,5 × 4 000', 6640), ('-(3 + 2) × 2', -10),
])
def test_una_cuenta_simple_la_evalua_el_codigo(texto, resultado):
    """047:RF-75 — + − × · x / y paréntesis, con las cifras normalizadas."""
    lecturas, operandos = _evaluar(texto)
    assert lecturas == {resultado} and operandos


@pytest.mark.parametrize('texto', ['62 %', '7 × (', '3 / 0', '22,9/0,40 kV', '__import__("os")', '2 ** 10', 'x'])
def test_lo_que_no_es_una_cuenta_no_se_evalua(texto):
    """047:RF-75 — ni relaciones como «22,9/0,40 kV», ni división por cero, ni nada que no sea aritmética simple."""
    assert _evaluar(texto) is None


def test_el_analizador_no_usa_eval():
    """047:RF-75 — un analizador propio: el módulo no llama a ``eval``, ``exec`` ni ``compile``."""
    arbol = ast.parse(Path(contradicciones.__file__).read_text(encoding='utf-8'))
    llamadas = {n.func.id for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not llamadas & {'eval', 'exec', 'compile'}


def test_cada_operando_esta_en_las_fuentes_citadas(tmp_path):
    """047:RF-75 / RF-78 — «8 × 80» con «e1 e2» cuenta; si el precio no está en la fuente citada, no es fundada."""
    propuesta = {**PROPUESTA, 'coste_usd': 640, 'accion': 'instalar 8 separadores en el vano V31'}
    fragmentos = {k: FRAGMENTOS[k] for k in ('e1', 'e2')}
    r, d = _revisar(tmp_path, [_c('coste_usd', '600', '8 × 80', 'e1 e2')], propuesta={**propuesta, 'coste_usd': 600},
                    fragmentos=fragmentos)
    assert not r['aprobada'] and d['contradicciones'], 'una cuenta con sus operandos en dos fuentes no cuenta'
    r, d = _revisar(tmp_path, [_c('coste_usd', '600', '8 × 75', 'e1')], propuesta={**propuesta, 'coste_usd': 600},
                    fragmentos=fragmentos)
    assert d['contradicciones'] == [] and d['contradicciones_descartadas'][0]['motivo'].startswith('no fundada')
    r, d = _revisar(tmp_path, [_c('coste_usd', '640', '8 × 80', 'e1 e9')], propuesta=propuesta, fragmentos=fragmentos)
    assert d['contradicciones_descartadas'][0]['motivo'].startswith('no fundada')


def test_un_precio_por_unidad_o_por_km_se_pasa_a_total(tmp_path):
    """047:RF-76 — con la cantidad anclada (campo o acción) se multiplica y se compara, en vez de descartar."""
    fragmentos = {k: FRAGMENTOS[k] for k in ('e1', 'e2')}
    propuesta = {**PROPUESTA, 'accion': 'instalar 8 separadores en el vano V31', 'coste_usd': 500}
    r, d = _revisar(tmp_path, [_c('coste_usd', '500', '80', 'e2')], propuesta=propuesta, fragmentos=fragmentos)
    assert not r['aprobada'] and d['contradicciones'][0]['valor_evidencia_total'] == 640
    propuesta = {'accion': 'tender 1,5 km de cable de guarda en el vano V31', 'coste_usd': 5000,
                 'restricciones_deterministas': {'plan_completo': True}}
    r, d = _revisar(tmp_path, [_c('coste_usd', '5000', '4 000 USD/km', 'e3')], propuesta=propuesta,
                    fragmentos={'e3': FRAGMENTOS['e3']})
    assert d['contradicciones'] and d['contradicciones'][0]['valor_evidencia_total'] == 6000
    r, d = _revisar(tmp_path, [_c('coste_usd', '6000', '4 000 USD/km', 'e3')], propuesta={**propuesta, 'coste_usd': 6000},
                    fragmentos={'e3': FRAGMENTOS['e3']})
    assert r['aprobada'] and d['contradicciones_descartadas'][0]['motivo'].startswith('valores iguales tras convertir')
    sin_cantidad = {'accion': 'tender cable de guarda en el vano V31', 'coste_usd': 5000,
                    'restricciones_deterministas': {'plan_completo': True}}
    r, d = _revisar(tmp_path, [_c('coste_usd', '5000', '4 000 USD/km', 'e3')], propuesta=sin_cantidad,
                    fragmentos={'e3': FRAGMENTOS['e3']})
    assert d['contradicciones_descartadas'][0]['motivo'].startswith('bases distintas')


def test_el_coste_lo_comprueba_el_codigo_sin_el_llm(tmp_path):
    """047:RF-77 — 8 × 80 + 1,5 × 4 000 = 6 640: con 7 040 en la propuesta, ni un LLM favorable la aprueba."""
    r, _d = _revisar(tmp_path)
    assert not r['aprobada'], 'un coste que no cuadra con la evidencia se aprueba si el LLM no lo ve'
    comprobacion = r['comprobaciones_del_codigo'][0]
    assert comprobacion['coincide'] is False and comprobacion['valor_calculado'] == 6640
    assert comprobacion['origen'] == 'codigo' and '8 × 80' in comprobacion['calculo'] and '1.5 × 4 000' in comprobacion['calculo']
    assert 'no cuadra' in r['motivo']
    r, _d = _revisar(tmp_path, propuesta={**PROPUESTA, 'coste_usd': 6640})
    assert r['aprobada'] and r['comprobaciones_del_codigo'][0]['coincide']


@pytest.mark.parametrize('fragmentos, coste, cuadra', [
    ({'e1': 'Partidas: postes 1 200 USD; montaje 300 USD.'}, 1500, True),
    ({'e1': 'Partidas: postes 1 200 USD; montaje 300 USD.'}, 1200, False),
    ({'e1': 'Separador: 80 USD c/u; para 8 unidades, 640 USD.'}, 640, True),
    ({'e1': 'Separador: 80 USD c/u, 640 USD en total.'}, 600, False),
])
def test_partidas_y_totales_de_la_evidencia(tmp_path, fragmentos, coste, cuadra):
    """047:RF-77 — la suma de las partidas, o el importe que ya es su total, o el total explícito."""
    propuesta = {'accion': 'instalar 8 separadores', 'separadores': 8, 'coste_usd': coste}
    resultado = _comprobar(propuesta, {k: {'fragmento': v} for k, v in fragmentos.items()})
    assert resultado and resultado[0]['coincide'] is cuadra


@pytest.mark.parametrize('propuesta, fragmentos', [
    ({'accion': 'instalar separadores', 'coste_usd': 640}, {'e1': 'Separador: 80 USD por unidad.'}),
    ({'accion': 'instalar 8 separadores'}, {'e1': 'Separador: 80 USD por unidad.'}),
    ({'accion': 'instalar 8 separadores', 'coste_usd': 640}, {'e1': '640 USD en total.', 'e2': '700 USD en total.'}),
    ({'accion': 'instalar 8 separadores', 'coste_usd': 640}, {'e1': 'El vano necesita 8 separadores.'}),
])
def test_sin_datos_estructurados_no_comprueba_nada(propuesta, fragmentos):
    """047:RF-77 — sin cantidad anclada, sin coste, con dos totales o sin importes, el código no inventa la cuenta."""
    assert _comprobar(propuesta, {k: {'fragmento': v} for k, v in fragmentos.items()}) == []


def test_el_informe_cuenta_las_comprobaciones_que_fallan(tmp_path):
    """047:RF-77 — la medida dice por caso qué calculó el código y, por modo, cuántas no cuadran."""
    contexto, evidencia = _paquete(tmp_path, FRAGMENTOS)
    casos = [{'id': 'x1', 'defecto': 'coste', 'contexto': contexto, 'evidencia': evidencia, 'propuesta': PROPUESTA}]
    r = comparar_revision(casos, lambda medir: (lambda rol, p, ev, ctx, ronda: {**FAVORABLE,
                                                'evidencia_ids': sorted(ev)}), rondas=1)
    for modo in ('rol_unico', 'equipo'):
        assert r[modo].get('comprobaciones_fallidas') == 1 and r[modo]['detectados'] == 1
        assert r[modo]['por_caso'][0]['comprobaciones_del_codigo'][0]['valor_calculado'] == 6640


def test_el_encargo_admite_varias_fuentes_para_una_cuenta(tmp_path):
    """047:RF-78 — el rol sabe que una cuenta puede citar los IDs de las dos fuentes de sus cifras."""
    contexto, evidencia = _paquete(tmp_path, FRAGMENTOS)
    peticiones = []
    revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1, roles=('unico',),
                      revisor=revision_roles.revisor_ollama(_cliente(_dictamen_llm(
                          {**FAVORABLE, 'evidencia_ids': ['e1']}), peticiones)))
    assert 'los IDs de las fuentes de sus cifras' in peticiones[0][1]['messages'][0]['content']
