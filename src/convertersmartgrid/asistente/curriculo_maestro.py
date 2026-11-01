"""047:RF-11 — currículo escrito por Codex; etiquetas sintéticas, nunca confirmaciones humanas.

Cada columna es una familia distinta de entrenamiento, selección, calibración y
prueba. Las expansiones de una familia no pueden cruzar columnas. Las explicaciones
son descripciones públicas del catálogo, no razonamientos internos del maestro.
"""
from __future__ import annotations

MAESTRO = {'autor': 'Codex, maestro de la sesión', 'revision': '2026-10-31-v2',
           'metodo': 'response_distillation_single_annotation', 'votos_por_anotacion': 1,
           'logits_del_maestro_disponibles': False, 'quality': 'silver_teacher_verified'}

# El catálogo histórico de órdenes fijas se revisa como material didáctico
# sintético adicional. No se reutiliza su antigua partición como prueba.
MAESTRO['fuentes_revisadas'] = ['currículo de sesión', 'ordenes_fijas.FRASES (catálogo histórico)']

# Orden: entrenamiento, selección, calibración, prueba. Datos entre llaves se
# etiquetan mediante el parser común; sus valores permanecen locales.
FAMILIAS = {
    'estado': ('describe el contenido actual del espacio', 'resumen de lo cargado en esta sesion',
               'ensename el estado de mis datos', 'que informacion esta disponible ahora'),
    'proyectos': ('enumera los proyectos conocidos de powerfactory', 'catalogo de proyectos disponibles en pf',
                  'muestra los proyectos que conoces', 'dame la relacion de proyectos de digsilent'),
    'resultados_pide': ('consulta el resultado de inversiones de {proyecto}', 'resumen de resultados pide para {proyecto}',
                        'muestra las prioridades calculadas del pide en {proyecto}', 'revisa la salida del plan pide de {proyecto}'),
    'episodios': ('consulta el historial de episodios de {proyecto}', 'registros del gemelo para {proyecto}',
                  'lista los episodios guardados en {proyecto}', 'muestra el inventario de episodios del proyecto {proyecto}'),
    'pregunta': ('explicame como funciona la calibracion de cabecera', 'que significa una red desenergizada',
                 'explica la funcion del caso cargas nuevas', 'para que sirve verificar las tensiones'),
    'clasificar_informe': ('identifica la clase de este estudio: {texto}', 'determina el tipo de informe para {texto}',
                           'clasificacion del pedido tecnico {texto}', 'asigna un subtipo de estudio al pedido {texto}'),
    'buscar_internet': ('localiza fuentes en la web sobre {texto}', 'consulta github acerca de {texto}',
                        'investiga en paginas publicas sobre {texto}', 'encuentra publicaciones externas de {texto}'),
    'leer_proyectos': ('sincroniza el inventario de proyectos con digsilent', 'vuelve a consultar los proyectos en powerfactory',
                       'refresca los proyectos leyendo pf', 'actualiza desde digsilent los proyectos disponibles'),
    'evaluar_gemelo': ('compara la precision del gemelo con el motor nativo', 'verifica los errores predictivos del gemelo',
                       'cuantifica el desacuerdo del gemelo con powerfactory', 'audita la exactitud del gemelo digital'),
    'cargar_fuente': ('abre los archivos de entrada de la red', 'lee los ficheros txt seleccionados',
                      'incorpora la fuente seleccionada al espacio', 'inicia la lectura de los datos de red'),
    'convertir': ('exporta {alimentadores} al formato dgs', 'crea un archivo dgs para {alimentadores}',
                   'realiza la conversion a dgs de {alimentadores}', 'transforma la red {alimentadores} en dgs'),
    'unir': ('combina {alimentadores} en una red conjunta', 'exportacion conjunta de {alimentadores}',
              'genera una unica red con {alimentadores}', 'construye un dgs compartido para {alimentadores}'),
    'convertir_sistema': ('exporta a dgs el sistema completo {sistema}', 'conversion del sistema electrico {sistema}',
                          'crea los dgs del sistema {sistema}', 'genera la conversion integral de {sistema}'),
    'sistema_completo': ('procesa y calibra el sistema {sistema} para {periodo}', 'ejecuta conversion importacion y ajuste de {sistema} en {periodo}',
                         'flujo completo del sistema {sistema} con mediciones de {periodo}', 'prepara y recalibra todo el sistema {sistema} para {periodo}'),
    'flujo': ('ejecuta el flujo de potencia para {alimentadores}', 'calcula el estado de carga de {alimentadores}',
               'resuelve el flujo electrico en {alimentadores}', 'simula el flujo de carga del alimentador {alimentadores}'),
    'verificar_caso_base': ('audita el caso base del proyecto {proyecto}', 'verificacion inicial de la red base de {proyecto}',
                            'contrasta el caso base de {proyecto}', 'comprueba la validez del escenario base en {proyecto}'),
    'cargas_nuevas': ('incorpora los nuevos suministros de {ruta} al proyecto {proyecto}', 'agrega cargas nuevas desde {ruta} en {proyecto}',
                      'integra en {proyecto} los clientes nuevos del archivo {ruta}', 'lee {ruta} y conecta las nuevas cargas en {proyecto}'),
    'obras': ('ejecuta las mejoras guardadas para {proyecto}', 'incorpora las obras propuestas en {proyecto}',
              'aplica las intervenciones de red en {proyecto}', 'construye las obras seleccionadas de {proyecto}'),
    'estudios': ('realiza los estudios electricos del proyecto {proyecto}', 'lanza los calculos de estudios para {proyecto}',
                 'evalua los estudios seleccionados en {proyecto}', 'procesa las simulaciones de estudio de {proyecto}'),
    'transferencia': ('migra demanda entre {alimentadores} en {proyecto}', 'traslado de cargas entre {alimentadores} del proyecto {proyecto}',
                      'redistribuye carga mediante transferencia entre {alimentadores} en {proyecto}', 'realiza una transferencia entre los circuitos {alimentadores} de {proyecto}'),
    'pide': ('elabora el plan de inversiones pide de {proyecto}', 'planifica las inversiones pide para {proyecto}',
             'ejecuta la planificacion pide del proyecto {proyecto}', 'calcula las obras del horizonte pide para {proyecto}'),
    'gemelo_aprender': ('genera {numero} escenarios de aprendizaje del gemelo en {proyecto}', 'captura escenarios para que aprenda el gemelo en {proyecto}',
                        'amplia los episodios de aprendizaje con {numero} escenarios en {proyecto}', 'recolecta nuevas simulaciones de aprendizaje del gemelo para {proyecto}'),
    'gemelo_entrenar': ('ajusta de nuevo los pesos de la pinn', 'reentrenamiento del modelo fisico neuronal del gemelo',
                        'actualiza el aprendizaje de la red pinn', 'entrena otra vez el predictor electrico del gemelo'),
    'gemelo_temporal': ('pronostica la curva de {alimentadores} usando el gemelo temporal', 'reproduce la demanda temporal de {alimentadores}',
                        'simula la serie mensual de {alimentadores} con la gru', 'usa el modelo temporal para la curva de {alimentadores}'),
    'informe_estudio': ('redacta el documento de estudio de {subtipo} para {alimentadores} en {proyecto}', 'genera el informe tecnico del estudio {subtipo} en {proyecto}',
                        'prepara la memoria de estudio de {subtipo} para {alimentadores} de {proyecto}', 'elabora el informe del estudio {subtipo} del proyecto {proyecto}'),
    'informe_factibilidad': ('prepara la factibilidad de {sed} del proyecto {proyecto}', 'documento de factibilidad del suministro {sed} en {proyecto}',
                             'redacta el dictamen de factibilidad para {sed} de {proyecto}', 'genera el informe de factibilidad de la sed {sed} en {proyecto}'),
    'entrenar_asistente': ('actualiza el modelo de ordenes del asistente', 'vuelve a entrenar al interprete de instrucciones',
                           'entrena el asistente con los ejemplos disponibles', 'reentrena la red que reconoce mis ordenes'),
}
