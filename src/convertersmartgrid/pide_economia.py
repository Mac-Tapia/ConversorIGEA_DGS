"""Evaluación económica y priorización del PIDE (spec 024, T14; RF-33, RF-34, RF-54 a RF-59).

Art. 14 de la norma prepublicada con la RM 428-2017-MEM/DM: costo de inversión (CI),
de operación y mantenimiento (COyM) y de pérdidas (CP); costo anual = anualidad del CI
+ COyM + CP, con 30 años de vida útil y la tasa del art. 79 de la LCE; VAN y TIR. Además,
el flujo de caja de la empresa (privada) con las tarifas del pliego y su tasa, porque el
usuario lo pidió el 2026-10-21 («tarifas, costos de energía vendida por la potencia nueva
instalada de nuevos clientes para un horizonte de 20 años, tasa a privados»).

Art. 15: entre las alternativas factibles técnica y económicamente, primero las de menor
costo/kW, costo/kW.h, costo/usuario y costo/km con rentabilidad aceptable; después los
criterios del art. 15.3 con los pesos del perfil. Puro: no lee DIgSILENT.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

from .formatos_pide import filas_de_obras
from .pide import RUBRO_DE_ALTERNATIVA
from .util import finite_or_none, frc
from .valle import frase_valle

#: Palabras de la denominación de una obra del CAPEX → alternativa del PIDE (RF-54).
#: Se prueban en este orden: «transformador de potencia» es de una SET, no de una SED.
PALABRAS_ALTERNATIVA = (
    ('nueva_set', ('subestacion de transformacion', 'transformador de potencia', ' set ', 'nueva set')),
    ('bancos', ('banco de condensador', 'bancos de condensador', 'compensacion reactiva')),
    ('reguladores', ('regulador',)),
    ('nueva_terna', ('terna',)),
    ('cambio_seccion', ('cambio de seccion', 'cambio de conductor', 'reconductor', 'repotenci')),
    ('refuerzo_red', ('enlace', 'interconexion', 'migracion', 'transferencia', 'refuerzo')),
    ('nuevo_alimentador', ('nuevo alimentador', 'alimentador nuevo', 'nuevos alimentadores')),
    ('nueva_sed', ('sed', 'subestacion de distribucion', 'transformador de distribucion')),
)


class EconomiaPideError(ValueError):
    """Falta un dato del perfil o del libro: se dice cuál, nunca se supone (RF-58e)."""


def _plano(texto: Any) -> str:
    s = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return f" {re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()} "


# ------------------------------------------------------------------ libro CAPEX (RF-54 a 56)
@dataclass(frozen=True)
class ObraCapex:
    nombre: str
    zona: str
    objetivo: str
    descripcion: str
    unidad: str
    cantidad: float | None
    costo_unitario: float | None
    inversion: float | None
    alternativa: str | None


def alternativa_de(*textos: str) -> str | None:
    """La alternativa del PIDE que nombra una obra del CAPEX, o ``None``."""
    plano = _plano(' '.join(textos))
    for alternativa, palabras in PALABRAS_ALTERNATIVA:
        # Al principio de palabra: «repotenci» vale para «repotenciación».
        if any(re.search(rf'\b{re.escape(p.strip())}', plano) for p in palabras):
            return alternativa
    return None




def leer_capex(ruta: Path | str, config: Mapping[str, Any]) -> tuple[list[ObraCapex], list[str]]:
    """Obras del libro CAPEX con su alternativa del PIDE, por los nombres del perfil.

    Solo se leen las columnas del perfil: responsables, líderes y contratos del libro no
    salen de aquí (RF-56). Devuelve las obras y los avisos (RF-55): hoja o columna que no
    está y alternativas del PIDE sin ninguna obra en el libro.
    """
    from contextlib import closing
    from openpyxl import load_workbook

    columnas = dict(config.get('columnas') or {})
    hoja_nombre = config.get('hoja')
    with closing(load_workbook(ruta, read_only=True, data_only=True)) as libro:
        if hoja_nombre not in libro.sheetnames:
            raise EconomiaPideError(f'el libro no tiene la hoja «{hoja_nombre}» del perfil')
        hoja = libro[hoja_nombre]
        filas = hoja.iter_rows(values_only=True)
        marca = _plano(config.get('fila_cabecera_contiene') or columnas.get('costo_unitario'))
        indice: dict[str, int] = {}
        for fila in filas:
            planos = [_plano(v) for v in fila]
            if marca in planos:
                for clave, nombre in columnas.items():
                    if _plano(nombre) in planos:
                        indice[clave] = planos.index(_plano(nombre))
                break
        faltan = [c for c in columnas if c not in indice]
        if 'nombre' in faltan or 'costo_unitario' in faltan:
            raise EconomiaPideError(f'no se encontraron las columnas {faltan} en «{hoja_nombre}»')
        avisos = [f'columna «{columnas[c]}» del perfil no encontrada' for c in faltan]

        def celda(fila, clave):
            i = indice.get(clave)
            return fila[i] if i is not None and i < len(fila) else None

        obras = []
        for fila in filas:
            nombre = celda(fila, 'nombre')
            if not nombre or _plano(nombre) == _plano(columnas['nombre']):
                continue
            textos = [str(celda(fila, k) or '') for k in ('nombre', 'objetivo', 'descripcion')]
            obras.append(ObraCapex(str(nombre).strip(), str(celda(fila, 'zona') or ''),
                                   str(celda(fila, 'objetivo') or ''), str(celda(fila, 'descripcion') or ''),
                                   str(celda(fila, 'unidad') or ''), finite_or_none(celda(fila, 'cantidad')),
                                   finite_or_none(celda(fila, 'costo_unitario')), finite_or_none(celda(fila, 'inversion')),
                                   alternativa_de(*textos)))
    sin = sorted(set(RUBRO_DE_ALTERNATIVA) - {o.alternativa for o in obras if o.alternativa})
    if sin:
        avisos.append(f'alternativas del PIDE sin obra en el libro CAPEX: {", ".join(sin)}')
    return obras, avisos


def costos_por_alternativa(obras: Iterable[ObraCapex]) -> dict[str, dict[str, Any]]:
    """Costo unitario de cada alternativa: la mediana de sus obras, con su unidad y cuántas."""
    grupos: dict[str, list[ObraCapex]] = {}
    for o in obras:
        if o.alternativa and o.costo_unitario:
            grupos.setdefault(o.alternativa, []).append(o)
    out = {}
    for alt, lista in grupos.items():
        unidades = sorted({o.unidad for o in lista if o.unidad})
        out[alt] = {'costo_unitario': median(o.costo_unitario for o in lista),
                    'unidad': unidades[0] if len(unidades) == 1 else '/'.join(unidades),
                    'obras': len(lista), 'denominacion': lista[0].nombre,
                    # 087:RF-36: de qué filas del libro sale, para citarlas.
                    'proyectos': [f'{o.nombre} ({o.zona}): {o.descripcion[:60]}' for o in lista]}
    return out


def costos_en_moneda_de_trabajo(costos: Mapping[str, Mapping[str, Any]],
                                escala: float | None) -> dict[str, dict[str, Any]]:
    """Los costos del libro en la moneda de trabajo, con la escala del perfil (025:RF-77), una sola vez.

    Es la regla de la escalera (``escalera_optima.costos_de_alternativas``) para el PIDE: el libro de Electro
    Dunas está en miles de dólares y el PIDE lo tomaba en dólares (hallazgo H1, 2026-11-14). Con costos y sin
    escala no se supone 1: :class:`EconomiaPideError`. Cada costo guarda la ``escala_aplicada``, y uno que ya
    la trae no se vuelve a escalar.
    """
    if any(c.get('costo_unitario') for c in costos.values()) and not escala:
        raise EconomiaPideError('el perfil no dice en qué escala está el libro CAPEX respecto de la moneda de '
                                'trabajo: escalera.escala_capex, p. ej. 1000 si está en miles')
    if not escala:                                     # sin costos que escalar
        return {alt: dict(c) for alt, c in costos.items()}
    out = {}
    for alt, c in costos.items():
        if c.get('escala_aplicada') is not None or not c.get('costo_unitario'):
            out[alt] = dict(c)
            continue
        out[alt] = {**c, 'costo_unitario': float(c['costo_unitario']) * float(escala), 'escala_aplicada': escala}
    return out


# ------------------------------------------------------------------ art. 14 (RF-57, RF-58)
# El FRC (``frc``) es ``util.frc``, la única fórmula del conversor (UNA-TASA); se importa de ahí y se reexporta.
def costo_anual(ci: float | None, coym: float | None, cp: float | None, *, tasa: float,
                vida: int) -> dict[str, Any]:
    """Costo anual = anualidad del CI + COyM + CP (art. 14.4); lo que falta queda dicho.

    072:RF-16 (H5, 2026-11-14): sin alguno de los tres, el costo anual queda vacío y ``falta`` dice cuál. Antes valía
    anualidad + lo que hubiera, y los formatos lo escribían como si estuviera completo.
    """
    anualidad = ci * frc(tasa, vida) if ci is not None else None
    falta = [n for n, v in (('inversión', ci), ('COyM', coym), ('pérdidas', cp)) if v is None]
    return {'anualidad': anualidad, 'coym': coym, 'cp': cp,
            'costo_anual': anualidad + coym + cp if not falta else None,
            'completo': not falta, 'falta': falta}


def valor_kw_perdidas(plan: Mapping[str, Any], *, factor_carga: float | None,
                      precio_compra_kwh: float | None) -> float | None:
    """Lo que vale evitar 1 kW de pérdidas en la máxima, en valor presente de la vida útil.

    La energía perdida sale del factor de pérdidas de Buller y Woodrow (0,3·fc + 0,7·fc²)
    con el factor de carga del perfil, y se valora a su precio de compra. Sin factor de
    carga o sin precio no hay valor: no se inventa (RF-58e, 024:RF-70).
    """
    if factor_carga is None or precio_compra_kwh is None:
        return None
    return _valor_anual_kw_perdido(factor_carga, precio_compra_kwh) / frc(float(plan['tasa_regulada']), int(plan['vida_util_anios']))


def _valor_anual_kw_perdido(factor_carga: float, precio_compra_kwh: float) -> float:
    return 8760 * (0.3 * factor_carga + 0.7 * factor_carga ** 2) * precio_compra_kwh


def _entre_anios(medidas: Mapping[int, float], anio: int) -> float:
    """El valor de un año entre dos medidos, en línea recta; fuera de ellos, el más cercano."""
    anios = sorted(medidas)
    if anio <= anios[0]:
        return medidas[anios[0]]
    if anio >= anios[-1]:
        return medidas[anios[-1]]
    hasta = next(a for a in anios if a >= anio)
    desde = max(a for a in anios if a < anio)
    return medidas[desde] + (medidas[hasta] - medidas[desde]) * (anio - desde) / (hasta - desde)


def evaluar_con_y_sin(inversiones: Mapping[int, float], perdidas_sin: Mapping[int, float], perdidas_con: Mapping[int, float],
                      plan: Mapping[str, Any], *, factor_carga: float | None,
                      precio_compra_kwh: float | None) -> dict[str, Any]:
    """La cartera frente a no hacerla: lo que ahorra en pérdidas cada año, medido (072:RF-14).

    Es la evaluación del art. 14 con los dos casos del mismo año; DIgSILENT mide cada uno. El ahorro de
    pérdidas es el único beneficio que el flujo mide: la energía no servida y la calidad quedan fuera,
    así que un VAN negativo aquí no dice que la obra no se justifique. ``inversiones``: lo que se
    invierte cada año, porque una obra del año 08 no se paga en el año 00.
    """
    comunes = {a: v for a, v in perdidas_sin.items() if v is not None and perdidas_con.get(a) is not None}
    if not any(inversiones.values()):
        return {'hueco': 'sin costo de la cartera: falta el libro CAPEX o el costo oficial'}
    if not comunes:
        return {'hueco': 'faltan las pérdidas de «Con proyecto» en los años del estudio (072:RF-12)'}
    if factor_carga is None or precio_compra_kwh is None:
        return {'hueco': 'faltan el factor de carga o el precio de compra para valorar las pérdidas'}
    ahorro = {a: comunes[a] - float(perdidas_con[a]) for a in comunes}
    horizonte = int(plan['horizonte_anios'])
    valor = _valor_anual_kw_perdido(factor_carga, precio_compra_kwh)
    por_anio = {t: _entre_anios(ahorro, t) for t in range(1, horizonte + 1)}
    flujos = [-float(inversiones.get(0, 0.0))] + [por_anio[t] * valor - float(inversiones.get(t, 0.0))
                                                  for t in range(1, horizonte + 1)]
    avisos = []
    if max(ahorro) < horizonte:
        avisos.append(f'el ahorro del año {max(ahorro):02d} se mantiene hasta el {horizonte:02d}: no hay caso medido después')
    return {'ahorro_kw': por_anio, 'flujos': flujos, 'van': van(flujos, float(plan['tasa_regulada'])),
            'tir': tir(flujos), 'avisos': avisos}


def van(flujos: Sequence[float], tasa: float) -> float:
    """Valor actual neto de flujos anuales desde el año 0."""
    return sum(f / (1 + tasa) ** t for t, f in enumerate(flujos))


def tir(flujos: Sequence[float]) -> float | None:
    """Tasa interna de retorno por bisección; ``None`` si no cambia de signo."""
    lo, hi = -0.99, 10.0
    f_lo, f_hi = van(flujos, lo), van(flujos, hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = van(flujos, mid)
        if abs(f_mid) < 1e-9:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def retorno(flujos: Sequence[float]) -> float | None:
    """Años hasta recuperar la inversión (flujo acumulado ≥ 0), con interpolación."""
    acumulado = 0.0
    for t, f in enumerate(flujos):
        anterior = acumulado
        acumulado += f
        if t > 0 and acumulado >= 0 > anterior:
            return t - 1 + (-anterior / f if f else 0)
    return None


# ------------------------------------------------------------------ flujo privado (RF-58c, d)
def ingreso_anual_kw(kw: float, tarifa: Mapping[str, Any], *, factor_carga: float,
                     fraccion_punta: float) -> float:
    """Lo que factura en un año 1 kW nuevo con la opción tarifaria dada (sin IGV).

    Energía: kW × factor de carga × 8760 h a su cargo (en MT3, punta y fuera de punta con
    ``fraccion_punta``). Potencia: generación y distribución, por mes.
    """
    energia = kw * factor_carga * 8760
    if 'energia_kwh' in tarifa:
        por_energia = energia * tarifa['energia_kwh']
    else:
        por_energia = energia * (fraccion_punta * tarifa['energia_punta_kwh']
                                 + (1 - fraccion_punta) * tarifa['energia_fuera_punta_kwh'])
    por_potencia = 12 * kw * (tarifa.get('potencia_generacion_kw_mes', 0.0)
                              + tarifa.get('potencia_distribucion_kw_mes', 0.0))
    return por_energia + por_potencia


def plan_en_moneda_de_trabajo(plan: Mapping[str, Any], *, moneda_trabajo: str | None,
                              tipo_cambio: float | None) -> tuple[dict[str, Any], list[str]]:
    """La planificación con las tarifas y el precio de compra en la moneda de trabajo (025:RF-67, RF-77; H4).

    El CAPEX va en la moneda de trabajo (``costos_en_moneda_de_trabajo``); las tarifas del pliego y el precio de
    compra, en la de ``tarifas.moneda`` (una distribuidora real: PEN). Si no coinciden, se dividen una vez por el tipo de
    cambio que escribe el operador (unidades de la moneda de las tarifas por una de la de trabajo, como en la
    escalera). Sin él no se supone 1: las tarifas y el precio de compra quedan fuera, la evaluación privada y el
    valor de las pérdidas no se calculan (024:RF-58e) y se dice. El plan de entrada no cambia.
    """
    out = dict(plan)
    out['moneda_trabajo'] = moneda_trabajo
    tarifas = dict(plan.get('tarifas') or {})
    de = tarifas.get('moneda')
    if not tarifas or not de or not moneda_trabajo or de == moneda_trabajo:
        return out, []
    if not tipo_cambio or float(tipo_cambio) <= 0:
        out['tarifas'] = {'moneda': de}
        out['precio_compra_kwh'] = None
        return out, [f'las tarifas y el precio de compra están en {de} y el CAPEX en {moneda_trabajo}: sin el tipo '
                     f'de cambio ({de} por {moneda_trabajo}) no se hacen la evaluación privada ni el valor de las '
                     'pérdidas']
    tc = float(tipo_cambio)
    out['tarifas'] = {k: ({c: (v / tc if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                           for c, v in opcion.items()} if isinstance(opcion, Mapping) else opcion)
                      for k, opcion in tarifas.items()}
    out['tarifas'].update(moneda=moneda_trabajo, moneda_del_pliego=de, tipo_cambio_aplicado=tc)
    if plan.get('precio_compra_kwh') is not None:
        out['precio_compra_kwh'] = float(plan['precio_compra_kwh']) / tc
    return out, []


@dataclass
class Evaluacion:
    ci: float | None
    regulada: dict[str, Any]
    privada: dict[str, Any] | None
    indicadores: dict[str, float | None]
    avisos: list[str] = field(default_factory=list)
    #: 025:RF-68 (H4 y H5): la evaluación privada no se hizo porque las tarifas están en otra moneda sin tipo de cambio.
    sin_tipo_de_cambio: bool = False


def evaluar(ci: float | None, *, kw_nuevos: float, usuarios: int, km: float, coym_anual: float | None,
            cp_anual: float | None, plan: Mapping[str, Any], factor_carga: float | None,
            precio_compra_kwh: float | None, opcion: str, fraccion_punta: float = 5 / 24,
            crecimiento: float = 0.0) -> Evaluacion:
    """Evaluación regulada (art. 14) y privada (flujo de 20 años) de una alternativa.

    072:RF-16 (H5, 2026-11-14): ``ci`` None es una obra sin costo, no una gratuita: anualidad, indicadores y
    evaluación privada quedan vacíos. Un costo que falta (COyM o CP) no se toma por 0 sin decirlo: el costo anual y el
    valor actual de los costos quedan vacíos, y el flujo privado lleva ``completo`` y ``falta``.
    """
    avisos = []
    vida, tasa_r = int(plan['vida_util_anios']), float(plan['tasa_regulada'])
    horizonte = int(plan['horizonte_anios'])
    regulada = costo_anual(ci, coym_anual, cp_anual, tasa=tasa_r, vida=vida)
    regulada['van_costos'] = (van([-ci] + [-coym_anual - cp_anual] * horizonte, tasa_r)
                              if regulada['completo'] else None)
    if ci is None:
        avisos.append('sin costo: falta el libro CAPEX o el costo oficial de esta alternativa')
    elif not regulada['completo']:
        avisos.append(f"costo anual incompleto, sin {' ni '.join(regulada['falta'])}: el perfil o el flujo no lo dan")
    energia_anual = kw_nuevos * (factor_carga or 0) * 8760
    conocido = ci is not None
    indicadores = {
        'costo_kw': ci / kw_nuevos if conocido and kw_nuevos else None,
        'costo_kwh': ci / energia_anual if conocido and energia_anual else None,
        'costo_usuario': ci / usuarios if conocido and usuarios else None,
        'costo_km': ci / km if conocido and km else None,
    }
    moneda_tarifas, moneda_trabajo = (plan.get('tarifas') or {}).get('moneda'), plan.get('moneda_trabajo')
    if moneda_tarifas and moneda_trabajo and moneda_tarifas != moneda_trabajo:
        # 025:RF-77 (H4): ingresos en una moneda menos inversión en otra no es una VAN.
        avisos.append(f'evaluación privada sin hacer: las tarifas están en {moneda_tarifas} y el CAPEX en '
                      f'{moneda_trabajo} (plan_en_moneda_de_trabajo)')
        return Evaluacion(ci, regulada, None, indicadores, avisos, sin_tipo_de_cambio=True)
    if ci is None:
        return Evaluacion(ci, regulada, None, indicadores, avisos)
    tarifa = (plan.get('tarifas') or {}).get(opcion)
    tasa_p = plan.get('tasa_privada')
    if tarifa is None or tasa_p is None or factor_carga is None or precio_compra_kwh is None:
        avisos.append('evaluación privada sin hacer: faltan tarifa, tasa privada, factor de carga '
                      'o precio de compra')
        return Evaluacion(ci, regulada, None, indicadores, avisos)
    flujos = [-ci]
    for t in range(1, horizonte + 1):
        kw = kw_nuevos * (1 + crecimiento) ** t
        ingresos = ingreso_anual_kw(kw, tarifa, factor_carga=factor_carga, fraccion_punta=fraccion_punta)
        compra = kw * factor_carga * 8760 * precio_compra_kwh
        flujos.append(ingresos - compra - (coym_anual or 0) - (cp_anual or 0))
    # 072:RF-16 (H5): el flujo sin COyM o sin CP no se presenta como completo. La cifra se conserva porque los costos
    # que faltan solo la bajarían: una VAN negativa sin ellos también lo es con ellos.
    falta = [n for n, v in (('COyM', coym_anual), ('pérdidas', cp_anual)) if v is None]
    if falta:
        avisos.append(f"flujo privado sin {' ni '.join(falta)}: la VAN y la TIR quedan por encima de las reales")
    beneficios = sum(f / (1 + tasa_p) ** t for t, f in enumerate(flujos) if t > 0)
    privada = {'van': van(flujos, float(tasa_p)), 'tir': tir(flujos), 'retorno_anios': retorno(flujos),
               'beneficio_costo': beneficios / ci if ci else None, 'flujos': flujos,
               'completo': not falta, 'falta': falta}
    return Evaluacion(ci, regulada, privada, indicadores, avisos)


# ------------------------------------------------------------------ art. 15 (RF-33, RF-34)
@dataclass
class Candidata:
    codigo: str
    alternativa: str
    problema: str
    cumple_norma: bool
    evaluacion: Evaluacion
    criterios: dict[str, float] = field(default_factory=dict)   # 0 a 1, del art. 15.3
    puntaje: float = 0.0
    sobredimensionada: bool = False
    descartada: str | None = None

    @property
    def rubro(self) -> str:
        return RUBRO_DE_ALTERNATIVA.get(self.alternativa, 'ampliacion_reforzamiento')


INDICADORES = ('costo_kw', 'costo_kwh', 'costo_usuario', 'costo_km')


def priorizar(candidatas: Sequence[Candidata], pesos: Mapping[str, float]) -> list[Candidata]:
    """Orden del art. 15 (RF-33, RF-34, RF-58b).

    1. Fuera: las que no cumplen la norma y las de rentabilidad no aceptable (VAN privado
       negativo cuando lo hay).
    2. Puntaje: por cada indicador de costo, el menor de todas entre el suyo (1 para la más
       barata); más los criterios del art. 15.3 por sus pesos. Mayor puntaje, antes.
    3. Para un mismo problema, las que cumplen con mayor costo que la elegida quedan
       marcadas como sobredimensionadas.
    4. 072:RF-16 (H5, 2026-11-14): una sin costo no se compara con las que lo tienen. Antes valía 0 y ganaba el
       desempate como la más barata; ahora va tras todas las que tienen costo, ordenada por sus criterios, con su
       aviso, y nunca deja sobredimensionada a otra.
    """
    validas = []
    for c in candidatas:
        if not c.cumple_norma:
            c.descartada = 'no cumple la norma'
        elif (c.rubro == 'ampliacion_reforzamiento' and c.evaluacion.privada is not None
              and c.evaluacion.privada['van'] < 0):
            # Solo la ampliación se paga con la energía que vende; el mejoramiento se
            # justifica por la calidad que exige la norma (art. 12.4 b).
            c.descartada = 'rentabilidad no aceptable (VAN privado negativo)'
        else:
            validas.append(c)
    minimos = {i: min((v for c in validas if (v := c.evaluacion.indicadores.get(i))), default=None)
               for i in INDICADORES}
    for c in validas:
        p = 0.0
        for i, m in minimos.items():
            v = c.evaluacion.indicadores.get(i)
            if m and v:
                p += m / v
        p += sum(float(pesos.get(k, 0)) * float(v) for k, v in c.criterios.items())
        c.puntaje = p
    sin_costo = [c for c in validas if c.evaluacion.ci is None]
    for c in sin_costo:
        c.evaluacion.avisos.append('sin costo: se prioriza tras las obras que lo tienen (art. 15)')
    orden = (sorted((c for c in validas if c.evaluacion.ci is not None),
                    key=lambda c: (-c.puntaje, c.evaluacion.ci, c.codigo))
             + sorted(sin_costo, key=lambda c: (-c.puntaje, c.codigo)))
    elegida: dict[str, Candidata] = {}
    for c in orden:
        if c.problema not in elegida:
            elegida[c.problema] = c
        elif (c.evaluacion.ci is not None and elegida[c.problema].evaluacion.ci is not None
              and c.evaluacion.ci > elegida[c.problema].evaluacion.ci):
            c.sobredimensionada = True
    return orden + [c for c in candidatas if c.descartada]


# ------------------------------------------------------------------ propuesta (RF-45 a RF-47)
#: Causas de calidad del art. 15.3 («subsanación de deficiencias por calidad de producto»).
CAUSAS_DE_CALIDAD = ('caida_de_tension', 'factor_de_potencia', 'sobretension')


def con_y_sin_de_las_aplicadas(obras: Iterable[Mapping[str, Any]], anios: Iterable[Mapping[str, Any]],
                               plan: Mapping[str, Any], *, factor_carga: float | None,
                               precio_compra_kwh: float | None) -> dict[str, Any]:
    """Con y sin proyecto de lo que está en «Con proyecto»: solo las obras aplicadas (072:RF-14).

    Una cartera de diez obras con dos construidas compararía el costo de diez con el ahorro de dos.
    """
    inversiones: dict[int, float] = {}
    for o in obras:
        if o.get('variacion_autonoma'):
            if not o.get('ci'):
                # 072:RF-16 (H5): una obra aplicada sin costo no vale 0; la cartera sin ella sería otra cartera.
                return {'hueco': f"sin costo de la obra aplicada {o.get('codigo') or o['variacion_autonoma']}: falta "
                                 'el libro CAPEX o el costo oficial'}
            inversiones[int(o['anio'])] = inversiones.get(int(o['anio']), 0.0) + float(o['ci'])
    anios = list(anios)
    return evaluar_con_y_sin(inversiones, {a['anio']: a.get('perdidas_kw') for a in anios},
                             {a['anio']: (a.get('con_proyecto') or {}).get('perdidas_kw') for a in anios}, plan,
                             factor_carga=factor_carga, precio_compra_kwh=precio_compra_kwh)


def _problemas_por_anio(informe: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Cada problema con el primer año en que aparece en DIgSILENT (RF-51, RF-53)."""
    primero: dict[tuple, dict] = {}
    for fila in sorted(informe.get('anios') or [], key=lambda a: a['anio']):
        for p in fila.get('problemas') or []:
            clave = (p.get('causa'), p.get('elemento'))
            if clave not in primero:
                primero[clave] = {**p, 'anio': fila['anio']}
    return list(primero.values())


