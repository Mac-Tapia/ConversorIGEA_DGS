"""047:RF-69 a RF-74 (MEJ34): el corpus v7 de órdenes del alumno destilado, con el contrato vigente entero.

El corpus v6 (065, resellado por 047:RF-57) cubre las 29 tareas de ``TAREAS_HASTA_069``: el alumno que sale de él no
conoce las tareas posteriores (calibrar, escanear, el PIT, la nube, la biblioteca normativa…) y no puede ponerse en uso.
El v7 parte de los mismos contextos reales del v6 (sus TXT, su estructura, sus mediciones, sus vínculos de proyecto) y
redacta, como maestro de sesión, solicitudes para las 67 tareas de ``TAREAS``, con:

- una columna de frases por partición (entrenamiento, selección, calibración y prueba) que no se cruzan; las de
  entrenamiento suman las plantillas del catálogo y ``ESTILO_REAL``, que solo entrenan;
- los valores de la fuente seudonimizados (alimentador, SED, SET, sistema, proyecto y rutas): el corpus no lleva ningún
  nombre real, y el mapa seudónimo → huella del original queda custodiado aparte;
- los valores que ninguna fuente aporta (la carpeta del caso del VAD, el .json de una norma…) como sintéticos
  controlados, uno por partición y declarados en la fila y en el manifiesto;
- cada fuente copiada a la custodia del propio corpus (``fuentes/<sha256>.bin``) y comprobada por su sha256;
- la prueba y la selección fijadas y con su huella antes de sellar, y selladas antes de entrenar;
- el prompt del perfil ``llm_destilado_v2`` (``sistema_alumno_contrato``), con el contrato vigente.

No genera resultados eléctricos ni presenta una solicitud redactada como orden humana.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
import hashlib
import json
from pathlib import Path
import random
import re
import shutil

from ..evaluacion_modelos import huella, texto_canonico
from .curriculo_maestro import ESTILO_REAL, FAMILIAS
from .curriculo_llm_real import ABSTENCION_TRAIN, PREFIJOS, PRUEBA_NUEVA
from .tareas import TAREAS, TAREAS_HASTA_069, sistema_alumno_contrato
from .llm_destilacion import (PARTICIONES, auditar_fuentes_corpus, custodiar, renderizar_orden,
                              respuesta_de_etiquetas as _respuesta_de_spans, sellar_particiones, verificar_fuente)

#: El esquema del corpus v7 y su perfil de prompt (047:RF-69).
SCHEMA = 3
PERFIL = 'llm_destilado_v2'
CALIDAD = 'silver_teacher_real_source'
#: 047:RF-70: los orígenes que se declaran. Las filas del corpus son del maestro o sintéticas controladas; las órdenes
#: humanas confirmadas se reservan aparte (``humanas_reservadas.json``) y nunca entran en una partición redactada.
ORIGENES = ('maestro', 'humano', 'sintetico_controlado')
ORIGENES_EN_PARTICION = ('maestro', 'sintetico_controlado')
MAESTRO_V7 = {'autor': 'Claude, maestro de la sesión', 'metodo': 'response_distillation', 'revision': '20261121-contrato-v7',
              'votos': 1, 'redaccion': 'plantillas por tarea y partición; renderizado determinista local'}
ORIGEN_FILA = 'maestro de sesion (Claude); solicitud redactada con valores de la fuente seudonimizados'
#: Por tarea: muestras de entrenamiento como máximo, y las fijas de cada partición apartada.
PRESUPUESTO = {'max_train_por_tarea': 48, 'seleccion_por_tarea': 3, 'calibracion_por_tarea': 2, 'prueba_por_tarea': 6}

#: 047:RF-71: las frases del maestro para las tareas posteriores a la 069, una columna por partición: entrenamiento,
#: selección, calibración y prueba. Se redactaron sin mirar ningún conjunto sellado; los valores van entre llaves.
CURRICULO_CONTRATO: dict[str, tuple[str, str, str, str]] = {
    'consultar_datos': ('enumera las sed y los medidores que tiene {alimentadores}',
                        'que datos guardados hay del circuito {alimentadores}',
                        'consulta la informacion registrada de {alimentadores}',
                        'Muestra lo que el espacio conoce del alimentador {alimentadores}'),
    'no_disponible': ('calcula la corriente de cortocircuito en {proyecto}',
                      'haz la coordinacion de reles de {proyecto}',
                      'quiero el flujo optimo no lineal de {proyecto}',
                      'Prepara el estudio de cortocircuito monofasico de {proyecto}'),
    'evaluar_carga_nueva': ('evalua de una vez la conexion de {sed} en {alimentadores} del proyecto {proyecto}',
                            'diagnostica si cabe la carga {sed} en {alimentadores} de {proyecto}',
                            'analiza la factibilidad completa de {sed} sobre {alimentadores} en {proyecto}',
                            'Haz la evaluacion integral de la carga nueva {sed} conectada a {alimentadores} dentro de {proyecto}'),
    'cancelar_trabajo': ('deten el trabajo que esta en curso', 'aborta la tarea que se esta ejecutando',
                         'interrumpe lo que lanzaste', 'Cancela de inmediato los trabajos que siguen corriendo en este espacio'),
    'repetir_trabajo': ('relanza el trabajo fallido con sus mismos datos', 'vuelve a correr la ultima tarea que dio error',
                        'intenta otra vez lo que se cayo', 'Repite el ultimo trabajo que termino con fallo'),
    'convertir_set': ('genera el dgs de la subestacion {set}', 'convierte unicamente la set {set} con su barra',
                      'exporta a dgs la set {set} y sus alimentadores', 'Produce la conversion DGS de la SET {set} por separado'),
    'set_completo': ('convierte importa y calibra la set {set} para {periodo}',
                     'lleva la set {set} de punta a punta con la medicion de {periodo}',
                     'procesa entera la set {set} usando {periodo}',
                     'Realiza el flujo completo de la SET {set} con la maxima de barra de {periodo}'),
    'alimentadores_completo': ('convierte importa y calibra {alimentadores} con la medicion de {periodo}',
                               'procesa de principio a fin {alimentadores} para {periodo}',
                               'lleva {alimentadores} completo hasta calibrar con {periodo}',
                               'Haz el proceso entero de {alimentadores} con los datos de {periodo}'),
    'buscar_maxima': ('encuentra la demanda maxima de {alimentadores} en {periodo}',
                      'calcula la maxima coincidente de {alimentadores} para {periodo}',
                      'ubica el pico de demanda de {alimentadores} en {periodo}',
                      'Determina la maxima de cabecera de {alimentadores} durante {periodo}'),
    'cruzar_clientes': ('cruza la tabla de clientes de {alimentadores} para {periodo}',
                        'identifica los clientes fijos de {alimentadores} en {periodo}',
                        'relaciona los clientes con la maxima de {alimentadores} en {periodo}',
                        'Haz el cruce de clientes de {alimentadores} con la maxima de {periodo}'),
    'calibrar': ('calibra el proyecto {proyecto} con la maxima buscada', 'aplica el ajuste de demandas en {proyecto}',
                 'lleva {proyecto} a la maxima medida', 'Ejecuta la calibracion del proyecto {proyecto} con la ultima maxima'),
    'simular_calibracion': ('ensaya la calibracion de {proyecto} sin aplicarla',
                            'calcula el plan de calibracion de {proyecto} sin escribir',
                            'haz una calibracion de prueba en {proyecto}',
                            'Simula el ajuste a la maxima de {proyecto} sin guardar cambios'),
    'recalibrar': ('recalibra el proyecto {proyecto} para {periodo}', 'ajusta otra vez {proyecto} con la medicion de {periodo}',
                   'calibra de nuevo {proyecto} usando {periodo}',
                   'Vuelve a ajustar el proyecto {proyecto} a la maxima de {periodo} sin reconvertir'),
    'escanear': ('lee los bancos y generadores de {alimentadores} en {proyecto}',
                 'inspecciona lo modificado a mano en {alimentadores} de {proyecto}',
                 'revisa centrales y condensadores de {alimentadores} en {proyecto}',
                 'Escanea el alimentador {alimentadores} dentro del proyecto {proyecto}'),
    'verificar_convergencia': ('comprueba si converge el proyecto {proyecto}', 'corre un flujo de prueba en {proyecto} sin grabar',
                               'mira si {proyecto} sigue resolviendo el flujo',
                               'Verifica la convergencia del proyecto {proyecto}'),
    'carga_nueva_sola': ('conecta solo la carga {sed} en {alimentadores} del proyecto {proyecto}',
                         'agrega unicamente {sed} a {alimentadores} en {proyecto}',
                         'incorpora la carga nueva {sed} sola sobre {alimentadores} de {proyecto}',
                         'Conecta la carga nueva {sed} por si sola en {alimentadores} dentro de {proyecto}'),
    'proyecto_entero': ('haz el proyecto completo del sistema {sistema} con {periodo}',
                        'lleva el sistema {sistema} etapa por etapa con {periodo}',
                        'procesa todas las etapas de {sistema} para {periodo}',
                        'Arma el proyecto entero del sistema {sistema} usando la medicion de {periodo}'),
    'leer_solicitud': ('lee la solicitud del cliente en {ruta}', 'extrae los datos del solicitante de {ruta}',
                       'propon los datos de la carta {ruta}', 'Lee los documentos del solicitante que estan en {ruta}'),
    'descargar_resultados': ('prepara el zip con los resultados de {alimentadores}', 'dame el enlace de descarga de {alimentadores}',
                             'empaqueta las salidas de {alimentadores}', 'Genera la descarga de los resultados de {alimentadores}'),
    'pronostico': ('pronostica la demanda de {alimentadores} con el libro {ruta}', 'proyecta la cabecera de {alimentadores} usando {ruta}',
                   'haz el pronostico de demanda de {alimentadores} desde {ruta}',
                   'Estima la demanda futura de cabecera de {alimentadores} con {ruta}'),
    'enviar_informe': ('prepara el correo con el informe {ruta}', 'deja listo el envio por correo de {ruta}',
                       'adjunta {ruta} a un correo para el cliente', 'Prepara el envio del informe {ruta} por correo electronico'),
    'publicar_nube': ('publica la salida {ruta} en drive', 'deja lista la publicacion de {ruta} en onedrive',
                      'sube {ruta} a la nube del operador', 'Prepara la publicacion de {ruta} en la nube'),
    'compartir_nube': ('comparte en solo lectura el expediente publicado', 'da permiso de lectura al expediente de la nube',
                       'prepara compartir el expediente que ya se publico', 'Deja listo compartir el expediente publicado en la nube'),
    'importar_nube': ('abre el selector de drive para traer un archivo', 'trae a una entrada un fichero de onedrive',
                      'importa un documento desde la nube', 'Abre el selector de la nube para importar un fichero a una entrada'),
    'conectar_nube': ('vincula mi cuenta de google drive', 'deja lista la conexion con microsoft',
                      'conecta la cuenta de onedrive', 'Prepara la conexion de la cuenta de Google'),
    'pit_diagnostico': ('diagnostica el plan de inversiones de transmision con {ruta}', 'haz el diagnostico anual del pit usando {ruta}',
                        'evalua el pit del area de demanda con {ruta}', 'Prepara el diagnostico del PIT del area con el libro {ruta}'),
    'pit_expediente': ('arma el expediente pit con los formatos de {ruta}', 'prepara el expediente del plan de inversiones desde {ruta}',
                       'genera el expediente pit del periodo con {ruta}', 'Elabora el expediente del PIT del area usando {ruta}'),
    'vad_crear_estudio': ('crea un estudio nuevo de costos vad', 'abre el estudio del vad para el grupo de la empresa',
                          'inicia el estudio de costos del vad del periodo', 'Crea el estudio de costos del VAD de la empresa'),
    'vad_empresa_modelo': ('arma la empresa modelo del vad con el caso {ruta}',
                           'dimensiona la empresa modelo sistema por sistema con {ruta}',
                           'construye la empresa modelo usando {ruta}', 'Prepara la empresa modelo del VAD con la carpeta {ruta}'),
    'plano_maniobra': ('abre en el plano la maniobra de {alimentadores}', 'cierra en una variacion el seccionador de {alimentadores}',
                       'opera en el plano el interruptor de {alimentadores} y estudialo',
                       'Abre la maniobra del alimentador {alimentadores} en una variacion del plano'),
    'benchmark_anonimo': ('arma el benchmark anonimizado de la fuente cargada', 'genera en local el conjunto de referencia anonimo',
                          'produce el benchmark sin nombres de la red', 'Genera el benchmark anonimizado de la red TXT cargada'),
    'vnr_estudio': ('calcula el valor nuevo de reemplazo de la red', 'haz el vnr por la guia 232',
                    'prepara el estudio vnr del espacio', 'Elabora el estudio VNR de la red con el SICODI de la empresa'),
    'clientes_fijos_evolucion': ('muestra la evolucion mensual de los fijos de {alimentadores}',
                                 'como cambian mes a mes los clientes fijos de {alimentadores}',
                                 'serie de clientes fijos de {alimentadores}',
                                 'Presenta la evolucion de los clientes fijos de {alimentadores} mes a mes'),
    'normativa_comprobar': ('verifica las huellas de la biblioteca normativa', 'comprueba la vigencia de las normas registradas',
                            'revisa las fuentes oficiales de las normas',
                            'Comprueba las fuentes oficiales de la biblioteca normativa y su vigencia'),
    'normativa_agregar': ('anade la norma del fichero {ruta}', 'incorpora a la biblioteca la norma {ruta}',
                          'registra la norma de {ruta} en la capa del usuario',
                          'Agrega a la biblioteca normativa la norma del archivo {ruta}'),
    'normativa_regenerar': ('regenera el registro de la guia 232', 'vuelve a generar los formatos 217 desde su fuente',
                            'reconstruye el registro del coes',
                            'Regenera el registro normativo de la Guia VNR desde su fuente oficial'),
    'asignar_entrada': ('pon {ruta} en la casilla de equipos', 'asigna el fichero {ruta} a la entrada de cargas',
                        'usa {ruta} como entrada de la red', 'Asigna el archivo {ruta} a la casilla de la red del espacio'),
    'subir_fuente_empresa': ('sube el libro {ruta} a las fuentes de la empresa', 'registra {ruta} como libro de demanda de la empresa',
                             'carga {ruta} en la carpeta de fuentes de la empresa',
                             'Sube el libro {ruta} a las fuentes de la empresa para su anio'),
}

#: 047:RF-72: la fuente real de la ruta de cada tarea, cuando la hay; por defecto, el libro de cargas nuevas.
RUTA_DE_FUENTE = {'asignar_entrada': 'red', 'pronostico': 'mediciones', 'subir_fuente_empresa': 'mediciones'}
#: 047:RF-72: lo que ninguna fuente del corpus aporta, sintético controlado: un valor por partición, declarado.
_LOTE = {'entrenamiento': '01', 'seleccion': '02', 'calibracion': '03', 'prueba': '04'}
RUTAS_SINTETICAS = {
    'leer_solicitud': 'D:/solicitudes/lote_{lote}/carta_solicitante.pdf',
    'pit_diagnostico': 'D:/pit/lote_{lote}/libro_red_area.xlsx',
    'pit_expediente': 'D:/pit/lote_{lote}/libro_red_area.xlsx',
    'vad_empresa_modelo': 'D:/vad/lote_{lote}/caso_vad',
    'normativa_agregar': 'D:/normas/lote_{lote}/norma_usuario.json',
    'enviar_informe': 'D:/salida/lote_{lote}/informe_estudio.docx',
    'publicar_nube': 'D:/salida/lote_{lote}/expediente',
}
#: Los seudónimos de cada tipo de valor de la fuente y de las rutas, por el nombre de la fuente.
_PREFIJO = {'alimentadores': 'AL', 'sed': 'SED', 'set': 'SET', 'sistema': 'SIS', 'proyecto': 'PROY_'}
_RUTA_SEUDONIMA = {'red': 'D:/datos/red_de_la_fuente', 'loads': 'D:/datos/cargas_de_la_fuente',
                   'equipment': 'D:/datos/equipos_de_la_fuente', 'estructura': 'D:/datos/estructura_de_sistemas',
                   'mediciones': 'D:/datos/mediciones_de_cabecera', 'nuevos_clientes': 'D:/datos/cargas_nuevas'}
_SET = re.compile(r'^(SE\d+)\b')


def plantillas_de(tarea: str, parte: str) -> list[str]:
    """Las frases de una tarea en una partición; las columnas no se cruzan (047:RF-71)."""
    if tarea in TAREAS_HASTA_069:
        columnas = (FAMILIAS[tarea][0], FAMILIAS[tarea][1], FAMILIAS[tarea][2], PRUEBA_NUEVA[tarea])
    else:
        columnas = CURRICULO_CONTRATO[tarea]
    if parte == 'entrenamiento':
        return list(dict.fromkeys([*TAREAS[tarea].plantillas, *ESTILO_REAL.get(tarea, ()), columnas[0]]))
    return [columnas[PARTICIONES.index(parte)]]


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


class Seudonimos:
    """El mismo original da siempre el mismo seudónimo; el mapa guarda solo la huella del original (047:RF-70)."""

    def __init__(self):
        self._mapa: dict[tuple[str, str], str] = {}
        self._usados: Counter = Counter()

    def de(self, tipo: str, original: str) -> str:
        clave = (tipo, original)
        if clave not in self._mapa:
            self._usados[tipo] += 1
            n = self._usados[tipo]
            self._mapa[clave] = f'{_PREFIJO[tipo]}{n:03d}' if tipo != 'sed' else f'SED{n:05d}'
        return self._mapa[clave]

    def ruta(self, fuente: str, original: str) -> str:
        clave = ('ruta', original)
        if clave not in self._mapa:
            self._mapa[clave] = _RUTA_SEUDONIMA[fuente] + Path(original.replace('\\', '/')).suffix.lower()
        return self._mapa[clave]

    def registro(self) -> list[dict]:
        return [{'tipo': t, 'seudonimo': s, 'sha256_original': _sha(o)} for (t, o), s in sorted(self._mapa.items())]


def contextos_seudonimos(contextos: list[dict], copia_de: Callable[[dict], dict]) -> tuple[list[dict], Seudonimos]:
    """Los contextos del v6 con sus valores seudonimizados y sus fuentes en la custodia del v7 (047:RF-70, RF-73).

    ``copia_de`` da, para una evidencia de fuente, la evidencia de su copia custodiada (misma sha256 y bytes). Las
    pertenencias no cambian: cada SED sigue en su alimentador y cada proyecto en los suyos, con otro nombre.
    """
    s = Seudonimos()
    nuevos = []
    for c in sorted(contextos, key=lambda x: x['network_id']):
        alimentador = s.de('alimentadores', c['alimentador'])
        fuentes = {k: copia_de(f) for k, f in sorted(c['fuentes'].items())}
        sistema = c.get('sistema') or None
        m = _SET.match((sistema or {}).get('linea') or '')
        nuevos.append({
            'network_id': 'NET_' + alimentador, 'alimentador': alimentador,
            'source_fingerprint': c['source_fingerprint'], 'particion': c['particion'],
            'seds': [{'valor': s.de('sed', x['valor']), 'section_sha256': _sha(x['section']),
                      'device_sha256': _sha(x['device'])} for x in c['seds']],
            'proyectos': [{'valor': s.de('proyecto', p['valor']),
                           'fuente': {**copia_de(p['fuente']),
                                      'localizador': 'pf_project_bindings#sha256=' + _sha(p['fuente']['localizador'])[:16]}}
                          for p in c['proyectos']],
            'sistema': ({'valor': s.de('sistema', sistema['valor']), 'pagina': sistema.get('pagina'),
                         'linea_sha256': _sha(sistema.get('linea') or '')} if sistema else None),
            'set': {'valor': s.de('set', m[1]), 'pagina': (sistema or {}).get('pagina')} if m else None,
            'periodos': list(c['periodos']),
            'ruta': s.ruta('nuevos_clientes', c['ruta']),
            'rutas': {k: s.ruta(k, c['fuentes'][k]['ruta']) for k in sorted(c['fuentes']) if k in _RUTA_SEUDONIMA},
            'fuentes': fuentes,
            'network_sha256': _sha(c['network_id'])})
    return nuevos, s


def _valores(c: dict, tarea: str, parte: str, i: int) -> tuple[dict[str, str], dict[str, str]]:
    """Los valores de una fila y, por tipo, su origen: ``fuente`` o ``sintetico_controlado`` (047:RF-72)."""
    proyecto = c['proyectos'][i % len(c['proyectos'])] if c['proyectos'] else None
    sed = c['seds'][i % len(c['seds'])] if c['seds'] else None
    ruta = (RUTAS_SINTETICAS[tarea].format(lote=_LOTE[parte]) if tarea in RUTAS_SINTETICAS
            else c['rutas'].get(RUTA_DE_FUENTE.get(tarea, 'nuevos_clientes'), c['ruta']))
    valores = {'alimentadores': c['alimentador'], 'ruta': ruta, 'numero': '1',
               'texto': 'la lectura de ' + Path(c['ruta']).name, 'subtipo': 'alimentación de carga nueva',
               'periodo': c['periodos'][i % len(c['periodos'])]}
    origen = {'ruta': 'sintetico_controlado' if tarea in RUTAS_SINTETICAS else 'fuente'}
    if proyecto:
        valores['proyecto'] = proyecto['valor']
    if c.get('sistema'):
        valores['sistema'] = c['sistema']['valor']
    if c.get('set'):
        valores['set'] = c['set']['valor']
    if sed:
        valores['sed'] = sed['valor']
    return valores, origen


def _evidencias(c: dict, tipos: set[str], proyecto: dict | None, sed_i: int | None, sintetica: bool) -> list[dict]:
    ev = [{**c['fuentes'][k], 'localizador': ('SECTION/FEEDER#sha256=' + c['network_sha256'][:16]) if k == 'red'
           else c['fuentes'][k]['localizador']} for k in ('red', 'loads', 'equipment')]
    if proyecto and 'proyecto' in tipos:
        ev.append(proyecto['fuente'])
    for tipo, archivo in (('sistema', 'estructura'), ('set', 'estructura'), ('periodo', 'mediciones')):
        if tipo in tipos and c['fuentes'][archivo] not in ev:
            ev.append(c['fuentes'][archivo])
    if 'ruta' in tipos and not sintetica:
        ev.append(c['fuentes']['nuevos_clientes'])
    if sed_i is not None and 'sed' in tipos:
        sed = c['seds'][sed_i]
        ev[1] = {**c['fuentes']['loads'], 'localizador': 'CUSTOMER LOADS#sha256=' + sed['section_sha256'][:16]}
    return ev


def construir_corpus_contrato(contextos: list[dict], *, norma: dict, humanas: Iterable[dict] = (),
                              vedados: Iterable[str] = (), presupuesto: dict | None = None) -> tuple[list[dict], dict]:
    """047:RF-69 a RF-72: las filas del v7 para las 67 tareas de ``TAREAS`` y su manifiesto, sin sellar.

    ``contextos`` ya seudonimizados (:func:`contextos_seudonimos`); ``norma``, la evidencia custodiada de la política;
    ``humanas``, las órdenes humanas reservadas, que no entran; ``vedados``, textos de otros conjuntos sellados del
    proyecto que tampoco entran (se comparan por su forma canónica, sin leerlos para redactar).
    """
    p = {**PRESUPUESTO, **(presupuesto or {})}
    if not contextos:
        raise ValueError('se requieren contextos reales')
    fuera = {texto_canonico(r['texto']) for r in humanas} | {texto_canonico(t) for t in vedados}
    por_proyecto = defaultdict(list)
    for c in contextos:
        for pr in c['proyectos']:
            por_proyecto[(c['particion'], pr['valor'])].append(c)
    filas, vistos, omitidos, excluidas = [], {}, Counter(), Counter()
    for c in contextos:
        parte = c['particion']
        for tarea in sorted(TAREAS):
            for plantilla in plantillas_de(tarea, parte):
                for i, prefijo in enumerate(PREFIJOS):
                    rnd = random.Random(int(huella([c['network_id'], tarea, plantilla, i])[:8], 16))
                    valores, origen = _valores(c, tarea, parte, i)
                    proyecto = c['proyectos'][i % len(c['proyectos'])] if c['proyectos'] else None
                    if tarea in ('unir', 'transferencia'):
                        candidatos = (por_proyecto[(parte, proyecto['valor'])] if proyecto else
                                      [v for v in contextos if v['particion'] == parte])
                        otros = [v['alimentador'] for v in candidatos if v['network_id'] != c['network_id']]
                        if not otros:
                            omitidos[(parte, tarea)] += 1; continue
                        valores['alimentadores'] += ' y ' + otros[i % len(otros)]
                    if any(not valores.get(t) for t in re.findall(r'\{(\w+)\}', plantilla)):
                        omitidos[(parte, tarea)] += 1; continue
                    texto, datos = renderizar_orden(prefijo + plantilla, valores, rnd)
                    canonico = texto_canonico(texto)
                    if canonico in fuera:
                        excluidas[parte] += 1; continue
                    # La misma orden escrita con otros espacios en la misma partición y tarea es una repetición; en
                    # otra partición u otra tarea, una fuga o una contradicción.
                    firma = (parte, tarea)
                    if canonico in vistos:
                        if vistos[canonico] != firma:
                            raise ValueError(f'solapamiento o contradiccion en instrucciones: {tarea} en {parte}')
                        continue
                    vistos[canonico] = firma
                    tipos = {t for _, _, t in datos}
                    sinteticos = sorted(t for t in tipos if origen.get(t) == 'sintetico_controlado')
                    sed_i = (i % len(c['seds'])) if c['seds'] else None
                    r = {'texto': texto, 'tarea': tarea, 'datos': datos, 'particion': parte,
                         'group_id': huella({'plantilla': plantilla, 'tarea': tarea}),
                         'context_id': huella([c['source_fingerprint'], c['network_id']]),
                         'quality': CALIDAD, 'fuentes': _evidencias(c, tipos, proyecto, sed_i, bool(sinteticos)),
                         'origen': ORIGEN_FILA,
                         'origen_declarado': 'sintetico_controlado' if sinteticos else 'maestro',
                         'valores_sinteticos': sinteticos, 'seudonimizado': True,
                         'ejecutado': False, 'observacion_humana': False}
                    r['respuesta'] = _respuesta_de_spans(r)
                    r['record_id'] = huella(r)
                    filas.append(r)
    preparadas = []
    for parte, clave in (('entrenamiento', 'max_train_por_tarea'), ('seleccion', 'seleccion_por_tarea'),
                         ('calibracion', 'calibracion_por_tarea'), ('prueba', 'prueba_por_tarea')):
        for tarea in sorted(TAREAS):
            candidatos = [r for r in filas if r['particion'] == parte and r['tarea'] == tarea]
            if parte != 'entrenamiento' and len(candidatos) < p[clave]:
                raise ValueError(f'fuentes insuficientes para {parte} de {tarea}: {len(candidatos)}/{p[clave]}')
            random.Random(int(huella([parte, tarea, 4721])[:8], 16)).shuffle(candidatos)
            preparadas.extend(candidatos[:p[clave]])
    filas = preparadas
    for parte in PARTICIONES:
        faltan = set(TAREAS) - {r['tarea'] for r in filas if r['particion'] == parte}
        if faltan:
            raise ValueError(f'faltan tareas con fuentes reales en {parte}: {sorted(faltan)}')
    fuente_real = next(r['fuentes'] for r in filas if r['particion'] == 'entrenamiento')
    for orden in ABSTENCION_TRAIN:
        for prefijo in PREFIJOS:
            r = {'texto': prefijo + orden, 'tarea': None, 'datos': [], 'particion': 'entrenamiento',
                 'group_id': huella(['abstencion', orden]), 'context_id': huella(['control_politica', 'train']),
                 'quality': CALIDAD, 'fuentes': [norma, *fuente_real],
                 'origen': 'maestro de sesion (Claude); control de politica fundamentado, no operacion observada',
                 'origen_declarado': 'maestro', 'valores_sinteticos': [], 'seudonimizado': True,
                 'ejecutado': False, 'observacion_humana': False}
            r['respuesta'] = _respuesta_de_spans(r); r['record_id'] = huella(r); filas.append(r)
    sinteticos = defaultdict(set)
    for r in filas:
        for a, b, t in r['datos']:
            if t in r['valores_sinteticos']:
                sinteticos[t].add(r['texto'][a:b])
    meta = {'schema_version': SCHEMA, 'perfil_prompt': PERFIL, 'dataset_hash': huella(filas),
            'contrato_tareas': sorted(TAREAS), 'huella_contrato': huella(sorted(TAREAS)),
            'por_particion': dict(Counter(r['particion'] for r in filas)),
            'por_tarea': {pp: dict(Counter(r['tarea'] for r in filas if r['particion'] == pp)) for pp in PARTICIONES},
            'por_origen': dict(Counter(r['origen_declarado'] for r in filas)),
            # 047:RF-74: la prueba y la selección quedan fijadas aquí, antes de sellar y de entrenar.
            'apartadas_preparadas': {pp: huella([r for r in filas if r['particion'] == pp])
                                     for pp in PARTICIONES if pp != 'entrenamiento'},
            'ordenes_humanas': 0, 'instrucciones_redactadas_maestro': True,
            'humanas_reservadas': len({texto_canonico(r['texto']) for r in humanas}),
            'humanas_text_hashes': sorted({huella(texto_canonico(r['texto'])) for r in humanas}),
            'vedados_otros_sellados': len({texto_canonico(t) for t in vedados}),
            'excluidas_por_reserva': dict(excluidas),
            'valores_sinteticos': {t: sorted(v) for t, v in sorted(sinteticos.items())},
            'entidades_red_fuentes_reales': True, 'valores_seudonimizados': True, 'resultados_nativos_generados': 0,
            'presupuesto_corpus': p, 'confianza_anotada': '0.9 es etiqueta de entrenamiento, no posterior calibrado',
            'omitidas_sin_fuente': {f'{pp}/{t}': n for (pp, t), n in sorted(omitidos.items())},
            'maestro': MAESTRO_V7}
    validar_corpus_contrato(filas, meta)
    return filas, meta


def validar_corpus_contrato(filas: list[dict], meta: dict, *, custodia=None,
                            nombres: Callable[[str], list] | None = None) -> None:
    """047:RF-69 a RF-74: lo que admite el corpus v7; ``nombres`` busca nombres reales en todo lo escrito."""
    if (meta.get('schema_version') != SCHEMA or meta.get('perfil_prompt') != PERFIL or huella(filas) != meta.get('dataset_hash')
            or meta.get('contrato_tareas') != sorted(TAREAS)):
        raise ValueError('integridad del corpus v7 invalida o de otro contrato de tareas')
    textos, grupos, contextos, fuentes = {}, {}, {}, {}
    for r in filas:
        if r.get('record_id') != huella({k: v for k, v in r.items() if k != 'record_id'}):
            raise ValueError('registro modificado')
        if r.get('particion') not in PARTICIONES or r.get('quality') != CALIDAD or not r.get('fuentes'):
            raise ValueError('particion, calidad o fuentes invalidas')
        if r.get('origen_declarado') not in ORIGENES_EN_PARTICION or not str(r.get('origen') or '').strip():
            raise ValueError('fila sin origen declarado (maestro o sintetico controlado)')
        if r.get('observacion_humana') or r.get('ejecutado') or 'resultado_electrico' in r:
            raise ValueError('no presentar solicitudes del maestro como observacion o resultado real')
        if (r['origen_declarado'] == 'sintetico_controlado') != bool(r.get('valores_sinteticos')):
            raise ValueError('valores sinteticos sin declarar en su origen')
        if _respuesta_de_spans(r) != r.get('respuesta'):
            raise ValueError('respuesta distinta de sus etiquetas verificadas')
        for tabla, clave in ((textos, texto_canonico(r['texto'])), (grupos, r['group_id']), (contextos, r['context_id'])):
            if clave in tabla and tabla[clave] != r['particion']:
                raise ValueError('fuga entre particiones')
            tabla[clave] = r['particion']
        for f in r['fuentes']:
            fuentes.setdefault((f['ruta'], f['sha256']), f)
    for parte in PARTICIONES:
        if {r['tarea'] for r in filas if r['particion'] == parte} - {None} != set(TAREAS):
            raise ValueError(f'la particion {parte} no cubre el contrato vigente')
    if nombres is not None:
        # ``datos`` son posiciones del texto: sus cifras sueltas no son nombres y su valor ya está en el texto.
        hallazgos = sum(len(nombres(json.dumps({k: v for k, v in r.items() if k != 'datos'}, ensure_ascii=False)))
                        for r in filas)
        if hallazgos:
            raise ValueError(f'el corpus v7 lleva {hallazgos} nombres reales; se seudonimizan antes de sellar')
    for f in fuentes.values():
        verificar_fuente(f, custodia=custodia)


def es_v7(dataset: Path) -> bool:
    """Si el corpus de ``dataset`` es un v7 (esquema 3); un manifiesto que no se lee no lo es."""
    try:
        return json.loads((Path(dataset) / 'dataset_manifest.json').read_text(encoding='utf-8')).get('schema_version') == SCHEMA
    except (OSError, ValueError, AttributeError):
        return False


def sellar_v7(dataset: Path, destino: Path) -> dict:
    """047:RF-69, RF-74: sella el v7 con su validador y el prompt del contrato vigente."""
    return sellar_particiones(Path(dataset), Path(destino), validar=validar_corpus_contrato, sistema=sistema_alumno_contrato())


def auditar_v7(dataset: Path) -> dict:
    """047:RF-69, RF-72: la auditoría de fuentes y entidades del v7 sellado, con su validador."""
    return auditar_fuentes_corpus(Path(dataset), validar=validar_corpus_contrato)


def reservar_humanas_contrato(eventos: Iterable[dict]) -> list[dict]:
    """Las órdenes humanas confirmadas o corregidas de cualquier tarea del contrato vigente, sin repetir (origen humano)."""
    unicas: dict[str, dict] = {}
    for r in eventos:
        if r.get('origen') not in ('confirmado', 'corregido') or r.get('tarea') not in TAREAS or not str(r.get('texto') or '').strip():
            continue
        clave = texto_canonico(r['texto'])
        if clave in unicas and (unicas[clave]['tarea'], unicas[clave].get('datos')) != (r['tarea'], r.get('datos')):
            raise ValueError('anotaciones humanas contradictorias')
        unicas[clave] = r
    return list(unicas.values())


def custodiar_copias(evidencias: Iterable[dict], resolver: Callable[[dict], Path], destino: Path) -> dict[tuple, dict]:
    """047:RF-73: copia cada fuente distinta a ``destino/fuentes/<sha256>.bin`` y comprueba su sha256 y sus bytes."""
    carpeta = destino / 'fuentes'
    carpeta.mkdir(parents=True, exist_ok=True)
    copias = {}
    for e in evidencias:
        clave = (e['sha256'], e['bytes'])
        if clave in copias:
            continue
        origen = resolver(e)
        copia = carpeta / f'{e["sha256"]}.bin'
        if not copia.exists():
            with Path(origen).open('rb') as entrada, copia.open('xb') as salida:
                shutil.copyfileobj(entrada, salida)
        evidencia = custodiar(copia, localizador='archivo completo')
        if (evidencia['sha256'], evidencia['bytes']) != clave:
            raise ValueError(f'la copia custodiada de {e["sha256"][:12]} no casa por sha256 o por bytes')
        copias[clave] = evidencia
    return copias


def preparar_v7(base: Path, destino: Path, *, nombres: Callable[[str], list] | None = None,
                humanas_extra: Iterable[dict] = (), vedados: Iterable[str] = (), presupuesto: dict | None = None) -> dict:
    """047:RF-69 a RF-74: prepara el corpus v7 sin sellar desde el corpus sellado v6 de ``base``.

    Del v6 solo se leen su manifiesto, sus contextos, sus órdenes humanas reservadas y sus fuentes resueltas (por su
    sha256); ninguna de sus particiones. Escribe en ``destino`` ``corpus.json``, ``dataset_manifest.json``,
    ``contextos.json``, ``humanas_reservadas.json``, ``seudonimos.json`` y la custodia ``fuentes/``; después se sella con
    ``tools/llm_destilar.py sellar --dataset``.
    """
    from ...dominio.util import publicar_duradero
    base, destino = Path(base), Path(destino)
    if destino.exists():
        raise ValueError('destino existente conservado; use una ruta nueva')
    meta_base = json.loads((base / 'dataset_manifest.json').read_text(encoding='utf-8'))
    resueltas = {(f['sha256'], f['bytes']): Path(f['resuelta'])
                 for f in (meta_base.get('resellado') or {}).get('fuentes_resueltas') or []}

    def resolver(e: dict) -> Path:
        # La copia del 065 por su sha256; ``custodiar_copias`` comprueba que la copia nueva case con lo sellado.
        return resueltas.get((e['sha256'], e['bytes'])) or Path(e['ruta'])

    for clave in ('contextos_fuente', 'humanas_reservadas_archivo'):
        verificar_fuente(meta_base[clave])
    contextos = json.loads(Path(meta_base['contextos_fuente']['ruta']).read_text(encoding='utf-8'))
    humanas_base = json.loads(Path(meta_base['humanas_reservadas_archivo']['ruta']).read_text(encoding='utf-8'))
    politica = (meta_base.get('politica_custodiada') or {}).get('copia')
    if not politica:
        raise ValueError('el corpus base no declara su política custodiada')
    evidencias = [politica, *(f for c in contextos for f in c['fuentes'].values()),
                  *(p['fuente'] for c in contextos for p in c['proyectos'])]
    destino.mkdir(parents=True)
    try:
        copias = custodiar_copias(evidencias, resolver, destino)

        def copia_de(e: dict) -> dict:
            return {**copias[(e['sha256'], e['bytes'])], 'localizador': e['localizador']}

        nuevos, seudonimos = contextos_seudonimos(contextos, copia_de)
        humanas = reservar_humanas_contrato([*humanas_base, *humanas_extra])
        norma = {**copias[(politica['sha256'], politica['bytes'])], 'localizador': politica['localizador']}
        filas, meta = construir_corpus_contrato(nuevos, norma=norma, humanas=humanas, vedados=vedados,
                                                presupuesto=presupuesto)
        limpias = [h for h in humanas if not (nombres and nombres(h['texto']))]
        archivos = {'seudonimos.json': seudonimos.registro(), 'contextos.json': nuevos, 'humanas_reservadas.json': limpias}
        for nombre, datos in archivos.items():
            publicar_duradero(destino / nombre, json.dumps(datos, ensure_ascii=False, indent=1))
        meta['seudonimos'] = custodiar(destino / 'seudonimos.json', localizador='seudonimo y huella del original')
        meta['humanas_reservadas_con_nombre_fuera_del_fichero'] = len(humanas) - len(limpias)
        meta['base'] = {'manifiesto': custodiar(base / 'dataset_manifest.json', localizador='corpus sellado v6'),
                        'dataset_hash': meta_base['dataset_hash'], 'prompt_hash': meta_base.get('prompt_hash'),
                        'tareas': len(meta_base.get('por_tarea', {}).get('prueba', {})),
                        'source_fingerprint': sorted({c['source_fingerprint'] for c in contextos}),
                        'conteos_reales': (meta_base.get('fuentes_manifest') or {}).get('conteos_reales')}
        meta['fuentes_custodiadas'] = sorted(copias.values(), key=lambda e: e['sha256'])
        meta['sin_nombres'] = {'comprobado': nombres is not None}
        validar_corpus_contrato(filas, meta, nombres=nombres)
        if nombres is not None:
            for nombre in ('contextos.json', 'seudonimos.json', 'humanas_reservadas.json'):
                if nombres((destino / nombre).read_text(encoding='utf-8')):
                    raise ValueError(f'{nombre} lleva nombres reales')
            if nombres(json.dumps(meta, ensure_ascii=False)):
                raise ValueError('el manifiesto del v7 lleva nombres reales')
        publicar_duradero(destino / 'corpus.json', json.dumps(filas, ensure_ascii=False))
        publicar_duradero(destino / 'dataset_manifest.json', json.dumps(meta, ensure_ascii=False, indent=2))
    except BaseException:
        shutil.rmtree(destino, ignore_errors=True)
        raise
    return meta
