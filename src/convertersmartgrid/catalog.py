"""Catálogo de parámetros eléctricos: tabla de entrada y auditoría del modelo.

El problema que resuelve. El catálogo de equipos que viene en el TXT de CYMDIST es lo
único que fija la impedancia de cada tramo, y nadie lo revisa contra la ficha del
conductor que de verdad está colgado. Cuando una fila está mal —y las hay— el error se
propaga en silencio a todos los tramos de ese tipo, en todos los alimentadores, y sale
por el otro lado como una pérdida técnica o una caída de tensión que nadie cuestiona
porque viene «del sistema».

Cómo lo resuelve. Se genera en ``input/`` una tabla con todos los parámetros de todos
los elementos que los alimentadores usan de verdad, cada uno con:

* lo que dice el modelo hoy,
* lo que dice la ficha del fabricante o la norma, cuando se tiene,
* cuánto se separan, y
* de dónde sale el valor de referencia.

El ingeniero completa las casillas que faltan con las fichas de sus proveedores y
vuelve a cargar el fichero. A partir de ahí la tabla manda.

Un límite que conviene tener claro: esta herramienta **no decide** que el catálogo esté
mal. Señala dónde el modelo y la ficha no concuerdan, con la cuenta hecha y la fuente
puesta, para que lo decida quien tiene la red delante. Corregir se corrige cuando
alguien lo pide, nunca solo.
"""

from __future__ import annotations

from .runtime_paths import staging_publicacion

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .catalog_data import (
    AAAC_FICHA,
    AAAC_FUENTE,
    AAAC_K_7_HILOS,
    AAAC_K_19_HILOS,
    AAAC_RHO20_OHM_MM2_KM,
    AAAC_SECCIONES_DERIVADAS,
    PARAMETROS,
    TRAFO_FUENTE_PERDIDAS,
    TRAFO_FUENTE_UK,
    TRAFO_GRUPO_TIPICO,
    TRAFO_IO_TIPICO,
    TRAFO_PERDIDAS_UE,
    TRAFO_TOMAS_TIPICAS,
    TRAFO_UK_TIPICO,
    aaac_r20_ohm_km,
    trafo_interpola,
)

INPUT_DIRNAME = 'input'
"""Carpeta donde vive la tabla. Se crea junto al proyecto, no dentro del código."""

CATALOG_FILENAME = 'catalogo_parametros.xlsx'

HOJAS = (
    'conductores_aereos',
    'cables_subterraneos',
    'transformadores_sed',
    'condensadores',
    'reguladores',
    'parametros_por_elemento',
    'hallazgos',
)

#: Umbral a partir del cual una diferencia con la ficha deja de ser redondeo.
TOLERANCIA_PCT = 2.0

#: Por encima de esto la diferencia ya no se explica por temperatura ni por cableado.
GRAVE_PCT = 10.0

#: Rango físico de la susceptancia de una línea aérea de MT, en µS/km.
B_AEREO_MIN, B_AEREO_MAX = 1.0, 8.0

#: Rango físico de la susceptancia de un cable de MT, en µS/km.
B_CABLE_MIN, B_CABLE_MAX = 30.0, 400.0


class CatalogError(RuntimeError):
    """La tabla de entrada no se puede leer o le falta algo imprescindible."""


# --------------------------------------------------------------------------------
# Hallazgos
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Hallazgo:
    """Una discrepancia entre el modelo y la referencia, con su cuenta hecha."""

    severidad: str
    """``grave``, ``aviso`` o ``dato``."""
    elemento: str
    codigo: str
    atributo: str
    valor_modelo: float | str
    valor_referencia: float | str
    unidad: str
    mensaje: str
    fuente: str
    tramos: int = 0
    km: float = 0.0
    alimentadores: int = 0
    unidad_uso: str = 'tramos'
    """Qué se está contando en ``tramos``: tramos de línea, o unidades de equipo."""

    @property
    def desviacion_pct(self) -> float | None:
        try:
            ref = float(self.valor_referencia)
            mod = float(self.valor_modelo)
        except (TypeError, ValueError):
            return None
        if ref == 0.0:
            return None
        return (mod - ref) / ref * 100.0

    def linea(self) -> str:
        d = self.desviacion_pct
        cola = f' ({d:+.1f} %)' if d is not None else ''
        uso = ''
        if self.tramos:
            uso = f' — {self.tramos:,} {self.unidad_uso}'
            if self.km:
                uso += f', {self.km:,.1f} km'
        return (f'[{self.severidad}] {self.elemento} {self.codigo}.{self.atributo}: '
                f'modelo {self.valor_modelo} vs referencia {self.valor_referencia} '
                f'{self.unidad}{cola}{uso}. {self.mensaje}')


@dataclass
class UsoTipo:
    """Cuánto se usa un tipo de línea en el conjunto de alimentadores."""

    codigo: str
    tipo: Any
    tramos: int = 0
    km: float = 0.0
    alimentadores: set[str] = field(default_factory=set)


@dataclass
class Auditoria:
    """Resultado de comparar los modelos con la referencia."""

    hallazgos: list[Hallazgo] = field(default_factory=list)
    usos: dict[str, UsoTipo] = field(default_factory=dict)
    trafos_kva: dict[float, int] = field(default_factory=dict)
    km_total: float = 0.0
    tramos_total: int = 0

    @property
    def graves(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad == 'grave']

    @property
    def avisos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad == 'aviso']

    @property
    def km_afectados(self) -> float:
        """Kilómetros de red bajo al menos un hallazgo grave, sin contar dos veces."""
        vistos: dict[str, float] = {}
        for h in self.graves:
            vistos[h.codigo] = max(vistos.get(h.codigo, 0.0), h.km)
        return sum(vistos.values())

    def resumen(self) -> str:
        pct = (self.km_afectados / self.km_total * 100.0) if self.km_total else 0.0
        return (f'{len(self.graves)} hallazgos graves y {len(self.avisos)} avisos sobre '
                f'{self.tramos_total:,} tramos ({self.km_total:,.1f} km). '
                f'Afectan a {self.km_afectados:,.1f} km, el {pct:.1f} % de la red.')


# --------------------------------------------------------------------------------
# Lectura de los códigos del catálogo CYMDIST
# --------------------------------------------------------------------------------


def seccion_de_codigo(codigo: str) -> float | None:
    """Sección en mm² a partir del código del catálogo, o ``None`` si no se deduce.

    Los códigos siguen el patrón ``<material><sección×10><fases><variante>``:
    ``AA12003D`` es aleación de aluminio de 120,0 mm², 3 fases, variante D. El mismo
    patrón vale para ``CU`` (cobre), ``N2`` y ``NK`` (cables) y ``EC``.

    Se devuelve ``None`` para ``DEFAULT`` y para cualquier código que no encaje: es
    preferible no auditar un tipo que auditarlo contra una sección inventada.
    """
    if len(codigo) < 6:
        return None
    cuerpo = codigo[2:6]
    if not cuerpo.isdigit():
        return None
    seccion = int(cuerpo) / 10.0
    return seccion if seccion > 0 else None


def material_de_codigo(codigo: str) -> str:
    return {
        'AA': 'AAAC', 'CU': 'Cobre', 'N2': 'Cable XLPE', 'NK': 'Cable XLPE',
        'EC': 'Cable XLPE',
    }.get(codigo[:2].upper(), '')


def es_aereo(tipo: Any) -> bool:
    return getattr(tipo, 'source_table', '') == 'LINE'


# --------------------------------------------------------------------------------
# Auditoría
# --------------------------------------------------------------------------------


def recolectar_uso(models: Iterable[Any]) -> tuple[dict[str, UsoTipo], dict[float, int], int, float]:
    """Cuenta tramos, kilómetros y alimentadores por tipo, y potencias de SED."""
    usos: dict[str, UsoTipo] = {}
    trafos: dict[float, int] = {}
    tramos = 0
    km = 0.0
    for model in models:
        for tipo in model.line_types.values():
            usos.setdefault(tipo.code, UsoTipo(tipo.code, tipo))
        for line in model.lines:
            tipo = model.line_types.get(line.type_key)
            if tipo is None:
                continue
            uso = usos.setdefault(tipo.code, UsoTipo(tipo.code, tipo))
            uso.tramos += 1
            uso.km += line.length_km
            uso.alimentadores.add(model.name)
            tramos += 1
            km += line.length_km
        for sed in getattr(model, 'seds', ()):
            if sed.design_kva > 0:
                trafos[sed.design_kva] = trafos.get(sed.design_kva, 0) + 1
    return usos, trafos, tramos, km