def _valle_de_la_obra(de_alimentador: Mapping[str, Any] | None, alternativa: str) -> dict[str, Any]:
    """Lo que el valle dice de una obra (073:RF-29, RF-31, RF-40): bancos y proyectos. ``modulos`` y la
    tensión de arriba son del banco; las demás, de ``por_alternativa``, medida por quien la evalúa."""
    d = de_alimentador or {}
    if alternativa != 'bancos':
        otra = (d.get('por_alternativa') or {}).get(alternativa) or {}
        return {'comprobado': otra.get('valle') is not None, 'modulos_admisibles': None, 'texto': frase_valle(otra)}
    return {'comprobado': bool(d.get('comprobado')), 'modulos_admisibles': d.get('modulos'), 'texto': frase_valle(d)}


def _obra_011(alternativa: str, alimentador: str | None, elemento: str, kv: float | None,
              bancos_kvar: Mapping[float, float] | None) -> tuple[dict | None, str | None]:
    """La obra de la spec 011 que construye la alternativa, o el motivo de no tenerla."""
    if not alimentador:
        return None, 'no se sabe el alimentador del problema'
    if alternativa == 'bancos':
        if kv is None or not bancos_kvar:
            return None, 'falta el tamaño de banco por tensión en el perfil'
        kvar = min(bancos_kvar.items(), key=lambda x: abs(x[0] - kv))[1]
        return {'clase': 'condensador', 'alimentador': alimentador, 'barra': elemento,
                'q_kvar': kvar, 'escalones': 1, 'casos': ['Con proyecto']}, None
    if alternativa == 'nueva_terna':
        return {'clase': 'terna', 'alimentador': alimentador,
                'tramos': [elemento.removesuffix('.ElmLne')], 'casos': ['Con proyecto']}, None
    return None, (f'«{alternativa}» necesita elegir un tipo de la biblioteca o un diseño: queda '
                  'propuesta para el operador')


