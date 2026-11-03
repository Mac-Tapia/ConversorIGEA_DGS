"""La prueba sellada de las órdenes desde la spec 079 (RF-38 a RF-45): la que decide.

Por qué existe: la anterior (huella ``df5e1db88595d378``) ya se había medido dos veces por familia y orientó el diseño de la
079, de modo que dejó de ser ciega. Sigue midiéndose, sin decidir.

Método declarado: un solo autor, Claude, la escribió de una vez el 2026-11-03, en una sola pasada y sin mirar ningún modelo, seis
frases por cada tarea del catálogo, sin abrir ``prueba_sellada.py`` ni sus filas, ni ``ejemplos.jsonl``, ni ``maestro_real/``. Se
fijó su huella antes de escribir el currículo de la 079 y antes de medir nada con ella. Cada frase se expande con ``expandir``,
con la semilla que sale de la tarea y del lugar de la frase, con un vocabulario propio e inventado, de modo que no depende del
espacio. La comparación con el resto del corpus la hace ``destilacion_integral``; solo se habría cambiado una frase si chocara, y
nunca tras medir.

Lo que no garantiza: el autor es el mismo de la 079 y del currículo que entrena, y conocía qué tareas salen flojas en selección,
aunque no qué falla en ninguna prueba. Otro redactor no era posible aquí. Mide el salto a frases de otra redacción solo en parte:
es optimista frente a un redactor distinto y no sustituye a las órdenes confirmadas por el operador. Si se ajusta tras medir,
deja de valer: ``HUELLA`` lo delata (079:RF-40).
"""
from __future__ import annotations

import random

from ..evaluacion_modelos import huella, texto_canonico
from .sinteticos import expandir
from .tareas import TAREAS

POR_FRASE = 8
RUIDO = .06
SEMILLA = 7907
CONJUNTO = 'sellada_079'
#: 079:RF-39, RF-40: la huella de las filas; se fijó antes de medir nada con ellas.
HUELLA = 'b721cf76aa291d43'
#: Propio e inventado, para que la prueba no dependa del espacio ni de ninguna empresa (P13).
VOCABULARIO = {'alimentadores': ('QX101', 'QX202', 'WV303', 'WV404', 'TZ115'),
               'proyecto': ('Ensayo Norte 7', 'ZK210_ZK220', 'Variante Sur'),
               'sistema': ('Altiplano', 'Litoral Medio', 'Quebrada'),
               'set': ('Mirador', 'Ribera Alta', 'Los Pinos'),
               'sed': ('SE70707', 'SE80808', 'E91919'),
               'ruta': ('E:/planeamiento/cargas futuras.xlsx', 'E:/insumos/medicion', 'F:\\estudios\\solicitud.pdf')}

