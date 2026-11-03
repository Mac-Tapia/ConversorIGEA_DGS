"""047:RF-16 — 200 propuestas nuevas del maestro, con familias y fixtures explícitas.

Se reservan para evaluación de la configuración fijada, no para entrenar. Los
prefijos/valores generan variantes correlacionadas; no se anuncian 200 familias
independientes ni 200 observaciones humanas.
"""
from __future__ import annotations

from collections import Counter
import re

from ..evaluacion_modelos import huella, texto_canonico
from .tareas import TAREAS

VOCABULARIO = {
    'alimentadores': ['AB101', 'CD202', 'EF303', 'GH404'],
    'proyecto': ['Red Demo Norte', 'Red Demo Sur', 'Red Demo Centro'],
    'sistema': ['Costa Clara', 'Valle Verde', 'Sierra Azul'],
    'sed': ['SED01001', 'SED02002', 'SED03003'],
    'periodo': ['2026-07', '2026-08', '2026-09'],
    'ruta': ['D:/ensayo/demanda_01.xlsx', 'D:/ensayo/demanda_02.xlsx', 'D:/ensayo/demanda_03.xlsx'],
    'numero': ['5', '10', '20'],
    'subtipo': ['mejora de tensión', 'refuerzo de red', 'alimentación de carga nueva'],
    'set': ['SET Uno', 'SET Dos', 'SET Tres'],
    'estudio': ['flujo', 'troncal', 'n-1'],
    'texto': ['por qué puede no converger un flujo de carga',
              'cómo se verifica una tensión fuera de límites',
              'qué significa una sobrecarga en un transformador'],
}

