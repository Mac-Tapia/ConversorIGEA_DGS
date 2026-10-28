"""El conjunto fijo de 200 órdenes del asistente, escritas por el maestro (spec 027, RF-65 a RF-67).

El usuario, el 2026-10-28: «debería tener las 200 órdenes fijadas». El operador había dado 5
órdenes reales. Claude, como maestro (RF-56), escribe aquí 200 órdenes con la forma en que el
operador las pide en la web —frases cortas, sin tildes, con erratas— y no con las plantillas del
entrenamiento (``sinteticos``): son otras frases, para que medir con ellas diga algo. Los datos
(alimentadores, proyectos, sistemas) son los nombres reales del espacio y, a veces, inventados con
su forma, como en el entrenamiento (P13: aprende la forma, no una empresa). El conjunto es fijo:
la misma semilla da las mismas 200 órdenes, con su huella, y una de cada cinco va a la prueba.

No cuentan como órdenes del operador para RF-19: mientras él no confirme 200, todo lo que escribe
sigue pidiendo confirmación (RF-67).
"""
from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence

from .sinteticos import Ejemplo, expandir
from .tareas import TAREAS

TOTAL = 200
SEMILLA = 2026
#: Erratas leves, como en las órdenes reales («complata», «eletrico», «aliematdores»).
RUIDO = 0.06

#: Frases del maestro por tarea; ``{tipo}`` es un dato real y ``[a|b]`` una variante.
FRASES: dict[str, tuple[str, ...]] = {
    'estado': ('que tengo cargado ahora', 'estado del espacio', 'que alimentadores hay cargados',
               'muestrame lo que hay', 'como va el espacio de trabajo'),
    'proyectos': ('que proyectos hay en digsilent', 'lista los proyectos', 'cuales son mis proyectos de pf',
                  'que proyecto tengo importado'),
    'resultados_pide': ('dame los resultados del pide de {proyecto}', 'obras del pide de {proyecto}',
                        'que salio en el pide de {proyecto}', 'prioridades del pide {proyecto}'),
    'episodios': ('cuantos episodios tiene {proyecto}', 'dime los episodios del gemelo en {proyecto}',
                  'cuantos episodios hay en el gemelo'),
    'pregunta': ('como se calibra una barra de 60 kv', 'que hace el escaneo del alimentador',
                 'por que no converge el flujo', 'como se reparte la demanda en las escaladas',
                 'que es el caso base verificado', 'como funciona la recalibracion'),
    'clasificar_informe': ('clasifica este pedido {texto}', 'que tipo de estudio es {texto}',
                           'a que subtipo corresponde {texto}'),
    'buscar_internet': ('busca en internet {texto}', 'busca articulos de {texto}', 'busca en pypi {texto}',
                        'investiga {texto}'),
    'leer_proyectos': ('lee los proyectos de digsilent', 'actualiza la lista de proyectos de pf',
                       'vuelve a leer digsilent'),
    'evaluar_gemelo': ('evalua el gemelo', 'cuanto se aparta el gemelo de digsilent', 'mide el gemelo'),
    'cargar_fuente': ('carga los txt', 'lee la fuente', 'carga la red y las cargas', 'sube la fuente'),
    'convertir': ('pasa {alimentadores} a dgs', 'convierte el alimentador {alimentadores}',
                  'hazme el dgs de {alimentadores}', 'convierte {alimentadores} por favor'),
    'unir': ('une {alimentadores} en un solo dgs', 'red unida de {alimentadores}', 'junta {alimentadores}'),
    'convertir_sistema': ('convierte todo el sistema {sistema}', 'dgs por sistema de {sistema}',
                          'genera el dgs del sistema electrico {sistema}'),
    'sistema_completo': ('calibra todo {sistema} con las medidas de {periodo}', 'haz todo el sistema {sistema} de {periodo}',
                         'convierte importa y calibra {sistema} {periodo}', 'calibra {sistema} con la maxima de {periodo}'),
    'flujo': ('corre el flujo de {alimentadores}', 'saca el flujo de potencia de {alimentadores}',
              'importa {alimentadores} en digsilent y corre flujo'),
    'verificar_caso_base': ('valida el caso base de {proyecto}', 'comprueba el caso base {proyecto} {alimentadores}',
                            'revisa el caso base de {proyecto}'),
    'cargas_nuevas': ('integra las cargas nuevas de {ruta} en {proyecto}', 'mete las cargas nuevas {ruta} en {proyecto}',
                      'cargas nuevas de {ruta} para {alimentadores} en {proyecto}'),
    'obras': ('aplica las obras en {proyecto} {alimentadores}', 'pon las obras pendientes en {proyecto}',
              'mete las obras de {alimentadores} en {proyecto}'),
    'estudios': ('corre los estudios de {proyecto} {alimentadores}', 'haz los estudios de {alimentadores} en {proyecto}',
                 'estudios electricos de {proyecto}'),
    'transferencia': ('transfiere carga entre {alimentadores} en {proyecto}', 'transferencia de {alimentadores} en {proyecto}',
                      'pasa carga de {alimentadores} en {proyecto}'),
    'pide': ('haz el pide de {proyecto} {alimentadores}', 'corre la metodologia pide en {proyecto}',
             'plan de inversiones pide de {proyecto} para {alimentadores}'),
    'gemelo_aprender': ('que el gemelo aprenda de {proyecto} con {numero} escenarios',
                        'aprendizaje del gemelo en {proyecto} {alimentadores}', 'entrena escenarios del gemelo en {proyecto}'),
    'gemelo_entrenar': ('vuelve a entrenar la pinn con lo nuevo', 'entrena el gemelo otra vez', 'vuelve a entrenar el oraculo'),
    'gemelo_temporal': ('gemelo temporal de {alimentadores}', 'curva del mes de {alimentadores} con el gemelo',
                        'reproduce el mes con la gru'),
    'informe_estudio': ('haz el informe de estudio de {alimentadores} en {proyecto} de {subtipo}',
                        'informe de {subtipo} de {proyecto} {alimentadores}', 'redacta el estudio de {subtipo} de {alimentadores} en {proyecto}'),
    'informe_factibilidad': ('informe de factibilidad de {sed} en {proyecto} {alimentadores} de {subtipo}',
                             'factibilidad de la carga en {sed} de {alimentadores} en {proyecto}'),
    'entrenar_asistente': ('reentrena el asistente con lo confirmado', 'entrena el transformer de ordenes', 'que aprenda el asistente'),
}