def _auditar_resistencia_aaac(uso: UsoTipo) -> list[Hallazgo]:
    seccion = seccion_de_codigo(uso.codigo)
    if seccion is None or not uso.codigo.upper().startswith('AA'):
        return []
    esperado = aaac_r20_ohm_km(seccion)
    real = float(uso.tipo.r1_ohm_km)
    if real <= 0:
        return []
    desv = abs(real - esperado) / esperado * 100.0
    if desv < TOLERANCIA_PCT:
        return []
    publicada = seccion in AAAC_FICHA
    if desv >= GRAVE_PCT:
        # Si la resistencia coincide con la de otra sección normalizada, casi siempre
        # es una fila copiada. Decirlo ahorra la mitad de la investigación.
        pista = ''
        for otra in sorted(set(AAAC_FICHA) | set(AAAC_SECCIONES_DERIVADAS)):
            if otra != seccion and abs(real - aaac_r20_ohm_km(otra)) / real < 0.02:
                pista = (f' El valor coincide con el de {otra:g} mm², así que parece una '
                         f'fila copiada del catálogo, no una medida.')
                break
        equivalente = AAAC_RHO20_OHM_MM2_KM * AAAC_K_7_HILOS / real
        mensaje = (
            f'La resistencia del modelo corresponde a un conductor de unos '
            f'{equivalente:.0f} mm², no a los {seccion:g} mm² que declara el código.'
            f'{pista} Revisar con la ficha del conductor instalado.'
        )
        sev = 'grave'
    else:
        mensaje = (
            'Diferencia moderada: puede ser otra temperatura de referencia o otro '
            'factor de cableado. Confirmar con la ficha antes de tocarla.'
        )
        sev = 'aviso'
    fuente = AAAC_FUENTE + ('' if publicada else ' (sección derivada con ρ20/S · k)')
    return [Hallazgo(
        sev, 'Conductor aéreo', uso.codigo, 'rline', round(real, 4), round(esperado, 4),
        'Ω/km', mensaje, fuente, uso.tramos, uso.km, len(uso.alimentadores),
    )]


def _auditar_susceptancia(uso: UsoTipo) -> list[Hallazgo]:
    b = float(getattr(uso.tipo, 'b1_source', 0.0) or 0.0)
    aereo = es_aereo(uso.tipo)
    lo, hi = (B_AEREO_MIN, B_AEREO_MAX) if aereo else (B_CABLE_MIN, B_CABLE_MAX)
    clase = 'Conductor aéreo' if aereo else 'Cable subterráneo'
    if b <= 0:
        return [Hallazgo(
            'aviso', clase, uso.codigo, 'bline', b, f'{lo}–{hi}', 'µS/km',
            'El catálogo no trae susceptancia para este tipo; PowerFactory la tomará '
            'como cero y no habrá corriente capacitiva en esos tramos.',
            'Rango físico para MT a 60 Hz', uso.tramos, uso.km, len(uso.alimentadores),
        )]
    if lo <= b <= hi:
        return []
    # Fuera de rango: casi siempre es un error de unidad en la fila del catálogo.
    factor = ''
    for exp in (3, 4, 6):
        if lo <= b * 10 ** exp <= hi:
            factor = f' Multiplicada por 10^{exp} cae en el rango, así que apunta a un error de unidad.'
            break
    return [Hallazgo(
        'grave', clase, uso.codigo, 'bline', round(b, 6), f'{lo}–{hi}', 'µS/km',
        f'Susceptancia fuera de todo rango físico para MT a 60 Hz.{factor}',
        'Rango físico para MT a 60 Hz', uso.tramos, uso.km, len(uso.alimentadores),
    )]


def _auditar_homopolar(uso: UsoTipo) -> list[Hallazgo]:
    r1, r0 = float(uso.tipo.r1_ohm_km), float(uso.tipo.r0_ohm_km)
    x1, x0 = float(uso.tipo.x1_ohm_km), float(uso.tipo.x0_ohm_km)
    if r1 <= 0 or x1 <= 0:
        return []
    if not (math.isclose(r0, r1, rel_tol=1e-6) and math.isclose(x0, x1, rel_tol=1e-6)):
        return []
    aereo = es_aereo(uso.tipo)
    clase = 'Conductor aéreo' if aereo else 'Cable subterráneo'
    esperado = 'R0 ≈ 2–3 × R1 y X0 ≈ 3–3,5 × X1' if aereo else 'R0 > R1 y X0 ≠ X1'
    return [Hallazgo(
        'aviso', clase, uso.codigo, 'rline0 / xline0', f'R0={r0:g}, X0={x0:g}',
        esperado, 'Ω/km',
        'La secuencia homopolar es copia exacta de la directa. Con el retorno por '
        'tierra eso no ocurre, así que el cortocircuito monofásico y los ajustes de '
        'protección de tierra saldrán optimistas. No afecta al flujo de potencia '
        'equilibrado.',
        'Teoría de componentes simétricas con retorno por tierra',
        uso.tramos, uso.km, len(uso.alimentadores),
    )]


def _perdidas_fabricadas_w(kva: float) -> tuple[float, float]:
    """Lo que el escritor DGS pone hoy: pcutr = 1 % de Sn y pfe = 0,15 % de Sn.

    Son dos fórmulas, no dos medidas. Están calibradas contra una única muestra
    (NA205) y se aplican por igual a toda potencia, que es justo lo que se audita.
    """
    return (
        max(kva / 1000.0 * 10.0, 0.1) * 1000.0,
        max(kva / 1000.0 * 1.5, 0.05) * 1000.0,
    )


def _auditar_trafos(trafos: dict[float, int]) -> list[Hallazgo]:
    """Compara las pérdidas que el conversor fabrica con los máximos reglamentarios.

    Se agrega en un hallazgo por atributo, no uno por potencia. Aunque la desviación
    se calcule potencia a potencia, **el defecto es uno solo**: una fórmula fija
    aplicada a todo el parque. Emitir 84 hallazgos idénticos daría la impresión de 84
    problemas distintos y enterraría los de conductor, que sí son independientes entre
    sí. El detalle por potencia está en la hoja «transformadores_sed».
    """
    hallazgos: list[Hallazgo] = []
    if not trafos:
        return hallazgos

    for atributo, indice, etiqueta, consecuencia in (
        ('pcutr', 0, 'con carga',
         'Poner el valor del protocolo de ensayo de cada transformador.'),
        ('pfe', 1, 'en vacío',
         'Son pérdidas permanentes: sobreestimarlas infla la energía no facturada.'),
    ):
        afectadas: list[tuple[float, int, float, float]] = []
        for kva, cuantos in sorted(trafos.items()):
            limite = trafo_interpola(kva, TRAFO_PERDIDAS_UE, indice)
            if limite is None:
                continue
            modelo = _perdidas_fabricadas_w(kva)[indice]
            if modelo > limite * 1.05:
                afectadas.append((kva, cuantos, modelo, limite))
        if not afectadas:
            continue
        unidades = sum(c for _, c, _, _ in afectadas)
        peor = max(afectadas, key=lambda t: (t[2] - t[3]) / t[3])
        menor = min(a[0] for a in afectadas)
        mayor = max(a[0] for a in afectadas)
        rango = f'{menor:g} kVA' if menor == mayor else f'{menor:g}–{mayor:g} kVA'
        hallazgos.append(Hallazgo(
            'grave', 'Transformador SED', rango, atributo,
            round(peor[2], 1), round(peor[3], 1), 'W',
            f'Las pérdidas {etiqueta} no salen de ninguna ficha: el conversor las '
            f'calcula con una fracción fija de la potencia nominal, y en '
            f'{len(afectadas)} de las {len(trafos)} potencias del parque el resultado '
            f'supera el máximo reglamentario. El peor caso es {peor[0]:g} kVA. '
            f'{consecuencia}',
            TRAFO_FUENTE_PERDIDAS, unidades, 0.0, 0, 'transformadores',
        ))

    hallazgos.append(Hallazgo(
        'dato', 'Transformador SED', 'todas las potencias', 'curmg', 0.0,
        f'{min(TRAFO_IO_TIPICO.values()):.1f}–{max(TRAFO_IO_TIPICO.values()):.1f}',
        '%',
        'La corriente de magnetización se escribe como cero para todos los '
        'transformadores, así que el modelo no consume reactiva en vacío. Con '
        f'{sum(trafos.values()):,} SED el efecto agregado no es despreciable.',
        TRAFO_FUENTE_UK, sum(trafos.values()), 0.0, 0, 'transformadores',
    ))
    return hallazgos