PLANTILLAS = {
    'estado': ('Indica qué entradas y resultados conserva este espacio', 'Quiero conocer el contenido disponible de la sesión'),
    'proyectos': ('Consulta el listado de proyectos ya conocidos', 'Enséñame el catálogo actual de proyectos de DIgSILENT'),
    'resultados_pide': ('Enséñame qué inversiones resultaron del PIDE en «{proyecto}»', 'Consulta las obras priorizadas que dejó el PIDE de «{proyecto}»'),
    'episodios': ('Enumera las experiencias guardadas del gemelo para «{proyecto}»', 'Consulta el recuento de episodios almacenados de «{proyecto}»'),
    'pregunta': ('Quisiera entender esta duda: «{texto}»', 'Dame una explicación sobre «{texto}»'),
    'clasificar_informe': ('Determina la categoría de informe correspondiente a este pedido: «{texto}»', 'Clasifica el tipo de estudio solicitado aquí: «{texto}»'),
    'buscar_internet': ('Encuentra bibliografía en internet acerca de «{texto}»', 'Realiza una búsqueda web sobre «{texto}»'),
    'leer_proyectos': ('Actualiza el catálogo consultando de nuevo los proyectos en PowerFactory', 'Lee otra vez DIgSILENT para refrescar sus proyectos'),
    'evaluar_gemelo': ('Mide el error del predictor del gemelo respecto del cálculo nativo', 'Comprueba la precisión actual del modelo eléctrico del gemelo'),
    'cargar_fuente': ('Importa al espacio los archivos de entrada que seleccioné', 'Carga aquí la fuente de datos de la red seleccionada'),
    'convertir': ('Construye la exportación DGS del circuito {alimentadores}', 'Pasa la fuente del alimentador {alimentadores} al formato DGS'),
    'unir': ('Reúne {alimentadores} dentro de un mismo archivo DGS', 'Crea un DGS único que combine los circuitos {alimentadores}'),
    'convertir_sistema': ('Exporta solamente el sistema «{sistema}» a formato DGS', 'Haz la conversión DGS de todos los circuitos de «{sistema}»'),
    'sistema_completo': ('Convierte, importa y calibra «{sistema}» usando el período {periodo}', 'Ejecuta el proceso completo de conversión y calibración de «{sistema}» para {periodo}'),
    'flujo': ('Resuelve el flujo de potencia del circuito {alimentadores}', 'Calcula las tensiones y cargas mediante un flujo de {alimentadores}'),
    'verificar_caso_base': ('Verifica formalmente el Caso base del proyecto «{proyecto}»', 'Valida que el escenario Caso base de «{proyecto}» sea correcto'),
    'cargas_nuevas': ('Incorpora los nuevos clientes de «{ruta}» en {alimentadores} del proyecto «{proyecto}»', 'Agrega las cargas nuevas del archivo «{ruta}» para {alimentadores} de «{proyecto}»'),
    'obras': ('Aplica las obras guardadas de {alimentadores} en «{proyecto}»', 'Ejecuta las mejoras seleccionadas para {alimentadores} del proyecto «{proyecto}»'),
    'estudios': ('Ejecuta los estudios eléctricos seleccionados de {alimentadores} en «{proyecto}»', 'Lanza las simulaciones de estudios para {alimentadores} del proyecto «{proyecto}»'),
    'obras_escalera': ('Sube la escalera de refuerzos de {alimentadores} en «{proyecto}»', 'Prueba obras por escalones en {alimentadores} del proyecto «{proyecto}»'),
    'optimizar_con_proyecto': ('Optimiza el caso con proyecto de {alimentadores} en «{proyecto}»', 'Calcula la mejor salida de con proyecto para {alimentadores} de «{proyecto}»'),
    'transferencia': ('Estudia pasar carga entre {alimentadores} dentro de «{proyecto}»', 'Realiza una transferencia de demanda entre {alimentadores} en «{proyecto}»'),
    'pide': ('Desarrolla la planificación PIDE de {alimentadores} para «{proyecto}»', 'Ejecuta el plan de inversiones PIDE de «{proyecto}» en {alimentadores}'),
    'gemelo_aprender': ('Obtén {numero} escenarios nuevos para que aprenda el gemelo de {alimentadores} en «{proyecto}»', 'Recoge episodios de aprendizaje del gemelo con {numero} escenarios de {alimentadores} en «{proyecto}»'),
    'gemelo_entrenar': ('Vuelve a ajustar los pesos del oráculo PINN con sus episodios', 'Reentrena el predictor neuronal físico del gemelo digital'),
    'gemelo_temporal': ('Reproduce con la GRU la curva temporal del circuito {alimentadores}', 'Genera la evolución mensual de {alimentadores} mediante el gemelo temporal'),
    'informe_estudio': ('Elabora la memoria del estudio de «{subtipo}» de {alimentadores} en «{proyecto}»', 'Redacta el informe de estudio eléctrico de {alimentadores} en «{proyecto}» para «{subtipo}»'),
    'informe_factibilidad': ('Redacta la factibilidad de la SED {sed} de {alimentadores} en «{proyecto}»', 'Prepara el informe de factibilidad del suministro {sed} de {alimentadores} en «{proyecto}»'),
    'entrenar_asistente': ('Ajusta otra vez el Transformer que interpreta las instrucciones del operador', 'Reentrena al asistente de órdenes con su corpus disponible'),
}

