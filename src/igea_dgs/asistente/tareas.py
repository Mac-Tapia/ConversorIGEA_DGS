"""Catálogo de lo que el asistente sabe hacer (spec 026, RF-8 a RF-11).

Cada tarea dice qué datos necesita, si escribe (y por eso pide confirmación, RF-8), cómo
se ejecuta y con qué frases se suele pedir. Las frases son plantillas: ``[a|b]`` elige
una variante y ``{tipo}`` es un dato que se rellena con nombres reales del espacio
(``sinteticos.py``, RF-21). La ejecución no se define aquí sino en ``ejecutor.py``, por
las mismas rutas de la web (P5): este fichero solo nombra la función de ``web/services``
(o la herramienta de ``tools/``) que hace el trabajo, y su prueba comprueba que existe.

Modos: ``consulta`` se responde en la misma petición con lo que ya hay; ``trabajo`` va por
las rutas y la cola de la web; ``proceso`` lanza una herramienta de ``tools/``.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Tipos de dato que el intérprete reconoce y el plan contrasta (RF-2, RF-6).
TIPOS_DATO = ('proyecto', 'alimentadores', 'sistema', 'periodo', 'caso', 'numero', 'ruta',
              'sed', 'subtipo', 'texto')


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
          (S, PER, Dato('ruta', 'ruta', obligatorio=False, descripcion='carpeta de los libros de demanda')),
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
    Tarea('estudios', 'Estudios de la red en los casos del proyecto (spec 011).', (P, A), True, 'trabajo',
          'estudios_ejecutar', (
              '[corre|ejecuta|haz] los estudios de {alimentadores} [de|en] {proyecto}',
              'estudios de {proyecto} {alimentadores}', 'estudio de la red de {alimentadores} en {proyecto}')),
    Tarea('transferencia', 'Transferencia de carga entre dos alimentadores (spec 011).', (P, A), True, 'trabajo',
          'transferencia_ejecutar', (
              'transfiere carga entre {alimentadores} [de|en] {proyecto}',
              'transferencia [de|entre] {alimentadores} [de|en] {proyecto}')),
    Tarea('pide', 'Metodología del PIDE: diagnóstico, obras propias y formatos (024, T13 y T14).', (P, A),
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
    Tarea('entrenar_asistente', 'Reentrena el Transformer de órdenes y el clasificador de informes (RF-20).', (),
          True, 'proceso', 'asistente_entrenar', (
              'reentrena el asistente', 'entrena el transformer', 'aprende de las órdenes', 'aprende de las ordenes')),
)

TAREAS: dict[str, Tarea] = {t.nombre: t for t in _TAREAS}


def descripcion_para_modelo() -> list[dict]:
    """Las tareas como herramientas, para el modelo de Ollama (RF-3)."""
    return [{'tarea': t.nombre, 'descripcion': t.descripcion,
             'datos': {d.nombre: {'tipo': d.tipo, 'obligatorio': d.obligatorio, 'que_es': d.descripcion}
                       for d in t.datos}} for t in _TAREAS]