FRASES: dict[str, tuple[str, ...]] = {
    'alimentadores_completo': (
        'quiero {alimentadores} listos de principio a fin para {periodo}',
        'lleva {alimentadores} desde la conversion hasta la calibracion con {periodo}',
        'del txt a digsilent calibrado: {alimentadores}, medicion de {periodo}',
        'encadena conversion, importacion y calibracion para los circuitos {alimentadores} con {periodo}',
        'procesa entero {alimentadores} tomando {periodo}',
        '{alimentadores} completos, con los libros de {ruta}, periodo {periodo}'),
    'buscar_internet': (
        'averigua en internet {texto}',
        'hay algun repositorio publico sobre {texto}',
        'encuentra papers de {texto}',
        'mira en la web si alguien resolvio {texto}',
        'necesito bibliografia externa de {texto}',
        'rastrea paquetes de python para {texto}'),
    'buscar_maxima': (
        'a que hora toco techo {alimentadores} en {periodo}',
        'ubica el instante de mayor demanda de {alimentadores} durante {periodo}',
        'saca la punta de la barra de {set} en {periodo}',
        'encuentra la coincidente de 60 kv del sistema {sistema} en {periodo}',
        'momento de maxima carga para {alimentadores}',
        'la hora punta de la set {set} en {periodo}, buscala'),
    'calibrar': (
        'deja calibrado {proyecto} con la maxima que ya tienes',
        'lleva las demandas de {proyecto} a la medicion encontrada y guardalo',
        'aplicale a {proyecto} el ajuste de cabecera',
        'calibrame de una vez {proyecto}',
        'que {proyecto} quede ajustado a la punta ya ubicada',
        'pasa la calibracion definitiva a {proyecto}'),
    'cancelar_trabajo': (
        'para lo que esta corriendo',
        'deten el proceso en curso',
        'cancela eso ya',
        'corta la ejecucion actual',
        'no sigas con el trabajo de ahora',
        'anula lo que lanzaste recien'),
    'carga_nueva_sola': (
        'conecta la carga {sed} al circuito {alimentadores} en {proyecto}',
        'mete solo el cliente {sed} en {alimentadores} del proyecto {proyecto}',
        'anade una unica carga {sed} a {alimentadores}, proyecto {proyecto}',
        'en {proyecto} cuelga {sed} de {alimentadores}',
        'da de alta {sed} sobre {alimentadores} en {proyecto}',
        'una carga suelta: {sed} en {alimentadores} de {proyecto}'),
    'cargar_fuente': (
        'sube la fuente de este espacio',
        'toma los datos asignados y cargalos',
        'lee la entrada que tiene el espacio',
        'trae a memoria la fuente',
        'inicia la lectura de la fuente asignada',
        'carga lo que le corresponde a este espacio'),
    'cargas_nuevas': (
        'integra el excel {ruta} en {alimentadores} de {proyecto}',
        'pasa el bloque de clientes nuevos de {ruta} a {proyecto} en {alimentadores}',
        'usa {ruta} para meter las demandas futuras en {alimentadores} de {proyecto}',
        'el libro {ruta} trae cargas para {alimentadores}: ingresalas en {proyecto}',
        'en con proyecto de {proyecto} agrega las cargas de {ruta} para {alimentadores}',
        'bloque de cargas {ruta} sobre {proyecto} {alimentadores}'),
    'clasificar_informe': (
        'a que rubro pertenece este pedido: {texto}',
        'que clase de informe seria {texto}',
        'categoriza este encargo: {texto}',
        'ponle tipo y subtipo a {texto}',
        'dime de que estudio se trata {texto}',
        'encasilla el siguiente requerimiento {texto}'),
    'consultar_datos': (
        'cuantas sed tiene {alimentadores}',
        'listame los medidores de {alimentadores}',
        'que clientes fijos hay en {alimentadores}',
        'que anios de medicion existen para {alimentadores}',
        'ensename la ultima calibracion guardada de {proyecto}',
        'que hay en el catalogo para la set {set}'),
    'convertir': (
        'saca un dgs por cada uno de {alimentadores}',
        'traduce {alimentadores} para digsilent',
        'necesito el archivo de importacion de {alimentadores}',
        'de txt a dgs con {alimentadores}',
        'conversion separada de {alimentadores}',
        'prepara {alimentadores} en formato de powerfactory'),
    'convertir_set': (
        'saca el dgs solamente de la subestacion {set}',
        'traduce la set {set} para digsilent',
        'archivo de importacion de la set {set} con sus circuitos',
        'de txt a dgs la barra de {set}',
        'quiero solo {set} convertida',
        'conversion por subestacion: {set}'),
    'convertir_sistema': (
        'traduce el sistema electrico {sistema} a digsilent',
        'archivo de importacion del sistema {sistema}',
        'todo lo de {sistema} a dgs por sistema',
        'de txt a dgs el sistema {sistema}',
        'quiero convertido entero el sistema {sistema}',
        'conversion por sistema electrico: {sistema}'),
    'cruzar_clientes': (
        'quienes quedan fijos en la maxima de {alimentadores}',
        'cruza la punta de {periodo} con los clientes de {alimentadores}',
        'empata clientes con la maxima encontrada',
        'que clientes coinciden con el pico de {alimentadores} en {periodo}',
        'une la lista de clientes a la maxima ya hallada',
        'revisa que demanda de clientes cae en esa maxima'),
    'descargar_resultados': (
        'bajame todo lo que salio',
        'dame un zip con las salidas',
        'comprime los resultados para llevarmelos',
        'enlace de descarga de {alimentadores}',
        'quiero llevarme los archivos generados',
        'paquete descargable de lo producido'),
    'entrenar_asistente': (
        'reentrenate con las ordenes nuevas',
        'vuelve a ajustar tu interprete',
        'entrena otra vez tu modelo de ordenes',
        'actualiza lo que aprendiste de mis ordenes',
        'corre el entrenamiento del asistente',
        'mejora tu clasificador de ordenes con lo confirmado'),
    'episodios': (
        'cuantos episodios guardo el gemelo para {proyecto}',
        'lista los episodios del proyecto {proyecto}',
        'que casos tiene el gemelo registrados',
        'ensename el bufer de episodios de {proyecto}',
        'hay episodios nuevos en {proyecto}',
        'conteo de episodios por clase'),
    'escanear': (
        'mira si tocaron algo a mano en {alimentadores} de {proyecto}',
        'lee los bancos y generadores de {alimentadores} en {proyecto} sin escribir',
        'recorre {alimentadores} de {proyecto} y dime que cambio',
        'antes de recalibrar revisa {alimentadores} en {proyecto}',
        'pasa el escaner por {alimentadores}, proyecto {proyecto}',
        'hay centrales o bancos nuevos en {alimentadores} de {proyecto}'),
    'estado': (
        'en que estamos',
        'que tienes ahora en el espacio',
        'situacion actual del trabajo',
        'resumeme que esta cargado',
        'hay algo corriendo ahorita',
        'dame el panorama de este espacio'),
    'estudios': (
        'calcula los estudios electricos de {alimentadores} en {proyecto}',
        'corre {estudio} y los demas estudios de {alimentadores} en {proyecto}',
        'analiza la red de {alimentadores} con los estudios de {proyecto}',
        'pasa los estudios sobre {proyecto} para {alimentadores}',
        'quiero el estudio {estudio} de {alimentadores} en {proyecto}',
        'manda a calcular los estudios de {proyecto} en {alimentadores}'),
    'evaluar_carga_nueva': (
        'admite {alimentadores} la carga {sed} en {proyecto}',
        'evalua el ingreso de {sed} en {alimentadores} de {proyecto}',
        'hazme toda la evaluacion de la carga {sed} sobre {alimentadores} en {proyecto}',
        'es factible conectar {sed} a {alimentadores} del proyecto {proyecto}',
        'revisa de una vez si {sed} entra en {alimentadores}, proyecto {proyecto}',
        'de diagnostico a informe para la carga {sed} en {alimentadores} de {proyecto}'),
    'evaluar_gemelo': (
        'que tan lejos esta el gemelo de digsilent',
        'mide el error del oraculo',
        'contrasta el gemelo con la fisica',
        'cuanto se equivoca el gemelo',
        'precision del gemelo frente al simulador',
        'valida el modelo del gemelo contra digsilent'),
    'flujo': (
        'corre la carga de {alimentadores} en digsilent',
        'load flow de {alimentadores}',
        'dame tensiones y cargabilidad de {alimentadores} con flujo',
        'resuelve el flujo para {alimentadores}',
        'haz correr potencia en {alimentadores}',
        'quiero ver el reparto de potencia de {alimentadores}'),
    'gemelo_aprender': (
        'que el gemelo aprenda de {alimentadores} en {proyecto} con {numero} escenarios',
        'aprendizaje activo en {proyecto} sobre {alimentadores}',
        'lanza {numero} escenarios en una copia de {proyecto} para {alimentadores}',
        'alimenta al gemelo con corridas de {alimentadores} en {proyecto}',
        'junta muestras para el gemelo de {alimentadores}, proyecto {proyecto}',
        'nuevos escenarios activos en {alimentadores} de {proyecto}'),
    'gemelo_entrenar': (
        'reentrena la pinn',
        'vuelve a entrenar el oraculo con el bufer',
        'actualiza el gemelo con los episodios guardados',
        'corre el ajuste del oraculo',
        'entrena el modelo fisico otra vez',
        'que el oraculo aprenda lo del bufer'),
    'gemelo_temporal': (
        'reconstruye el mes de {alimentadores} con el gemelo',
        'curva temporal de {alimentadores} con el gemelo',
        'pasa el gemelo temporal por {alimentadores}',
        'simula el mes de {alimentadores} con las curvas de la maxima',
        'gemelo del mes completo para {alimentadores}',
        'recrea las tensiones del mes en {alimentadores} con el gemelo'),
    'informe_estudio': (
        'redactame el word del estudio de {alimentadores} en {proyecto}',
        'informe electrico de {subtipo} para {alimentadores} de {proyecto}',
        'genera el documento de estudio de {alimentadores}, proyecto {proyecto}',
        'arma el informe de {alimentadores} en {proyecto}',
        'necesito el entregable de estudio de {subtipo} de {proyecto} en {alimentadores}',
        'saca en word lo de {alimentadores} en {proyecto}'),
    'informe_factibilidad': (
        'redactame la factibilidad de {sed} en {alimentadores} de {proyecto}',
        'documento de factibilidad de suministro para {sed}, {alimentadores}, {proyecto}',
        'emite la factibilidad del cliente {sed} en {proyecto} {alimentadores}',
        'informe para la carga {sed} de {alimentadores} en {proyecto}',
        'necesito la carta de factibilidad de {sed} sobre {alimentadores} de {proyecto}',
        'arma la factibilidad {sed} en {proyecto} por {alimentadores}'),
    'leer_proyectos': (
        'actualiza la lista desde digsilent',
        'pregunta a digsilent que proyectos tiene',
        'refresca los proyectos de powerfactory',
        'vuelve a traer los proyectos del servidor de digsilent',
        'sincroniza con powerfactory la lista de proyectos',
        'abre digsilent y lista lo que tenga'),
    'leer_solicitud': (
        'lee el pdf del solicitante en {ruta}',
        'revisa los documentos del cliente de {ruta}',
        'saca los datos de la carta en {ruta}',
        'que pide el solicitante en {ruta}',
        'extrae potencia y ubicacion de {ruta}',
        'abre la solicitud que esta en {ruta}'),
    'no_disponible': (
        'calcula el cortocircuito trifasico de {proyecto}',
        'coordina los reles de {proyecto}',
        'haz un estudio de armonicos en {proyecto}',
        'corre un opf de {proyecto}',
        'ajusta protecciones en {proyecto}',
        'dame la icc de las barras de {proyecto}'),
    'obras': (
        'ejecuta en digsilent las obras pendientes de {alimentadores} en {proyecto}',
        'aplica lo pendiente de obras en {proyecto} {alimentadores}',
        'mete las mejoras a {alimentadores} de {proyecto}',
        'materializa las obras previstas de {alimentadores}, proyecto {proyecto}',
        'pasa las obras del espacio a {proyecto} en {alimentadores}',
        'escribe las obras en {alimentadores} de {proyecto}'),
    'obras_escalera': (
        'sube los escalones en {alimentadores} de {proyecto}: bancos, seccion y terna',
        'prueba bancos luego seccion luego terna en {alimentadores} de {proyecto}',
        'escalera hasta dejar en norma {alimentadores} de {proyecto}',
        'corre la escalera de mejora para {proyecto} {alimentadores}',
        'haz la secuencia de obras en escalera de {alimentadores} en {proyecto}',
        'desde bancos hasta terna en {proyecto} para {alimentadores}'),
    'optimizar_con_proyecto': (
        'optimiza con proyecto en {proyecto} para {alimentadores}',
        'busca las obras de menor costo en {alimentadores} de {proyecto}',
        'resuelve carga a carga {alimentadores} en {proyecto} y propon set nueva si no caben',
        'mejor alternativa para con proyecto de {alimentadores} en {proyecto}',
        'optimizacion de obras de {proyecto} {alimentadores}',
        'que {proyecto} quede optimo con las cargas de {alimentadores}'),
    'pide': (
        'corre la metodologia pide en {alimentadores} de {proyecto}',
        'arma el pide de {proyecto} para {alimentadores}',
        'plan de inversiones de {alimentadores} en {proyecto} con {periodo}',
        'haz los formatos del pide de {alimentadores}, proyecto {proyecto}',
        'calcula el pide con obras propias de {proyecto} en {alimentadores}',
        'ejecuta el pide completo de {alimentadores} en {proyecto}'),
    # Sin {texto}: la pregunta es el mensaje entero y el modelo no marca un trozo (069:RF-30).
    'pregunta': (
        'como decide el conversor que barra es la de cabecera',
        'podrias explicarme por que se excluyen los trafomix',
        'no entiendo para que sirve la escalera de obras',
        'que criterio usa el oraculo para aprobar un modelo',
        'en que fichero se escribe el dgs',
        'aclarame cuando se considera desenergizada una red'),
    'pronostico': (
        'pronostica la cabecera con {ruta}',
        'proyecta la demanda de {alimentadores} usando {ruta}',
        'que demanda tendra {alimentadores} segun {ruta}',
        'forecast de los clientes fijos con {ruta}',
        'predice la carga futura desde {ruta}',
        'corre la competencia de modelos de pronostico con {ruta}'),
    'proyecto_entero': (
        'todas las etapas del proyecto del sistema {sistema} con {periodo}',
        'anda etapa por etapa en {sistema} para {periodo}',
        'el proyecto de {sistema} de cabo a rabo con {periodo}',
        'lista y corre las etapas de {sistema}, {periodo}',
        'haz el proyecto entero de {sistema} con {periodo}',
        'encadena todo el trabajo del sistema {sistema} en {periodo}'),
    'proyectos': (
        'cuales proyectos conoces',
        'lista los proyectos que la web ya tiene',
        'con que proyectos cuento',
        'que proyectos estan vinculados',
        'ensename los proyectos registrados',
        'dime los nombres de los proyectos'),
    'recalibrar': (
        'ajusta otra vez {proyecto} a {periodo}',
        'pasa {proyecto} a la medicion de {periodo} sin reconvertir',
        'calibra de nuevo {proyecto} para {periodo}',
        'cambia el mes de calibracion de {proyecto} a {periodo}',
        'reajusta {proyecto} con la maxima de {periodo}',
        'recalibracion de {proyecto} tomando {periodo}'),
    'resultados_pide': (
        'que obras salieron en el ultimo pide de {proyecto}',
        'prioridades del pide de {proyecto}',
        'ensename los formatos del ultimo pide',
        'como quedo el pide de {proyecto}',
        'lo que arrojo el pide en {proyecto}',
        'revisemos el resultado del pide de {proyecto}'),
    'set_completo': (
        'la set {set} de inicio a fin con {periodo}',
        'convierte importa y calibra la subestacion {set} en {periodo}',
        'lleva {set} hasta calibrada para {periodo}',
        'procesa entera la set {set} tomando {periodo}',
        'calibrame la barra de {set} con {periodo}',
        'todo el flujo de la set {set} con la maxima de {periodo}'),
    'simular_calibracion': (
        'haz un ensayo de calibracion de {proyecto} sin tocarlo',
        'y si calibro {proyecto}, como saldria',
        'calibra {proyecto} de mentira',
        'dry run de la calibracion en {proyecto}',
        'solo simula el ajuste de demandas de {proyecto}',
        'muestrame como quedaria {proyecto} calibrado sin aplicar'),
    'sistema_completo': (
        'el sistema {sistema} de inicio a fin con {periodo}',
        'lleva el sistema {sistema} hasta calibrado para {periodo}',
        'procesa entero {sistema} tomando {periodo}',
        'todo el flujo del sistema {sistema} con la medicion de {periodo}',
        'convierte, sube y ajusta el sistema {sistema} a {periodo}',
        'ejecuta entero el sistema electrico {sistema} con datos de {periodo}'),
    'transferencia': (
        'pasa carga entre {alimentadores} en {proyecto}',
        'transfiere demanda de {alimentadores} en el proyecto {proyecto}',
        'estudia la transferencia entre {alimentadores} de {proyecto}',
        'traslada parte de la carga entre {alimentadores}, proyecto {proyecto}',
        'alivia un alimentador pasando carga: {alimentadores} en {proyecto}',
        'maniobra de transferencia {alimentadores} en {proyecto}'),
    'unir': (
        'todo {alimentadores} en un unico dgs',
        'fusiona {alimentadores} en una sola red',
        'un dgs conjunto de {alimentadores}',
        'red combinada con {alimentadores}',
        'no los separes: {alimentadores} en un archivo',
        'consolida {alimentadores} en una red unica'),
    'verificar_caso_base': (
        'compara el caso base de {proyecto} con el archivo de origen',
        'esta bien importado el caso base de {proyecto}',
        'pasa la revision del caso base a {proyecto}',
        'verificame solo el caso base en {proyecto} {alimentadores}',
        'contra el original: caso base de {proyecto}',
        'da el visto bueno al caso base de {proyecto}'),
    'verificar_convergencia': (
        've si {proyecto} converge',
        'llega a converger {proyecto} con lo activo',
        'corre el flujo de {proyecto} sin grabar para ver si resuelve',
        'no estoy seguro de que {proyecto} converja, compruebalo',
        'sigue resolviendo el flujo de {proyecto}',
        'test de convergencia en {proyecto} {alimentadores}'),
}


def filas() -> list[dict]:
    """Las filas de la prueba, sin comprobar su huella: las mismas con cualquier espacio."""
    salida, vistos = [], {}
    for tarea in sorted(TAREAS):
        for j, plantilla in enumerate(FRASES[tarea]):
            rnd = random.Random(SEMILLA + j + int(huella(tarea)[:8], 16))
            grupo = huella({'sellada_079': plantilla, 'tarea': tarea})
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
    """Las filas comprobadas: si alguien tocó una frase, se rechaza por la huella (079:RF-40)."""
    registros = filas()
    if huella_de(registros) != HUELLA:
        raise ValueError(f'la huella de {CONJUNTO} no coincide: las frases o su expansión cambiaron')
    return registros