PLANTILLAS.update({
    'consultar_datos': ('Enumera las subestaciones de distribución de {alimentadores}', 'Relaciona los medidores asociados a {alimentadores}'),
    'no_disponible': ('Calcula las corrientes de cortocircuito de «{proyecto}»', 'Comprueba la selectividad de protecciones de «{proyecto}»'),
    'evaluar_carga_nueva': ('Evalúa de una vez la conexión de {sed} en {alimentadores} de «{proyecto}»', 'Lleva hasta su informe la carga nueva {sed} de {alimentadores} en «{proyecto}»'),
    'cancelar_trabajo': ('Interrumpe el trabajo que corre en este espacio', 'Detén la ejecución en curso de este espacio'),
    'convertir_set': ('Construye el DGS de la subestación {set}', 'Pasa a DGS la subestación {set} con sus circuitos'),
    'set_completo': ('Convierte, importa y calibra la subestación {set} con el período {periodo}', 'Proceso completo de la subestación {set} para {periodo}'),
    'alimentadores_completo': ('Convierte, importa y calibra los circuitos {alimentadores} con {periodo}', 'Proceso completo de {alimentadores} para {periodo}'),
    'buscar_maxima': ('Obtén la demanda máxima de {alimentadores} en {periodo}', 'Averigua el pico coincidente de {alimentadores}'),
    'cruzar_clientes': ('Empareja los clientes importantes de {alimentadores}', 'Arma el cruce de suministros de {alimentadores}'),
    'calibrar': ('Aplica el ajuste de demanda en «{proyecto}» con la máxima buscada', 'Graba en «{proyecto}» la calibración preparada'),
    'simular_calibracion': ('Ensaya sin grabar la calibración de «{proyecto}»', 'Mide el efecto de calibrar «{proyecto}» sin aplicar'),
    'recalibrar': ('Calibra de nuevo «{proyecto}» con {periodo}', 'Actualiza el ajuste de «{proyecto}» a {periodo}'),
    'escanear': ('Examina lo cambiado a mano en {alimentadores} de «{proyecto}»', 'Lee generadores y bancos de {alimentadores} en «{proyecto}»'),
    'verificar_convergencia': ('Comprueba que el flujo de «{proyecto}» tenga solución', 'Averigua si «{proyecto}» sigue resolviendo el flujo'),
    'carga_nueva_sola': ('Añade solo el suministro {sed} a {alimentadores} en «{proyecto}»', 'Conecta como carga aislada {sed} en {alimentadores} de «{proyecto}»'),
    'proyecto_entero': ('Realiza todo el trabajo de «{sistema}» con {periodo}', 'Recorre todas las etapas de «{sistema}» para {periodo}'),
    'leer_solicitud': ('Toma los datos de los documentos en «{ruta}»', 'Revisa la documentación del solicitante en «{ruta}»'),
    'descargar_resultados': ('Comprime las salidas de este espacio para bajarlas', 'Prepara el comprimido con los resultados'),
    'pronostico': ('Calcula la demanda esperada de cabecera con «{ruta}»', 'Estima el consumo futuro de cabecera desde «{ruta}»'),
})
PREFIJOS = ('', 'Por favor: ', 'Ahora, ', 'Necesito lo siguiente: ')


def generar_propuestas() -> tuple[list[dict], dict]:
    if set(PLANTILLAS) != set(TAREAS):
        raise ValueError('catálogo de propuestas incompleto')
    filas = []
    for i in range(200):
        tarea = sorted(TAREAS)[i % len(TAREAS)]
        variante = i // len(TAREAS)
        plantilla = PLANTILLAS[tarea][variante % 2]
        texto, datos = PREFIJOS[(variante // 2) % len(PREFIJOS)], []
        posicion = 0
        for m in re.finditer(r'\{(\w+)\}', plantilla):
            texto += plantilla[posicion:m.start()]
            tipo = m[1]
            valor = VOCABULARIO[tipo][variante % len(VOCABULARIO[tipo])]
            if tipo == 'alimentadores' and tarea in ('unir', 'transferencia'):
                valor += ' y ' + VOCABULARIO[tipo][(variante + 1) % len(VOCABULARIO[tipo])]
            datos.append([len(texto), len(texto) + len(valor), tipo]); texto += valor
            posicion = m.end()
        texto += plantilla[posicion:]
        r = {'texto': texto, 'tarea': tarea, 'datos': datos, 'quality': 'silver_teacher_verified',
             'group_id': huella({'plantilla': plantilla, 'tarea': tarea}), 'particion': 'prueba',
             'del_maestro': True, 'origen': 'propuesta_maestro_codex_20261031_v1'}
        r['record_id'] = huella(r); filas.append(r)
    if len({texto_canonico(r['texto']) for r in filas}) != 200:
        raise ValueError('el currículo no produce 200 propuestas únicas')
    return filas, {'schema_version': 1, 'propuestas': 200, 'unicas': 200, 'humanas': 0,
        'familias': len({r['group_id'] for r in filas}), 'por_tarea': dict(Counter(r['tarea'] for r in filas)),
        'dataset_hash': huella(filas), 'vocabulario': VOCABULARIO,
        'alcance': 'aceptación asistida; no observaciones humanas ni aceptación eléctrica'}