def generar(vocab: Mapping[str, Sequence[str]] | None = None, *, total: int = TOTAL,
            semilla: int = SEMILLA) -> list[Ejemplo]:
    """Las ``total`` órdenes fijas, repartidas por igual entre las tareas (RF-65)."""
    faltan = sorted(set(TAREAS) - set(FRASES))
    if faltan:
        raise ValueError(f'tareas sin frases del maestro: {faltan}')
    rnd = random.Random(semilla)
    tareas = sorted(FRASES)
    out = []
    for i in range(total):
        tarea = tareas[i % len(tareas)]
        out.append(expandir(rnd.choice(FRASES[tarea]), tarea, rnd, vocab or {}, RUIDO))
    return out


def huella(ejemplos: Sequence[Ejemplo]) -> str:
    """La huella del conjunto: cambia si cambia una orden, su tarea o sus datos (RF-65)."""
    return hashlib.sha256(json.dumps([[e.texto, e.tarea, e.datos] for e in ejemplos],
                                     ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


def repartir(ejemplos: Sequence[Ejemplo]) -> tuple[list[Ejemplo], list[Ejemplo]]:
    """Una de cada cinco a la prueba fija; el resto, a entrenar (RF-66)."""
    entrenar, prueba = [], []
    for i, e in enumerate(ejemplos):
        (prueba if i % 5 == 4 else entrenar).append(e)
    return entrenar, prueba
