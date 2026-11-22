"""Catálogo de lo que el asistente sabe hacer (spec 026, RF-8 a RF-11).

Cada tarea dice qué datos necesita, si escribe (y por eso pide confirmación, RF-8), cómo
se ejecuta y con qué frases se suele pedir. Las frases son plantillas: ``[a|b]`` elige
una variante y ``{tipo}`` es un dato que se rellena con nombres reales del espacio
(``sinteticos.py``, RF-21). La ejecución no se define aquí sino en ``ejecutor.py``, por
las mismas rutas de la web (P5): este fichero solo nombra la función de ``web/services``
(o la herramienta de ``tools/``, o ``modulo.funcion`` de un router de ``web/``) que hace el trabajo, y su prueba
comprueba que existe.

Modos: ``consulta`` se responde en la misma petición con lo que ya hay; ``trabajo`` va por
las rutas y la cola de la web; ``proceso`` lanza una herramienta de ``tools/``; ``etapas``
encadena varias tareas con una sola confirmación de su lista (067:RF-37, 070:RF-51).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: Tipos de dato que el intérprete reconoce y el plan contrasta (RF-2, RF-6).
#: 070:RF-18: los nuevos, siempre al final: la etiqueta de un modelo heredado es su posición en esta lista.
TIPOS_DATO = ('proyecto', 'alimentadores', 'sistema', 'periodo', 'caso', 'numero', 'ruta',
              'sed', 'subtipo', 'texto', 'set', 'estudio', 'alcance', 'anio')


@dataclass(frozen=True)
class Dato:
    nombre: str
    tipo: str
    obligatorio: bool = True
    descripcion: str = ''


@dataclass(frozen=True)
class Tarea:
    nombre: str
    descripcion: str
    datos: tuple[Dato, ...]
    escribe: bool
    modo: str
    funcion: str
    plantillas: tuple[str, ...]
    #: 067:RF-36: expresiones de lo que la orden nombra sin ambigüedad, para reconocer la tarea
    #: mientras el Transformer en uso no la haya aprendido (no se tocan sus pesos).
    frases_literales: tuple[str, ...] = ()
    #: 070:RF-41, RF-47: «¿qué SED tiene …?» es una orden de estas tareas aunque venga como pregunta;
    #: en las demás, una pregunta sobre la tarea no la lanza (067:RF-36).
    literal_en_pregunta: bool = False

    def dato(self, nombre: str) -> Dato | None:
        return next((d for d in self.datos if d.nombre == nombre), None)


P = Dato('proyecto', 'proyecto', descripcion='proyecto de DIgSILENT')
P_OPC = Dato('proyecto', 'proyecto', obligatorio=False, descripcion='proyecto de DIgSILENT')
A = Dato('alimentadores', 'alimentadores', descripcion='alimentadores, o «todos»')
A_OPC = Dato('alimentadores', 'alimentadores', obligatorio=False, descripcion='alimentadores, o «todos»')
S = Dato('sistema', 'sistema', descripcion='sistema eléctrico o zonal de la estructura')
PER = Dato('periodo', 'periodo', descripcion='mes AAAA-MM o año AAAA')
N = Dato('numero', 'numero', obligatorio=False, descripcion='cuántos escenarios')
SED = Dato('sed', 'sed', descripcion='SED de la carga del informe')
SUB = Dato('subtipo', 'subtipo', obligatorio=False, descripcion='subtipo de estudio')
TXT = Dato('texto', 'texto', descripcion='la pregunta o el texto')
SET = Dato('set', 'set', descripcion='SET de la estructura')
SET_OPC = Dato('set', 'set', obligatorio=False, descripcion='SET de la estructura')
ESTUDIO_OPC = Dato('estudio', 'estudio', obligatorio=False, descripcion='el estudio del catálogo, si es solo uno')
LIBROS = Dato('ruta', 'ruta', obligatorio=False, descripcion='carpeta de los libros de demanda; sin ella, la del espacio')
CAPEX = Dato('ruta', 'ruta', obligatorio=False, descripcion='libro CAPEX')
INFORME = Dato('ruta', 'ruta', obligatorio=False, descripcion='el informe de la salida; sin él, el último cerrado')
SALIDA = Dato('ruta', 'ruta', obligatorio=False, descripcion='la carpeta de la salida; sin ella, toda la salida')
ENTRADAS_PIT = Dato('ruta', 'ruta', descripcion='el libro de la red y la proyección del área (y las alternativas)')
CASO_VAD = Dato('ruta', 'ruta', descripcion='la carpeta del caso del VAD, con su sistemas.json')
NORMA_JSON = Dato('ruta', 'ruta', descripcion='el fichero .json de la norma, con el esquema de la biblioteca normativa')
FICHERO_ENTRADA = Dato('ruta', 'ruta', descripcion='el fichero de la máquina que entra en la casilla')
LIBRO_EMPRESA = Dato('ruta', 'ruta', descripcion='el libro de la empresa que se sube a sus fuentes')

_TAREAS = (
    # ------------------------------------------------------------ consultas (sin confirmar)
    Tarea('estado', 'Qué hay cargado en el espacio, sus alimentadores, trabajos y salidas.', (), False,
          'consulta', 'feeder_rows', (
              '[qué|que] hay cargado', '[estado|situación] del espacio', '[qué|que] trabajos están corriendo',
              '[dime|muéstrame|muestrame] el estado', '[cuántos|cuantos] alimentadores hay cargados',
              '[qué|que] salidas hay', '[cómo|como] va [todo|el trabajo]')),
    Tarea('proyectos', 'Los proyectos de DIgSILENT que la web ya conoce.', (), False, 'consulta',
          'pf_proyectos_guardados', (
              '[qué|que|cuáles|cuales] proyectos [hay|tengo] en [digsilent|powerfactory]',
              '[lista|listar|muestra] los proyectos', 'proyectos de [digsilent|powerfactory]')),
    Tarea('resultados_pide', 'Las obras, prioridades y formatos del último PIDE de un proyecto.', (P_OPC,), False,
          'consulta', 'pide_ejecutar', (
              '[resultados|resultado] del pide [de|del proyecto] {proyecto}', '[qué|que] obras propuso el pide',
              '[muéstrame|muestrame|dame] las obras del pide de {proyecto}',
              '[cuál|cual] es la prioridad de las obras del pide', 'formatos del pide de {proyecto}')),
    Tarea('episodios', 'Los episodios del gemelo digital por clase y caso.', (P_OPC,), False, 'consulta',
          'gemelo_episodios', (
              '[cuántos|cuantos] episodios tiene el gemelo', 'episodios del gemelo de {proyecto}',
              '[qué|que] ha aprendido el gemelo', 'búfer del gemelo')),
    Tarea('pregunta', 'Cómo funciona el conversor, con cita de ficheros, funciones y RF.', (TXT,), False,
          'consulta', 'asistente_pregunta', (
              '[cómo|como] {texto}', '[qué|que] hace {texto}', 'explícame {texto}', 'explicame {texto}',
              '[dónde|donde] se {texto}', '[por qué|porque] {texto}', '¿[cómo|como] {texto}?',
              '¿[cómo|como] se {texto}?', '[cómo|como] funciona {texto}', '¿[qué|que] es {texto}?',
              '[dime|explícame] [cómo|como] se {texto}'),
          # 067:RF-36: «¿cómo se calcula la Q de las cargas fijas?» se quedaba sin responder con el modelo al 0,92
          # (auditor, 2026-11-14, F7); con el modelo seguro de otra tarea, sigue mandando el modelo.
          frases_literales=(r'^\W*(?:como se|por que|porque|explica\w*)\b',), literal_en_pregunta=True),
    Tarea('clasificar_informe', 'A qué tipo y subtipo de estudio corresponde un informe o un pedido.',
          (TXT,), False, 'consulta', 'asistente_clasificar', (
              'clasifica [este|el] informe {texto}', '[qué|que] tipo de estudio es {texto}',
              '[a qué|a que] estudio corresponde {texto}')),
    Tarea('buscar_internet', 'Busca librerías, proyectos o artículos, sin datos de la red (RF-29).', (TXT,),
          False, 'consulta', 'asistente_buscar', (
              'busca [librerías|librerias|proyectos] [de|para] {texto}', 'busca en github {texto}',
              '[hay|existe] alguna [librería|libreria] [de|para] {texto}', 'artículos sobre {texto}',
              'busca en [internet|la web|arxiv|pypi] {texto}', '[investiga|busca] {texto} en github')),
    # ------------------------------------------------------------ trabajos que solo leen
    Tarea('leer_proyectos', 'Lee de DIgSILENT la lista de proyectos.', (), False, 'trabajo', 'pf_projects', (
        'lee los proyectos de [digsilent|powerfactory]', 'actualiza la lista de proyectos',
        '[refresca|recarga] los proyectos de [digsilent|powerfactory]')),
    Tarea('evaluar_gemelo', 'Cuánto se apartan de DIgSILENT el modelo del gemelo y la física (024:RF-74).',
          (), False, 'trabajo', 'gemelo_evaluar', (
              '[evalúa|evalua] el gemelo', '[aprendió|aprendio] el [gemelo|modelo|pinn]',
              '[qué|que] error tiene la pinn', '[cuánto|cuanto] se equivoca el gemelo')),
    # ------------------------------------------------------------ trabajos que escriben
    Tarea('cargar_fuente', 'Carga la fuente asignada al espacio.', (), True, 'trabajo', 'load_dataset', (
        'carga la fuente', 'carga los [txt|datos|ficheros]', 'lee la [red|fuente]')),
    Tarea('convertir', 'Convierte alimentadores a DGS, uno por fichero.', (A,), True, 'trabajo', 'convert', (
        'convierte {alimentadores}', '[convertir|genera el dgs de|haz el dgs de] {alimentadores}',
        'pasa a dgs {alimentadores}', 'convierte [todos los alimentadores|todo]',
        '[completa|haz|termina] la conversión de {alimentadores}', 'conversión [de|del alimentador] {alimentadores}',
        'el dgs de {alimentadores}')),
    Tarea('unir', 'Convierte varios alimentadores en una red unida.', (A,), True, 'trabajo', 'convert_group', (
        'une {alimentadores}', '[convierte|genera] {alimentadores} en una red unida',
        'red unida con {alimentadores}', 'junta {alimentadores} en un dgs')),
    Tarea('convertir_sistema', 'Convierte un sistema eléctrico a un DGS por sistema.', (S,), True, 'trabajo',
          'convert_group', (
              'convierte el sistema {sistema}', 'dgs del sistema [eléctrico|electrico] {sistema}',
              'convierte por sistema {sistema}', 'genera el sistema {sistema}')),
    Tarea('sistema_completo', 'Sistema eléctrico de punta a punta: convertir, importar y calibrar (022:RF-56).',
          (S, PER, LIBROS),
          True, 'proceso', 'sistema_web', (
              'calibra el sistema {sistema} con {periodo}', 'calibra {sistema} [para|en|con] {periodo}',
              '[haz|ejecuta] el sistema {sistema} completo [con|para] {periodo}',
              'importa y calibra {sistema} {periodo}', 'sistema {sistema} de punta a punta con {periodo}',
              'calibración del sistema {sistema} [con|en|para] {periodo}',
              '[la|haz la] calibración de {sistema} [con|de] {periodo}')),
    Tarea('flujo', 'Flujo de potencia en DIgSILENT de los alimentadores.', (A,), True, 'trabajo',
          'powerfactory_flow', (
              '[corre|ejecuta|haz] el flujo de {alimentadores}', 'flujo de potencia de {alimentadores}',
              'importa {alimentadores} en [digsilent|powerfactory]')),
    Tarea('verificar_caso_base', 'Verifica el «Caso base» frente al archivo original (spec 015).', (P, A_OPC),
          True, 'trabajo', 'pf_verificar_base', (
              'verifica el caso base de {proyecto}', '[comprueba|revisa] el caso base [de|del proyecto] {proyecto}',
              'verificación del caso base de {proyecto} {alimentadores}')),
    Tarea('cargas_nuevas', 'Integra las cargas nuevas de un Excel en «Con proyecto» (specs 007 y 014).',
          (P, A, Dato('ruta', 'ruta', descripcion='Excel de cargas nuevas')), True, 'trabajo', 'cargas_ejecutar', (
              'integra las cargas nuevas de {ruta} en {proyecto} {alimentadores}',
              'agrega las cargas nuevas del excel {ruta} a {alimentadores} de {proyecto}',
              'carga nueva [en|para] {alimentadores} [de|del proyecto] {proyecto} desde {ruta}')),
    Tarea('obras', 'Aplica en DIgSILENT las obras pendientes del espacio (spec 011).', (P, A), True, 'trabajo',
          'obras_ejecutar', (
              'aplica las obras [de|en] {alimentadores} [de|del proyecto] {proyecto}',
              'implementa las obras pendientes de {proyecto} {alimentadores}',
              'ejecuta las obras de {alimentadores} en {proyecto}')),
    Tarea('estudios', 'Estudios de la red en los casos del proyecto (spec 011).', (P, A, ESTUDIO_OPC), True, 'trabajo',
          'estudios_ejecutar', (
              '[corre|ejecuta|haz] los estudios de {alimentadores} [de|en] {proyecto}',
              'estudios de {proyecto} {alimentadores}', 'estudio de la red de {alimentadores} en {proyecto}')),
    Tarea('obras_escalera', 'Escalera de obras en «Con proyecto»: bancos, sección y terna hasta dejar la red en '
          'norma (025:RF-44).', (P, A, CAPEX), True, 'trabajo', 'obras_escalera', (
              '[haz|corre|ejecuta] la escalera de obras [de|en] {alimentadores} [de|en] {proyecto}',
              'escalera de obras de {proyecto} {alimentadores}',
              '[lanza|aplica] la escalera en {alimentadores} [de|del proyecto] {proyecto}',
              'bancos sección y terna en escalera para {alimentadores} de {proyecto}'),
          frases_literales=(r'\bescalera\b',)),
    Tarea('optimizar_con_proyecto', 'Optimiza «Con proyecto»: escalera carga a carga y SET nueva para las que no '
          'caben (042:RF-13, spec 052).', (P, A, CAPEX, SET_OPC), True, 'trabajo', 'con_proyecto_optimizar', (
              '[optimiza|optimizar] con proyecto [de|en] {alimentadores} [de|en] {proyecto}',
              'optimización de con proyecto de {proyecto} {alimentadores}',
              'optimiza el caso con proyecto de {alimentadores} en {proyecto}',
              'set nueva para las cargas que no caben en {alimentadores} de {proyecto}'),
          frases_literales=(r'optimiz\w*\W+(?:(?:de|del|el|caso)\W+)*con\W+proyecto',)),
    Tarea('transferencia', 'Transferencia de carga entre dos alimentadores (spec 011).', (P, A), True, 'trabajo',
          'transferencia_ejecutar', (
              'transfiere carga entre {alimentadores} [de|en] {proyecto}',
              'transferencia [de|entre] {alimentadores} [de|en] {proyecto}')),
    # La descripción entra en el identificador de cada fila del currículo: cambiarla movía la prueba histórica
    # sellada (069:RF-13, 070:RF-72). Los módulos de la 072 y su año van en el dato «periodo», no aquí.
    Tarea('pide', 'Metodología del PIDE: diagnóstico, obras propias y formatos (024, T13 y T14).',
          (P, A, Dato('periodo', 'periodo', obligatorio=False, descripcion='año de presentación del estudio')),
          True, 'trabajo', 'pide_ejecutar', (
              '[haz|ejecuta|corre] el pide de {proyecto} {alimentadores}', 'plan de inversiones de {proyecto} {alimentadores}',
              'pide [de|del proyecto|para] {proyecto} {alimentadores}', 'diagnóstico pide de {alimentadores} en {proyecto}',
              # 072:RF-29, RF-34: la misma tarea con su plazo; va al final para no mover las semillas de las anteriores.
              '[haz|corre] el planeamiento de largo plazo de {proyecto} {alimentadores}')),
    Tarea('gemelo_aprender', 'Aprendizaje activo del gemelo: escenarios en una copia del proyecto (024, T10).',
          (P, A, N), True, 'trabajo', 'gemelo_aprender', (
              '[que aprenda|aprende] el gemelo con {proyecto} {alimentadores}',
              '[simula|genera] {numero} escenarios de {proyecto} {alimentadores}',
              'aprendizaje activo [de|en] {proyecto} {alimentadores}')),
    Tarea('gemelo_entrenar', 'Reentrena el oráculo PINN del gemelo con lo que hay en el búfer (024, T11).', (),
          True, 'trabajo', 'gemelo_entrenar', (
              'reentrena la pinn', 'entrena el [oráculo|oraculo|modelo] del gemelo', 'reentrena el gemelo')),
    Tarea('gemelo_temporal', 'Gemelo temporal del mes con las curvas de la última máxima (024, T12).', (A_OPC,),
          True, 'trabajo', 'gemelo_temporal', (
              'gemelo temporal [del mes|] [de|para] {alimentadores}', 'reproduce el mes de {alimentadores}',
              '[curvas|demanda] del mes con la gru [de|para] {alimentadores}')),
    Tarea('informe_estudio', 'Informe de estudio eléctrico en Word (spec 017).', (P, A, SUB), True, 'trabajo',
          'informe_estudio', (
              '[haz|genera|escribe] el informe de estudio [de|del alimentador] {alimentadores} [de|en] {proyecto}',
              'informe de estudio eléctrico [de|para] {alimentadores} {proyecto}',
              'informe de {subtipo} [de|para] {alimentadores} en {proyecto}')),
    Tarea('informe_factibilidad', 'Informe de factibilidad de una carga nueva (spec 017).', (P, A, SED, SUB),
          True, 'trabajo', 'informe_factibilidad', (
              '[haz|genera|escribe] el informe de factibilidad de la sed {sed} [de|en] {alimentadores} {proyecto}',
              'factibilidad de la carga [de|en] {sed} {alimentadores} {proyecto}',
              'informe de factibilidad {proyecto} {alimentadores} {sed}')),
    # ------------------------------------------------------------ spec 070, por las mismas rutas de la web
    Tarea('consultar_datos', 'Consulta lo que hay: alimentadores, SED, medidores, clientes fijos, máximas buscadas, años de '
          'medición, catálogo, variaciones escaneadas, proyectos y última calibración, con su fuente (070:RF-41).',
          (A_OPC, P_OPC, SET_OPC, Dato('periodo', 'periodo', obligatorio=False, descripcion='mes AAAA-MM o año AAAA')),
          False, 'consulta', 'sed_de_alimentador', (
              '[qué|que] sed tiene {alimentadores}', 'dame los medidores de {alimentadores}', '[qué|que] variaciones tiene {proyecto}',
              '[qué|que] clientes son fijos en {alimentadores}', '[qué|que] años de medición tengo', 'muéstrame el catálogo de equipos'),
          frases_literales=(
              r'\b(que|cuales|cuantas?|cuantos|dame|dime|lista\w*|muestra\w*|ensename)\b.*\b(seds?|medidor(es)?|variacion(es)?|catalogo)\b',
              r'\b(que|cuales|cuantos|dame|lista\w*|muestra\w*)\b.*\bclientes\b.*\bfijos\b',
              r'\bque clientes\b', r'\b(anos|ano) de medicion\b', r'\bmaximas? (ya )?buscadas?\b',
              r'\bultima calibracion\b', r'\bque alimentadores hay\b(?!.*\bcargad)'),
          literal_en_pregunta=True),
    Tarea('no_disponible', 'Dice por qué un estudio no está disponible: cortocircuito, protecciones, optimización no lineal '
          'y los que el catálogo no ofrece, sin ejecutar nada (070:RF-47).', (ESTUDIO_OPC, P_OPC), False, 'consulta',
          'estudios_catalogo', (
              '[corre|hazme|sácame] el cortocircuito de {proyecto}', 'revisa la coordinación de protecciones de {proyecto}',
              'corre la optimización no lineal de {proyecto}', 'corrientes de falla de {proyecto}'),
          frases_literales=(r'^(?!\W*(que es|que significa|como funciona|como se|explica)).*\b('
                            r'cortocircuito|corrientes? de falla|protecciones|reles|selectividad|flujo optimo|armonic\w*|'
                            r'cuasi\w*|pnl|optimizacion no lineal|optimizacion mixta)\b',),
          literal_en_pregunta=True),
    Tarea('evaluar_carga_nueva', 'Evalúa una carga nueva de una vez: diagnóstico, calibración si hace falta, carga, informe y '
          'obras solo si hay problemas (070:RF-50).',
          (P, A, SED, Dato('periodo', 'periodo', obligatorio=False, descripcion='con qué calibrar, si hace falta'), LIBROS),
          True, 'etapas', 'agente_proyecto', (
              'evalúa la carga nueva {sed} en {alimentadores} de {proyecto}',
              '[¿|]se puede conectar {sed} en {alimentadores} de {proyecto}[?|]',
              'evaluación de conexión de {sed} en {alimentadores} de {proyecto}',
              'ingreso de la carga nueva {sed} en {alimentadores} de {proyecto}',
              # 072:RF-29, RF-33: el estudio de corto plazo con su carga, con sus propias etapas (orquestador).
              '[haz|corre] el estudio de corto plazo con la carga {sed} en {alimentadores} de {proyecto}'),
          frases_literales=(r'\bevalu\w*\b.*\bcarga nueva\b', r'\bevalu\w*\b.*\bconexion\b', r'\bingreso de (una |la )?carga nueva\b',
                            # 070:RF-50: «quiero saber si entra una carga de 2 MW … de punta a punta» (auditor, F4).
                            r'\bsi (entra|cabe)\b.*\bcarga\b', r'\bcarga\b.*\bde punta a punta\b')),
    Tarea('cancelar_trabajo', 'Cancela los trabajos en curso del espacio, nombrándolos antes (070:RF-32).', (),
          True, 'trabajo', 'pf_projects', (
              '[cancela|cancelar|para] lo que [está|esta] corriendo', '[para|detén|deten] ese trabajo',
              'ya no sigas con ese trabajo', 'cancela el trabajo en curso'),
          frases_literales=(r'\bcancel(a|ar|alo|en)\b', r'\b(para|deten|detener) (ese|este|el) trabajo\b', r'\bya no sigas\b')),
    # 026:RF-43: repetir el último trabajo que falló, con sus mismos datos: se rehace su plan (con el sello de ahora y su
    # confirmación de siempre), como una corrección del operador; nunca se relanza el trabajo viejo a ciegas.
    Tarea('repetir_trabajo', 'Repite el último trabajo del espacio que falló, con sus mismos datos (026:RF-43).', (),
          True, 'trabajo', 'asistente_plan_repetido', (
              '[repite|repetir|vuelve a lanzar] el [último|ultimo] trabajo que fall[ó|o]', '[reintenta|repite] lo que fall[ó|o]',
              'vuelve a intentarlo con los mismos datos', 'lanza otra vez el trabajo que fall[ó|o]'),
          frases_literales=(r'\b(repite|repetir|reintenta|vuelve a lanzar)\b.*\b(fall\w*|mismos datos)\b',)),
    Tarea('convertir_set', 'Convierte una SET sola, con sus alimentadores y su barra (022:RF-82).', (SET,), True,
          'trabajo', 'sistema_seleccion', (
              'convierte [solo|] la set {set}', 'dgs de la set {set}', 'arma la set {set} con sus alimentadores',
              'conviérteme la set {set}'),
          frases_literales=(r'\b(convier|convert|conversion|dgs)\w*\b(?!.*\bset nueva\b).*\bset\b',)),
    Tarea('set_completo', 'Una SET de punta a punta: convertir, importar y calibrar con su máxima de barra (070:RF-21).',
          (SET, PER, LIBROS), True, 'proceso', 'sistema_web', (
              'calibra la set {set} con {periodo}', '[hazme|haz] la set {set} completa para {periodo}',
              'arma y calibra la set {set} con {periodo}'),
          frases_literales=(r'\b(calibra|arma y calibra|completa)\b(?!.*\bset nueva\b).*\bla set\b',
                            r'\bla set\b(?!.* nueva\b).*\bpunta a punta\b')),
    Tarea('alimentadores_completo', 'Uno o varios alimentadores de punta a punta: convertir, importar y calibrar (028:RF-25).',
          (A, PER, LIBROS), True, 'proceso', 'sistema_web', (
              'calibra {alimentadores} de punta a punta con {periodo}', 'convierte y calibra {alimentadores} para {periodo}',
              'arma {alimentadores} desde cero con {periodo}'),
          frases_literales=(r'^(?!.*\b(sistema|set|proyecto)\b).*(punta a punta|convierte y calibra|desde cero)',)),
    Tarea('buscar_maxima', 'Busca la máxima según el alcance: alimentadores, SET o sistema (028:RF-27).',
          (A_OPC, SET_OPC, Dato('sistema', 'sistema', obligatorio=False, descripcion='sistema eléctrico'),
           Dato('periodo', 'periodo', obligatorio=False, descripcion='mes AAAA-MM o año AAAA'),
           Dato('alcance', 'alcance', obligatorio=False, descripcion='alimentadores, set o sistema')), False, 'trabajo',
          'demanda_cabecera', (
              'búscame la máxima coincidente de {alimentadores} en {periodo}',
              '[cuál|cual] es la máxima de la barra de {set} en {periodo}',
              'dame la máxima de 60 kv del sistema {sistema} en {periodo}'),
          frases_literales=(r'^(?!.*\bbuscadas?\b)(?!.*\bcalibr).*\b(busca\w*|dame|saca\w*|cual es)\b.*\bmaxima\b',),
          literal_en_pregunta=True),
    Tarea('cruzar_clientes', 'Cruza los clientes de la máxima ya buscada: quiénes quedan fijos (035:RF-1).',
          (A_OPC, Dato('periodo', 'periodo', obligatorio=False, descripcion='mes AAAA-MM de los libros')), False, 'trabajo',
          'demanda_clientes', (
              'crúzame los clientes de {alimentadores} en {periodo}', 'sácame la tabla cruzada de {periodo}',
              'cruza los clientes de {alimentadores}'),
          frases_literales=(r'\bcruz\w*\b.*\bclientes\b', r'\btabla cruzada\b')),
    Tarea('calibrar', 'Calibra un proyecto con la última máxima buscada: prepara el plan y lo aplica (spec 006).', (P,),
          True, 'trabajo', 'ajuste_plan', (
              'aplica la calibración de {proyecto}', 'ajusta {proyecto} a su máxima', 'cuadra {proyecto} con la máxima buscada'),
          frases_literales=(r'\baplica (la )?calibracion\b', r'\bcalibra (el )?proyecto\b', r'\b(cuadra|ajusta)\b.*\bmaxima\b')),
    Tarea('simular_calibracion', 'Simula la calibración de un proyecto con la última máxima, sin aplicarla (spec 006).', (P,),
          True, 'trabajo', 'ajuste_plan', (
              'simula la calibración de {proyecto}', 'prueba el ajuste de {proyecto} sin grabar',
              'corre la calibración de {proyecto} en seco'),
          frases_literales=(r'\bsimula\w* (la )?calibracion\b', r'\bcalibracion\b.*\ben seco\b', r'\bajuste\b.*\bsin grabar\b')),
    Tarea('recalibrar', 'Recalibra un proyecto ya importado, sin reconvertir (028:RF-21).', (P, PER, LIBROS), True, 'proceso',
          'sistema_web', (
              'recalibra {proyecto} con {periodo}', 'vuelve a calibrar {proyecto} con {periodo}',
              'actualiza la calibración de {proyecto} a {periodo}'),
          frases_literales=(r'^(?!.*\bsistema\b).*\brecalibr\w*\b', r'\bvuelve a calibrar\b')),
    Tarea('escanear', 'Lee del proyecto generadores, bancos y lo cambiado a mano, sin escribir (spec 028).', (P, A), False,
          'trabajo', 'escanear_alimentadores', (
              'escanea {alimentadores} de {proyecto}', '[qué|que] bancos y centrales hay en {alimentadores} de {proyecto}',
              'revisa [qué|que] cambiaron a mano en {alimentadores} de {proyecto}'),
          frases_literales=(r'\bescane\w*\b',)),
    Tarea('verificar_convergencia', 'Corre el flujo con lo activo para ver si el proyecto converge, sin grabar (008:RF-18).',
          (P, A_OPC), False, 'trabajo', 'pf_verificar', (
              '¿converge {proyecto}?', 'verifícame el flujo de {proyecto}', 'prueba si {proyecto} sigue convergiendo'),
          frases_literales=(r'^(?!.*\b(caso base|por que|porque|como)\b).*\b(converge|convergiendo|convergencia)\b',),
          literal_en_pregunta=True),
    Tarea('carga_nueva_sola', 'Conecta una carga nueva sola, con el formulario de 3.2 (008:RF-24, 070:RF-29).', (P, A, SED),
          True, 'trabajo', 'cargas_plan', (
              'conecta {sed} en {alimentadores} de {proyecto}', 'mete una sola carga nueva {sed} a {alimentadores} en {proyecto}',
              'agrega el cliente {sed} como carga nueva en {alimentadores} de {proyecto}'),
          frases_literales=(r'^(?!.*\b(xlsx|excel|libro)\b).*\b(conecta|mete|agrega|integra|ingresa)\b.*\d\s*(kw|mw)\b',
                            r'\buna (sola )?carga nueva\b(?!.*\bevalu)')),
    Tarea('proyecto_entero', 'El proyecto entero de un sistema, etapa por etapa, con la lista de etapas a la vista (027:RF-43).',
          (S, PER, LIBROS), True, 'etapas', 'agente_proyecto', (
              'hazme todo el proyecto de {sistema} con {periodo}', 'lleva {sistema} desde cero con {periodo}',
              'proyecto entero de {sistema} para {periodo}'),
          frases_literales=(r'\b(todo el proyecto|proyecto entero|proyecto desde cero)\b', r'\blleva\b.*\bdesde cero\b')),
    Tarea('leer_solicitud', 'Lee los PDF del solicitante y propone sus datos, sin rellenar el formulario (017:RF-137).',
          (Dato('ruta', 'ruta', descripcion='PDF o carpeta con los PDF del solicitante'),), True, 'trabajo', 'informe_documentos', (
              'lee los pdf del solicitante en {ruta}', 'saca los datos de esta carta {ruta}', 'jala la potencia de la ficha {ruta}'),
          frases_literales=(r'\b(lee|leer|saca|extrae|jala)\b.*\b(pdf|carta|ficha|solicitud)\b',)),
    Tarea('descargar_resultados', 'Prepara el ZIP de los resultados y da el enlace para bajarlo (spec 001).', (A_OPC,), False,
          'trabajo', 'feeder_rows', (
              'pásame los resultados en zip', 'prepara la descarga de {alimentadores}', 'descarga los resultados del espacio'),
          # 026:RF-45 (T19): también los entregables de un módulo (PIDE, PIT, VAD, VNR o los informes); va antes que el
          # expediente del PIT en el catálogo: «descarga el expediente del PIT» lo baja, no lo vuelve a armar.
          frases_literales=(r'\bzip\b', r'\bdescarg\w*\b.*\bresultados\b', r'\bpasame los resultados\b',
                            r'\b(descarg\w*|baja\w*|pasame)\b.*\b(pide|pit|vad|vnr|informes?|entregables?|expediente)\b')),
    Tarea('pronostico', 'Pronóstico de demanda de cabecera o de clientes fijos, con su competencia de modelos (spec 046). '
          'Es un pronóstico, nunca una medición.', (Dato('ruta', 'ruta', descripcion='libro de la medición'), A_OPC), True,
          'trabajo', 'gemelo_temporal', (
              'pronostica la cabecera de {alimentadores} con el libro {ruta}', 'pronóstico de clientes fijos con {ruta}',
              'proyecta la demanda de cabecera de {alimentadores} con {ruta}'),
          frases_literales=(r'\bpronostic\w*\b',)),
    # ------------------------------------------------------------ nube y correo (070:RF-79 a RF-83)
    # El asistente lo prepara todo con las rutas que no envían ni publican (la vista previa del correo, las cuentas, los
    # recibos) y deja en su panel la tarjeta con lo exacto que saldrá; solo el clic del operador en ella lo envía,
    # publica, comparte, importa o conecta, desde el navegador (109:RF-15, 110:RF-5, RF-6).
    Tarea('enviar_informe', 'Prepara el correo de un informe con sus adjuntos y lo deja listo para «Confirmar y enviar»; '
          'solo sale con ese clic.', (INFORME,), False, 'trabajo', 'correo_api.registrar_rutas_correo', (
              'envía el informe {ruta} por correo', 'manda por correo el informe {ruta}',
              'envíale el informe por correo al cliente', 'prepara el correo del informe {ruta}'),
          frases_literales=(r'\b(envia\w*|manda\w*|remite|remitele)\b.*\b(correo|mail|email|e-mail)\b',
                            r'\bpor (correo|mail|email)\b', r'\bcorreo del informe\b')),
    Tarea('publicar_nube', 'Deja listo publicar una salida en Google Drive u OneDrive; se publica con el clic del operador.',
          (SALIDA,), False, 'trabajo', 'nube_api.registrar_rutas_nube', (
              'publica {ruta} en la nube', 'sube la salida a google drive', 'publica el expediente en onedrive',
              'sube los resultados a drive'),
          frases_literales=(r'\b(publica\w*|sube|subir|subelo|subela)\b.*\b(nube|drive|onedrive|google drive)\b',)),
    Tarea('compartir_nube', 'Deja listo compartir un expediente publicado, solo lectura y con quien diga la orden; se '
          'comparte con el clic del operador.', (), False, 'trabajo', 'nube_api.registrar_rutas_nube', (
              'comparte el expediente publicado', 'dale acceso al expediente en la nube',
              'comparte lo publicado en drive', 'comparte el enlace del expediente'),
          frases_literales=(r'\bcompart\w*\b.*\b(nube|drive|onedrive|expediente|publicad\w*|enlace)\b',
                            r'\bdale acceso\b.*\b(nube|drive|onedrive|expediente)\b')),
    Tarea('importar_nube', 'Abre el selector de Google Drive u OneDrive para traer un fichero a una entrada; entra con lo '
          'que el operador elija.', (), False, 'trabajo', 'nube_api.registrar_rutas_nube', (
              'trae un fichero de la nube', 'importa el libro desde google drive', 'jala el archivo de onedrive',
              'carga un fichero desde drive'),
          frases_literales=(r'\b(trae\w*|importa\w*|jala\w*|baja\w*|carga\w*)\b.*\b(de|desde) (la nube|mi drive|drive|google drive|onedrive)\b',)),
    Tarea('conectar_nube', 'Deja listo conectar la cuenta de Google o de Microsoft; la contraseña se escribe en la página '
          'del proveedor.', (), False, 'trabajo', 'nube_api.registrar_rutas_nube', (
              'conecta mi cuenta de google', 'vincula onedrive', 'conecta la cuenta de microsoft',
              'enlaza mi google drive'),
          frases_literales=(r'\b(conecta\w*|vincula\w*|enlaza\w*)\b.*\b(cuenta|drive|onedrive|google|microsoft|outlook|gmail)\b',)),
    # ------------------------------------------------------------ PIT (070:RF-79; spec 107)
    # Por las rutas de ``/api/pit``: sube al espacio los ficheros que nombra la orden y pide el trabajo del carril engine.
    Tarea('pit_diagnostico', 'Diagnóstico del PIT de un área de demanda, año por año, con el libro de la red y la '
          'proyección que nombre la orden.', (ENTRADAS_PIT,), True, 'trabajo', 'rutas_pit.crear_router', (
              'diagnostico del pit con {ruta}', 'haz el diagnostico del plan de inversiones con {ruta}',
              'diagnostica el pit del area con {ruta}', 'corre el diagnostico pit con {ruta}'),
          frases_literales=(r'\bdiagnostic\w*\b.*\b(pit|plan de inversiones)\b',
                            r'\b(pit|plan de inversiones)\b.*\bdiagnostic\w*\b')),
    Tarea('pit_expediente', 'Arma el expediente del PIT de un área para un periodo, con sus formatos, su informe y lo '
          'que queda pendiente.', (ENTRADAS_PIT,), True, 'trabajo', 'rutas_pit.crear_router', (
              'arma el expediente del pit con {ruta}', 'expediente del plan de inversiones con {ruta}',
              'prepara el expediente pit del area con {ruta}', 'haz el expediente del pit con {ruta}'),
          frases_literales=(r'\bexpediente\b.*\b(pit|plan de inversiones)\b',
                            r'\b(pit|plan de inversiones)\b.*\bexpediente\b')),
    # ------------------------------------------------------------ VAD (070:RF-79, RF-86; spec 108)
    Tarea('vad_crear_estudio', 'Crea el estudio de costos del VAD de la empresa del perfil para un grupo y un periodo, con '
          'el TdR del registro normativo.', (), True, 'trabajo', 'vad_api.registrar_rutas_vad', (
              'crea el estudio del vad del grupo 1', 'nuevo estudio de costos del vad', 'abre el estudio vad del periodo',
              'registra el estudio del vad'),
          frases_literales=(r'\b(crea\w*|abre|nuevo|registra\w*)\b.*\bestudio\b.*\bvad\b',)),
    Tarea('vad_empresa_modelo', 'Arma la empresa modelo del estudio del VAD, sistema por sistema, con el caso que nombre la '
          'orden; deja su manifiesto.', (CASO_VAD,), True, 'trabajo', 'vad_api.registrar_rutas_vad', (
              'arma la empresa modelo con {ruta}', 'empresa modelo del vad con {ruta}',
              'dimensiona la empresa modelo con el caso {ruta}', 'corre el estudio vad con {ruta}'),
          frases_literales=(r'\bempresa modelo\b', r'\b(arma|corre|haz)\b.*\bestudio\b.*\bvad\b.*\bcaso\b')),
    # ------------------------------------------------------------ plano (070:RF-79; spec 111)
    Tarea('plano_maniobra', 'Abre o cierra una maniobra de un alimentador en una variación del plano, sin tocar el caso '
          'base, y la estudia con DIgSILENT o con el motor abierto.', (A, P_OPC), True, 'trabajo',
          'plano_api.registrar_rutas_plano', (
              'abre el seccionador del alimentador {alimentadores} en el plano', 'cierra la maniobra de {alimentadores} y estudiala',
              'en el plano abre el interruptor de {alimentadores}', 'simula abrir la maniobra en {alimentadores}'),
          # «abre el seccionador para transferir la carga» es de `transferencia`, que el modelo conoce: no se le quita.
          frases_literales=(r'^(?!.*\btransf\w*)(?=.*\b(abre|abrir|cierra|cerrar|abrelo|cierralo)\b)'
                            r'.*\b(maniobra|interruptor|seccionador|reconectador|recloser|cuchilla)\b',)),
    # ------------------------------------------------------------ benchmarks (070:RF-79; spec 112)
    Tarea('benchmark_anonimo', 'Genera en local el benchmark anonimizado de la fuente TXT cargada; si el estudio no se '
          'reproduce o el control encuentra una fuga, no se emite nada.', (), True, 'proceso', 'benchmark_anonimo', (
              'genera el benchmark anonimizado', 'haz un dataset de referencia anonimizado de la red',
              'prepara el benchmark de la red cargada', 'anonimiza la red para un benchmark'),
          frases_literales=(r'\bbenchmark\w*\b', r'\b(dataset|conjunto)\b.*\banonimizad\w*\b',
                            r'\banonimiz\w*\b.*\bred\b')),
    Tarea('entrenar_asistente', 'Reentrena el Transformer de órdenes y, solo si hay informes reales en su prueba, el '
          'clasificador de informes; lo que no pase sus puertas deja el modelo en uso (026:RF-20, 067:RF-28).', (),
          True, 'proceso', 'asistente_entrenar', (
              'reentrena el asistente', 'entrena el transformer', 'aprende de las órdenes', 'aprende de las ordenes')),
    # 026:RF-44 (T18): los módulos que le faltaban al asistente, por sus mismas rutas de la web.
    Tarea('vnr_estudio', 'Estudio VNR de la red del espacio por la Guía 232-2017, con el SICODI de la empresa: el sector '
          'típico de la Guía y el del SICODI, su resolución, el año y la moneda (108:RF-20 a RF-25).', (), True, 'trabajo',
          'vnr_api.registrar_rutas_vnr', (
              'haz el estudio vnr', 'calcula el vnr de la red', 'estudio del valor nuevo de reemplazo',
              'corre el vnr con el sicodi', 'valoriza la red por la guia 232'),
          frases_literales=(r'\b(estudio|calcul\w*|corre|haz)\b.*\bvnr\b', r'\bvalor nuevo de reemplazo\b',
                            r'\bvaloriz\w*\b.*\bguia 232\b')),
    Tarea('clientes_fijos_evolucion', 'Evolución mes a mes de los clientes fijos de los alimentadores que nombre la orden, '
          'con los libros de clientes del rango de meses (105:RF-17).', (A,), True, 'trabajo',
          'evolucion_fijas_api.registrar_rutas_evolucion', (
              'evolucion de los clientes fijos de {alimentadores}', 'como evolucionan los clientes fijos de {alimentadores}',
              'historico de clientes fijos de {alimentadores}', 'clientes fijos de {alimentadores} mes a mes'),
          frases_literales=(r'\bclientes? fij\w*\b.*\b(evoluci\w*|historic\w*|mes a mes)\b',
                            r'\b(evoluci\w*|historic\w*)\b.*\bclientes? fij\w*\b')),
    # 026:RF-46 (T20): la biblioteca normativa por el asistente (107:RF-21, RF-22).
    Tarea('normativa_comprobar', 'Comprueba las fuentes oficiales de la biblioteca normativa: la huella de cada una '
          'contra la registrada y su vigencia hoy; solo lee y nada se descarga (107:RF-22).', (), False, 'consulta',
          'normativa_api.registrar_rutas_normativa', (
              'comprueba las fuentes de la normativa', 'revisa la biblioteca normativa',
              'que normas estan vigentes', 'cuadran las fuentes oficiales'),
          frases_literales=(r'\b(comprueb\w*|revis\w*|verific\w*)\b.*\b(fuentes?|biblioteca)\b.*\bnormativ\w*\b',
                            r'\bfuentes? oficial\w*\b.*\b(cuadr\w*|huella)\b')),
    Tarea('normativa_agregar', 'Agrega a la capa del usuario de la biblioteca normativa la norma del fichero .json que '
          'nombre la orden (con el esquema de la biblioteca normativa); lo que no valida no entra (107:RF-21).', (NORMA_JSON,), True,
          'trabajo', 'normativa_api.registrar_rutas_normativa', (
              'agrega la norma {ruta}', 'anade a la biblioteca normativa {ruta}', 'sube la norma {ruta}'),
          frases_literales=(r'\b(agreg\w*|anad\w*|sub\w*|incorpor\w*)\b.*\bnorma\b.*\.json\b',)),
    Tarea('normativa_regenerar', 'Regenera un registro de la biblioteca desde su fuente oficial ya descargada, con su '
          'generador (Guía VNR 232, formatos 217, COES o reconsideraciones): comprueba la huella, dice qué reglas '
          'entran, salen o cambian y lo escribe en la capa del usuario (107:RF-22).', (), True, 'trabajo',
          'normativa_api.registrar_rutas_normativa', (
              'regenera la guia vnr', 'regenera los formatos 217', 'actualiza el registro del coes',
              'regenera las reconsideraciones'),
          frases_literales=((r'\b(regener\w*|rehaz\w*|actualiz\w*)\b.*\b(registro|biblioteca|guia vnr|formatos 217|'
                             r'coes|reconsideracion\w*)\b'),)),
    # 026:RF-42 (T16): las entradas del espacio por el asistente, por las mismas rutas que la web: la casilla recibe el
    # fichero de la máquina por su subida (se valida antes de tocar la vigente, 086:RF-3) y el libro de la empresa entra
    # en sus fuentes con su clase y su año (109:RF-25). De la nube, el fichero lo elige el operador en el selector.
    Tarea('asignar_entrada', 'Asigna un fichero de la máquina a una casilla de entrada del espacio (la red, las cargas, '
          'los equipos, la base de la red, el estudio, el paquete del VNR-GIS o los alias), como la subida de la web; lo '
          'que la casilla no admite no entra y la entrada vigente se queda (026:RF-42).', (FICHERO_ENTRADA,), True,
          'trabajo', 'app.create_app', (
              'asigna {ruta} a la casilla de la red', 'pon {ruta} en la entrada de las cargas',
              'usa {ruta} como base de la red del espacio', 'asigna el paquete del vnr gis {ruta}'),
          frases_literales=(r'\basign\w*\b.*\b(casilla|entrada|red|cargas?|equipos?|base|mdb|vnr|gis|alias\w*|'
                            r'estudio|fichero|archivo)\b',
                            r'\b(pon\w*|coloca\w*|mete\w*|usa)\b.*\b(en|a|como) (la )?(casilla|entrada)\b')),
    Tarea('subir_fuente_empresa', 'Sube un libro de las fuentes de la empresa (demanda, SICODI, perfil, interrupciones, '
          'catálogo y los demás de la empresa) a su carpeta y a su año, como la web; queda vigente para todos los módulos '
          '(026:RF-42).', (LIBRO_EMPRESA,), True, 'trabajo', 'fuentes_api.registrar_rutas_fuentes', (
              'sube el sicodi {ruta} de 2025 a las fuentes de la empresa', 'registra el libro de demanda {ruta} del 2024',
              'sube las interrupciones {ruta} del 2025', 'agrega el catalogo {ruta} a las fuentes de la empresa'),
          frases_literales=(r'\b(sub\w*|registr\w*|agreg\w*|guard\w*)\b.*\b(fuentes?|libros?) de la empresa\b',
                            r'\b(sub\w*|registr\w*)\b.*\b(sicodi|interrupciones|perfil de la empresa|catalogo|'
                            r'libro de (la )?demanda)\b')),
)

TAREAS: dict[str, Tarea] = {t.nombre: t for t in _TAREAS}

#: 086:RF-23: lo que hace cada tarea en el mundo. Aparte de ``Tarea`` porque el catálogo hasta la 069 entra en la
#: huella de la prueba sellada (069:RF-13). Una tarea nueva sin su línea hace fallar ``test_cada_tarea_declara_su_efecto``.
LEE, LICENCIA, RED, ESCRIBE = 'lee', 'usa_licencia', 'sale_a_la_red', 'escribe'
EFECTOS: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(('estado', 'proyectos', 'resultados_pide', 'episodios', 'pregunta', 'clasificar_informe',
                     'consultar_datos', 'no_disponible', 'evaluar_gemelo', 'buscar_maxima', 'cruzar_clientes',
                     'descargar_resultados'), (LEE,)),
    # 070:RF-81: lo que el asistente hace solo lee o prepara; enviar, publicar, compartir, importar y conectar son el
    # clic del operador en su tarjeta, por las rutas del navegador.
    **dict.fromkeys(TAREAS_107_112_NUBE := ('enviar_informe', 'publicar_nube', 'compartir_nube', 'importar_nube',
                                            'conectar_nube'), (LEE,)),
    # 070:RF-79: el PIT por el asistente; escribe su expediente en el espacio.
    **dict.fromkeys(TAREAS_107_112_PIT := ('pit_diagnostico', 'pit_expediente'), (ESCRIBE,)),
    # 070:RF-79, RF-86: el VAD por el asistente; escribe su estudio y su manifiesto en el espacio.
    **dict.fromkeys(TAREAS_107_112_VAD := ('vad_crear_estudio', 'vad_empresa_modelo'), (ESCRIBE,)),
    # 070:RF-79: el plano por el asistente; escribe la variación y, con licencia y vínculo, estudia en DIgSILENT.
    **dict.fromkeys(TAREAS_107_112_PLANO := ('plano_maniobra',), (ESCRIBE, LICENCIA)),
    # 070:RF-79: el benchmark de la 112, en local y sin red; escribe su carpeta en la salida.
    **dict.fromkeys(TAREAS_107_112_BENCH := ('benchmark_anonimo',), (ESCRIBE,)),
    # 026:RF-44 (T18): el VNR y la evolución de clientes fijos escriben su resultado en el espacio.
    **dict.fromkeys(TAREAS_026_RF44 := ('vnr_estudio', 'clientes_fijos_evolucion'), (ESCRIBE,)),
    # 026:RF-46 (T20): comprobar solo lee; agregar y regenerar escriben en la capa del usuario de la biblioteca.
    'normativa_comprobar': (LEE,),
    **dict.fromkeys(TAREAS_026_RF46 := ('normativa_agregar', 'normativa_regenerar'), (ESCRIBE,)),
    # 026:RF-42 (T16): asignar una casilla y subir un libro de la empresa escriben en el espacio.
    **dict.fromkeys(TAREAS_026_RF42 := ('asignar_entrada', 'subir_fuente_empresa'), (ESCRIBE,)),
    **dict.fromkeys(('leer_proyectos', 'escanear', 'verificar_convergencia'), (LICENCIA,)),
    'buscar_internet': (RED,),
    **dict.fromkeys(('cargar_fuente', 'convertir', 'unir', 'convertir_sistema', 'convertir_set', 'gemelo_entrenar',
                     'gemelo_temporal', 'informe_estudio', 'leer_solicitud', 'pronostico', 'entrenar_asistente',
                     'cancelar_trabajo', 'repetir_trabajo'), (ESCRIBE,)),
    **dict.fromkeys(('sistema_completo', 'set_completo', 'alimentadores_completo', 'flujo', 'verificar_caso_base',
                     'cargas_nuevas', 'obras', 'estudios', 'obras_escalera', 'optimizar_con_proyecto', 'transferencia',
                     'pide', 'gemelo_aprender', 'informe_factibilidad', 'evaluar_carga_nueva', 'calibrar',
                     'simular_calibracion', 'recalibrar', 'carga_nueva_sola', 'proyecto_entero'), (ESCRIBE, LICENCIA)),
}
#: 086:RF-26: lo que el asistente puede repetir solo tras un fallo: repetirlo da lo mismo. Lo que escribe en un
#: proyecto de DIgSILENT no está: «aplica las obras» fallaba a mitad y se volvía a ejecutar entero.
TAREAS_IDEMPOTENTES = frozenset({
    *(n for n, e in EFECTOS.items() if ESCRIBE not in e and RED not in e),
    'cargar_fuente', 'convertir', 'unir', 'convertir_sistema', 'convertir_set', 'gemelo_entrenar', 'gemelo_temporal',
    'informe_estudio', 'leer_solicitud', 'pronostico', 'entrenar_asistente',
})


def requiere_confirmacion(tarea: str | None) -> bool:
    """086:RF-24: gastar la licencia o salir a la red también espera al operador, aunque no se escriba nada."""
    return bool({LICENCIA, RED} & set(EFECTOS.get(tarea or '', ())))

#: Las del catálogo hasta la spec 069. La prueba anterior, las órdenes fijas y el corpus sellado del LLM son de
#: ellas: sus huellas no pueden moverse con las tareas nuevas (068:RF-28, RF-41, 069:RF-13, 070:RF-72, RF-75).
TAREAS_HASTA_069: dict[str, Tarea] = {n: TAREAS[n] for n in (
    'estado', 'proyectos', 'resultados_pide', 'episodios', 'pregunta', 'clasificar_informe', 'buscar_internet',
    'leer_proyectos', 'evaluar_gemelo', 'cargar_fuente', 'convertir', 'unir', 'convertir_sistema', 'sistema_completo',
    'flujo', 'verificar_caso_base', 'cargas_nuevas', 'obras', 'estudios', 'obras_escalera', 'optimizar_con_proyecto',
    'transferencia', 'pide', 'gemelo_aprender', 'gemelo_entrenar', 'gemelo_temporal', 'informe_estudio',
    'informe_factibilidad', 'entrenar_asistente')}

#: 070:RF-85: las tareas de las specs 107 a 112. Las dos pruebas selladas de antes se quedan con las suyas y su huella;
#: estas se miden en la prueba sellada nueva (070 T21).
TAREAS_107_112: frozenset[str] = frozenset((*TAREAS_107_112_NUBE, *TAREAS_107_112_PIT, *TAREAS_107_112_VAD,
                                            *TAREAS_107_112_PLANO, *TAREAS_107_112_BENCH))
#: 026:RF-44 y RF-46 (2026-11-18): las tareas de la 026 posteriores a la 107-112, medidas en su propia prueba sellada
#: (``prueba_sellada_026``), con el mismo criterio que la 070:RF-85.
TAREAS_026: frozenset[str] = frozenset((*TAREAS_026_RF44, 'normativa_comprobar', *TAREAS_026_RF46))
#: 026:RF-42 y RF-43 (2026-11-19): repetir el último trabajo que falló y las órdenes de las entradas, con su propia
#: prueba sellada (``prueba_sellada_026.selladas_control``); la de la 026 de arriba conserva su huella.
TAREAS_026_CONTROL: frozenset[str] = frozenset(('repetir_trabajo', *TAREAS_026_RF42))
#: Lo que las pruebas selladas de la 070 y la 079 no miden: así conservan su huella con cada tarea nueva.
TAREAS_SIN_SELLADA_070_079: frozenset[str] = TAREAS_107_112 | TAREAS_026 | TAREAS_026_CONTROL


#: 072:RF-29: los tres tipos de análisis, por las palabras de la orden, y la tarea del catálogo que hace cada uno. Sin
#: tareas nuevas: el catálogo entra en las huellas de las pruebas selladas (069:RF-13, 070:RF-69). «Haz el planeamiento
#: de largo plazo» acababa en un PIDE que aplicaba obras en «Con proyecto», lo que prohíbe 072:RF-35: el largo plazo va
#: por la misma ruta ``/pide`` con su ``plazo`` y sin aplicar (072:RF-34), y el corto plazo es la evaluación de su carga
#: con sus propias etapas (``orquestador.ETAPAS_CORTO_PLAZO``).
TIPOS_DE_ANALISIS = {'corto_plazo': 'evaluar_carga_nueva', 'pide': 'pide', 'largo_plazo': 'pide'}
NOMBRE_DEL_TIPO = {'corto_plazo': 'corto plazo', 'pide': 'PIDE', 'largo_plazo': 'largo plazo'}
_PALABRAS_DEL_TIPO = (('corto_plazo', re.compile(r'\bcorto plazo\b')),
                      ('pide', re.compile(r'\bpide\b|\bplan de inversiones\b')),
                      ('largo_plazo', re.compile(r'\blargo plazo\b')))
#: Las rutas no son palabras de la orden: «E:/planeamiento/…» o una carpeta «largo plazo» no eligen nada.
_RUTAS = re.compile(r'"[^"]*"|[a-z]:[\\/]\S*')
#: Pedir lo que ya salió es una consulta (``resultados_pide``), no un estudio nuevo que escribe.
_CONSULTA_DEL_TIPO = re.compile(r'\b(resultados?|muestra\w*|ver)\b')


def tipos_de_analisis_de(texto: str) -> list[str]:
    """Los tipos de análisis que nombra la orden ya normalizada (``sinteticos.normalizar``), en el orden del catálogo."""
    t = _RUTAS.sub(' ', texto)
    return [tipo for tipo, palabras in _PALABRAS_DEL_TIPO if palabras.search(t)]


def tarea_del_tipo_de_analisis(texto: str) -> str | None:
    """La tarea que manda la orden normalizada que nombra el corto o el largo plazo (072:RF-29), entienda lo que
    entienda el modelo. El PIDE solo lo sigue decidiendo el modelo, que distingue hacerlo de consultar sus resultados;
    si la orden nombra más de un tipo, va al PIDE, cuyo plan pregunta cuál (``web/asistente_operacion._pide``)."""
    tipos = tipos_de_analisis_de(texto)
    if not {'corto_plazo', 'largo_plazo'} & set(tipos) or _CONSULTA_DEL_TIPO.search(texto):
        return None
    return TIPOS_DE_ANALISIS[tipos[0]] if len(tipos) == 1 else 'pide'


#: 070:RF-51: una cita de requisito, de spec o de tarea entre paréntesis: «(072:RF-29)», «(spec 017)», «(024, T13 y T14)».
_CITA = re.compile(r'\s*\([^()]*\b(?:\d{3}\s*:\s*RF-\d+|RF-\d+|specs?\s+\d{3}|T\d+[a-z]?)\b[^()]*\)')


def sin_citas(texto: str) -> str:
    """El texto sin sus citas, para lo que lee el operador; la cita queda en el código y en el registro.

    La consola enseña el plan tal cual y terminaba en «Dígalo en la orden (072:RF-29).». Sirve también para los
    mensajes de otros módulos que llegan al plan (una excepción, el motivo de un modelo que no cargó).
    """
    return _CITA.sub('', texto)


def descripcion_para_operador(tarea: str) -> str:
    """La descripción de la tarea sin citas. La del catálogo no se toca: entra en las huellas selladas (069:RF-13)."""
    return sin_citas(TAREAS[tarea].descripcion)


def descripcion_para_modelo() -> list[dict]:
    """Las tareas como herramientas, para el modelo de Ollama (RF-3)."""
    return [{'tarea': t.nombre, 'descripcion': t.descripcion,
             'datos': {d.nombre: {'tipo': d.tipo, 'obligatorio': d.obligatorio, 'que_es': d.descripcion}
                       for d in t.datos}} for t in _TAREAS]


def sistema_alumno() -> str:
    """El mismo contrato compacto se usa para ajuste y para atender ordenes (perfil ``llm_destilado_v1``).

    Es el de las tareas hasta la 069: su huella es la de los corpus sellados v5 y v6 y no se mueve con el catálogo.
    """
    return _sistema_de(TAREAS_HASTA_069.values())


def sistema_alumno_contrato() -> str:
    """047:RF-69: el mismo texto con el contrato vigente entero, ``TAREAS`` (perfil ``llm_destilado_v2``, corpus v7).

    Cada tarea con la primera frase de su descripción, sin citas: con las descripciones enteras el prompt pasaba de
    los 2.900 tokens y cada ejemplo del ajuste triplicaba el coste del v1.
    """
    return _sistema_de(TAREAS.values(), _primera_frase)


def _primera_frase(descripcion: str) -> str:
    texto = sin_citas(descripcion).strip()
    m = re.match(r'(.+?[.:;])(\s|$)', texto)
    return (m[1] if m else texto).rstrip('.:;') + '.'


def _sistema_de(tareas, descripcion=lambda d: d) -> str:
    catalogo = '\n'.join(f'{t.nombre}: {descripcion(t.descripcion)} Campos: '
        + ','.join(d.tipo for d in t.datos) for t in tareas)
    return ('Interpreta una solicitud del operador del conversor de redes electricas. '
        'Devuelve solo JSON con tarea, datos y confianza. Elige exactamente una tarea del catalogo. '
        'datos es un objeto de listas de textos literales copiados de la solicitud. '
        'No inventes entidades ni declares haber ejecutado acciones. No agregues campos de otras tareas. '
        'Si no corresponde a ninguna tarea devuelve tarea null, datos {} y confianza 0. '
        'La respuesta propone una solicitud; la web verifica fuentes, permisos y confirmacion.\n' + catalogo)


#: 047:RF-69: el prompt de cada perfil del alumno destilado y las tareas que cubre su corpus sellado. El v1 es el de los
#: corpus v5 y v6 (29 tareas); el v2, el del corpus v7, con el contrato vigente entero.
PERFILES_ALUMNO = {'llm_destilado_v1': (sistema_alumno, TAREAS_HASTA_069),
                   'llm_destilado_v2': (sistema_alumno_contrato, TAREAS)}
