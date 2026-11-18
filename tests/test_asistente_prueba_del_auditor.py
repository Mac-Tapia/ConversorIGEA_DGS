"""Fallos de la prueba del auditor con 58 órdenes reales (2026-11-14), cada uno con su prueba permanente.

Los nombres de esta prueba son inventados y de ninguna empresa (P13); los casos son los de la batería:
F2 «todos» en el PIDE de un proyecto, F3 las coordenadas de una carga, F4 el corto plazo de punta a punta,
F5 una errata que se parece igual a dos alimentadores y F9 la frase literal con el modelo por debajo de su umbral.
"""
from __future__ import annotations

import random

import pytest

from convertersmartgrid.aplicacion.asistente import interprete, plan as modulo_plan
from convertersmartgrid.aplicacion.asistente.interprete import Interpretacion, interpretar
from convertersmartgrid.aplicacion.asistente.plan import parecido, resolver

SEMILLA = random.randrange(10**6)


def _codigos(rnd: random.Random, n: int) -> list[str]:
    return sorted({f'{rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")}{rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")}{rnd.randint(100, 399)}'
                   for _ in range(n)})


class Modelo:
    """El modelo de órdenes, sustituido: dice una tarea con la confianza que se le pida."""

    def __init__(self, tarea, confianza=1.0, umbral=0.95, **datos):
        self.tarea, self.confianza, self.umbral = tarea, confianza, umbral
        self.tareas = ('consultar_datos', 'evaluar_carga_nueva', 'pide', 'convertir', 'estudios', tarea)
        self.datos = {k: [{'valor': v} for v in (vs if isinstance(vs, list) else [vs])] for k, vs in datos.items()}

    def predecir(self, texto):
        return {'tarea': self.tarea, 'confianza': self.confianza, 'datos': self.datos}


def test_f2_todos_en_un_proyecto_son_los_del_proyecto():
    """026:RF-6 — «el pide de <proyecto> con todos los alimentadores» deja que la ruta tome los del proyecto; los de
    la fuente metían en el PIDE de un sistema los de toda la empresa. Sin proyecto, «todos» sigue siendo la fuente."""
    rnd = random.Random(f'{SEMILLA}-f2')
    fuente = _codigos(rnd, rnd.randint(5, 30))
    vocab = {'alimentadores': fuente, 'proyecto': ['Ensayo Alfa']}
    texto = 'haz el pide de Ensayo Alfa para 2027 con todos los alimentadores'
    plan = resolver(Interpretacion(texto, 'pide', 1.0, 'transformer',
                                   {'proyecto': [{'valor': 'Ensayo Alfa'}], 'alimentadores': [{'valor': 'todos'}]}), vocab)
    assert plan.datos['alimentadores'] == ['todos'], SEMILLA
    assert any('del proyecto Ensayo Alfa' in r for r in plan.razonamiento)
    from convertersmartgrid.aplicacion.asistente.ejecutor import pasos

    assert pasos('pide', plan.datos, {})[0].cuerpo['feeders'] == []      # la ruta toma los del vínculo del proyecto
    sin = resolver(Interpretacion('convierte todos los alimentadores', 'convertir', 1.0, 'transformer',
                                  {'alimentadores': [{'valor': 'todos'}]}), vocab)
    assert sin.datos['alimentadores'] == fuente


@pytest.mark.parametrize('lugar, esperado', [
    ('x 374207.83 y 8476517', {'x': '374207.83', 'y': '8476517'}),
    ('coordenadas 374207.83 8476517', {'x': '374207.83', 'y': '8476517'}),
    ('coordenadas utm x: 374207,83, y: 8476517', {'x': '374207,83', 'y': '8476517'}),
    ('lat -13.71 lon -76.20', {'lat': '-13.71', 'lon': '-76.20'})])
def test_f3_las_coordenadas_son_la_ubicacion(lugar, esperado):
    """070:RF-29 — «x … y …» o «coordenadas X Y» son la ubicación de la carga: ni una SED ni un alimentador."""
    texto = f'evalua la carga nueva de 800 kW en QX511 de Ensayo Alfa, {lugar}'
    assert interprete.ubicacion_de(texto) == esperado
    numeros = list(esperado.values())
    interp = Interpretacion(texto, 'evaluar_carga_nueva', 1.0, 'transformer',
                            {'proyecto': [{'valor': 'Ensayo Alfa'}], 'sed': [{'valor': numeros[0]}],
                             'alimentadores': [{'valor': 'QX511'}, {'valor': numeros[1]}]})
    plan = resolver(interp, {'alimentadores': ['QX511'], 'proyecto': ['Ensayo Alfa']})
    assert plan.datos.get('sed') not in numeros and plan.datos['alimentadores'] == ['QX511']
    assert not any(n in d for n in numeros for d in plan.dudas), plan.dudas


