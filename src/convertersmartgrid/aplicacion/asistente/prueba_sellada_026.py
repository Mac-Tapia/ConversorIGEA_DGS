"""La prueba sellada de las tareas de la spec 026 posteriores a la 107-112 (026:RF-44, RF-46): el Estudio VNR, la
evolución de clientes fijos y las tres órdenes de la biblioteca normativa.

Por qué existe: las selladas de la 070, la 079 y la 107-112 conservan su huella y dejan fuera estas tareas
(``tareas.TAREAS_SIN_SELLADA_070_079``), con el mismo criterio que la 070:RF-85. Sin una prueba propia, ningún modelo que
las aprenda podría medirse en ellas.

Método declarado: un solo autor, Claude, la escribió de una vez el 2026-11-18, en una sola pasada y sin mirar ningún
modelo, seis frases por cada una de esas tareas, con otra redacción que la de ``curriculo_maestro``,
``propuestas_maestro`` y las plantillas del catálogo. Su huella se fijó antes de entrenar o medir nada con ella. Cada
frase se expande con ``expandir``, con la semilla de la tarea y del lugar de la frase y un vocabulario propio e inventado.
``fuga_evaluacion.fugas_de_las_selladas`` comprueba que ninguna de sus frases esté en lo que entrena.

Lo que no garantiza: el autor es el mismo del currículo de esas tareas; es optimista frente a otro redactor y no sustituye
a las órdenes confirmadas por el operador. Si se ajusta tras medir, deja de valer: ``HUELLA`` lo delata.
"""
from __future__ import annotations

import random

from ..evaluacion_modelos import huella, texto_canonico
from .sinteticos import expandir
from .tareas import TAREAS_026, TAREAS_026_CONTROL

POR_FRASE = 8
RUIDO = .06
SEMILLA = 2026
CONJUNTO = 'sellada_026'
#: 026:RF-44, RF-46: la huella de las filas; se fijó antes de medir nada con ellas.
HUELLA = '76e901845e43937d'
#: Propio e inventado, para que la prueba no dependa del espacio ni de ninguna empresa (P13).
VOCABULARIO = {'alimentadores': ('QT110', 'QT220', 'ZN330', 'ZN440'),
               'ruta': ('G:/biblioteca/rcd_041_2027.json', 'H:\\normas\\modificatoria_0907.json',
                        'G:/normas/nueva_tarifa_2028.json')}

FRASES: dict[str, tuple[str, ...]] = {
    'vnr_estudio': ('necesito el vnr de esta red con el sicodi que cargue', 'cuanto vale reponer la red segun la guia 232',
                    'estimame el valor nuevo de reemplazo con la resolucion vigente',
                    'saca el vnr del sector urbano con el sicodi de la empresa',
                    'quiero la valorizacion vnr de las instalaciones en dolares',
                    'pasa la red por el calculo del vnr de osinergmin'),
    'clientes_fijos_evolucion': ('como fueron cambiando los fijos de {alimentadores} en estos meses',
                                 'grafica la serie mensual de clientes fijos de {alimentadores}',
                                 'quiero ver mes por mes los suministros fijos de {alimentadores}',
                                 'tendencia de los fijos de {alimentadores} durante el periodo',
                                 'dame la evolucion mensual de fijos en {alimentadores} sin la cabecera',
                                 'compara mes a mes los clientes fijos que tiene {alimentadores}'),
    'normativa_comprobar': ('las fuentes oficiales de las normas siguen intactas',
                            'chequea que los libros oficiales de la biblioteca no se hayan alterado',
                            'mira si alguna norma de la biblioteca perdio su fuente',
                            'dime que normas estan en vigor y si sus fuentes cuadran',
                            'haz una revision de la huella de cada fuente normativa',
                            'controla la biblioteca de normas contra sus sumas'),
    'normativa_agregar': ('mete en la biblioteca la norma que esta en {ruta}',
                          'registra la resolucion nueva del archivo {ruta}',
                          'carga a la capa del usuario la norma {ruta}',
                          'suma esta norma a la biblioteca desde {ruta}',
                          'quiero que la biblioteca tenga la norma de {ruta}',
                          'pon la modificatoria {ruta} en la biblioteca normativa'),
    'normativa_regenerar': ('vuelve a generar el registro del coes con la fuente descargada',
                            'reconstruye el registro de la guia del vnr desde el pdf oficial',
                            'rearma desde sus libros oficiales el registro de los formatos 217',
                            'genera otra vez el registro de las reconsideraciones del vad',
                            'refresca el registro de la guia 232 y dime que cambia',
                            'recalcula el registro del coes y ensename lo que entra y sale'),
}


