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
    'transferencia': ('Estudia pasar carga entre {alimentadores} dentro de «{proyecto}»', 'Realiza una transferencia de demanda entre {alimentadores} en «{proyecto}»'),
    'pide': ('Desarrolla la planificación PIDE de {alimentadores} para «{proyecto}»', 'Ejecuta el plan de inversiones PIDE de «{proyecto}» en {alimentadores}'),
    'gemelo_aprender': ('Obtén {numero} escenarios nuevos para que aprenda el gemelo de {alimentadores} en «{proyecto}»', 'Recoge episodios de aprendizaje del gemelo con {numero} escenarios de {alimentadores} en «{proyecto}»'),
    'gemelo_entrenar': ('Vuelve a ajustar los pesos del oráculo PINN con sus episodios', 'Reentrena el predictor neuronal físico del gemelo digital'),
    'gemelo_temporal': ('Reproduce con la GRU la curva temporal del circuito {alimentadores}', 'Genera la evolución mensual de {alimentadores} mediante el gemelo temporal'),
    'informe_estudio': ('Elabora la memoria del estudio de «{subtipo}» de {alimentadores} en «{proyecto}»', 'Redacta el informe de estudio eléctrico de {alimentadores} en «{proyecto}» para «{subtipo}»'),
    'informe_factibilidad': ('Redacta la factibilidad de la SED {sed} de {alimentadores} en «{proyecto}»', 'Prepara el informe de factibilidad del suministro {sed} de {alimentadores} en «{proyecto}»'),
    'entrenar_asistente': ('Ajusta otra vez el Transformer que interpreta las instrucciones del operador', 'Reentrena al asistente de órdenes con su corpus disponible'),
}

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
