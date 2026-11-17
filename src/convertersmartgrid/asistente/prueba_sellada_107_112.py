"""La prueba sellada de las tareas de las specs 107 a 112 (070:RF-85, T21): mide lo que las dos anteriores no miden.

Por qué existe: la 070 y la 079 conservan su huella y dejan fuera las tareas de la nube, el correo, el PIT, el VAD, el plano y
el benchmark (070:RF-85). Sin una prueba propia, ningún modelo que las aprenda podría medirse en ellas.

Método declarado: un solo autor, Claude, la escribió de una vez el 2026-11-16, en una sola pasada y sin mirar ningún modelo,
seis frases por cada una de esas tareas, sin abrir ``prueba_sellada.py``, ``prueba_sellada_079.py`` ni sus filas, y con otra
redacción que la de ``curriculo_maestro`` y ``propuestas_maestro``. Su huella se fijó antes de entrenar o medir nada con ella.
Cada frase se expande con ``expandir``, con la semilla de la tarea y del lugar de la frase y un vocabulario propio e inventado.

Lo que no garantiza: el autor es el mismo del currículo de esas tareas; es optimista frente a otro redactor y no sustituye a las
órdenes confirmadas por el operador. Se mide junto con la 079 y no decide hasta que el reentrenamiento (T22) la incorpore. Si
se ajusta tras medir, deja de valer: ``HUELLA`` lo delata.
"""
from __future__ import annotations

import random

from ..evaluacion_modelos import huella, texto_canonico
from .sinteticos import expandir
from .tareas import TAREAS_107_112

POR_FRASE = 8
RUIDO = .06
SEMILLA = 10712
CONJUNTO = 'sellada_107_112'
#: 070:RF-85: la huella de las filas; se fijó antes de medir nada con ellas.
HUELLA = '8de089d3e87366bf'
#: Propio e inventado, para que la prueba no dependa del espacio ni de ninguna empresa (P13).
VOCABULARIO = {'alimentadores': ('RB501', 'RB602', 'MK703', 'MK804'),
               'proyecto': ('Ensayo Oriente 3', 'MK703_MK804', 'Variante Centro'),
               'ruta': ('G:/estudios/informe_entrega.docx', 'G:/insumos/red_area.xlsx', 'H:\\casos\\vad_rural')}

FRASES: dict[str, tuple[str, ...]] = {
    'enviar_informe': ('hazle llegar por correo el informe al ingeniero', 'quiero que el informe salga por mail hoy',
                       'mandame un correo con el informe {ruta}', 'el informe tiene que irse por email al cliente',
                       'despacha por correo el ultimo informe', 'adjunta el informe en un correo y prepáralo'),
    'publicar_nube': ('deja la carpeta de resultados en el drive del area', 'sube a onedrive lo que salio del estudio',
                      'necesito la salida {ruta} en la nube', 'pon el expediente en google drive para el equipo',
                      'publica en el drive la carpeta de salidas', 'carga a la nube los entregables del estudio'),
    'compartir_nube': ('dale lectura del expediente al revisor externo', 'comparte con osinergmin lo que subimos',
                       'que el consultor pueda ver lo publicado', 'comparte el expediente de la nube con el jefe',
                       'abre el acceso al expediente publicado', 'comparte solo lectura lo que esta en drive'),
    'importar_nube': ('baja del drive el libro de demanda', 'trae desde onedrive la red del area',
                      'jala de la nube el archivo de clientes', 'importa de google drive el excel de cargas',
                      'quiero usar un archivo que esta en mi drive', 'carga el libro que tengo en la nube'),
    'conectar_nube': ('enlaza la cuenta de google del area', 'quiero vincular mi correo de outlook',
                      'conecta la cuenta corporativa de microsoft', 'registra mi google drive en el conversor',
                      'vincula la cuenta de gmail para mandar informes', 'conecta onedrive para subir expedientes'),
    'pit_diagnostico': ('revisa el area de demanda del plan de inversiones con {ruta}', 'diagnostico de transmision del pit',
                        'evalua año a año la red del pit con {ruta}', 'como esta el area del plan de inversiones',
                        'corre el diagnostico de la red de transmision del pit', 'diagnostica el area con el libro {ruta}'),
    'pit_expediente': ('genera el expediente del plan de inversiones del periodo', 'quiero los formatos del pit con {ruta}',
                       'arma la presentacion del pit a osinergmin', 'expediente pit del area con {ruta}',
                       'prepara el expediente del plan de inversiones', 'saca el expediente del pit de este periodo'),
    'vad_crear_estudio': ('empieza el estudio del vad del grupo 3', 'abre un estudio vad nuevo para la empresa',
                          'registra un estudio de costos del vad del periodo', 'quiero un estudio vad del grupo 2',
                          'da de alta el estudio del valor agregado', 'nuevo estudio de costos vad de la empresa'),
    'vad_empresa_modelo': ('dimensiona la empresa modelo eficiente con {ruta}', 'corre la empresa modelo del vad',
                           'arma la empresa modelo sistema por sistema', 'empresa modelo del estudio con el caso {ruta}',
                           'calcula la empresa modelo con {ruta}', 'construye la empresa modelo eficiente'),
    'plano_maniobra': ('en el plano deja abierto el seccionador de {alimentadores}', 'prueba cerrando el interruptor de {alimentadores}',
                       'abre la cuchilla de {alimentadores} en una variacion', 'que pasa si abro el reconectador de {alimentadores}',
                       'cierra el seccionador de {alimentadores} y mira el resultado', 'abre en el plano la maniobra de {alimentadores}'),
    'benchmark_anonimo': ('saca un benchmark de la red sin datos reales', 'genera un benchmark para comparar metodos',
                          'anonimiza la red cargada para publicarla', 'quiero un dataset anonimizado de esta red',
                          'prepara un benchmark reproducible', 'benchmark anonimo de la red del espacio'),
}


def filas() -> list[dict]:
    """Las filas de la prueba, sin comprobar su huella: las mismas con cualquier espacio."""
    if set(FRASES) != set(TAREAS_107_112):
        raise ValueError('la prueba sellada de las specs 107 a 112 no cubre exactamente sus tareas')
    salida, vistos = [], {}
    for tarea in sorted(FRASES):
        for j, plantilla in enumerate(FRASES[tarea]):
            rnd = random.Random(SEMILLA + j + int(huella(tarea)[:8], 16))
            grupo = huella({CONJUNTO: plantilla, 'tarea': tarea})
            for _ in range(POR_FRASE):
                e = expandir(plantilla, tarea, rnd, VOCABULARIO, ruido=RUIDO)
                clave = texto_canonico(e.texto)
                if clave in vistos:
                    if vistos[clave] != tarea:
                        raise ValueError('la prueba sellada da un mismo texto a dos tareas')
                    continue
                vistos[clave] = tarea
                r = {'texto': e.texto, 'tarea': tarea, 'datos': [list(d) for d in sorted(e.datos)], 'group_id': grupo,
                     'particion': 'prueba', 'quality': 'silver_teacher_verified', 'del_maestro': True, 'conjunto': CONJUNTO}
                r['record_id'] = huella(r)
                salida.append(r)
    return sorted(salida, key=lambda r: r['record_id'])


def huella_de(registros: list[dict]) -> str:
    return huella(sorted(r['record_id'] for r in registros))[:16]


def selladas() -> list[dict]:
    """Las filas comprobadas: si alguien tocó una frase, se rechaza por la huella."""
    registros = filas()
    if huella_de(registros) != HUELLA:
        raise ValueError(f'la huella de {CONJUNTO} no coincide: las frases o su expansión cambiaron')
    return registros