def auditar(models: Iterable[Any]) -> Auditoria:
    """Compara los modelos con la referencia y devuelve los hallazgos."""
    modelos = list(models)
    usos, trafos, tramos, km = recolectar_uso(modelos)
    aud = Auditoria(usos=usos, trafos_kva=trafos, tramos_total=tramos, km_total=km)
    for uso in sorted(usos.values(), key=lambda u: -u.km):
        if uso.codigo.upper() == 'DEFAULT':
            continue
        aud.hallazgos.extend(_auditar_resistencia_aaac(uso))
        aud.hallazgos.extend(_auditar_susceptancia(uso))
        aud.hallazgos.extend(_auditar_homopolar(uso))
    aud.hallazgos.extend(_auditar_trafos(trafos))
    orden = {'grave': 0, 'aviso': 1, 'dato': 2}
    aud.hallazgos.sort(key=lambda h: (orden.get(h.severidad, 9), -h.km, h.codigo))
    return aud


# --------------------------------------------------------------------------------
# Escritura de la tabla de entrada
# --------------------------------------------------------------------------------

#: Columnas de las hojas de conductor y de cable.
#:
#: El par ``*_modelo_*`` / ``*_ficha_*`` es lo que hace legible la tabla: a la
#: izquierda lo que hoy tiene el modelo, a la derecha lo que dice la ficha. La
#: identidad del elemento —``codigo``, ``material``, ``seccion_mm2``— sale del TXT o
#: de la base Access y **no se toca**: un AAAC de 120 mm² sigue siendo un AAAC de
#: 120 mm². Lo que se corrige son sus características.
COLUMNAS_CONDUCTOR = (
    'codigo', 'material', 'seccion_mm2', 'tramos', 'km', 'alimentadores',
    'R1_modelo_ohm_km', 'R1_ficha_ohm_km', 'desviacion_pct',
    'X1_modelo_ohm_km', 'X1_ficha_ohm_km',
    'R0_modelo_ohm_km', 'R0_ficha_ohm_km',
    'X0_modelo_ohm_km', 'X0_ficha_ohm_km',
    'B1_modelo_uS_km', 'B1_ficha_uS_km',
    'ampacidad_modelo_A', 'ampacidad_ficha_A',
    'diametro_mm', 'hilos', 'Ithr_kA_1s', 'temp_servicio_C',
    'estado', 'fuente', 'observaciones',
)

#: ``columna de ficha -> atributo de LineType``. Es la única definición del enlace
#: entre la tabla y el modelo: añadir una característica corregible es añadir aquí
#: una línea, y el lector, el aplicador y el informe la recogen solos.
CARACTERISTICAS = {
    'R1_ficha_ohm_km': ('r1_ohm_km', 'rline', 'Ω/km'),
    'X1_ficha_ohm_km': ('x1_ohm_km', 'xline', 'Ω/km'),
    'R0_ficha_ohm_km': ('r0_ohm_km', 'rline0', 'Ω/km'),
    'X0_ficha_ohm_km': ('x0_ohm_km', 'xline0', 'Ω/km'),
    'B1_ficha_uS_km': ('b1_source', 'bline', 'µS/km'),
    'ampacidad_ficha_A': ('ampacity_a', 'sline', 'A'),
}

COLUMNAS_TRAFO = (
    'kVA', 'unidades_en_modelo', 'tension_AT_kV', 'tension_BT_kV', 'grupo_conexion',
    'uk_pct', 'Pk_W', 'Po_W', 'io_pct', 'tomas',
    'Pk_max_nivel1_W', 'Po_max_nivel1_W', 'Pk_max_nivel2_W', 'Po_max_nivel2_W',
    'estado', 'fuente', 'observaciones',
)

COLUMNAS_CONDENSADOR = (
    'codigo', 'kvar', 'tension_kV', 'conexion', 'escalones', 'perdidas_W_kvar',
    'nodo', 'estado', 'fuente', 'observaciones',
)

COLUMNAS_REGULADOR = (
    'codigo', 'kVA', 'tension_kV', 'rango_regulacion_pct', 'numero_tomas',
    'escalon_pct', 'ancho_banda_V', 'RT_corriente', 'RT_tension',
    'nodo', 'estado', 'fuente', 'observaciones',
)

COLUMNAS_PARAMETRO = (
    'elemento', 'clase_PowerFactory', 'atributo', 'descripcion', 'unidad',
    'origen_actual', 'ficha_necesaria', 'que_estudio_afecta',
)

COLUMNAS_HALLAZGO = (
    'severidad', 'elemento', 'codigo', 'atributo', 'valor_modelo',
    'valor_referencia', 'unidad', 'desviacion_pct', 'tramos', 'km',
    'alimentadores', 'mensaje', 'fuente',
)


def _hoja_conductores(aud: Auditoria, aereos: bool) -> list[list[Any]]:
    """Una fila por tipo en uso: identidad del TXT/MDB, valores del modelo y de ficha.

    La columna ``R1_ficha_ohm_km`` se precarga cuando hay fuente para hacerlo, de modo
    que el flujo por defecto ya corrige sin que nadie teclee nada. Las demás columnas
    ``*_ficha_*`` salen vacías a propósito: no hay fuente pública que las respalde y
    una casilla en blanco con su fuente anotada es más útil que un número inventado en
    una tabla que va a alimentar decisiones de inversión.
    """
    filas: list[list[Any]] = []
    for uso in sorted(aud.usos.values(), key=lambda u: -u.km):
        if es_aereo(uso.tipo) != aereos:
            continue
        codigo = uso.codigo
        seccion = seccion_de_codigo(codigo)
        tipo = uso.tipo
        r1 = float(tipo.r1_ohm_km)
        r1_ficha: float | str = ''
        desv: float | str = ''
        estado = 'por_confirmar'
        fuente = 'Pendiente: ficha del proveedor'
        observaciones = ''
        if codigo.upper().startswith('AA') and seccion:
            esperado = aaac_r20_ohm_km(seccion)
            r1_ficha = round(esperado, 6)
            if r1 > 0:
                desv = round((r1 - esperado) / esperado * 100.0, 1)
            estado = 'ficha' if seccion in AAAC_FICHA else 'derivado'
            fuente = AAAC_FUENTE
            if seccion not in AAAC_FICHA:
                fuente += ' — sección derivada con ρ20/S · k'
        elif codigo.upper() != 'DEFAULT' and seccion:
            observaciones = (
                f'Identidad conservada del export: {material_de_codigo(codigo)} de '
                f'{seccion:g} mm². Para corregir sus características, escriba el valor '
                f'de la ficha de su proveedor y ponga «ficha» en «estado».'
            )
        diametro: float | str = ''
        hilos: int | str = ''
        if seccion in AAAC_FICHA:
            diametro = float(AAAC_FICHA[seccion]['diam_ext_mm'])
            hilos = int(AAAC_FICHA[seccion]['hilos'])
        filas.append([
            codigo, material_de_codigo(codigo), seccion or '',
            uso.tramos, round(uso.km, 3), len(uso.alimentadores),
            round(r1, 6), r1_ficha, desv,
            round(float(tipo.x1_ohm_km), 6), '',
            round(float(tipo.r0_ohm_km), 6), '',
            round(float(tipo.x0_ohm_km), 6), '',
            round(float(getattr(tipo, 'b1_source', 0.0) or 0.0), 6), '',
            round(float(tipo.ampacity_a), 1), '',
            diametro, hilos, '', '',
            estado, fuente, observaciones,
        ])
    return filas


