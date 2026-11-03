"""La prueba sellada de las órdenes desde la spec 070 (RF-69 a RF-71).

La anterior medía una sola paráfrasis por tarea, expandida: el candidato de la 069 aprendió a responderla y ya la
habíamos visto. Esta se generó así, y no se vuelve a tocar:

1. Quien la escribe redactó de una sola vez seis frases por tarea, sin mirar ningún modelo ni ninguna medida.
2. Solo se cambió una frase si coincidía con una familia que ya entrena, antes de calcular la huella.
3. Cada frase se expande ``POR_FRASE`` veces con ``sinteticos.expandir``, una semilla que sale de la frase y de su
   tarea, erratas de la misma proporción que las demás y el vocabulario de aquí: inventado y de ninguna empresa (P13).
4. ``HUELLA`` fija el resultado. Si cambia, cambió la prueba, y ``filas`` lo rechaza: no se ajusta nada mirándola.

Nada de esto entrena: sus familias quedan fuera de entrenamiento, selección y calibración (RF-71).
"""
from __future__ import annotations

import random

from ..evaluacion_modelos import huella, texto_canonico
from .sinteticos import expandir
from .tareas import TAREAS

POR_FRASE = 8
RUIDO = .06
#: La de ``filas``, fijada antes de entrenar ningún candidato (RF-70).
HUELLA = 'df5e1db88595d378'
CONJUNTO = 'sellada_070'

VOCABULARIO = {
    'alimentadores': ('QX511', 'RZ622', 'TW733', 'UV844'),
    'proyecto': ('Ensayo Alfa', 'Ensayo Beta', 'Ensayo Gamma'),
    'sistema': ('Meseta', 'Ribera', 'Altiplano'),
    'set': ('SET Quinua', 'SET Totora', 'SET Molle'),
    'sed': ('SX4411', 'SX5522', 'SX6633'),
    'ruta': ('D:/sellada/libro_uno.xlsx', 'D:/sellada/libro_dos.xlsx'),
    'subtipo': ('mejora de tensión', 'refuerzo de red', 'transferencia'),
    'texto': ('el reparto de la demanda', 'la verificacion de limites', 'la lectura de la red'),
}

