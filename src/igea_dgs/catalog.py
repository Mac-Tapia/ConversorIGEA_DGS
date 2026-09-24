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
             p.origen, p.ficha_necesaria, p.impacto]
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

    ``valores`` va indexado por el **atributo de** :class:`~igea_dgs.model.LineType`,
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
        valores = dict(corr.valores)

        # La homopolar del catálogo CYMDIST es, en todos los tipos, copia exacta de la
        # directa. Si se corrige R1 y se deja R0 quieto, el resultado es R0 < R1, que
        # con retorno por tierra no puede darse: sería peor que el defecto de partida,
        # porque un valor imposible desconcierta más que uno consistente y erróneo.
        # Mientras no haya valor de ficha para la homopolar, la copia se mantiene.
        for directa, homopolar, etiqueta in (
            ('r1_ohm_km', 'r0_ohm_km', 'rline0'),
            ('x1_ohm_km', 'x0_ohm_km', 'xline0'),
        ):
            nuevo_directo = valores.get(directa)
            if nuevo_directo is None or homopolar in valores:
                continue
            if math.isclose(float(getattr(tipo, homopolar, 0.0) or 0.0),
                            float(getattr(tipo, directa, 0.0) or 0.0),
                            rel_tol=TOLERANCIA_CAMBIO_REL):
                valores[homopolar] = nuevo_directo

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