def _hoja_trafos(aud: Auditoria, nominal_kv: float) -> list[list[Any]]:
    filas: list[list[Any]] = []
    for kva, cuantos in sorted(aud.trafos_kva.items()):
        pk1 = trafo_interpola(kva, TRAFO_PERDIDAS_UE, 0)
        po1 = trafo_interpola(kva, TRAFO_PERDIDAS_UE, 1)
        pk2 = trafo_interpola(kva, TRAFO_PERDIDAS_UE, 2)
        po2 = trafo_interpola(kva, TRAFO_PERDIDAS_UE, 3)
        uk = trafo_interpola(kva, TRAFO_UK_TIPICO)
        io = trafo_interpola(kva, TRAFO_IO_TIPICO)
        dentro = pk1 is not None
        filas.append([
            kva, cuantos, round(nominal_kv, 4), 0.22, TRAFO_GRUPO_TIPICO,
            round(uk, 2) if uk is not None else '',
            round(pk2, 0) if pk2 is not None else '',
            round(po2, 0) if po2 is not None else '',
            round(io, 2) if io is not None else '',
            TRAFO_TOMAS_TIPICAS,
            round(pk1, 0) if pk1 is not None else '',
            round(po1, 0) if po1 is not None else '',
            round(pk2, 0) if pk2 is not None else '',
            round(po2, 0) if po2 is not None else '',
            'referencia' if dentro else 'por_confirmar',
            TRAFO_FUENTE_PERDIDAS if dentro else 'Fuera del rango tabulado: pedir ficha',
            '' if dentro else 'Potencia fuera de la tabla del Reglamento: no se interpola.',
        ])
    return filas


def construir_hojas(aud: Auditoria, *, nominal_kv: float = 22.9) -> dict[str, tuple[tuple[str, ...], list[list[Any]]]]:
    """Cabeceras y filas de cada hoja del catálogo."""
    return {
        'conductores_aereos': (COLUMNAS_CONDUCTOR, _hoja_conductores(aud, True)),
        'cables_subterraneos': (COLUMNAS_CONDUCTOR, _hoja_conductores(aud, False)),
        'transformadores_sed': (COLUMNAS_TRAFO, _hoja_trafos(aud, nominal_kv)),
        'condensadores': (COLUMNAS_CONDENSADOR, []),
        'reguladores': (COLUMNAS_REGULADOR, []),
        'parametros_por_elemento': (COLUMNAS_PARAMETRO, [
            [p.elemento, p.clase_pf, p.atributo, p.descripcion, p.unidad,
             {'txt': 'fuente'}.get(p.origen, p.origen), p.ficha_necesaria, p.impacto]
            for p in PARAMETROS
        ]),
        'hallazgos': (COLUMNAS_HALLAZGO, [
            [h.severidad, h.elemento, h.codigo, h.atributo, h.valor_modelo,
             h.valor_referencia, h.unidad,
             round(h.desviacion_pct, 1) if h.desviacion_pct is not None else '',
             h.tramos, round(h.km, 3), h.alimentadores, h.mensaje, h.fuente]
            for h in aud.hallazgos
        ]),
    }