FRASES: dict[str, tuple[str, ...]] = {
    'estado': ('a ver que tienes abierto', 'cuentame en que quedamos con los datos', 'pasame el panorama del espacio',
               'que tan avanzado esta lo mio', 'hay algo en marcha o ya acabo', 'cuanto llevamos procesado'),
    'proyectos': ('recuerdame los proyectos que manejas de pf', 'cuales proyectos de digsilent te sabes', 'nombrame los proyectos guardados',
                  'con que proyectos cuentas', 'pasa la relacion de proyectos que ya viste', 'enlistame lo importado en digsilent'),
    'resultados_pide': ('como salio el pide en {proyecto}', 'pasame lo que dejo el pide de {proyecto}', 'que inversiones arrojo el pide de {proyecto}',
                        'el orden de prioridad del pide de {proyecto} cual fue', 'quiero ver lo calculado por el pide en {proyecto}', 'alcanzame los formatos que dejo el pide de {proyecto}'),
    'episodios': ('cuanto ha guardado el gemelo sobre {proyecto}', 'con cuantos casos cuenta el gemelo para {proyecto}', 'pasame el conteo de episodios en {proyecto}',
                  'que experiencia acumula el gemelo de {proyecto}', 'cuantos episodios van', 'el gemelo que tiene almacenado de {proyecto}'),
    'pregunta': ('aclarame {texto}', 'no entiendo {texto}, como es', 'en palabras simples {texto}', 'de que trata {texto}',
                 'podrias explicar {texto}', 'quisiera saber sobre {texto}'),
    'clasificar_informe': ('en que categoria cae {texto}', 'a que clase de informe pertenece {texto}', 'ponle tipo a este pedido {texto}',
                           'como catalogarias {texto}', 'bajo que subtipo va {texto}', 'encasilla esta solicitud {texto}'),
    'buscar_internet': ('mira en la red que hay sobre {texto}', 'rastrea repositorios acerca de {texto}', 'quiero papers de {texto}',
                        'consulta afuera por {texto}', 'revisa en arxiv lo de {texto}', 'busca alguna biblioteca para {texto}'),
    'leer_proyectos': ('pregunta de nuevo a pf que proyectos tiene', 'relee los proyectos desde power factory', 'trae otra vez la lista desde digsilent',
                       'sincronizate con digsilent por los proyectos', 'vuelve a consultar a pf la lista', 'lee de nuevo que hay en pf'),
    'evaluar_gemelo': ('que tan lejos anda el gemelo de digsilent', 'pon a prueba la exactitud de la pinn', 'contrasta la pinn con el motor',
                       'dime si el gemelo ya predice bien', 'cuanto falla el modelo del gemelo', 'mide la precision del oraculo'),
    'cargar_fuente': ('abre la red que asigne', 'trae al espacio los archivos de entrada', 'levanta los datos de red asignados',
                      'empieza por leer la fuente', 'jalate los archivos de la red', 'pon en memoria la fuente del espacio'),
    'convertir': ('generame el archivo dgs de {alimentadores}', 'necesito en dgs a {alimentadores}', 'sacame {alimentadores} en formato dgs',
                  'quiero el dgs individual de {alimentadores}', 'exportame {alimentadores} como dgs', 'produce el dgs para {alimentadores}'),
    'unir': ('mete en un mismo dgs a {alimentadores}', 'que {alimentadores} queden en una sola red', 'fusiona {alimentadores} en un archivo',
             'arma una red comun con {alimentadores}', 'consolida {alimentadores} en un dgs', 'agrupa {alimentadores} como una sola red'),
    'convertir_sistema': ('necesito en dgs el sistema {sistema} entero', 'exportame el sistema {sistema}', 'sacame todo {sistema} en dgs',
                          'produce el dgs completo del sistema {sistema}', 'quiero {sistema} como un solo sistema en dgs', 'a dgs todo el sistema electrico {sistema}'),
    'sistema_completo': ('del sistema {sistema} encargate de todo con {periodo}', 'procesame el sistema {sistema} completo para {periodo}', 'deja calibrado el sistema {sistema} con {periodo}',
                         'de principio a fin el sistema {sistema} en {periodo}', 'el sistema {sistema} importado y calibrado con {periodo}', 'lleva hasta la calibracion el sistema {sistema} con {periodo}'),
    'flujo': ('resuelve el flujo de carga en {alimentadores}', 'quiero las tensiones de {alimentadores} en digsilent', 'mete {alimentadores} a power factory y corre flujo',
              'calcula flujo para {alimentadores}', 'pasa {alimentadores} por el flujo de potencia', 'simula la carga de {alimentadores} con flujo'),
    'verificar_caso_base': ('el caso base de {proyecto} esta bien', 'contrasta con el original el caso base de {proyecto}', 'pasale la verificacion al caso base de {proyecto}',
                            'asegura que el caso base de {proyecto} cuadre', 'audita el escenario original de {proyecto}', 'confirma el caso base del proyecto {proyecto}'),
    'cargas_nuevas': ('toma las nuevas de {ruta} y ponlas en {proyecto}', 'el libro {ruta} trae cargas nuevas para {proyecto}, integralas', 'de {ruta} saca las nuevas hacia {proyecto}',
                      'carga masiva de nuevas con {ruta} en {proyecto}', 'pasa a {proyecto} las nuevas del excel {ruta}', 'alta en bloque desde {ruta} en {proyecto}'),
    'obras': ('materializa las obras de {proyecto}', 'lleva a {proyecto} las obras que quedaron', 'pon en digsilent las obras pendientes de {proyecto}',
              'ejecuta en {proyecto} lo que hay de obras', 'dale curso a las obras de {alimentadores} en {proyecto}', 'construye las obras anotadas en {proyecto}'),
    'estudios': ('saca los estudios de la red {proyecto}', 'realiza el estudio de {estudio} en {alimentadores} de {proyecto}', 'quiero {estudio} de {alimentadores} en {proyecto}',
                 'pasa {proyecto} por sus estudios', 'analiza {alimentadores} de {proyecto} con todos los estudios', 'estudio de {estudio} para {alimentadores} de {proyecto}'),
    'obras_escalera': ('intenta la escalera en {alimentadores} de {proyecto}', 'prueba escalon por escalon las obras en {proyecto}', 'a ver la escalera para {proyecto}',
                       'sube por la escalera de obras {alimentadores} de {proyecto}', 'desde bancos hasta terna en {proyecto}', 'la escalera de {proyecto} lanzala'),
    'optimizar_con_proyecto': ('saca el optimo del con proyecto de {proyecto}', 'mejora el con proyecto en {proyecto}', 'manda las que no entran a set nueva en {proyecto}',
                               'optimizacion del caso con proyecto para {proyecto}', 'decide las obras del con proyecto de {proyecto}', 'corre el optimizador del con proyecto en {alimentadores} de {proyecto}'),
    'transferencia': ('cuanto puedo pasar entre {alimentadores} en {proyecto}', 'respaldo entre {alimentadores} de {proyecto}', 'mira el traspaso de demanda de {alimentadores} en {proyecto}',
                      'mueve carga entre {alimentadores} del proyecto {proyecto}', 'evalua transferir entre {alimentadores} en {proyecto}', 'capacidad de transferencia de {alimentadores} en {proyecto}'),
    'pide': ('arma el pide de {proyecto}', 'corre el plan de inversiones en {alimentadores} de {proyecto}', 'planifica con pide {proyecto}',
             'quiero el pide completo de {proyecto}', 'procesa la metodologia pide para {alimentadores} de {proyecto}', 'saca el plan pide de {proyecto}'),
    'gemelo_aprender': ('alimenta al gemelo con {numero} casos de {proyecto}', 'que el gemelo practique con {proyecto}', 'pon {numero} escenarios al gemelo desde {proyecto}',
                        'dale experiencia al gemelo en {proyecto}', 'corre aprendizaje del gemelo sobre {alimentadores} en {proyecto}', 'junta casos para el gemelo con {proyecto}'),
    'gemelo_entrenar': ('dale otra pasada de entrenamiento a la pinn', 'reajusta el oraculo con lo acumulado', 'pon a entrenar el gemelo',
                        'actualiza los pesos de la pinn', 'nuevo entrenamiento del modelo fisico', 'vuelve a afinar el gemelo'),
    'gemelo_temporal': ('rehaz la curva del mes de {alimentadores}', 'la serie mensual de {alimentadores} con el gemelo temporal', 'reconstruye el mes de {alimentadores}',
                        'corre lo temporal para {alimentadores}', 'recorre el mes con el modelo temporal en {alimentadores}', 'la curva mensual de {alimentadores} con gru'),
    'informe_estudio': ('escribeme el estudio de {alimentadores} de {proyecto}', 'word del estudio de {alimentadores} en {proyecto}', 'documento del estudio electrico de {alimentadores} en {proyecto}',
                        'prepara el informe de {subtipo} de {alimentadores} en {proyecto}', 'necesito el reporte de estudio de {alimentadores} en {proyecto}', 'redacta para {alimentadores} el estudio de {subtipo} de {proyecto}'),
    'informe_factibilidad': ('saca el documento de factibilidad de {sed} en {alimentadores} de {proyecto}', 'redactame la factibilidad de {sed} en {proyecto}', 'informe de punto de diseño de {sed} de {alimentadores} en {proyecto}',
                             'escribe la factibilidad para {sed} en {proyecto}', 'necesito la factibilidad de {sed} de {alimentadores} en {proyecto}', 'prepara la factibilidad de suministro de {sed} para {proyecto}'),
    'entrenar_asistente': ('pon a entrenar tu modelo de ordenes', 'aprende lo que te confirme', 'actualiza lo que entiendes de mis ordenes',
                           'renueva el modelo que me interpreta', 'dale otra vuelta a tu entrenamiento', 'reentrenate con mis ordenes'),
    'consultar_datos': ('que subestaciones cuelgan de {alimentadores}', 'con que medidor se mide {alimentadores}', 'cuantas variaciones hay en {proyecto}',
                        'quienes son los clientes fijos de {alimentadores}', 'de que años hay medicion cargada', 'cual es el ultimo ajuste aplicado en {proyecto}'),
    'no_disponible': ('necesito las corrientes de cortocircuito de {proyecto}', 'cuanto da la falla trifasica en {proyecto}', 'estan coordinadas las protecciones de {proyecto}',
                      'hazme la selectividad de {proyecto}', 'resuelve con pnl {proyecto}', 'sacame los armonicos de {proyecto}'),
    'evaluar_carga_nueva': ('entra {sed} en {alimentadores} de {proyecto}, evalualo', 'revisa de punta a punta si {sed} cabe en {alimentadores} de {proyecto}', 'quiero el dictamen de {sed} en {alimentadores} de {proyecto} con su informe',
                            'analiza entera la conexion de {sed} a {alimentadores} en {proyecto}', 'hazme la evaluacion completa de {sed} para {alimentadores} de {proyecto}', 'evaluame este cliente nuevo {sed} en {alimentadores} de {proyecto}'),
    'cancelar_trabajo': ('frena lo que corre', 'corta ese proceso ahora', 'no continues con el trabajo', 'detente con lo que estas haciendo', 'suspende la ejecucion actual', 'aborta eso'),
    'convertir_set': ('necesito en dgs la set {set}', 'exportame solamente la set {set}', 'el dgs de la subestacion {set}', 'sacame {set} sola en dgs', 'produce el dgs de esa set {set}', 'a dgs la set {set} y nada mas'),
    'set_completo': ('deja calibrada la set {set} con {periodo}', 'de principio a fin la set {set} en {periodo}', 'encargate de la set {set} con {periodo}',
                     'la set {set} importada y calibrada con {periodo}', 'procesame entera la set {set} para {periodo}', 'lleva hasta calibrar la set {set} con {periodo}'),
    'alimentadores_completo': ('deja calibrado {alimentadores} con {periodo} empezando de cero', 'de principio a fin {alimentadores} en {periodo}', 'procesame entero {alimentadores} para {periodo}',
                               'encargate de todo con {alimentadores} en {periodo}', 'importa y calibra {alimentadores} desde la fuente con {periodo}', 'todo el camino para {alimentadores} con {periodo}'),
    'buscar_maxima': ('cual fue el pico de {alimentadores} en {periodo}', 'ubicame la mayor demanda de {alimentadores}', 'en que instante tuvo su tope {alimentadores} en {periodo}',
                      'el pico de la barra de {set} en {periodo}', 'la punta de 60 kv de {sistema} en {periodo}', 'halla la maxima conjunta de {alimentadores}'),
    'cruzar_clientes': ('empatame los clientes de {alimentadores} con la red', 'pasa los clientes de {periodo} por la red', 'el cruce de clientes de {alimentadores} en {periodo}',
                        'liga suministros y clientes de {alimentadores}', 'con la maxima buscada cruza a los clientes de {alimentadores}', 'quiero el cruce con los clientes de {periodo}'),
    'calibrar': ('ya con la maxima, calibrame {proyecto}', 'pon {proyecto} a la demanda buscada', 'lleva {proyecto} a su maxima y graba', 'graba la calibracion que toca en {proyecto}',
                 'ajusta las demandas de {proyecto} a lo buscado', 'deja {proyecto} calibrado con esa maxima'),
    'simular_calibracion': ('calibra {proyecto} de mentira primero', 'ensayo de calibracion para {proyecto}', 'sin escribir nada mira como calibra {proyecto}',
                            'prueba de calibrar {proyecto} y no guardes', 'que pasaria si calibro {proyecto}', 'corrida seca del ajuste de {proyecto}'),
    'recalibrar': ('rehaz la calibracion de {proyecto} con {periodo}', 'otra calibracion a {proyecto} para {periodo}', 'pon al dia {proyecto} con {periodo}, sin reconvertir',
                   'sobre {proyecto} ya importado calibra {periodo}', 'nuevo ajuste en {proyecto} con {periodo}', 'recalculo de la calibracion de {proyecto} en {periodo}'),
    'escanear': ('que le hicieron a mano a {alimentadores} en {proyecto}', 'pasale el escaner a {alimentadores} de {proyecto}', 'detecta los bancos de {alimentadores} en {proyecto}',
                 'levantame generadores de {alimentadores} en {proyecto}', 'que modificaron en {alimentadores} de {proyecto}', 'revision de lo manual en {alimentadores} de {proyecto}'),
    'verificar_convergencia': ('resuelve el flujo {proyecto} o no', 'aun converge el proyecto {proyecto}', 'prueba rapida de convergencia en {proyecto}',
                               'dime si {proyecto} llega a converger', 'el flujo de {proyecto} converge ahora', 'hay convergencia en {proyecto}'),
    'carga_nueva_sola': ('pon solita la carga {sed} en {alimentadores} de {proyecto}', 'da de alta {sed} en {alimentadores} de {proyecto}', 'engancha {sed} a {alimentadores} en {proyecto}',
                         'solo esa carga {sed} va a {alimentadores} de {proyecto}', 'suma el suministro {sed} a {alimentadores} de {proyecto}', 'crea la carga {sed} en {alimentadores} del proyecto {proyecto}'),
    'proyecto_entero': ('todas las etapas de {sistema} con {periodo}, ensename primero', 'hazte cargo del proyecto de {sistema} con {periodo}', 'de cero a informe el sistema {sistema} en {periodo}',
                        'cumple todas las etapas de {sistema} para {periodo}', 'la lista de etapas de {sistema} con {periodo} y ejecutala', 'proyecto de inicio a fin de {sistema} en {periodo}'),
    'leer_solicitud': ('revisame estos documentos del cliente en {ruta}', 'que dice la carta en {ruta}', 'sacale la potencia al pdf {ruta}', 'lee lo que mando el solicitante en {ruta}',
                       'extrae lo pedido de los documentos {ruta}', 'jala los datos del solicitante de {ruta}'),
    'descargar_resultados': ('comprimeme lo que salio', 'quiero bajar todo lo generado', 'un zip con lo de {alimentadores}', 'empaca los resultados', 'ponme para descargar las salidas', 'dame los archivos finales comprimidos'),
    'pronostico': ('cuanta demanda esperas en la cabecera de {alimentadores} segun {ruta}', 'estimame el futuro de {alimentadores} desde {ruta}', 'pronostica clientes con el libro {ruta}',
                   'adelantame la cabecera con los datos de {ruta}', 'proyeccion de clientes fijos a partir de {ruta}', 'como vendra la demanda de cabecera segun {ruta}'),
}


