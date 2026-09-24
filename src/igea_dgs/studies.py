"""Qué estudios de PowerFactory se pueden correr hoy, y qué dato falta para cada uno.

El escenario base —el año 0 del PIDE— no es «el modelo que converge». Es el modelo que
converge **y** sobre el que los estudios que sustentan el plan dan resultados que
significan algo. Un ``ComRel3`` corre perfectamente con todas las tasas de falla a cero
y devuelve SAIDI = 0: no falla, miente.

Por eso este módulo separa tres cosas que es fácil confundir:

``se ejecuta``
    PowerFactory acepta la orden y devuelve un código de cálculo.
``tiene datos``
    Las entradas que el estudio necesita existen y no son ceros ni valores por defecto.
``es defendible``
    Ambas, y además la fuente del dato está identificada. Es el listón del PIDE, porque
    el expediente va a Osinergmin.

Lo que hay aquí es la tabla de requisitos, comprobable contra el export sin necesidad de
PowerFactory. La ejecución vive en ``tools/base_scenario.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

#: Estados posibles de una entrada de datos.
DISPONIBLE = 'disponible'
"""El export lo trae con valores reales."""

PARCIAL = 'parcial'
"""Está en el export pero el conversor no lo usa, o solo cubre parte de los elementos."""

POR_DEFECTO = 'por_defecto'
"""Existe la columna, pero todas las filas traen el mismo valor de catálogo."""

AUSENTE = 'ausente'
"""No está. Hay que pedirlo a la empresa o a un tercero."""


@dataclass(frozen=True)
class Entrada:
    """Un dato que un estudio necesita, y dónde está hoy."""

    nombre: str
    estado: str
    donde: str
    """De dónde sale, o de dónde tendría que salir."""
    sin_esto: str
    """Qué pasa si se corre el estudio sin este dato. Lo importante de la tabla."""

    @property
    def bloquea(self) -> bool:
        """Sin esto el resultado no significa nada, aunque el estudio se ejecute."""
        return self.estado in (AUSENTE, POR_DEFECTO)


#: Cuánto cuesta un estudio sobre una red del tamaño del sistema completo.
LIGERO = 'ligero'
"""Un puñado de segundos: una resolución o un recorrido de la red."""

PESADO = 'pesado'
"""Resuelve la red muchas veces: N-1 lanza un flujo por contingencia, la fiabilidad
enumera fallos, y las optimizaciones iteran. Sobre 53.000 barras puede irse a horas."""


@dataclass(frozen=True)
class Estudio:
    """Un módulo de PowerFactory con lo que aporta al PIDE y lo que necesita."""

    clave: str
    clase_pf: str
    nombre: str
    capitulo: int
    aporta_al_pide: str
    entradas: tuple[Entrada, ...] = ()
    coste: str = LIGERO
    """Si es ``PESADO``, el orquestador lo aísla y le pone límite de tiempo."""

    @property
    def bloqueantes(self) -> tuple[Entrada, ...]:
        return tuple(e for e in self.entradas if e.bloquea)

    @property
    def defendible(self) -> bool:
        return not self.bloqueantes

    def resumen(self) -> str:
        estado = 'listo' if self.defendible else f'{len(self.bloqueantes)} dato(s) faltan'
        return f'[{estado}] {self.nombre} ({self.clase_pf}, cap. {self.capitulo})'


# --------------------------------------------------------------------------------
# Entradas reutilizadas por varios estudios
# --------------------------------------------------------------------------------

_TOPOLOGIA = Entrada(
    'Topología, impedancias y cargas de punta', DISPONIBLE,
    'RED_*.txt y BD_Equipo_*.txt (o la base Access)',
    'Nada: es lo que el conversor ya produce.',
)

_IMPEDANCIA_FUENTE = Entrada(
    'Potencia e impedancia de cortocircuito de cada subestación de cabecera',
    POR_DEFECTO,
    '[SUBSTATION] del BD_Equipo trae las 24 subestaciones, pero TODAS con los mismos '
    '200 MVA, R1=0,1, X1=0,6, R0=0,5, X0=2,0: son el valor por defecto de CYMDIST '
    'copiado. Hace falta el dato real por subestación, que sale del estudio de '
    'cortocircuito del sistema de transmisión o del COES.',
    'Las corrientes de falla salen iguales en toda la red y no sirven para ajustar '
    'protecciones ni para verificar poder de corte.',
)

_TASAS_FALLA = Entrada(
    'Tasa de falla (λ) y tiempo de reparación por tipo de elemento',
    AUSENTE,
    'Las columnas FailRate, TmpFailRate y OutageTime existen en el BD_Equipo y están '
    'TODAS a cero. Salen del histórico de interrupciones de la empresa, que Electro '
    'Dunas ya reporta a Osinergmin por la NTCSE.',
    'ComRel3 se ejecuta igual y devuelve SAIDI = SAIFI = ENS = 0. Es el peor caso: un '
    'resultado limpio y sin sentido.',
)

_CLIENTES = Entrada(
    'Número de clientes por SED', PARCIAL,
    'NumberOfCustomer está en [CUSTOMER LOADS] del CARGA y el conversor no lo lee.',
    'SAIFI y SAIDI se ponderan por cliente. Sin el denominador no son los índices de '
    'la NTCSE, son otra cosa.',
)

_TIEMPOS_MANIOBRA = Entrada(
    'Tiempo de maniobra y de localización de falla', AUSENTE,
    'Criterio de operación de la empresa; depende de si el equipo es telemandado.',
    'La parte de SAIDI que depende de reponer por maniobra queda sin modelar.',
)

_ENERGIA = Entrada(
    'Energía anual por suministro (kWh)', PARCIAL,
    'KWH está en [CUSTOMER LOADS] y el conversor lo lee, pero no lo escribe al DGS.',
    'Sin energía no hay factor de carga ni factor de pérdidas: las pérdidas anuales '
    'habría que estimarlas con un factor típico en lugar de medirlas.',
)

_PERFILES = Entrada(
    'Perfiles de carga horarios o curvas típicas por tipo de cliente', AUSENTE,
    'El export solo trae la punta. Saldrían de los medidores inteligentes o de las '
    'curvas típicas por sector del estudio de mercado.',
    'La simulación cuasi-dinámica no tiene nada que barrer, y el factor de pérdidas '
    'queda en un valor típico en vez de calculado.',
)

_PROYECCION = Entrada(
    'Proyección de demanda por SED y por alimentador', AUSENTE,
    'La serie histórica de energía por suministro permite construirla; el export trae '
    'el año de alta de cada carga (campo Year) pero no la serie.',
    'No hay año 4, 8, 12, 16 ni 20: el plan se queda en el año 0.',
)

_CURVAS_PROTECCION = Entrada(
    'Curvas tiempo-corriente de fusibles, reconectadores y relés', AUSENTE,
    'Las tablas FUSE, RECLOSER, BREAKER y RELAY del BD_Equipo solo traen la fila '
    'DEFAULT, con InterruptingRating = 0. Salen de la ficha del fabricante y de los '
    'ajustes de la empresa.',
    'No se puede verificar selectividad ni proponer los proyectos de mejora de calidad '
    'que el TdR del VAD nombra uno por uno.',
)

_PRECIOS = Entrada(
    'Precios unitarios de conductor, estructura, SED y equipos de maniobra',
    AUSENTE,
    'Valorización de la empresa, o los valores del VNR que ya presenta al regulador.',
    'Sin coste marginal de la sección no hay corriente económica; y sin inversión no '
    'hay VAN ni TIR, que es lo que el PIDE pide por proyecto.',
)

_COSTE_ENERGIA = Entrada(
    'Coste de la energía (US$/kWh) y tasa de actualización', PARCIAL,
    'La tasa la fija el TdR en 12 % y el valor de la ENS en 1 US$/kWh. El coste de la '
    'energía de pérdidas lo pone la empresa.',
    'Las pérdidas no se pueden capitalizar, que es la mitad de la función objetivo.',
)

_ETAPAS = Entrada(
    'Alternativas de inversión con sus etapas por año', AUSENTE,
    'Se construyen en PowerFactory como Network Variations y Expansion Stages una vez '
    'haya proyección y precios.',
    'ComTececo no tiene estrategia que valorar ni ComTececocmp alternativas que '
    'comparar.',
)

_ESPECTROS = Entrada(
    'Espectros armónicos de las cargas no lineales', AUSENTE,
    'Campañas de medición de calidad de producto de la empresa.',
    'El flujo armónico corre sin fuentes de armónicos: resultado vacío.',
)

_FASES = Entrada(
    'Reparto real de cargas por fase', DISPONIBLE,
    'El campo Phase de [CUSTOMER LOADS] y de [SECTION] trae la fase de cada elemento.',
    'Nada: el dato está. Falta que el conversor lo escriba, porque hoy ElmLod no lleva '
    'la fase (defecto C-04 del diagnóstico).',
)


# --------------------------------------------------------------------------------
# Los estudios
# --------------------------------------------------------------------------------

ESTUDIOS: tuple[Estudio, ...] = (
    Estudio(
        'flujo', 'ComLdf', 'Flujo de potencia', 24,
        'El estado base: tensiones, cargabilidad y pérdidas del año 0.',
        (_TOPOLOGIA,),
    ),
    Estudio(
        'flujo_desequilibrado', 'ComLdf', 'Flujo de potencia desequilibrado', 24,
        'El TdR del VAD pide explícitamente flujos desequilibrados (Anexo 6).',
        (_TOPOLOGIA, _FASES),
    ),
    Estudio(
        'cortocircuito', 'ComShc', 'Cortocircuito', 25,
        'Corrientes de falla para ajustar protecciones y verificar poder de corte.',
        (_TOPOLOGIA, _IMPEDANCIA_FUENTE),
    ),
    Estudio(
        'contingencias', 'ComSimoutage', 'Contingencias N-1', 26,
        'Qué alimentador puede respaldar a otro. Solo tiene sentido en la red unida.',
        (_TOPOLOGIA,),

        coste=PESADO,
    ),
    Estudio(
        'fiabilidad', 'ComRel3', 'Fiabilidad (SAIDI, SAIFI, ENS)', 45,
        'Los índices de la NTCSE y la ENS a 1 US$/kWh del régimen de incentivos.',
        (_TOPOLOGIA, _TASAS_FALLA, _CLIENTES, _TIEMPOS_MANIOBRA),

        coste=PESADO,
    ),
    Estudio(
        'cuasi_dinamica', 'ComStatsim', 'Simulación cuasi-dinámica', 27,
        'Factor de pérdidas real en lugar de un valor típico.',
        (_TOPOLOGIA, _PERFILES, _ENERGIA),

        coste=PESADO,
    ),
    Estudio(
        'troncal', 'ComBbone', 'Cálculo de troncal', 41,
        'El TdR distingue troncal y derivaciones para elegir el calibre económico.',
        (_TOPOLOGIA,),
    ),
    Estudio(
        'punto_apertura', 'ComTieopt', 'Punto de apertura óptimo', 41,
        'Reconfiguración: dónde conviene abrir para minimizar pérdidas.',
        (_TOPOLOGIA,),

        coste=PESADO,
    ),
    Estudio(
        'condensadores', 'ComCapo', 'Colocación óptima de condensadores', 41,
        'Los niveles de compensación que pide el Anexo 6.',
        (_TOPOLOGIA, _PRECIOS, _COSTE_ENERGIA),

        coste=PESADO,
    ),
    Estudio(
        'balance_fases', 'ComBalance', 'Balance de fases', 41,
        'El desequilibrio de carga que el TdR nombra entre los parámetros de diseño.',
        (_TOPOLOGIA, _FASES),

        coste=PESADO,
    ),
    Estudio(
        'perfil_tension', 'ComVoltplan', 'Optimización del perfil de tensión', 41,
        'Cumplimiento del límite de caída de tensión (6 % en zona rural).',
        (_TOPOLOGIA,),

        coste=PESADO,
    ),
    Estudio(
        'flujo_optimo', 'ComOpf', 'Flujo óptimo de potencia', 38,
        'Optimización con restricciones de red.',
        (_TOPOLOGIA, _COSTE_ENERGIA),

        coste=PESADO,
    ),
    Estudio(
        'economico', 'ComTececo', 'Evaluación técnico-económica', 43,
        'VAN de la estrategia de expansión, con depreciación y valor residual.',
        (_TOPOLOGIA, _PRECIOS, _COSTE_ENERGIA, _ETAPAS, _PROYECCION),

        coste=PESADO,
    ),
    Estudio(
        'comparacion', 'ComTececocmp', 'Comparación de alternativas', 43,
        'El núcleo del PIDE: justificar la alternativa elegida frente a las demás.',
        (_TOPOLOGIA, _PRECIOS, _COSTE_ENERGIA, _ETAPAS, _PROYECCION),

        coste=PESADO,
    ),
    Estudio(
        'protecciones', 'ComProtgraphic', 'Coordinación de protecciones', 32,
        'Selectividad; sustenta los proyectos de mejora de calidad del TdR.',
        (_TOPOLOGIA, _CURVAS_PROTECCION, _IMPEDANCIA_FUENTE),
    ),
    Estudio(
        'armonicos', 'ComHldf', 'Flujo armónico', 35,
        'Calidad de producto.',
        (_TOPOLOGIA, _ESPECTROS),
    ),
)


def estudios_ligeros() -> tuple[Estudio, ...]:
    return tuple(e for e in ESTUDIOS if e.coste == LIGERO)


def estudios_pesados() -> tuple[Estudio, ...]:
    return tuple(e for e in ESTUDIOS if e.coste == PESADO)


def estudios_ejecutables() -> tuple[Estudio, ...]:
    """Los que hoy dan un resultado defendible con lo que trae el export."""
    return tuple(e for e in ESTUDIOS if e.defendible)


def estudios_bloqueados() -> tuple[Estudio, ...]:
    return tuple(e for e in ESTUDIOS if not e.defendible)


def datos_que_faltan() -> dict[str, list[str]]:
    """``dato -> estudios que lo necesitan``, ordenado por cuántos desbloquea.

    Es la lista de la compra para el departamento técnico, y el orden importa: pedir
    primero el dato que desbloquea más estudios rinde más que pedirlos por orden
    alfabético.
    """
    pendientes: dict[str, list[str]] = {}
    for estudio in ESTUDIOS:
        for entrada in estudio.bloqueantes:
            pendientes.setdefault(entrada.nombre, []).append(estudio.nombre)
    return dict(sorted(pendientes.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def entradas_por_nombre() -> dict[str, Entrada]:
    return {e.nombre: e for estudio in ESTUDIOS for e in estudio.entradas}


# --------------------------------------------------------------------------------
# Comprobación contra el export cargado
# --------------------------------------------------------------------------------


@dataclass
class AuditoriaDatos:
    """Lo que el export de verdad trae, comprobado y no supuesto."""

    hallazgos: list[str] = field(default_factory=list)
    energia_kwh: float = 0.0
    cargas_con_energia: int = 0
    cargas_totales: int = 0
    tasas_falla_no_cero: int = 0
    subestaciones: int = 0
    subestaciones_distintas: int = 0

    def texto(self) -> str:
        return '\n'.join(self.hallazgos)


def auditar_datos(dataset: Any, modelos: Iterable[Any] = ()) -> AuditoriaDatos:
    """Comprueba en el export cargado qué entradas están de verdad.

    No se fía de la tabla de arriba: la tabla dice qué **debería** haber, esto mira qué
    **hay**. Si el día de mañana la empresa rellena las tasas de falla, esto lo detecta
    y el estudio de fiabilidad deja de estar bloqueado sin tocar el código.
    """
    aud = AuditoriaDatos()

    # customer_loads es un dict {clave: fila}; equipment_tables, el catálogo por tabla.
    cargas = getattr(dataset, 'customer_loads', None) or {}
    filas = list(cargas.values()) if hasattr(cargas, 'values') else list(cargas)
    aud.cargas_totales = len(filas)

    con_energia = 0
    energia = 0.0
    clientes = 0
    con_clientes = 0
    for fila in filas:
        d = fila if isinstance(fila, dict) else {}
        try:
            kwh = float(d.get('KWH') or 0)
        except (TypeError, ValueError):
            kwh = 0.0
        if kwh > 0:
            con_energia += 1
            energia += kwh
        try:
            n = int(float(d.get('NumberOfCustomer') or 0))
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            con_clientes += 1
            clientes += n
    aud.cargas_con_energia = con_energia
    aud.energia_kwh = energia

    if aud.cargas_totales:
        pct = con_energia / aud.cargas_totales * 100.0
        aud.hallazgos.append(
            f'Energía por suministro (KWH): {con_energia:,} de {aud.cargas_totales:,} '
            f'cargas ({pct:.0f} %), {energia:,.0f} kWh. El conversor la lee y NO la '
            f'escribe al DGS; es la base del factor de carga y de la proyección.'
        )
        aud.hallazgos.append(
            f'Número de clientes: {clientes:,} en {con_clientes:,} cargas. El conversor '
            f'NO lee este campo, y es el denominador de SAIFI y SAIDI.'
        )

    tablas = getattr(dataset, 'equipment_tables', None) or {}
    no_cero = 0
    revisadas = 0
    for nombre in ('LINE', 'CONCENTRIC NEUTRAL CABLE', 'SWITCH', 'BREAKER', 'FUSE',
                   'RECLOSER', 'SECTIONALIZER'):
        for fila in (tablas.get(nombre) or {}).values() if hasattr(
                tablas.get(nombre) or {}, 'values') else (tablas.get(nombre) or []):
            d = fila if isinstance(fila, dict) else {}
            revisadas += 1
            for campo in ('FailRate', 'TmpFailRate', 'OutageTime'):
                try:
                    if float(d.get(campo) or 0) != 0:
                        no_cero += 1
                except (TypeError, ValueError):
                    pass
    aud.tasas_falla_no_cero = no_cero
    aud.hallazgos.append(
        f'Tasas de falla y tiempos de reposición: {no_cero} valores distintos de cero '
        f'en {revisadas} filas de catálogo. Con todo a cero, ComRel3 se ejecuta y '
        f'devuelve SAIDI = SAIFI = ENS = 0.'
    )

    subs = (tablas.get('SUBSTATION') or {})
    subs_filas = list(subs.values()) if hasattr(subs, 'values') else list(subs)
    aud.subestaciones = len(subs_filas)
    firmas = {
        (d.get('MVA'), d.get('R1'), d.get('X1'), d.get('R0'), d.get('X0'))
        for d in (f if isinstance(f, dict) else {} for f in subs_filas)
    }
    aud.subestaciones_distintas = len(firmas)
    if aud.subestaciones:
        aud.hallazgos.append(
            f'Subestaciones de cabecera: {aud.subestaciones} en [SUBSTATION], con '
            f'{aud.subestaciones_distintas} juego(s) distinto(s) de impedancia. '
            + ('Todas comparten el mismo valor por defecto de CYMDIST: el cortocircuito '
               'saldría igual en toda la red.' if aud.subestaciones_distintas <= 1
               else 'Hay impedancias diferenciadas.')
        )
    return aud