def _filas(frases: dict[str, tuple[str, ...]], tareas: frozenset[str], conjunto: str) -> list[dict]:
    if set(frases) != set(tareas):
        raise ValueError(f'la prueba sellada {conjunto} no cubre exactamente sus tareas')
    salida, vistos = [], {}
    for tarea in sorted(frases):
        for j, plantilla in enumerate(frases[tarea]):
            rnd = random.Random(SEMILLA + j + int(huella(tarea)[:8], 16))
            grupo = huella({conjunto: plantilla, 'tarea': tarea})
            for _ in range(POR_FRASE):
                e = expandir(plantilla, tarea, rnd, VOCABULARIO, ruido=RUIDO)
                clave = texto_canonico(e.texto)
                if clave in vistos:
                    if vistos[clave] != tarea:
                        raise ValueError('la prueba sellada da un mismo texto a dos tareas')
                    continue
                vistos[clave] = tarea
                r = {'texto': e.texto, 'tarea': tarea, 'datos': [list(d) for d in sorted(e.datos)], 'group_id': grupo,
                     'particion': 'prueba', 'quality': 'silver_teacher_verified', 'del_maestro': True, 'conjunto': conjunto}
                r['record_id'] = huella(r)
                salida.append(r)
    return sorted(salida, key=lambda r: r['record_id'])


def filas() -> list[dict]:
    """Las filas de la prueba, sin comprobar su huella: las mismas con cualquier espacio."""
    return _filas(FRASES, TAREAS_026, CONJUNTO)


def huella_de(registros: list[dict]) -> str:
    return huella(sorted(r['record_id'] for r in registros))[:16]


def selladas() -> list[dict]:
    """Las filas comprobadas: si alguien tocó una frase, se rechaza por la huella."""
    registros = filas()
    if huella_de(registros) != HUELLA:
        raise ValueError(f'la huella de {CONJUNTO} no coincide: las frases o su expansión cambiaron')
    return registros


# --- 026:RF-42 y RF-43: repetir el último trabajo que falló y las órdenes de las entradas ---------------------------
#
# Método declarado: el mismo autor, Claude, las escribió de una vez el 2026-11-19, en una sola pasada y sin mirar ningún
# modelo, seis por tarea, con otra redacción que la de ``curriculo_maestro``, ``propuestas_maestro`` y las plantillas del
# catálogo; su huella se fijó antes de entrenar o medir nada con ellas. Van en su propio conjunto para que la sellada de
# arriba conserve la suya. Lo que no garantiza, lo mismo que la de arriba.
CONJUNTO_CONTROL = 'sellada_026_control'
#: 026:RF-42, RF-43: la huella de sus filas; se fijó antes de medir nada con ellas.
HUELLA_CONTROL = '54a19b36009d381b'
FRASES_CONTROL: dict[str, tuple[str, ...]] = {
    'repetir_trabajo': ('el trabajo de antes se cayo, mandalo de nuevo igual',
                        'otra vez lo mismo que no termino bien, con sus datos',
                        'relanza la tarea que quedo en error',
                        'insiste con lo ultimo que no salio',
                        'dale una segunda vuelta al que reviento',
                        'retoma el encargo que termino con fallo'),
    'asignar_entrada': ('quiero que la casilla de topologia tome {ruta}',
                        'la entrada de cargas debe ser {ruta}, asignala',
                        'asigna al espacio la base access {ruta}',
                        'el catalogo de conductores del espacio es {ruta}, asignalo a equipos',
                        'deja asignado {ruta} en la casilla del paquete gis',
                        'asigna este fichero de alias {ruta}'),
    'subir_fuente_empresa': ('el sicodi vigente esta en {ruta}, registralo para el 2026',
                             'quiero subir a los libros de la empresa la medicion {ruta} del 2025',
                             'registra para el 2024 las interrupciones que estan en {ruta}',
                             'sube como catalogo de la empresa el libro {ruta}',
                             'deja en las fuentes de la empresa la demanda {ruta} de 2023',
                             'registra el perfil de la empresa que esta en {ruta}'),
}


def filas_control() -> list[dict]:
    """026:RF-42, RF-43: las filas del conjunto de control, sin comprobar su huella."""
    return _filas(FRASES_CONTROL, TAREAS_026_CONTROL, CONJUNTO_CONTROL)


def selladas_control() -> list[dict]:
    """Las filas del conjunto de control, comprobadas por su huella."""
    registros = filas_control()
    if huella_de(registros) != HUELLA_CONTROL:
        raise ValueError(f'la huella de {CONJUNTO_CONTROL} no coincide: las frases o su expansión cambiaron')
    return registros