def propuesta_pide(informe: Mapping[str, Any], plan: Mapping[str, Any], *,
                   costos: Mapping[str, Mapping[str, Any]], bancos_kvar: Mapping[float, float] | None,
                   factor_carga: float | None = None, precio_compra_kwh: float | None = None,
                   valle: Mapping[str, Mapping[str, Any]] | None = None,
                   coym_pct_anual: float | None = None) -> dict[str, Any]:
    """Del diagnóstico año a año a las obras priorizadas, con su evaluación (RF-45, RF-52,
    RF-57 a RF-59), su obra de la spec 011 si se puede construir sola (RF-47) y las filas
    de los formatos (RF-63).

    073:RF-28, RF-29, RF-40: ``valle``, por alimentador, ``comprobado``, ``modulos`` y su tensión, y
    ``por_alternativa`` para las obras que no son bancos. El módulo que se propone sigue siendo uno,
    y nunca más de los que admite; sin dato, «no comprobado en valle». Una obra que se midió y no
    cumple en valle queda descartada.

    072:RF-22: ``coym_pct_anual`` es el COyM del perfil en % de la inversión, el mismo dato que usa la
    escalera (025:RF-53). Antes se pasaba siempre None y F10 a F12 salían sin COyM aunque el perfil lo
    diera; sin inversión conocida, el COyM tampoco se conoce y queda vacío.
    """
    from .pide import (
        ALTERNATIVAS_POR_CAUSA,
        CARACTER_DE_ALTERNATIVA,
        Problema,
        plan_por_etapas,
    )

    avisos: list[str] = []
    problemas = _problemas_por_anio(informe)
    anios = sorted(informe.get('anios') or [], key=lambda a: a['anio'])
    cab0 = (anios[0].get('cabeceras_kw') or {}) if anios else {}
    # Una caída de tensión en baja se resuelve en la SED, no con un banco de media.
    for p in problemas:
        if p.get('causa') == 'caida_de_tension' and p.get('kv') is not None and p['kv'] < 1:
            p['causa'] = 'transformador_sobrecargado'
    por_alim: dict[str | None, list[dict]] = {}
    for p in problemas:
        por_alim.setdefault(p.get('alimentador'), []).append(p)
    costo_rel = {a: c['costo_unitario'] for a, c in costos.items()}
    if not costos:
        avisos.append('sin libro CAPEX: las obras van sin costo y se eligen por menor intervención')
    candidatas, filas_obra = [], []
    n = 0
    valle = valle or {}
    for alimentador, lista in sorted(por_alim.items(), key=lambda x: str(x[0])):
        de_valle = valle.get(alimentador)
        sin_modulos = bool(de_valle and de_valle.get('comprobado') and de_valle.get('modulos') == 0)
        if sin_modulos:
            avisos.append(f'{alimentador}: el valle no admite ningún módulo de banco: se toma la alternativa '
                          'siguiente de cada causa.')
        obras = plan_por_etapas([Problema(p['tipo'], p['elemento'], p.get('valor'), p.get('limite'),
                                          p['causa'], p.get('evidencia', ''), int(p['anio']))
                                 for p in lista if p.get('causa') in ALTERNATIVAS_POR_CAUSA],
                                anios_pide=plan.get('anios_pide') or [4], costo_relativo=costo_rel or None,
                                vetadas=('bancos',) if sin_modulos else ())
        for o in obras:
            n += 1
            codigo = f'AL{n:02d}'
            grupo = [p for p in lista if p['causa'] == o.causa and any(
                x.startswith(f"{p['elemento']}:") for x in o.problemas)]
            # El banco va en la barra de media más baja del grupo, donde más sube la tensión.
            mt = [p for p in grupo if (p.get('kv') or 0) >= 1 and p.get('valor') is not None]
            sitio = min(mt, key=lambda p: p['valor']) if mt else (grupo[0] if grupo else {})
            elemento = sitio.get('elemento', o.elemento)
            costo = costos.get(o.alternativa)
            # 072:RF-16 (H5): sin costo, la inversión queda vacía; 0 la hacía la más barata en la priorización.
            ci = float(costo['costo_unitario']) if costo and costo.get('costo_unitario') else None
            if costo and str(costo.get('unidad', '')).lower().startswith('km'):
                avisos.append(f'{codigo}: costo por km con 1 km supuesto; el largo lo da el diseño')
            cab_obra = next((a.get('cabeceras_kw') or {} for a in anios if a['anio'] >= o.anio), cab0)
            kw = 0.0
            if o.rubro == 'ampliacion_reforzamiento' and alimentador:
                kw = max(0.0, (cab_obra.get(alimentador) or 0) - (cab0.get(alimentador) or 0))
            coym = ci * float(coym_pct_anual) / 100 if coym_pct_anual is not None and ci else None
            ev = evaluar(ci, kw_nuevos=kw, usuarios=0, km=0, coym_anual=coym, cp_anual=None, plan=plan,
                         factor_carga=factor_carga, precio_compra_kwh=precio_compra_kwh,
                         opcion=str(plan.get('opcion_tarifaria_mt') or 'MT3'))
            criterios = {'subsanacion_calidad': 1.0 if o.causa in CAUSAS_DE_CALIDAD else 0.0,
                         'crecimiento_demanda': 1.0 if kw > 0 else 0.0}
            # 073:RF-28: una causa que solo se resuelve con bancos se queda sin obra, con su motivo.
            banco_vetado = sin_modulos and o.alternativa == 'bancos'
            c = Candidata(codigo, o.alternativa, f'{alimentador}:{o.causa}', not banco_vetado, ev, criterios)
            obra, motivo = _obra_011(o.alternativa, alimentador, elemento, sitio.get('kv'), bancos_kvar)
            if banco_vetado:
                obra, motivo = None, 'el valle no admite ningún módulo y la causa no tiene otra alternativa (073:RF-28)'
            en_valle = _valle_de_la_obra(de_valle, o.alternativa)
            if not en_valle['comprobado']:
                avisos.append(f'{codigo}: {o.alternativa} de {alimentador}: no comprobado en valle.')
            if (de_valle or {}).get('por_alternativa', {}).get(o.alternativa, {}).get('valle') is False:
                c.cumple_norma, obra, motivo = False, None, 'no cumple en valle (073:RF-40)'
            candidatas.append(c)
            filas_obra.append({'codigo': codigo, 'anio': o.anio, 'alternativa': o.alternativa,
                               'rubro': o.rubro, 'caracter': CARACTER_DE_ALTERNATIVA[o.alternativa],
                               'alimentador': alimentador, 'elemento': elemento,
                               'causa': o.causa, 'problemas': o.problemas[:20],
                               'denominacion': (costo or {}).get('denominacion'), 'ci': ci, 'kw_nuevos': kw,
                               'energia_kwh': kw * factor_carga * 8760 if factor_carga else None,
                               'obra_011': obra, 'motivo_sin_obra': motivo, 'candidata': c, 'valle': en_valle})
    orden = priorizar(candidatas, plan.get('pesos_art_15_3') or {})
    prioridad = {c.codigo: i + 1 for i, c in enumerate(orden)}
    sin_costo = [c.codigo for c in candidatas if c.evaluacion.ci is None]
    if costos and sin_costo:
        avisos.append(f"{', '.join(sin_costo)} sin costo en el libro CAPEX: van tras las obras con costo en la "
                      'priorización')
    for f in filas_obra:
        c = f.pop('candidata')
        f.update(prioridad=prioridad[c.codigo], puntaje=c.puntaje, sobredimensionada=c.sobredimensionada,
                 descartada=c.descartada, regulada=c.evaluacion.regulada, privada=c.evaluacion.privada,
                 indicadores=c.evaluacion.indicadores, avisos=c.evaluacion.avisos,
                 sin_tipo_de_cambio=c.evaluacion.sin_tipo_de_cambio)
        if f['descartada'] and 'valle' in str(f['motivo_sin_obra']):
            f['descartada'] = 'no cumple en valle: ' + str(f['motivo_sin_obra'])
    filas_obra.sort(key=lambda f: f['prioridad'])
    return {'obras': filas_obra, 'avisos': avisos, 'formatos': filas_de_obras(filas_obra, anios)}