def input_dir(base: Path | str = '.') -> Path:
    """Carpeta ``input/``, creada si no existe."""
    carpeta = Path(base) / INPUT_DIRNAME
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def escribir_catalogo(
    aud: Auditoria, path: Path | str | None = None, *,
    base: Path | str = '.', nominal_kv: float = 22.9,
) -> Path:
    """Escribe el catálogo en ``input/catalogo_parametros.xlsx``."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:  # pragma: no cover - depende de la instalación
        raise CatalogError(
            'openpyxl es necesario para escribir el catálogo. '
            'Instale con: pip install -r requirements.txt'
        ) from exc

    destino = Path(path) if path is not None else input_dir(base) / CATALOG_FILENAME
    destino.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)
    cabecera_fill = PatternFill('solid', fgColor='DDEBF7')
    grave_fill = PatternFill('solid', fgColor='F8CBAD')
    aviso_fill = PatternFill('solid', fgColor='FFE699')

    for nombre, (columnas, filas) in construir_hojas(aud, nominal_kv=nominal_kv).items():
        ws = wb.create_sheet(nombre[:31])
        ws.append(list(columnas))
        for celda in ws[1]:
            celda.font = Font(bold=True)
            celda.fill = cabecera_fill
            celda.alignment = Alignment(wrap_text=True, vertical='center')
        for fila in filas:
            ws.append(fila)
        if nombre == 'hallazgos':
            for fila in ws.iter_rows(min_row=2):
                sev = fila[0].value
                if sev == 'grave':
                    fila[0].fill = grave_fill
                elif sev == 'aviso':
                    fila[0].fill = aviso_fill
        ws.freeze_panes = 'A2'
        for i, columna in enumerate(columnas, start=1):
            ancho = 14
            if columna in ('mensaje', 'fuente', 'descripcion', 'ficha_necesaria',
                           'que_estudio_afecta', 'observaciones'):
                ancho = 60
            elif columna in ('codigo', 'elemento', 'atributo', 'clase_PowerFactory'):
                ancho = 22
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = ancho

    wb.save(destino)
    return destino


# --------------------------------------------------------------------------------
# Lectura de la tabla, ya completada por el ingeniero
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class CorreccionConductor:
    """Los valores de ficha de un tipo, listos para sustituir a los del modelo.

    ``valores`` va indexado por el **atributo de** :class:`~convertersmartgrid.model.LineType`,
    no por el nombre de la columna: así el aplicador no vuelve a saber nada del
    formato de la hoja.
    """

    codigo: str
    valores: dict[str, float] = field(default_factory=dict)
    fuente: str = ''
    estado: str = ''

    def aplica(self) -> bool:
        return bool(self.valores)

    # Accesos cómodos para el caso corriente, que es la resistencia directa.
    @property
    def r1_ohm_km(self) -> float | None:
        return self.valores.get('r1_ohm_km')

    @property
    def ampacity_a(self) -> float | None:
        return self.valores.get('ampacity_a')


@dataclass(frozen=True)
class Cambio:
    """Un parámetro que cambia, con lo que costó y a cuánta red afecta."""

    codigo: str
    atributo_pf: str
    unidad: str
    antes: float
    despues: float
    tramos: int = 0
    km: float = 0.0
    fuente: str = ''

    @property
    def variacion_pct(self) -> float | None:
        if self.antes == 0.0:
            return None
        return (self.despues - self.antes) / self.antes * 100.0

    def linea(self) -> str:
        v = self.variacion_pct
        cola = f' ({v:+.1f} %)' if v is not None else ''
        uso = f' — {self.tramos:,} tramos, {self.km:,.1f} km' if self.tramos else ''
        return (f'{self.codigo}.{self.atributo_pf}: {self.antes:g} → '
                f'{self.despues:g} {self.unidad}{cola}{uso}')


def _num(valor: Any) -> float | None:
    if valor is None or valor == '':
        return None
    try:
        n = float(str(valor).replace(',', '.').strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


ESTADOS_QUE_CORRIGEN = ('ficha', 'derivado')
"""Los únicos estados que autorizan a tocar el modelo sin que nadie lo pida."""


def leer_catalogo(
    path: Path | str, *, incluir_referencia: bool = False,
) -> dict[str, CorreccionConductor]:
    """Lee las columnas ``*_ficha_*`` del catálogo y devuelve las correcciones.

    Solo se toman las filas cuyo ``estado`` es ``ficha`` o ``derivado``: una fila que
    sigue marcada ``por_confirmar`` no corrige nada, por mucho que tenga un número
    escrito. Es la salvaguarda que impide que un valor provisional entre en el modelo
    como si fuera de fabricante.

    ``incluir_referencia`` admite además las filas ``referencia`` —valores típicos de
    norma, no de la ficha del equipo instalado—. Existe porque a veces se quiere ver
    el efecto de un valor plausible antes de pedir la ficha, pero es una decisión
    consciente de quien ejecuta, nunca lo que pasa por defecto.
    """
    estados_validos = set(ESTADOS_QUE_CORRIGEN)
    if incluir_referencia:
        estados_validos.add('referencia')
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise CatalogError('openpyxl es necesario para leer el catálogo.') from exc

    ruta = Path(path)
    if not ruta.exists():
        raise CatalogError(f'No existe el catálogo: {ruta}')
    wb = load_workbook(ruta, data_only=True)
    correcciones: dict[str, CorreccionConductor] = {}
    for nombre in ('conductores_aereos', 'cables_subterraneos'):
        if nombre not in wb.sheetnames:
            continue
        ws = wb[nombre]
        filas = list(ws.iter_rows(values_only=True))
        if not filas:
            continue
        cab = {str(c).strip(): i for i, c in enumerate(filas[0]) if c}
        if 'codigo' not in cab:
            raise CatalogError(f'La hoja «{nombre}» no tiene columna «codigo».')

        def celda(fila: Sequence[Any], col: str) -> Any:
            i = cab.get(col)
            return fila[i] if i is not None and i < len(fila) else None

        for fila in filas[1:]:
            codigo = celda(fila, 'codigo')
            if not codigo:
                continue
            estado = str(celda(fila, 'estado') or '').strip().lower()
            if estado not in estados_validos:
                continue
            valores = {}
            for columna, (atributo, _pf, _unidad) in CARACTERISTICAS.items():
                valor = _num(celda(fila, columna))
                if valor is not None:
                    valores[atributo] = valor
            corr = CorreccionConductor(
                codigo=str(codigo).strip(), valores=valores,
                fuente=str(celda(fila, 'fuente') or '').strip(), estado=estado,
            )
            if corr.aplica():
                correcciones[corr.codigo] = corr
    return correcciones


#: Por debajo de esto no hay corrección que valga.
#:
#: Una resistencia de ficha viene con cuatro cifras significativas, así que una
#: diferencia del 0,1 % no dice nada sobre el conductor: dice cuántos decimales se
#: escribieron. Sin este margen, la hoja se llenaría de «correcciones» de 1,3511 a
#: 1,3510 que solo sirven para enterrar las de verdad.
TOLERANCIA_CAMBIO_REL = 1e-3


def _con_homopolar(valores: dict[str, float], actual) -> dict[str, float]:
    """``valores`` con la homopolar arrastrada desde la directa cuando hace falta.

    La homopolar del catálogo CYMDIST es, en todos los tipos, copia exacta de la
    directa. Si se corrige R1 y se deja R0 quieto, el resultado es R0 < R1, que con
    retorno por tierra no puede darse: sería peor que el defecto de partida, porque un
    valor imposible desconcierta más que uno consistente y erróneo. Mientras no haya
    valor de ficha para la homopolar, la copia se mantiene. ``actual(atributo)`` da el
    valor que tiene hoy el tipo, por atributo del modelo.
    """
    for directa, homopolar in (('r1_ohm_km', 'r0_ohm_km'), ('x1_ohm_km', 'x0_ohm_km')):
        nuevo_directo = valores.get(directa)
        if nuevo_directo is None or homopolar in valores:
            continue
        if math.isclose(actual(homopolar), actual(directa), rel_tol=TOLERANCIA_CAMBIO_REL):
            valores[homopolar] = nuevo_directo
    return valores


#: Atributo del modelo → (atributo de ``TypLne``, factor a la unidad de DIgSILENT, unidad
#: del informe). Sale de :data:`CARACTERISTICAS`; la corriente va en kA en ``sline``.
_EN_PF = {atr: (pf, 1e-3 if pf == 'sline' else 1.0, unidad)
          for atr, pf, unidad in CARACTERISTICAS.values()}


def fichas_para_pf(correcciones: dict[str, CorreccionConductor]) -> dict[str, dict[str, Any]]:
    """Las fichas del catálogo listas para el plan del ajuste de «Sin proyecto» (032:RF-14).

    ``{codigo: {'valores': {atributo del modelo: valor}, 'fuente': texto}}``; el guion de
    DIgSILENT las compara con cada ``TypLne`` con :func:`cambios_de_ficha`. Va en JSON, por
    eso no lleva objetos.
    """
    return {c: {'valores': dict(corr.valores), 'fuente': corr.fuente}
            for c, corr in sorted(correcciones.items()) if corr.aplica()}


def cambios_de_ficha(codigo: str, actuales_pf: dict[str, float | None], ficha: dict[str, Any],
                     *, tramos: int = 0, km: float = 0.0,
                     ) -> tuple[dict[str, float], list[Cambio], list[str]]:
    """Qué atributos de un ``TypLne`` cambia su ficha (032:RF-14, RF-16, RF-19).

    ``actuales_pf`` son los valores del tipo en DIgSILENT, por atributo de ``TypLne``
    (``rline``, ``sline`` en kA…). Devuelve los valores nuevos en unidades de DIgSILENT,
    los cambios para el informe (corriente en A) y los rechazos: una ficha que da cero o
    negativo donde el archivo tiene un valor positivo no se aplica, porque dejaría al
    conductor sin impedancia o sin capacidad (RF-19).
    """
    def actual(atr: str) -> float:
        pf, factor, _u = _EN_PF[atr]
        return float(actuales_pf.get(pf) or 0.0) / factor

    valores = _con_homopolar(dict(ficha.get('valores') or {}), actual)
    nuevos: dict[str, float] = {}
    cambios: list[Cambio] = []
    rechazos: list[str] = []
    for atr, valor in sorted(valores.items()):
        if atr not in _EN_PF:
            continue
        valor = float(valor)
        pf, factor, unidad = _EN_PF[atr]
        antes = actual(atr)
        if valor <= 0.0 and antes > 0.0:
            rechazos.append(f'{codigo}: la ficha da {pf}={valor:g} {unidad} y el archivo '
                            f'{antes:g} {unidad}; no se aplica (032:RF-19)')
            continue
        if math.isclose(valor, antes, rel_tol=TOLERANCIA_CAMBIO_REL):
            continue
        fuente = ficha.get('fuente') or ''
        if atr not in (ficha.get('valores') or {}):
            fuente += (' (arrastrado desde la secuencia directa: el catálogo tenía la '
                       'homopolar como copia y no hay valor de ficha para ella)')
        nuevos[pf] = valor * factor
        cambios.append(Cambio(codigo, pf, unidad, antes, valor, tramos, km, fuente))
    return nuevos, cambios, rechazos


def aplicar_correcciones(
    model: Any, correcciones: dict[str, CorreccionConductor],
) -> list[Cambio]:
    """Actualiza las características del modelo conservando la identidad del elemento.

    El flujo que implementa:

    1. El TXT o la base Access dan **qué elemento es** —``AA12003D`` es un AAAC de
       120 mm², ``NK12003D`` un cable de cobre de 120 mm²—. Eso es el inventario de
       lo que está físicamente instalado y **se mantiene intacto**: ni el código, ni
       el material, ni la sección, ni qué tramo usa qué tipo.
    2. El catálogo da, para esa misma designación, lo que dice la ficha del
       fabricante.
    3. Donde las características no concuerdan, mandan las de la ficha.

    La asimetría es deliberada y es lo que pidió el usuario: la designación viene del
    inventario de activos, mientras que la impedancia es un campo calculado del
    catálogo de CYMDIST, que es justo donde aparecen las filas copiadas. Ante una
    discrepancia se conserva la designación y se corrige el número.

    Conviene saber lo que eso implica. Si ``AA01003D`` es de verdad un conductor de
    10 mm², corregir su resistencia de 1,0891 a 3,3776 Ω/km la **triplica**, y con
    ella las pérdidas y la caída de tensión de esos tramos. El cambio es correcto,
    pero no es cosmético: por eso cada :class:`Cambio` lleva cuántos tramos y cuántos
    kilómetros toca, y el script no aplica nada sin enseñarlo antes.

    Trabaja sobre el modelo en memoria, antes de escribir el DGS. El TXT de origen no
    se toca: el catálogo de la empresa se corrige en la empresa, no aquí.
    """
    from dataclasses import replace

    # Cuánto pesa cada tipo, para que el informe diga a qué red afecta el cambio.
    peso: dict[str, tuple[int, float]] = {}
    for line in model.lines:
        tipo = model.line_types.get(line.type_key)
        if tipo is None:
            continue
        n, km = peso.get(tipo.code, (0, 0.0))
        peso[tipo.code] = (n + 1, km + line.length_km)

    cambios: list[Cambio] = []
    for clave, tipo in list(model.line_types.items()):
        corr = correcciones.get(tipo.code)
        if corr is None:
            continue
        valores = _con_homopolar(dict(corr.valores),
                                 lambda a, t=tipo: float(getattr(t, a, 0.0) or 0.0))

        nuevo = tipo
        for atributo, pf, unidad in CARACTERISTICAS.values():
            valor = valores.get(atributo)
            if valor is None:
                continue
            actual = float(getattr(tipo, atributo, 0.0) or 0.0)
            if math.isclose(valor, actual, rel_tol=TOLERANCIA_CAMBIO_REL):
                continue
            tramos, km = peso.get(tipo.code, (0, 0.0))
            fuente = corr.fuente
            if atributo not in corr.valores:
                fuente = (f'{corr.fuente} (arrastrado desde la secuencia directa: el '
                          f'catálogo tenía la homopolar como copia y no hay valor de '
                          f'ficha para ella)')
            cambios.append(Cambio(
                tipo.code, pf, unidad, actual, valor, tramos, km, fuente,
            ))
            nuevo = replace(nuevo, **{atributo: valor})
        if nuevo is not tipo:
            model.line_types[clave] = nuevo
    cambios.sort(key=lambda c: (-c.km, c.codigo, c.atributo_pf))
    return cambios


# --------------------------------------------------------------------------------
# El catálogo como fuente de equipos
# --------------------------------------------------------------------------------

#: Hoja del catálogo → tabla de equipos que entiende el modelo (la del BD_Equipo).
HOJA_A_TABLA = {
    'conductores_aereos': 'LINE',
    'cables_subterraneos': 'CONCENTRIC NEUTRAL CABLE',
}

#: Columna del catálogo → campo de la fila de equipos (``model._line_type_from_row``).
COLUMNA_MODELO_A_CAMPO = {
    'R1_modelo_ohm_km': 'R1',
    'X1_modelo_ohm_km': 'X1',
    'R0_modelo_ohm_km': 'R0',
    'X0_modelo_ohm_km': 'X0',
    'B1_modelo_uS_km': 'B1',
    'ampacidad_modelo_A': 'Amps',
}


@dataclass
class EquiposDesdeCatalogo:
    tablas: dict[str, tuple[dict[str, str], ...]]
    leidos: dict[str, int] = field(default_factory=dict)
    completados: dict[str, str] = field(default_factory=dict)
    """Código que faltaba → código del catálogo del que se tomaron sus valores."""
    sin_resolver: list[str] = field(default_factory=list)

    def texto(self) -> str:
        partes = [f'{t}: {n} tipos' for t, n in self.leidos.items()]
        if self.completados:
            partes.append('completados por sección y material: ' + ', '.join(
                f'{a}←{b}' for a, b in sorted(self.completados.items())))
        if self.sin_resolver:
            partes.append('SIN RESOLVER: ' + ', '.join(self.sin_resolver))
        return 'Equipos desde el catálogo — ' + '; '.join(partes)


def tablas_equipo_desde_catalogo(
    path: Path | str, *, codigos_en_red: Iterable[tuple[str, bool]] = (),
) -> EquiposDesdeCatalogo:
    """Construye el catálogo de equipos del modelo a partir de ``catalogo_parametros``.

    Para bases CYMDIST que traen la red pero **no** sus tablas de equipos (las
    ``CYMEQ*`` vacías). Cada fila del catálogo da un tipo con sus valores ``*_modelo_*``:
    la identidad —código, material, sección, aéreo o subterráneo— es la de la base. Las
    correcciones de ficha no se mezclan aquí: se aplican después con
    :func:`aplicar_correcciones`, como en cualquier otra conversión.

    ``codigos_en_red`` son los pares ``(código, aéreo)`` que usa la red. Si alguno no
    está en el catálogo se completa con el tipo **del mismo material y la misma
    sección** —el número de fases del código no cambia los parámetros por km del
    conductor—, y se informa. Si tampoco hay ese, queda en ``sin_resolver``: no se
    inventa un conductor.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise CatalogError('openpyxl es necesario para leer el catálogo.') from exc
    ruta = Path(path)
    if not ruta.exists():
        raise CatalogError(f'No existe el catálogo: {ruta}')
    wb = load_workbook(ruta, data_only=True, read_only=True)

    tablas: dict[str, list[dict[str, str]]] = {t: [] for t in HOJA_A_TABLA.values()}
    for hoja, tabla in HOJA_A_TABLA.items():
        if hoja not in wb.sheetnames:
            continue
        filas = list(wb[hoja].iter_rows(values_only=True))
        if not filas:
            continue
        cab = {str(c).strip(): i for i, c in enumerate(filas[0]) if c}
        for fila in filas[1:]:
            codigo = str(fila[cab['codigo']] or '').strip() if 'codigo' in cab else ''
            if not codigo:
                continue
            fila_eq = {'ID': codigo, 'B0': '0'}
            for columna, campo in COLUMNA_MODELO_A_CAMPO.items():
                i = cab.get(columna)
                valor = _num(fila[i]) if i is not None and i < len(fila) else None
                fila_eq[campo] = '' if valor is None else repr(float(valor))
            tablas[tabla].append(fila_eq)

    informe = EquiposDesdeCatalogo(tablas={})
    for codigo, aereo in sorted(set(codigos_en_red)):
        tabla = 'LINE' if aereo else 'CONCENTRIC NEUTRAL CABLE'
        if codigo.upper() == 'DEFAULT' or any(f['ID'] == codigo for f in tablas[tabla]):
            continue
        seccion, material = seccion_de_codigo(codigo), codigo[:2].upper()
        parecidos = [f for f in tablas[tabla]
                     if f['ID'][:2].upper() == material and seccion
                     and seccion_de_codigo(f['ID']) == seccion]
        if not parecidos:
            informe.sin_resolver.append(codigo)
            continue
        # Entre los de igual material y sección, el trifásico de la misma variante.
        parecidos.sort(key=lambda f: (f['ID'][-1:] != codigo[-1:], f['ID'][6:7] != '3', f['ID']))
        origen = parecidos[0]
        tablas[tabla].append({**origen, 'ID': codigo})
        informe.completados[codigo] = origen['ID']

    informe.tablas = {t: tuple(filas) for t, filas in tablas.items()}
    informe.leidos = {t: len(filas) for t, filas in tablas.items()}
    return informe


