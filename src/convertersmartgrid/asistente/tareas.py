"""Catálogo de lo que el asistente sabe hacer (spec 026, RF-8 a RF-11).

Cada tarea dice qué datos necesita, si escribe (y por eso pide confirmación, RF-8), cómo
se ejecuta y con qué frases se suele pedir. Las frases son plantillas: ``[a|b]`` elige
una variante y ``{tipo}`` es un dato que se rellena con nombres reales del espacio
(``sinteticos.py``, RF-21). La ejecución no se define aquí sino en ``ejecutor.py``, por
las mismas rutas de la web (P5): este fichero solo nombra la función de ``web/services``
(o la herramienta de ``tools/``) que hace el trabajo, y su prueba comprueba que existe.

Modos: ``consulta`` se responde en la misma petición con lo que ya hay; ``trabajo`` va por
las rutas y la cola de la web; ``proceso`` lanza una herramienta de ``tools/``; ``etapas``
encadena varias tareas con una sola confirmación de su lista (067:RF-37, 070:RF-51).
"""
from __future__ import annotations

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
              '[dime|explícame] [cómo|como] se {texto}')),
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
    Tarea('pide', 'Metodología del PIDE: diagnóstico, obras propias, formatos y módulos (024, 072).',
          (P, A, Dato('periodo', 'periodo', obligatorio=False, descripcion='año de presentación del estudio')),
          True, 'trabajo', 'pide_ejecutar', (
              '[haz|ejecuta|corre] el pide de {proyecto} {alimentadores}', 'plan de inversiones de {proyecto} {alimentadores}',
              'pide [de|del proyecto|para] {proyecto} {alimentadores}', 'diagnóstico pide de {alimentadores} en {proyecto}')),
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
              'ingreso de la carga nueva {sed} en {alimentadores} de {proyecto}'),
          frases_literales=(r'\bevalu\w*\b.*\bcarga nueva\b', r'\bevalu\w*\b.*\bconexion\b', r'\bingreso de (una |la )?carga nueva\b')),
    Tarea('cancelar_trabajo', 'Cancela los trabajos en curso del espacio, nombrándolos antes (070:RF-32).', (),
          True, 'trabajo', 'pf_projects', (
              '[cancela|cancelar|para] lo que [está|esta] corriendo', '[para|detén|deten] ese trabajo',
              'ya no sigas con ese trabajo', 'cancela el trabajo en curso'),
          frases_literales=(r'\bcancel(a|ar|alo|en)\b', r'\b(para|deten|detener) (ese|este|el) trabajo\b', r'\bya no sigas\b')),
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
          frases_literales=(r'\bzip\b', r'\bdescarg\w*\b.*\bresultados\b', r'\bpasame los resultados\b')),
    Tarea('pronostico', 'Pronóstico de demanda de cabecera o de clientes fijos, con su competencia de modelos (spec 046). '
          'Es un pronóstico, nunca una medición.', (Dato('ruta', 'ruta', descripcion='libro de la medición'), A_OPC), True,
          'trabajo', 'gemelo_temporal', (
              'pronostica la cabecera de {alimentadores} con el libro {ruta}', 'pronóstico de clientes fijos con {ruta}',
              'proyecta la demanda de cabecera de {alimentadores} con {ruta}'),
          frases_literales=(r'\bpronostic\w*\b',)),
    Tarea('entrenar_asistente', 'Reentrena el Transformer de órdenes y, solo si hay informes reales en su prueba, el '
          'clasificador de informes; lo que no pase sus puertas deja el modelo en uso (026:RF-20, 067:RF-28).', (),
          True, 'proceso', 'asistente_entrenar', (
              'reentrena el asistente', 'entrena el transformer', 'aprende de las órdenes', 'aprende de las ordenes')),
)

TAREAS: dict[str, Tarea] = {t.nombre: t for t in _TAREAS}

#: Las del catálogo hasta la spec 069. La prueba anterior, las órdenes fijas y el corpus sellado del LLM son de
#: ellas: sus huellas no pueden moverse con las tareas nuevas (068:RF-28, RF-41, 069:RF-13, 070:RF-72, RF-75).
TAREAS_HASTA_069: dict[str, Tarea] = {n: TAREAS[n] for n in (
    'estado', 'proyectos', 'resultados_pide', 'episodios', 'pregunta', 'clasificar_informe', 'buscar_internet',
    'leer_proyectos', 'evaluar_gemelo', 'cargar_fuente', 'convertir', 'unir', 'convertir_sistema', 'sistema_completo',
    'flujo', 'verificar_caso_base', 'cargas_nuevas', 'obras', 'estudios', 'obras_escalera', 'optimizar_con_proyecto',
    'transferencia', 'pide', 'gemelo_aprender', 'gemelo_entrenar', 'gemelo_temporal', 'informe_estudio',
    'informe_factibilidad', 'entrenar_asistente')}


def descripcion_para_modelo() -> list[dict]:
    """Las tareas como herramientas, para el modelo de Ollama (RF-3)."""
    return [{'tarea': t.nombre, 'descripcion': t.descripcion,
             'datos': {d.nombre: {'tipo': d.tipo, 'obligatorio': d.obligatorio, 'que_es': d.descripcion}
                       for d in t.datos}} for t in _TAREAS]