def test_f3_el_formulario_de_la_carga_lee_las_coordenadas():
    """070:RF-29 — la carga sola recibe «CoordX» y «CoordY» de «coordenadas X Y»; antes faltaba la ubicación."""
    from convertersmartgrid.aplicacion.asistente.plan import Plan
    from convertersmartgrid.presentacion.web.asistente_operacion import _datos_de_la_carga

    plan = Plan('p', 'conecta una carga nueva sola de 1500 kW con fp 0.98 en QX511, coordenadas 374207.83 8476517',
                'carga_nueva_sola', True, 'trabajo', datos={'alimentadores': ['QX511'], 'sed': 'MINERA'})
    extras: dict = {}
    _datos_de_la_carga(plan, extras)
    assert (extras['nueva']['CoordX'], extras['nueva']['CoordY']) == (374207.83, 8476517.0)
    assert not any('ubicación' in f for f in plan.faltan), plan.faltan


@pytest.mark.parametrize('orden', [
    'haz el estudio de corto plazo de QX511 de Ensayo Alfa con la carga nueva de 1200 kW',
    'quiero saber si entra una carga de 2 MW en el QX511 de Ensayo Alfa, de punta a punta hasta el informe',
    'haz el estudio de corto plazo del QX511'])
def test_f4_el_corto_plazo_de_punta_a_punta_se_entiende(orden):
    """070:RF-50 / 072:RF-29 — las órdenes 29, 30 y 57 de la batería, que el modelo en uso no reconocía, van a
    ``evaluar_carga_nueva`` aunque el modelo dude de ellas."""
    assert interpretar(orden, transformer=Modelo('estado', confianza=.16)).tarea == 'evaluar_carga_nueva'


def test_f5_una_errata_que_se_parece_igual_a_dos_se_pregunta():
    """026:RF-6 — «qx51» se parece igual a QX511 y QX512: el plan pregunta cuál y no elige ninguno."""
    rnd = random.Random(f'{SEMILLA}-f5')
    base = f'{rnd.choice("ABCDEFGH")}{rnd.choice("JKLMNPQR")}{rnd.randint(10, 39)}'
    gemelos = [f'{base}{d}' for d in rnd.sample('0123456789', 2)]
    vocab = {'alimentadores': sorted({*gemelos, *_codigos(rnd, 5)})}
    assert modulo_plan.empatados(base.lower(), vocab['alimentadores']) == sorted(gemelos)
    plan = resolver(Interpretacion(f'conviertme el {base.lower()} a dgs porfa', 'convertir', 1.0, 'transformer',
                                   {'alimentadores': [{'valor': base.lower()}]}), vocab)
    assert 'alimentadores' not in plan.datos, (plan.datos, SEMILLA)
    assert any('cuál' in f and all(g in f for g in gemelos) for f in plan.faltan), plan.faltan
    # Sin empate, la errata se sigue reconociendo.
    unico = gemelos[0]
    assert parecido(unico[:-1] + unico[-1], vocab['alimentadores']) == unico
    assert not modulo_plan.empatados(unico.lower(), vocab['alimentadores'])


@pytest.mark.parametrize('orden, tarea', [('cuantas sed tiene el QX511', 'consultar_datos'),
                                          ('que medidores hay en el espacio', 'consultar_datos')])
def test_f9_la_frase_literal_vale_con_el_modelo_por_debajo_de_su_umbral(orden, tarea):
    """067:RF-36 — con el modelo dudando (0,80), la frase literal del catálogo decide también en las tareas que el
    modelo conoce; con el modelo seguro de otra, manda el modelo."""
    assert interpretar(orden, transformer=Modelo(tarea, confianza=.80)).tarea == tarea
    assert interpretar(orden, transformer=Modelo('estado', confianza=.80)).tarea == tarea
    assert interpretar(orden, transformer=Modelo('estado', confianza=.99)).tarea == 'estado'


@pytest.mark.parametrize('orden, modelo', [('como se calcula la Q de las cargas fijas?', Modelo('pregunta', confianza=.92)),
                                           ('por que el caso base llega convergido a digsilent?', Modelo('estado', confianza=.67))])
def test_f7_una_pregunta_general_se_responde_aunque_el_modelo_dude(orden, modelo):
    """067:RF-36 — «¿cómo se …?» y «¿por qué …?» son preguntas cuando el modelo duda; con el modelo seguro de otra
    tarea, sigue siendo del modelo (070:RF-39)."""
    assert interpretar(orden, transformer=modelo).tarea == 'pregunta'
    assert interpretar(orden, transformer=Modelo('estado', confianza=.99)).tarea == 'estado'


@pytest.mark.parametrize('orden', ['borra el proyecto Ensayo Alfa de digsilent', 'elimina todos los espacios de trabajo'])
def test_f8_borrar_se_niega_sin_proponer_otras_tareas(orden):
    """084:RF-25 — borrar no es una orden del asistente: se dice, y no se ofrece «¿quiso decir …?»."""
    interp = Interpretacion(orden, None, .25, 'ninguno', {}, [('optimizar_con_proyecto', .25), ('cancelar_trabajo', .63)])
    plan = resolver(interp, {'proyecto': ['Ensayo Alfa']})
    assert plan.tarea is None and not plan.alternativas
    assert any('no borra' in f for f in plan.faltan) and not any('quiso decir' in f for f in plan.faltan)