def leer_trafos(path: Path | str) -> dict[float, dict[str, float]]:
    """Transformadores de SED del catálogo: ``{kVA: {uk_pct, Pk_W, Po_W, io_pct}}``.

    Solo entran las potencias con ``uk_pct``, ``Pk_W`` y ``Po_W`` escritos; las que
    el catálogo deja en blanco (fuera de la tabla del Reglamento) no se inventan y el
    escritor del DGS recurre a su cálculo por defecto para ellas.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise CatalogError('openpyxl es necesario para leer el catálogo.') from exc
    wb = load_workbook(Path(path), data_only=True, read_only=True)
    if 'transformadores_sed' not in wb.sheetnames:
        return {}
    filas = list(wb['transformadores_sed'].iter_rows(values_only=True))
    if not filas:
        return {}
    cab = {str(c).strip(): i for i, c in enumerate(filas[0]) if c}
    salida: dict[float, dict[str, float]] = {}
    for fila in filas[1:]:
        def num(col: str) -> float | None:
            i = cab.get(col)
            return _num(fila[i]) if i is not None and i < len(fila) else None
        kva, uk, pk, po = num('kVA'), num('uk_pct'), num('Pk_W'), num('Po_W')
        if kva and uk and pk and po:
            salida[round(kva, 3)] = {'uk_pct': uk, 'Pk_W': pk, 'Po_W': po,
                                     'io_pct': num('io_pct') or 0.0}
    return salida


# --------------------------------------------------------------------------------
# Spec 053: el catálogo crece con cada código nuevo
# --------------------------------------------------------------------------------
#
# Las fichas técnicas son universales: el mismo código de norma vale para cualquier
# distribuidora (usuario, 2026-11-01). Al convertir NJA202 y R205 de Electro Oriente, seis
# códigos no estaban en el catálogo y sus tramos salían con R = X = 0; el flujo de NJA202
# solo convergía con la demanda al 11,3 %. Un código nuevo se añade con lo que se pueda
# deducir de fichas que ya están, anotado, hasta que se escriba la del fabricante.

#: Resistividad a 20 °C (IEC 60228): cobre recocido 100 % IACS y aluminio 61 % IACS.
RHO20_CU_OHM_MM2_M = 0.017241
RHO20_AL_OHM_MM2_M = 0.028264

#: Familias de cable (van a la hoja de cables); las demás son aéreas.
FAMILIAS_CABLE = ('N2', 'NK', 'EC')

#: Norma del regulador (Anexo 2 de VNR-GIS): la red autoportante son cables con aislamiento
#: XLPE trenzados sobre un portante; eléctricamente, el cable XLPE de cobre de su sección,
#: con la resistividad de su material. ``familia → (familia de referencia, ρ/ρCu, material)``.
FAMILIA_EQUIVALENTE = {
    'CS': ('N2', 1.0, 'Autoportante Cu (XLPE)'),
    'AS': ('N2', RHO20_AL_OHM_MM2_M / RHO20_CU_OHM_MM2_M, 'Autoportante Al (XLPE)'),
    # Electro Oriente (2026-11-01) usa en 22 alimentadores estas familias y no entregó su base de
    # parámetros con la descripción de la norma: protegido = el desnudo del mismo material (la
    # cubierta apenas cambia R y X), cable seco de Al = el N2XSY por ρAl/ρCu, «EC» = cable seco
    # de Cu. Quedan «por confirmar» hasta la ficha del fabricante (053:RF-5).
    'AP': ('AA', 1.0, 'Aluminio protegido (aleación de Al con cubierta)'),
    'CP': ('CU', 1.0, 'Cobre protegido (Cu con cubierta)'),
    'NA': ('N2', RHO20_AL_OHM_MM2_M / RHO20_CU_OHM_MM2_M, 'Cable seco Al (NA2XSY)'),
    'EC': ('N2', 1.0, 'Cable seco Cu'),
    'NY': ('N2', 1.0, 'Cable NYY Cu'),
    'YC': ('N2', 1.0, 'Cable Cu'),
    # 080:RF-50: con el catálogo propio ya no hay filas NK de otra empresa de las que deducir.
    'NK': ('N2', 1.0, 'Cable NKY Cu'),
}

# --- 080:RF-49 a RF-51: la semilla del catálogo de una empresa, sin datos de ninguna.
FUENTE_INDECO_AAAC = 'Indeco (Nexans Perú), catálogo de conductores: AAAC aleación 6201-T81'
FUENTE_INDECO_CU = 'Indeco (Nexans Perú), catálogo de conductores: cobre desnudo temple duro'
FUENTE_INDECO_N2XSY = 'Indeco (Nexans Perú), ficha N2XSY 8,7/15 kV: tres unipolares en triángulo'
#: {sección mm²: (R Ω/km a 20 °C, ampacidad A)}, de la ficha del fabricante.
FICHAS_AAAC = {16: (2.09, 100), 25: (1.31, 125), 35: (0.952, 160), 50: (0.663, 195), 70: (0.484, 235),
               95: (0.352, 300), 120: (0.275, 340), 150: (0.227, 395), 185: (0.181, 455)}
FICHAS_CU = {10: (1.87, 106), 16: (1.17, 141), 25: (0.741, 188), 35: (0.534, 229), 50: (0.395, 277),
             70: (0.273, 348)}
#: {sección mm²: (R Ω/km, X Ω/km, ampacidad A)}: la ficha del cable sí da la X.
FICHAS_N2XSY = {25: (0.727, 0.1713, 160), 35: (0.524, 0.1627, 190), 50: (0.387, 0.1513, 225),
                70: (0.268, 0.1426, 275), 95: (0.193, 0.1365, 325), 120: (0.153, 0.1305, 370)}
#: Separación media geométrica entre fases de una línea aérea de MT (m): la X depende poco de ella
#: (va en el logaritmo). Dato deducido, anotado en cada fila; la calibración no lo cambia.
SEPARACION_AEREA_M = 1.2
#: Radio medio geométrico de un conductor cableado de 7 hilos respecto de su radio.
RMG_7_HILOS = 0.7265


def reactancia_aerea_ohm_km(seccion_mm2: float) -> float:
    """080:RF-51: X = 2πf·2·10⁻⁴·ln(DMG/RMG), en Ω/km a 60 Hz.

    Ninguna ficha de fabricante trae la X de un conductor desnudo, porque depende de cómo se
    tiende. La que usaba el catálogo era la del modelo de una empresa.
    """
    radio_m = math.sqrt(seccion_mm2 / math.pi) / 1000.0
    return round(2 * math.pi * 60.0 * 2e-4 * math.log(SEPARACION_AEREA_M / (RMG_7_HILOS * radio_m)), 6)


def filas_semilla() -> dict[str, list[dict[str, Any]]]:
    """Las filas iniciales del catálogo de una empresa: solo fichas, sin uso de ninguna red."""
    nota = (f'X calculada por geometría: separación de {SEPARACION_AEREA_M:g} m, 60 Hz, 7 hilos '
            '(080:RF-51). R0 y X0 iguales a R1 y X1, sin efecto en el flujo equilibrado.')
    aereos = []
    for familia, fichas, material, fuente in (('AA', FICHAS_AAAC, 'AAAC', FUENTE_INDECO_AAAC),
                                              ('CU', FICHAS_CU, 'Cobre', FUENTE_INDECO_CU)):
        for seccion, (r1, amperios) in fichas.items():
            x1 = reactancia_aerea_ohm_km(float(seccion))
            aereos.append({'codigo': f'{familia}{seccion * 10:04d}3D', 'material': material,
                           'seccion_mm2': seccion, 'R1_ficha_ohm_km': r1, 'X1_ficha_ohm_km': x1,
                           'R0_ficha_ohm_km': r1, 'X0_ficha_ohm_km': x1, 'ampacidad_ficha_A': amperios,
                           'estado': 'ficha', 'fuente': fuente, 'observaciones': nota})
    cables = [{'codigo': f'N2{seccion * 10:04d}3D', 'material': 'Cable N2XSY Cu', 'seccion_mm2': seccion,
               'R1_ficha_ohm_km': r1, 'X1_ficha_ohm_km': x1, 'R0_ficha_ohm_km': r1, 'X0_ficha_ohm_km': x1,
               'ampacidad_ficha_A': amperios, 'estado': 'ficha', 'fuente': FUENTE_INDECO_N2XSY,
               'observaciones': 'R0 y X0 iguales a R1 y X1, sin efecto en el flujo equilibrado.'}
              for seccion, (r1, x1, amperios) in FICHAS_N2XSY.items()]
    return {'conductores_aereos': aereos, 'cables_subterraneos': cables}


def asegurar_catalogo_empresa(ruta: Path | str) -> Path:
    """080:RF-50: el catálogo de una empresa; si no existe, se crea con la semilla."""
    import os

    from openpyxl import Workbook

    from .runtime_paths import staging_publicacion

    ruta = Path(ruta)
    with _bloqueo():
        if ruta.is_file():
            return ruta
        ruta.parent.mkdir(parents=True, exist_ok=True)
        libro = Workbook()
        libro.remove(libro.active)
        for hoja, filas in filas_semilla().items():
            ws = libro.create_sheet(hoja)
            ws.append(list(COLUMNAS_CONDUCTOR))
            for fila in filas:
                ws.append(['' if fila.get(c) is None else fila.get(c, '') for c in COLUMNAS_CONDUCTOR])
        # 065:RF-10, RF-11: el catálogo vive en input/ del checkout; su borrador «.tmp» quedaba junto a
        # él si el proceso caía. Se prepara fuera del código, en el mismo volumen, y se publica de una vez.
        with staging_publicacion(ruta) as temporal:
            libro.save(temporal)
            os.replace(temporal, ruta)
    return ruta

_BLOQUEO_CATALOGO: list = []


def _bloqueo():
    """Un solo escritor del catálogo a la vez en el proceso (la web convierte en hilos)."""
    if not _BLOQUEO_CATALOGO:
        import threading
        _BLOQUEO_CATALOGO.append(threading.Lock())
    return _BLOQUEO_CATALOGO[0]


def _filas_de(ws) -> list[dict[str, Any]]:
    valores = list(ws.iter_rows(values_only=True))
    if not valores:
        return []
    cabecera = [str(c or '') for c in valores[0]]
    return [dict(zip(cabecera, v)) for v in valores[1:] if v and v[0]]


def _valor(fila: dict[str, Any], nombre: str, unidad: str) -> float | None:
    """El de la ficha si su estado corrige; si no, el del modelo (como lo lee la fuente)."""
    ficha = _num(fila.get(f'{nombre}_ficha_{unidad}'))
    if ficha is not None and str(fila.get('estado') or '') in ESTADOS_QUE_CORRIGEN:
        return ficha
    return _num(fila.get(f'{nombre}_modelo_{unidad}'))


def _referencia(filas: Sequence[dict[str, Any]], familia: str, seccion: float):
    """La fila de la familia con R1 y X1 cuya sección está más cerca (en proporción) de la
    pedida; a igual distancia, la que tiene ficha. ``(distancia, sin_ficha, código, fila, S)``."""
    cand = []
    for f in filas:
        codigo = str(f.get('codigo') or '').strip()
        s = seccion_de_codigo(codigo)
        if codigo[:2].upper() != familia or not s:
            continue
        if _valor(f, 'R1', 'ohm_km') is None or _valor(f, 'X1', 'ohm_km') is None:
            continue
        cand.append((abs(math.log(s / seccion)), str(f.get('estado') or '') != 'ficha', codigo, f, s))
    return min(cand, key=lambda c: c[:3]) if cand else None


def deducir_conductor(codigo: str, filas: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Los parámetros de un código que no está en el catálogo, con su regla (053:RF-2 a RF-5)."""
    familia = codigo[:2].upper()
    seccion = seccion_de_codigo(codigo)
    ref_familia, factor, material = FAMILIA_EQUIVALENTE.get(familia, (familia, 1.0, material_de_codigo(codigo)))
    base = {'codigo': codigo, 'seccion_mm2': seccion or '', 'material': material}
    pendiente = {**base, 'estado': 'por_confirmar', 'fuente': 'Pendiente: ficha del proveedor (053:RF-5)'}
    if not seccion:
        return {**pendiente, 'regla': 'sin sección en el código'}
    ref = _referencia(filas, ref_familia, seccion)
    if ref is None:
        return {**pendiente, 'regla': f'ninguna fila de la familia {ref_familia} con R y X'}
    _d, _sin_ficha, ref_codigo, f, s_ref = ref
    r1 = _valor(f, 'R1', 'ohm_km') * s_ref / seccion * factor
    r0_ref, x1 = _valor(f, 'R0', 'ohm_km'), _valor(f, 'X1', 'ohm_km')
    a_ref = _valor(f, 'ampacidad', 'A')
    out = {**base,
           'R1_modelo_ohm_km': round(r1, 6),
           'X1_modelo_ohm_km': x1,
           'R0_modelo_ohm_km': round(r0_ref * s_ref / seccion * factor, 6) if r0_ref is not None else round(r1, 6),
           'X0_modelo_ohm_km': _valor(f, 'X0', 'ohm_km') or x1,
           'B1_modelo_uS_km': _valor(f, 'B1', 'uS_km'),
           # El calor que se disipa crece con el perímetro (∝ √S) y las pérdidas son I²·R con
           # R ∝ 1/S: I ∝ S^0,75. Con otro material, la misma R·I²: I ∝ √(ρref/ρ).
           'ampacidad_modelo_A': (round(a_ref * (seccion / s_ref) ** 0.75 / math.sqrt(factor), 1)
                                  if a_ref else None),
           'estado': 'por_confirmar',
           'regla': (f'de {ref_codigo}: R·{s_ref:g}/{seccion:g}'
                     + (f'·{factor:.3f} (ρAl/ρCu, IEC 60228)' if factor != 1.0 else '')
                     + '; X, X0 y B1 iguales; ampacidad·(S/Sref)^0,75'
                     + ('·√(ρCu/ρAl)' if factor != 1.0 else '')),
           'fuente': f"Deducido (spec 053) de {ref_codigo}: {f.get('fuente') or 'catálogo'}"}
    if familia == 'AA':                                                              # RF-3
        out['R1_ficha_ohm_km'] = round(aaac_r20_ohm_km(seccion), 6)
        out['estado'] = 'ficha' if seccion in AAAC_FICHA else 'derivado'
        out['regla'] = 'R de la ficha universal del AAAC; ' + out['regla']
        out['fuente'] = AAAC_FUENTE + '; X, X0, B1 y ampacidad ' + out['fuente']
    return out


