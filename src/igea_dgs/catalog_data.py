"""Datos de referencia de fabricante y de norma para los parámetros eléctricos.

Este módulo es **la fuente de referencia**, no la verdad. Cada valor lleva de dónde
sale (``fuente``) y cuánto se puede confiar en él (``estado``):

``ficha``
    Leído de una ficha técnica de fabricante o de una norma, con la referencia puesta.
    Se puede usar para corregir el modelo.
``derivado``
    Calculado a partir de un dato ``ficha`` con una fórmula explícita —la resistividad
    y el factor de cableado de la propia ficha—. Tan bueno como la fórmula, y la
    fórmula está escrita en el código, a la vista.
``referencia``
    Valor típico de norma o de práctica habitual, no de la ficha del equipo instalado.
    Sirve para detectar disparates, no para dar por buena una cifra.
``por_confirmar``
    No se encontró fuente pública fiable. La casilla existe para que la llene el
    ingeniero con la ficha de su proveedor.

La distinción importa: un modelo de planificación que alimenta decisiones de inversión
no debe tomar como dato de fabricante algo que salió de una estimación. Por eso el
auditor de :mod:`igea_dgs.catalog` nunca corrige a partir de una fila ``referencia`` o
``por_confirmar`` sin que alguien lo pida explícitamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------------
# Conductores de aleación de aluminio (AAAC)
# --------------------------------------------------------------------------------
#
# Ficha: «Conductor de aleación de aluminio tipo AAAC», Electrical Projects SAC
# (holley-epsac.com, COD-07), fabricación NTP 370.258 / NTP IEC 60104, designación A3,
# conductividad 52,5 % IACS, resistividad eléctrica a 20 °C = 0,032840 Ω·mm²/m.
#
# La ficha publica cuatro secciones (35, 50, 70 y 120 mm²) con su resistencia máxima
# a 20 °C. De ellas sale el factor de cableado, que es lo que separa la resistencia
# real de la del material puro:
#
#     R20 = ρ20 · 1000 / S · k_cableado
#
#     35 mm²  (7 hilos):  32,840/35  = 0,9383 ; ficha 0,9651 → k = 1,0285
#     50 mm²  (7 hilos):  32,840/50  = 0,6568 ; ficha 0,6755 → k = 1,0285
#     70 mm²  (7 hilos):  32,840/70  = 0,4691 ; ficha 0,4825 → k = 1,0285
#    120 mm² (19 hilos):  32,840/120 = 0,2737 ; ficha 0,2828 → k = 1,0333
#
# El factor sale idéntico en las tres de 7 hilos, así que se aplica a las secciones de
# 7 hilos que la ficha no publica; para las de 19 hilos se usa el suyo. Las secciones
# derivadas se marcan ``derivado``, no ``ficha``.

AAAC_RHO20_OHM_MM2_KM = 32.840
"""Resistividad a 20 °C de la aleación A3 al 52,5 % IACS, en Ω·mm²/km (ficha EPSAC)."""

AAAC_K_7_HILOS = 1.0285
"""Factor de cableado de 7 hilos, deducido de las tres secciones que publica la ficha."""

AAAC_K_19_HILOS = 1.0333
"""Factor de cableado de 19 hilos, deducido de la sección de 120 mm² de la ficha."""

AAAC_FUENTE = (
    'Ficha EPSAC COD-07 «Conductor de aleación de aluminio tipo AAAC» '
    '(NTP 370.258 / NTP IEC 60104, A3, 52,5 % IACS, ρ20 = 0,032840 Ω·mm²/m)'
)

# Secciones publicadas en la ficha, con su estructura y su resistencia máxima a 20 °C.
AAAC_FICHA: dict[float, dict[str, float | str]] = {
    35.0: {'r20': 0.9651, 'hilos': 7, 'diam_hilo_mm': 2.52, 'diam_ext_mm': 7.56,
           'rotura_kn': 10.81, 'masa_kg_km': 95.7},
    50.0: {'r20': 0.6755, 'hilos': 7, 'diam_hilo_mm': 3.02, 'diam_ext_mm': 9.06,
           'rotura_kn': 15.44, 'masa_kg_km': 136.8},
    70.0: {'r20': 0.4825, 'hilos': 7, 'diam_hilo_mm': 3.57, 'diam_ext_mm': 10.71,
           'rotura_kn': 20.95, 'masa_kg_km': 191.5},
    120.0: {'r20': 0.2828, 'hilos': 19, 'diam_hilo_mm': 2.84, 'diam_ext_mm': 14.20,
            'rotura_kn': 37.05, 'masa_kg_km': 329.8},
}

# Secciones normalizadas que aparecen en el catálogo CYMDIST y que la ficha no publica.
AAAC_SECCIONES_DERIVADAS = (10.0, 16.0, 25.0, 95.0, 125.0, 150.0, 185.0)


def aaac_r20_ohm_km(seccion_mm2: float) -> float:
    """Resistencia a 20 °C de un AAAC, con la fórmula y el factor de la ficha.

    Para las cuatro secciones que la ficha publica devuelve su valor literal; para las
    demás aplica ``ρ20/S · k``, con el factor de cableado que corresponda al número de
    hilos. El corte en 95 mm² es el de la propia ficha: 70 mm² lleva 7 hilos y
    120 mm² lleva 19.
    """
    publicada = AAAC_FICHA.get(float(seccion_mm2))
    if publicada is not None:
        return float(publicada['r20'])
    k = AAAC_K_19_HILOS if seccion_mm2 >= 95.0 else AAAC_K_7_HILOS
    return AAAC_RHO20_OHM_MM2_KM / float(seccion_mm2) * k


# --------------------------------------------------------------------------------
# Transformadores de distribución
# --------------------------------------------------------------------------------
#
# Pérdidas máximas del Reglamento (UE) 548/2014 (texto consolidado 2019/1783), tabla
# de transformadores trifásicos de potencia media sumergidos en líquido con un
# arrollamiento de Um ≤ 24 kV. Nivel 1 desde 1-7-2015, nivel 2 desde 1-7-2021.
#
# Son **máximos reglamentarios europeos**, no la ficha del transformador instalado.
# Se usan como cota: un transformador cuyas pérdidas modeladas superen el nivel 1 está
# fuera de cualquier práctica moderna y casi seguro es un valor inventado. Para poner
# la cifra real hace falta el protocolo de ensayo del fabricante, que es lo que pide la
# columna «Po_W» / «Pk_W» de la hoja.

TRAFO_FUENTE_PERDIDAS = (
    'Reglamento (UE) 548/2014, texto consolidado 02014R0548-20191114, tabla I.1 '
    '(trifásicos sumergidos en líquido, Um ≤ 24 kV) — máximos reglamentarios'
)

#: ``kVA -> (Pk nivel 1 W, Po nivel 1 W, Pk nivel 2 W, Po nivel 2 W)``
TRAFO_PERDIDAS_UE: dict[float, tuple[float, float, float, float]] = {
    25.0: (900.0, 70.0, 600.0, 63.0),
    50.0: (1100.0, 90.0, 750.0, 81.0),
    100.0: (1750.0, 145.0, 1250.0, 130.0),
    160.0: (2350.0, 210.0, 1750.0, 189.0),
    250.0: (3250.0, 300.0, 2350.0, 270.0),
    400.0: (4600.0, 430.0, 3250.0, 387.0),
    630.0: (6500.0, 600.0, 4600.0, 540.0),
    1000.0: (10500.0, 770.0, 7600.0, 693.0),
}

TRAFO_FUENTE_UK = (
    'IEC 60076-5 y práctica habitual de distribución: uk ≈ 4 % hasta 630 kVA y 6 % '
    'desde 630 kVA. VALOR DE REFERENCIA, no de ficha: confirmar con el protocolo de '
    'ensayo del fabricante'
)

#: Tensión de cortocircuito típica, en %. Referencia, no ficha.
TRAFO_UK_TIPICO: dict[float, float] = {
    25.0: 4.0, 50.0: 4.0, 100.0: 4.0, 160.0: 4.0,
    250.0: 4.0, 400.0: 4.0, 630.0: 4.0, 1000.0: 6.0,
}

#: Corriente de vacío típica, en % de In. Baja al subir la potencia.
TRAFO_IO_TIPICO: dict[float, float] = {
    25.0: 2.6, 50.0: 2.3, 100.0: 2.0, 160.0: 1.8,
    250.0: 1.6, 400.0: 1.4, 630.0: 1.2, 1000.0: 1.1,
}

TRAFO_GRUPO_TIPICO = 'Dyn5'
"""Grupo de conexión habitual en distribución MT/BT en el Perú. Confirmar en placa."""

TRAFO_TOMAS_TIPICAS = '±2 × 2,5 %'
"""Tomas sin tensión del lado de alta. Confirmar en placa."""


def trafo_interpola(kva: float, tabla: dict[float, tuple[float, ...]] | dict[float, float],
                    indice: int | None = None) -> float | None:
    """Interpola linealmente en las tablas por kVA, como manda el propio Reglamento.

    El Reglamento (UE) 548/2014 dice literalmente que las potencias intermedias se
    obtienen por interpolación lineal. Fuera del rango tabulado devuelve ``None`` en
    lugar de extrapolar: una SED de 5 kVA o de 3 MVA no se parece a nada de la tabla.
    """
    if not tabla:
        return None
    claves = sorted(tabla)
    if kva < claves[0] or kva > claves[-1]:
        return None

    def valor(k: float) -> float:
        v = tabla[k]
        return float(v[indice]) if indice is not None else float(v)  # type: ignore[index]

    if kva in tabla:
        return valor(kva)
    for bajo, alto in zip(claves, claves[1:]):
        if bajo <= kva <= alto:
            t = (kva - bajo) / (alto - bajo)
            return valor(bajo) + t * (valor(alto) - valor(bajo))
    return None


# --------------------------------------------------------------------------------
# Qué parámetro necesita cada elemento, y de dónde sale hoy
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class ParametroPF:
    """Un parámetro eléctrico de un elemento, con su origen actual en el conversor."""

    elemento: str
    clase_pf: str
    atributo: str
    descripcion: str
    unidad: str
    origen: str
    """De dónde sale hoy: ``txt``, ``fabricado``, ``cero`` o ``ausente``."""
    ficha_necesaria: str
    """Qué documento hay que pedir para ponerlo bien."""
    impacto: str
    """Qué estudio se estropea si el valor es falso."""


#: Inventario de parámetros por elemento. Es la hoja que el ingeniero usa para saber
#: qué fichas pedir, y el conversor para saber qué no debe presumir que es real.
PARAMETROS: tuple[ParametroPF, ...] = (
    # --- Líneas aéreas y cables ------------------------------------------------
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'rline', 'Resistencia de secuencia directa',
        'Ω/km', 'txt', 'Ficha del conductor (R a 20 °C, % IACS, cableado)',
        'Flujo de potencia, pérdidas técnicas, caída de tensión'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'xline', 'Reactancia de secuencia directa',
        'Ω/km', 'txt', 'Ficha del conductor y disposición de la estructura (GMD)',
        'Flujo de potencia, caída de tensión'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'rline0', 'Resistencia de secuencia homopolar',
        'Ω/km', 'txt', 'Cálculo con retorno por tierra (resistividad del terreno)',
        'Cortocircuito monofásico, protecciones de tierra'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'xline0', 'Reactancia de secuencia homopolar',
        'Ω/km', 'txt', 'Cálculo con retorno por tierra (resistividad del terreno)',
        'Cortocircuito monofásico, protecciones de tierra'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'bline', 'Susceptancia capacitiva directa',
        'µS/km', 'cero', 'Ninguna: el catálogo CYMDIST ya la trae',
        'Corriente capacitiva, reactiva en vacío, efecto Ferranti'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'bline0', 'Susceptancia capacitiva homopolar',
        'µS/km', 'cero', 'Ninguna: el catálogo CYMDIST ya la trae',
        'Corriente de falla a tierra en redes con neutro aislado o compensado'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'sline', 'Corriente admisible',
        'kA', 'txt', 'Ficha del conductor (ampacidad a 40 °C ambiente)',
        'Verificación de sobrecarga, selección de sección'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'Ithr', 'Corriente térmica de cortocircuito (1 s)',
        'kA', 'cero', 'Ficha del conductor o cálculo IEC 60949',
        'Verificación térmica ante cortocircuito'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'qurs', 'Sección del conductor',
        'mm²', 'ausente', 'Ficha del conductor',
        'Documentación; PowerFactory la usa en informes y en la selección de tipos'),
    ParametroPF(
        'Tramo MT aéreo', 'TypLne', 'rtemp / tmax',
        'Temperatura de servicio y máxima admisible',
        '°C', 'fabricado', 'Ficha del conductor y criterio de la empresa',
        'Corrección de resistencia con la temperatura'),
    ParametroPF(
        'Cable MT subterráneo', 'TypLne', 'bline',
        'Susceptancia capacitiva (mucho mayor que en aéreo)',
        'µS/km', 'cero', 'Ninguna: el catálogo CYMDIST ya la trae',
        'Reactiva capacitiva, corriente de falla a tierra, regulación de tensión'),
    ParametroPF(
        'Cable MT subterráneo', 'TypLne', 'cohl_', 'Marca de cable frente a línea aérea',
        '-', 'txt', 'Ninguna', 'Cálculos que distinguen cable de aéreo'),
    # --- Transformadores de SED ------------------------------------------------
    ParametroPF(
        'Transformador SED', 'TypTr2', 'uktr', 'Tensión de cortocircuito',
        '%', 'fabricado', 'Protocolo de ensayo del transformador (placa)',
        'Cortocircuito, caída de tensión, reparto de carga'),
    ParametroPF(
        'Transformador SED', 'TypTr2', 'pcutr', 'Pérdidas en el cobre (con carga)',
        'kW', 'fabricado', 'Protocolo de ensayo del transformador (placa)',
        'Pérdidas técnicas, eficiencia, cálculo tarifario'),
    ParametroPF(
        'Transformador SED', 'TypTr2', 'pfe', 'Pérdidas en el hierro (vacío)',
        'kW', 'fabricado', 'Protocolo de ensayo del transformador (placa)',
        'Pérdidas técnicas permanentes, energía no facturada'),
    ParametroPF(
        'Transformador SED', 'TypTr2', 'curmg', 'Corriente de magnetización',
        '%', 'cero', 'Protocolo de ensayo del transformador (placa)',
        'Reactiva en vacío, corriente de energización'),
    ParametroPF(
        'Transformador SED', 'TypTr2', 'uk0tr / ur0tr', 'Impedancia homopolar',
        '%', 'fabricado', 'Protocolo de ensayo o valor típico del grupo de conexión',
        'Cortocircuito monofásico, puesta a tierra'),
    ParametroPF(
        'Transformador SED', 'TypTr2', 'tr2cn_h / tr2cn_l / nt2ag',
        'Grupo de conexión y desfase',
        '-', 'fabricado', 'Placa del transformador',
        'Desfase, circulación de homopolar, cortocircuito desequilibrado'),
    ParametroPF(
        'Transformador SED', 'TypTr2', 'itapch / dutap / ntpmn / ntpmx',
        'Tomas de regulación sin tensión',
        '%', 'ausente', 'Placa del transformador',
        'Perfil de tensión en BT, ajuste de la red'),
    # --- Equipos que el conversor todavía no modela ----------------------------
    ParametroPF(
        'Condensador shunt', 'ElmShnt', 'qtotn / ushnm / ncapx',
        'Potencia reactiva, tensión nominal y escalones',
        'Mvar / kV', 'ausente', 'Ficha del banco de condensadores',
        'Compensación de reactiva, perfil de tensión, pérdidas'),
    ParametroPF(
        'Condensador shunt', 'ElmShnt', 'greaf0', 'Pérdidas del banco',
        '%', 'ausente', 'Ficha del banco de condensadores',
        'Pérdidas técnicas'),
    ParametroPF(
        'Regulador de tensión', 'ElmTr2 + ElmTap', 'dutap / ntpmn / ntpmx',
        'Escalón de regulación y número de tomas',
        '%', 'ausente', 'Ficha del regulador (CYMDIST: tabla REGULATOR)',
        'Perfil de tensión a lo largo del alimentador'),
    ParametroPF(
        'Regulador de tensión', 'ElmTr2', 'usetp / uk / Sn',
        'Consigna, impedancia y potencia',
        'p.u. / % / MVA', 'ausente', 'Ficha del regulador',
        'Flujo de potencia con regulación automática'),
    ParametroPF(
        'Seccionador / recloser', 'ElmCoup / StaSwitch', 'Inom / Ithr',
        'Corriente nominal y de cortocircuito',
        'kA', 'ausente', 'Ficha del equipo de maniobra',
        'Verificación de capacidad de corte, coordinación de protecciones'),
    ParametroPF(
        'Fusible', 'RelFuse + TypFuse', 'Curva tiempo-corriente',
        'Curva característica',
        's / A', 'ausente', 'Curva del fabricante del fusible',
        'Coordinación de protecciones, selectividad'),
)