def filas() -> list[dict]:
    """Las filas de la prueba, siempre las mismas: dependen de esto y de ``expandir``, no del espacio."""
    if set(FRASES) != set(TAREAS):
        raise ValueError('prueba sellada sin todas las tareas del catálogo')
    salida, vistas = [], set()
    for tarea in sorted(FRASES):
        for plantilla in FRASES[tarea]:
            grupo = huella({'sellada': plantilla, 'tarea': tarea})
            rnd = random.Random(int(grupo[:12], 16))
            for _ in range(POR_FRASE):
                e = expandir(plantilla, tarea, rnd, VOCABULARIO, RUIDO)
                clave = texto_canonico(e.texto)
                if clave in vistas:
                    continue
                vistas.add(clave)
                r = {'texto': e.texto, 'tarea': tarea, 'datos': [list(d) for d in e.datos], 'group_id': grupo,
                     'particion': 'prueba', 'quality': 'silver_teacher_verified', 'del_maestro': True, 'conjunto': CONJUNTO}
                r['record_id'] = huella(r)
                salida.append(r)
    return salida


def huella_de(registros: list[dict]) -> str:
    return huella(sorted(r['record_id'] for r in registros))[:16]


def selladas() -> list[dict]:
    """Las filas, comprobadas contra su huella: otra prueba no es esta (070:RF-70)."""
    registros = filas()
    if huella_de(registros) != HUELLA:
        raise ValueError('la prueba sellada cambió: su huella no coincide; no se ajusta mirándola')
    return registros