def ampliar_catalogo(path: Path | str, codigos: Iterable[str], *, origen: str = '',
                     fecha: str | None = None) -> list[dict[str, Any]]:
    """Añade al catálogo una fila por cada código que no tiene, sin tocar las demás (053:RF-1).

    Devuelve las filas añadidas, cada una con su regla en «observaciones». Se escribe en un
    fichero temporal que sustituye al catálogo, para que nunca quede a medias (RF-7). Es uno
    solo y universal: no depende de la empresa (RF-8).
    """
    import datetime as _dt
    import os

    from openpyxl import load_workbook

    ruta = Path(path)
    fecha = fecha or _dt.date.today().isoformat()
    with _bloqueo():
        wb = load_workbook(ruta)
        hojas = {n: wb[n] for n in ('conductores_aereos', 'cables_subterraneos') if n in wb.sheetnames}
        todas: list[dict[str, Any]] = []
        for ws in hojas.values():
            todas += _filas_de(ws)
        existentes = {str(f.get('codigo') or '').strip().upper() for f in todas
                      if _valor(f, 'R1', 'ohm_km') is not None}
        # Una fila que quedó pendiente (sin R ni X) se rellena en su sitio cuando ya se puede
        # deducir: con Electro Oriente, 20 códigos quedaban vacíos para siempre porque la regla
        # de su familia llegó después de añadirlos (2026-11-01).
        vacias = {}
        for hoja in hojas.values():
            cab = [str(c.value or '') for c in hoja[1]]
            for fila_xl in hoja.iter_rows(min_row=2):
                cod = str(fila_xl[0].value or '').strip().upper()
                if cod and cod not in existentes:
                    vacias[cod] = (cab, fila_xl)
        nuevas = []
        for codigo in dict.fromkeys(c.strip() for c in codigos if c and c.strip()):
            if codigo.upper() in existentes:
                continue
            fila = deducir_conductor(codigo, todas)
            if codigo.upper() in vacias:
                if fila.get('R1_modelo_ohm_km') is None:
                    continue
                cab, celdas = vacias[codigo.upper()]
                fila['observaciones'] = (f'Completado el {fecha} (spec 053). {fila.pop("regla")}. Con la '
                                         'ficha del fabricante, escriba sus valores y ponga «ficha».')
                for c, celda in zip(cab, celdas):
                    if c in fila and c != 'codigo':
                        celda.value = fila[c]
                existentes.add(codigo.upper())
                nuevas.append(fila)
                continue
            fila['observaciones'] = (f'Añadido el {fecha}' + (f' al aparecer en {origen}' if origen else '')
                                     + f" (spec 053). {fila.pop('regla')}. Con la ficha del fabricante, "
                                       'escriba sus valores y ponga «ficha».')
            nombre = 'cables_subterraneos' if codigo[:2].upper() in FAMILIAS_CABLE else 'conductores_aereos'
            ws = hojas.get(nombre)
            if ws is None:
                ws = hojas[nombre] = wb.create_sheet(nombre)
                ws.append(list(COLUMNAS_CONDUCTOR))
            cabecera = [str(c.value or '') for c in ws[1]]
            ws.append(['' if fila.get(c) is None else fila.get(c, '') for c in cabecera])
            todas.append(fila)
            existentes.add(codigo.upper())
            nuevas.append(fila)
        if nuevas:
            with staging_publicacion(ruta) as tmp:
                wb.save(tmp)
                _reemplazar(tmp, ruta)
    return nuevas


def _reemplazar(tmp: Path, ruta: Path, intentos: int = 10, pausa_s: float = 0.3) -> None:
    """Sustituye el catálogo por el nuevo; en Windows, si otro proceso (el antivirus, Excel)
    lo tiene abierto un instante, se reintenta; si sigue abierto, se dice cuál y no se pierde
    nada (el temporal se borra y el catálogo queda como estaba)."""
    import os
    import time

    for i in range(intentos):
        try:
            os.replace(tmp, ruta)
            return
        except PermissionError:
            if i == intentos - 1:
                tmp.unlink(missing_ok=True)
                raise CatalogError(f'{ruta} está abierto en otro programa (¿Excel?): ciérrelo para que el '
                                   'catálogo crezca (053:RF-7).') from None
            time.sleep(pausa_s)
