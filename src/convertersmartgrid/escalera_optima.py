"""Escalera optimizada de obras sobre «Con proyecto <año>» (spec 025, RF-44, RF-49 a RF-60).

Usuario, 2026-10-24: «primero se debe probar bancos, después nueva terna, cambio de sección
de cable, donde se debe iterar varias veces hasta obtener la mejor solución según la
optimización y cálculos estocásticos»; la mejor, la de menor costo anual; se sortea la
demanda existente por la curva de cabecera del año; vale si cumple en el 95 % de 200
sorteos; en «Sin proyecto» no se corrige nada, así que «cumplir» es no dejar la red peor
que allí y dar a cada carga nueva su tensión.

Puro: arma las variantes, juzga cada flujo, sortea, costea y elige. Medir en DIgSILENT es de
``tools/obras_pf.py`` (``--evaluar``). Ningún valor de una empresa: todo sale del perfil
(``escalera`` y ``planificacion``), de las bibliotecas y del libro CAPEX.
"""
from __future__ import annotations

import itertools
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .catalogo_reguladores import CatalogoError, unidad_para_corriente, unidades_para
from .estudios_pf import CON_PROYECTO
from .instalacion_ternas import capacidad_de_tramos
from .pide_economia import costo_anual
from .perfil_empresa import TASA_CRECIMIENTO_DE_REFERENCIA
from .set_nueva import margen_sin_tasa

#: Orden de la escalera: bancos, cambio de sección, terna y, al final, regulador (063:RF-21; cambia
#: 025:RF-44). Usuario, 2026-11-01: «primero debe comenzar con bancos y luego con cambio de sección
#: y una terna después, pero si y solo si se requiere».
ORDEN = ('bancos', 'seccion', 'terna', 'regulador')


#: 042:RF-55, RF-105: alternativas de solución que se presentan por alimentador si el perfil no da
#: ``escalera.alternativas``; el usuario (2026-11-07) admite de 3 a 6, y se le recomendaron 3 más la definitiva.
MAX_ALTERNATIVAS = 3
#: 042:RF-106: el rango que admite ``escalera.alternativas``.
ALTERNATIVAS_ADMITIDAS = (3, 6)
#: 042:RF-50: el paso a 22,9 kV no se combina: va solo, tras los bancos y antes de la sección.
ESCALERA = ('bancos', 'nivel', 'seccion', 'terna', 'regulador')


#: 094:RF-18: el nombre con que empieza la variante de bancos ubicados según el perfil de tensión.
PREFIJO_PERFIL = 'bancos según perfil'


def rango(escalones) -> int:
    """El escalón más alto que usa una variante; sin escalones (sin obras), antes de todos (063:RF-22)."""
    return max((ESCALERA.index(e) for e in escalones if e in ESCALERA), default=-1)
def grupo_economico(escalones) -> int:
    """042:RF-56: los bancos solos antes (063:RF-22), el regulador al final (RF-49); el resto compite por costo."""
    e = set(escalones or ())
    return 0 if e and e <= {'bancos'} else 2 if 'regulador' in e else 1


#: Alternativa del PIDE de cada escalón, para su costo en el libro CAPEX (RF-53).
ALTERNATIVA = {'bancos': 'bancos', 'regulador': 'reguladores', 'terna': 'nueva_terna',
               'seccion': 'cambio_seccion', 'nivel': 'cambio_tension', 'sed_nivel': 'cambio_tension_sed',
               'celda_nivel': 'celda', 'elevador_nivel': 'elevador',
               # 087:RF-32, RF-33: el enlace de una transferencia o un traslado es red de media nueva, por km.
               'transferencia': 'nuevo_alimentador', 'traslado': 'nuevo_alimentador'}
#: 042:RF-54, 087:RF-37: en dólares y por confirmar, para la empresa cuyo libro y perfil no traen estos costos.
#: La celda es la más parecida con costo público reciente: la celda GIS de 22,9 kV que fija Osinergmin en la
#: Resolución 058-2026-OS/CD (USD 58 699,52). Ninguna resolución vigente da la Metal Clad de salida de alimentador.
COSTOS_NIVEL_DE_REFERENCIA = {'cambio_tension': 40000.0, 'cambio_tension_sed': 9000.0, 'celda': 58699.52,
                              'elevador': 50000.0}
#: 087:RF-37: de dónde sale cada costo de referencia, para citarlo en el informe.
FUENTE_DE_REFERENCIA = {
    'celda': 'Osinergmin, Resolución 058-2026-OS/CD, celda GIS 22,9 kV (USD 58 699,52), la más parecida; por confirmar',
}
#: 042:RF-61: potencias normalizadas del elevador dedicado, en MVA; por encima de la última, RF-62.
MVA_ELEVADOR = (1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0)
#: Alternativas que se cuentan por unidad, no por km.
POR_UNIDAD = ('bancos', 'reguladores', 'cambio_tension_sed', 'celda')
#: Módulos de banco que se prueban sin valle medido ni ``escalera.modulos_max`` (073:RF-24). Es la
#: regla anterior a la spec 073, por compatibilidad, y solo vale marcada «no comprobado en valle».
MODULOS_SIN_VALLE = 2
#: Proyecto de DIgSILENT con los reguladores de catálogo (025:RF-59).
BIBLIOTECA_TIPOS = 'CSG_Biblioteca_tipos'
HORAS_ANIO = 8760


class EscaleraError(ValueError):
    """Falta un dato del perfil o del libro CAPEX: se dice cuál y no se supone (RF-57)."""


@dataclass(frozen=True)
class Parametros:
    cumplimiento: float
    sorteos: int
    semilla: int
    tolerancia_pu: float
    tolerancia_carga_pct: float
    max_variantes: int
    tasa: float
    vida: int
    tension_min_pu: float
    tension_max_pu: float
    cargabilidad_max_pct: float
    precio_perdidas_kwh: float | None = None
    precio_perdidas_kw_mes: float | None = None
    coym_pct_anual: float | None = None
    moneda: str = ''
    costos_unitarios: dict = field(default_factory=dict)       # alternativa → costo en ``moneda``
    escala_capex: float | None = None                          # ``moneda`` por unidad del libro CAPEX
    #: 025:RF-44: el regulador entra en la escalera, al final del orden (aclaración de 063:RF-26);
    #: un perfil puede quitarlo con ``escalera.con_regulador: false``.
    con_regulador: bool = True
    #: 073:RF-19, RF-24: techo del perfil para los módulos de banco; sin él, los del valle.
    modulos_max: int | None = None
    #: 084:RF-16: ``planificacion.ternas_subterraneas`` del perfil, con la capacidad por configuración.
    ternas: Mapping[str, Any] = field(default_factory=dict)
    #: 042:RF-27: los conductores normalizados de la empresa (prefijo del tipo); vacío, todos.
    secciones: tuple[str, ...] = ()
    #: 042:RF-35: desde este largo del camino a una carga, el regulador va por delante del tope de variantes.
    linea_larga_km: float = 10.0
    #: 042:RF-49: el regulador es un caso extremo: por debajo de este largo no se plantea.
    regulador_min_km: float = 15.0
    #: 042:RF-50: la tensión que se pasa y a cuál.
    migrar_desde_kv: float = 10.0
    migrar_a_kv: float = 22.9
    #: 042:RF-70, RF-71: margen del elevador y del regulador por el crecimiento que la corriente medida no cuenta.
    factor_sin_tasa: float = 1.0
    #: 042:RF-73, RF-91: los años a que una alternativa es definitiva: la vida útil.
    horizonte_anios: int = 30
    #: 042:RF-86: el crecimiento con que se proyecta ese horizonte.
    tasa_largo_plazo: float = 0.03
    #: 042:RF-87: los sorteos de la primera etapa y las fracciones con que ya se decide.
    sorteos_etapa: int = 50
    sorteos_decide_si: float = 0.98
    sorteos_decide_no: float = 0.90
    #: 042:RF-90: las que se prueban tras la primera que cumple, buscando otras alternativas.
    variantes_tras_cumplir: int = 25
    #: 042:RF-105: las alternativas que se presentan por alimentador, de 3 a 6.
    alternativas: int = MAX_ALTERNATIVAS
    #: 042:RF-98: ``escalera.conductor_terna`` del perfil, el código del conductor ``aereo`` y el del ``cable``
    #: con que quedan los dos circuitos de una terna; vacío, la terna es del mismo tipo del tramo (RF-100).
    conductor_terna: Mapping[str, str] = field(default_factory=dict)

    @property
    def consigna_regulador_pu(self) -> float:
        """El centro de la banda de tensión del perfil: sin un valor propio de la empresa."""
        return (self.tension_min_pu + self.tension_max_pu) / 2


def parametros(perfil: Mapping[str, Any], tipo_cambio: float | None = None) -> Parametros:
    """Los de la escalera, de ``escalera``, ``planificacion`` y ``estudios`` del perfil (RF-57).

    ``tipo_cambio``: unidades de la moneda de los precios de pérdidas por una de la moneda de
    trabajo, el que escribe el operador en la web (RF-67); no sale del perfil.
    """
    esc = dict(perfil.get('escalera') or {})
    plan = dict(perfil.get('planificacion') or {})
    lim = dict(perfil.get('estudios') or {})
    pedidos = {'escalera.cumplimiento': esc.get('cumplimiento'), 'escalera.sorteos': esc.get('sorteos'),
               'escalera.tolerancia_pu': esc.get('tolerancia_pu'),
               'escalera.tolerancia_carga_pct': esc.get('tolerancia_carga_pct'),
               'planificacion.tasa_regulada': plan.get('tasa_regulada'),
               'planificacion.vida_util_anios': plan.get('vida_util_anios'),
               'estudios.tension_min_pu': lim.get('tension_min_pu'),
               'estudios.tension_max_pu': lim.get('tension_max_pu'),
               'estudios.cargabilidad_max_pct': lim.get('cargabilidad_max_pct')}
    faltan = [k for k, v in pedidos.items() if v is None]
    if faltan:
        raise EscaleraError('el perfil de empresa no da ' + ', '.join(faltan) + ' (025:RF-57)')
    if not 0 < float(esc['cumplimiento']) <= 1 or int(esc['sorteos']) < 1:
        raise EscaleraError('escalera.cumplimiento va entre 0 y 1 y escalera.sorteos es al menos 1')
    # Los precios de pérdidas, en la moneda en que se publican; el costo, en la de trabajo
    # (usuario, 2026-10-24: «trabaja en dólares»), con el tipo de cambio que escribe el
    # operador en la web («la tasa de cambio de dólar debe ingresar por la web»).
    moneda = str(esc.get('moneda') or '')
    de = str(esc.get('moneda_precios_perdidas') or moneda)
    tc = 1.0
    if de != moneda and (esc.get('precio_perdidas_kwh') is not None or esc.get('precio_perdidas_kw_mes') is not None):
        if not tipo_cambio or float(tipo_cambio) <= 0:
            raise EscaleraError(f'los precios de pérdidas están en {de} y se trabaja en {moneda}: escriba en '
                                f'la web el tipo de cambio ({de} por {moneda}) (025:RF-68)')
        tc = float(tipo_cambio)
    esc = {**esc, 'precio_perdidas_kwh': _en(esc.get('precio_perdidas_kwh'), tc),
           'precio_perdidas_kw_mes': _en(esc.get('precio_perdidas_kw_mes'), tc)}
    return Parametros(
        cumplimiento=float(esc['cumplimiento']), sorteos=int(esc['sorteos']),
        semilla=int(esc.get('semilla') or 0), tolerancia_pu=float(esc['tolerancia_pu']),
        tolerancia_carga_pct=float(esc['tolerancia_carga_pct']),
        max_variantes=int(esc.get('max_variantes') or 40), tasa=float(plan['tasa_regulada']),
        vida=int(plan['vida_util_anios']), tension_min_pu=float(lim['tension_min_pu']),
        tension_max_pu=float(lim['tension_max_pu']),
        cargabilidad_max_pct=float(esc.get('cargabilidad_planeamiento_pct') or lim['cargabilidad_max_pct']),   # 042:RF-28
        precio_perdidas_kwh=_opcional(esc.get('precio_perdidas_kwh')),
        precio_perdidas_kw_mes=_opcional(esc.get('precio_perdidas_kw_mes')),
        coym_pct_anual=_opcional(esc.get('coym_pct_anual')), moneda=moneda,
        costos_unitarios={k: float(v) for k, v in (esc.get('costos_unitarios') or {}).items() if v is not None},
        escala_capex=_opcional(esc.get('escala_capex')), con_regulador=bool(esc.get('con_regulador', True)),
        modulos_max=None if esc.get('modulos_max') is None else int(esc['modulos_max']),
        ternas=dict(plan.get('ternas_subterraneas') or {}),
        secciones=tuple(str(x) for x in esc.get('secciones_normalizadas') or ()),
        linea_larga_km=float(esc.get('linea_larga_km') or 10.0),
        regulador_min_km=float(15.0 if esc.get('regulador_min_km') is None else esc['regulador_min_km']),
        migrar_desde_kv=float(esc.get('migrar_desde_kv') or 10.0), migrar_a_kv=float(esc.get('migrar_a_kv') or 22.9),
        factor_sin_tasa=margen_sin_tasa((perfil.get('planificacion') or {}).get('factor_seguridad_set_sin_tasa'),
                                        (perfil.get('planificacion') or {}).get('factor_seguridad_set')),
        horizonte_anios=int(plan['vida_util_anios']),
        tasa_largo_plazo=float((perfil.get('planificacion') or {}).get('crecimiento_demanda_anual') or TASA_CRECIMIENTO_DE_REFERENCIA),
        sorteos_etapa=int(50 if esc.get('sorteos_etapa') is None else esc['sorteos_etapa']),
        sorteos_decide_si=float(esc.get('sorteos_decide_si') or 0.98),
        sorteos_decide_no=float(esc.get('sorteos_decide_no') or 0.90),
        variantes_tras_cumplir=int(esc.get('variantes_tras_cumplir') or 25),
        alternativas=alternativas_del_perfil(esc), conductor_terna=conductor_terna_del_perfil(esc))


def alternativas_del_perfil(esc: Mapping[str, Any]) -> int:
    """042:RF-105, RF-106: ``escalera.alternativas``, un entero de 3 a 6; sin la clave, 3."""
    valor = esc.get('alternativas')
    if valor is None:
        return MAX_ALTERNATIVAS
    bajo, alto = ALTERNATIVAS_ADMITIDAS
    if isinstance(valor, bool) or not isinstance(valor, int) or not bajo <= valor <= alto:
        raise EscaleraError(f'escalera.alternativas es un entero de {bajo} a {alto}, no {valor!r} (042:RF-106)')
    return valor


def conductor_terna_del_perfil(esc: Mapping[str, Any]) -> dict[str, str]:
    """042:RF-98: ``escalera.conductor_terna`` = ``{"aereo": código, "cable": código}``; cada uno, opcional.

    Es un código de la empresa, como los de ``secciones_normalizadas``: no se fija en el código (P13).
    """
    valor = esc.get('conductor_terna')
    if valor is None:
        return {}
    if (not isinstance(valor, Mapping) or set(valor) - {'aereo', 'cable'}
            or not all(v is None or (isinstance(v, str) and v.strip()) for v in valor.values())):
        raise EscaleraError('escalera.conductor_terna es {"aereo": código, "cable": código}, con el código del '
                            f'conductor de la terna, no {valor!r} (042:RF-98)')
    return {k: str(v).strip() for k, v in valor.items() if v}


def _opcional(x) -> float | None:
    return None if x is None else float(x)


def _en(precio, tipo_cambio: float) -> float | None:
    return None if precio is None else float(precio) / tipo_cambio


def _unidad_de(alternativa: str) -> str:
    return 'MVA' if alternativa == 'elevador' else 'Und' if alternativa in POR_UNIDAD else 'km'


def costos_de_alternativas(capex: Mapping[str, Mapping[str, Any]], p: Parametros) -> dict[str, dict[str, Any]]:
    """Los del libro CAPEX, y los que el perfil da para las alternativas que el libro no tiene
    (bancos y reguladores en Electro Dunas); el libro manda si tiene la alternativa.

    RF-77: el libro se pasa a la moneda de trabajo con ``escalera.escala_capex``. El de Electro
    Dunas está en miles de dólares y la escalera lo tomaba en dólares: la terna salía a 60,9 por
    km y SI213 eligió terna y sección por las pérdidas (2026-10-24).
    """
    if any(v.get('costo_unitario') for v in capex.values()) and not p.escala_capex:
        raise EscaleraError('el perfil no dice en qué escala está el libro CAPEX respecto de la moneda '
                            f'de trabajo ({p.moneda}): escalera.escala_capex, p. ej. 1000 si está en miles '
                            '(025:RF-77)')
    out = {k: {**v, 'costo_unitario': (float(v['costo_unitario']) * p.escala_capex
                                       if v.get('costo_unitario') else v.get('costo_unitario')),
               'origen': v.get('origen') or 'capex'}
           for k, v in capex.items()}
    for alt, costo_u in p.costos_unitarios.items():
        if alt not in out or not out[alt].get('costo_unitario'):
            out[alt] = {'costo_unitario': costo_u, 'unidad': _unidad_de(alt), 'origen': 'perfil'}
    for alt, referencia in COSTOS_NIVEL_DE_REFERENCIA.items():                  # 042:RF-54
        if not (out.get(alt) or {}).get('costo_unitario'):
            seccion = out.get('cambio_seccion') or {}
            if alt == 'cambio_tension' and seccion.get('costo_unitario'):
                out[alt] = {**seccion, 'origen': 'deducido del cambio de sección, por confirmar'}
            else:
                out[alt] = {'costo_unitario': referencia, 'unidad': _unidad_de(alt),
                            'origen': FUENTE_DE_REFERENCIA.get(alt) or 'referencia, por confirmar'}
    # 087:RF-37: sin «nuevo alimentador» en el libro, el km de la terna, que es la misma red de media nueva.
    if not (out.get('nuevo_alimentador') or {}).get('costo_unitario'):
        for parecida in ('nueva_terna', 'cambio_seccion', 'cambio_tension'):
            if (out.get(parecida) or {}).get('costo_unitario'):
                out['nuevo_alimentador'] = {**out[parecida], 'origen': f'deducido de «{parecida}», por confirmar (087:RF-37)'}
                break
    return out


# --------------------------------------------------------------------------- variantes
@dataclass
class Variante:
    """Una combinación de obras de la escalera, con lo que hace falta para costearla."""
    nombre: str
    escalones: tuple[str, ...]
    obras: list[dict[str, Any]]
    cantidades: dict[str, float] = field(default_factory=dict)       # escalón → unidades o km
    #: 073:RF-20: un módulo más de los que admite el valle: se mide para dejar constancia, sin combinar.
    solo_evidencia: bool = False
    #: 094:RF-13, RF-14: en los bancos según el perfil, el perfil completo antes y después de la propuesta.
    perfil: dict[str, Any] | None = None


def _troncal_hasta(troncal: Sequence[Mapping[str, Any]], i: int) -> list[Mapping[str, Any]]:
    return list(troncal[:i + 1])


def _km(tramos) -> float:
    return sum(float(t.get('largo_m') or 0) for t in tramos) / 1000


def _nodos(tramos) -> list[dict[str, Any]]:
    """063:RF-31: cada tramo de una obra con su nodo de inicio y su nodo final, de la cabecera a
    la cola; sin esos datos (una lectura anterior), solo el tramo."""
    return [{'tramo': t['nombre'], 'desde': t.get('desde'), 'hasta': t.get('hasta')} for t in tramos]


def ubicacion(obra: Mapping[str, Any]) -> str:
    """Dónde va la obra en la red de media tensión, en una frase (063:RF-31).

    SM218 (2026-11-01, usuario): «en el cambio de tramos de cable y la ubicación de bancos deben
    indicarse los nodos de inicio y el nodo de MT donde se ubica el banco y los tramos».
    """
    if obra.get('clase') == 'condensador':
        return f"banco de {float(obra.get('q_kvar') or 0):g} kvar en el nodo de MT {obra.get('barra')}"
    nodos = list(obra.get('nodos') or [])
    que = (f"sección {(obra.get('tipo') or {}).get('nombre', '')}" if obra.get('clase') == 'seccion'
           else str(obra.get('clase') or 'obra'))
    if nodos and nodos[0].get('desde') and nodos[-1].get('hasta'):
        return (f"{que} desde el nodo {nodos[0]['desde']} hasta el nodo {nodos[-1]['hasta']} "
                f"({len(nodos)} tramos: " + ', '.join(
                    f"{n['tramo']} {n.get('desde') or '?'}→{n.get('hasta') or '?'}" for n in nodos) + ')')
    return f"{que} en los tramos " + ', '.join(str(t) for t in obra.get('tramos') or [])


def _bancos_en(alim, barras, banco_kvar, n: int, solo_evidencia: bool = False) -> Variante:
    # 063:RF-31: la barra del banco es el nodo de MT existente donde se instala.
    obras = [{'clase': 'condensador', 'alimentador': alim, 'casos': [CON_PROYECTO], 'barra': b,
              'q_kvar': float(banco_kvar) * n, 'escalones': n} for b in barras]
    return Variante(f'bancos {n}×{banco_kvar:g} kvar', ('bancos',), obras, {'bancos': float(len(barras) * n)},
                    solo_evidencia)


def _escalon_bancos(alim, barras, banco_kvar, modulos: int) -> list[Variante]:
    if not barras or not banco_kvar:
        return []
    return [_bancos_en(alim, barras, banco_kvar, n) for n in range(1, int(modulos) + 1)]


def nodo_a_dos_tercios(tramos: Sequence[Mapping[str, Any]]) -> str | None:
    """042:RF-37: la barra existente más cercana a 2/3 del camino; la de una carga nueva solo existe con ella."""
    total = _km(tramos)
    if total <= 0:
        return None
    acumulado, mejor = 0.0, None
    for t in tramos:
        acumulado += float(t.get('largo_m') or 0.0) / 1000.0
        hasta = str(t.get('hasta') or '')
        if hasta and not hasta.startswith('NODE_T_'):
            distancia = abs(acumulado - 2.0 * total / 3.0)
            if mejor is None or distancia < mejor[0]:
                mejor = (distancia, hasta)
    return mejor[1] if mejor else None


def puntos_de_regulador(camino: Sequence[Mapping[str, Any]], tension_min: float) -> list[int]:
    """042:RF-47: dónde rinde el regulador en el camino de una carga, por su tensión medida.

    En el último tramo que sale con la tensión dentro del límite, y a mitad de la caída hasta ese punto: más arriba lleva más
    corriente; más abajo ya hay barras fuera. Nunca el primero, que sale de la cabecera. Sin caída fuera de límites, ninguno.
    """
    def tension(t) -> float | None:
        u = (t.get('u') or {}).get(t.get('hasta'))
        return float(u) if u is not None else None

    tensiones = [tension(t) for t in camino]
    primero = next((i for i, u in enumerate(tensiones) if u is not None and u < tension_min), None)
    if primero is None or primero == 0:
        return [] if primero is None else [1] if len(camino) > 1 else []
    inicio = next((u for u in tensiones if u is not None), tension_min)
    objetivo = (inicio + tension_min) / 2
    medio = next((i for i, u in enumerate(tensiones) if u is not None and u < objetivo), primero)
    return sorted({max(1, primero), max(1, min(medio, primero))} & set(range(1, len(camino))))


def _regulador_en(alim, t, unidad, p: Parametros) -> Variante:
    obra = {'clase': 'regulador', 'alimentador': alim, 'casos': [CON_PROYECTO], 'tramo': t['nombre'],
            'consigna_pu': p.consigna_regulador_pu, 'rango_pct': 10.0, 'pasos': 16,
            'tipo': {'nombre': unidad.nombre, 'clase': 'TypVoltreg', 'origen': 'otro', 'proyecto': BIBLIOTECA_TIPOS}}
    return Variante(f"regulador {unidad.corriente_a:g} A en {t['nombre']}", ('regulador',), [obra], {'regulador': 1.0})


def _reguladores_en_caminos(alim, kv, caminos, p: Parametros, avisos) -> list[Variante]:
    """042:RF-47: en los puntos de cada camino, con la unidad que lleva su corriente bajo el límite de planeamiento."""
    out: dict[str, Variante] = {}
    for camino in sorted(caminos, key=_km, reverse=True):
        for i in puntos_de_regulador(camino, p.tension_min_pu):
            t = camino[i]
            # 042:RF-71: con el margen, como el elevador.
            corriente = p.factor_sin_tasa * float(t.get('corriente_a') or 0.0) / max(p.cargabilidad_max_pct / 100.0, 0.01)
            unidad = unidad_para_corriente(kv, corriente)
            if unidad is None:
                avisos.append(f"{alim}: ningún regulador del catálogo lleva {corriente:.0f} A en {t['nombre']} (042:RF-47).")
                continue
            out.setdefault(t['nombre'], _regulador_en(alim, t, unidad, p))
    return list(out.values())


def _escalon_regulador(alim, kv, troncal, fuera_desde, p: Parametros, avisos, caminos=()) -> list[Variante]:
    """042:RF-47 en el camino de cada carga si se conoce su tensión; si no, hasta tres sitios en la troncal, antes de la
    primera barra fuera de límites, con la unidad más chica que lleva la corriente del tramo (RF-60)."""
    try:
        unidades_para(kv)
    except CatalogoError as exc:
        avisos.append(f'{alim}: {exc}; no hay escalón de regulador.')
        return []
    en_caminos = _reguladores_en_caminos(alim, kv, caminos, p, avisos)
    if en_caminos:
        return en_caminos
    hasta = len(troncal) if fuera_desde is None else max(0, int(fuera_desde))
    candidatos = []
    for i, t in enumerate(troncal[:hasta]):
        corriente = t.get('corriente_a')
        if corriente is None:
            continue
        unidad = unidad_para_corriente(kv, p.factor_sin_tasa * float(corriente))       # 042:RF-71
        if unidad is not None:
            candidatos.append((i, t, unidad))
    if not candidatos:
        avisos.append(f'{alim}: ningún tramo de la troncal antes de la caída lleva una corriente '
                      'que admita un regulador del catálogo; no hay escalón de regulador.')
        return []
    elegidos = sorted({candidatos[min(len(candidatos) - 1, int(f * len(candidatos)))][0]
                       for f in (1 / 3, 1 / 2, 2 / 3)})
    out = []
    for i in elegidos:
        _, t, unidad = next(c for c in candidatos if c[0] == i)
        obra = {'clase': 'regulador', 'alimentador': alim, 'casos': [CON_PROYECTO], 'tramo': t['nombre'],
                'consigna_pu': p.consigna_regulador_pu, 'rango_pct': 10.0, 'pasos': 16,
                'tipo': {'nombre': unidad.nombre, 'clase': 'TypVoltreg', 'origen': 'otro',
                         'proyecto': BIBLIOTECA_TIPOS}}
        out.append(Variante(f"regulador {unidad.corriente_a:g} A en {t['nombre']}", ('regulador',),
                            [obra], {'regulador': 1.0}))
    return out


def camino_electrico(tramos: Sequence[Mapping[str, Any]], origen: str, destino: str) -> list[dict]:
    """Los tramos de ``origen`` a ``destino`` por la red (``desde``, ``hasta``), en orden (063:RF-32).

    El camino más corto en número de tramos, sin pasar dos veces por una barra; vacío si no hay.
    SM218 (2026-11-01): INKA cuelga de un ramal a 17,08 km de la cabecera, no de la troncal más
    larga a 10,32 km donde la ponía la cercanía GPS; las obras se probaban donde no hacía falta.
    """
    from collections import defaultdict, deque

    ady: dict[str, list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for t in tramos:
        ady[str(t['desde'])].append((str(t['hasta']), t))
        ady[str(t['hasta'])].append((str(t['desde']), t))
    previo: dict[str, tuple[str, Mapping[str, Any]] | None] = {origen: None}
    cola = deque([origen])
    while cola and destino not in previo:
        n = cola.popleft()
        for m, t in sorted(ady[n], key=lambda x: str(x[1].get('nombre'))):
            if m not in previo:
                previo[m] = (n, t)
                cola.append(m)
    if destino not in previo:
        return []
    out, n = [], destino
    while previo[n] is not None:
        a, t = previo[n]
        out.append({**t, 'desde': a, 'hasta': n})
        n = a
    return out[::-1]


def solo_lineas(camino: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """042:RF-44: del camino eléctrico, los tramos que pueden llevar obra: un acoplador conecta, pero no se refuerza."""
    return [t for t in camino if not t.get('puente')]


def _caminos(troncal, cargas) -> list[list[Mapping[str, Any]]]:
    """Por carga, los tramos donde van sección y terna: su camino eléctrico si la lectura lo da
    (063:RF-32); si no, la troncal hasta su índice (025:RF-44). Sin repetir caminos."""
    vistos, out = set(), []
    for c in cargas:
        tramos = list(c.get('camino') or [])
        if not tramos and c.get('indice_troncal') is not None:
            tramos = _troncal_hasta(troncal, int(c['indice_troncal']))
        clave = tuple(t['nombre'] for t in tramos)
        if tramos and clave not in vistos:
            vistos.add(clave)
            out.append(tramos)
    return out


def _ref_de(tipo: Mapping[str, Any]) -> dict[str, Any]:
    """La referencia de un tipo de línea leído, como la pide una obra (``obras_pf.TipoRef``)."""
    return {'nombre': tipo['nombre'], 'clase': 'TypLne', 'origen': tipo.get('origen') or 'proyecto',
            'proyecto': tipo.get('proyecto') or ''}


def _amperios(tipo: Mapping[str, Any] | None) -> float:
    return float(((tipo or {}).get('datos') or {}).get('sline') or 0.0) * 1000


def tipos_de_terna(tipos: Sequence[Mapping[str, Any]], kv: float, p: Parametros) -> dict[str, Mapping[str, Any]] | None:
    """042:RF-98, RF-100: el tipo de la biblioteca de cada código de ``escalera.conductor_terna``; ``None`` sin la clave.

    De los de ese código, el de la tensión más cercana a la del alimentador (el de ficha, si lo hay, RF-27): la
    simulación lo copia a la tensión del alimentador si hace falta (011:RF-79). Uno que no está no se supone.
    """
    if not p.conductor_terna:
        return None
    out: dict[str, Mapping[str, Any]] = {}
    for clase, codigo in p.conductor_terna.items():
        lineas = [t for t in tipos if t.get('clase', 'TypLne') == 'TypLne' and _amperios(t) > 0]
        hallados = normalizados(lineas, (codigo,))
        if hallados:
            out[clase] = min(hallados, key=lambda t: (abs(float((t.get('datos') or {}).get('uline') or 0.0) - kv),
                                                      str(t['nombre'])))
    return out


def obra_terna(alim: str, tramos: Sequence[Mapping[str, Any]], ternas: Mapping[str, Any] | None,
               de_terna: Mapping[str, Mapping[str, Any]] | None, avisos: list[str] | None = None) -> tuple[dict[str, Any], float]:
    """Una terna más en ``tramos``: la obra y los km de los tramos cuyo conductor cambia (042:RF-98 a RF-100, RF-103).

    Usuario (2026-11-07), tras PE102: «la nueva terna debe ser en 120 mm², ambas ternas». Con el conductor del perfil,
    el tramo más delgado pasa a él y la terna nueva es del mismo tipo; el que ya lleva igual o más corriente añade la
    terna de su tipo. ``ternas``: ``planificacion.ternas_subterraneas`` (084:RF-16). ``cambia_tipo`` es lo que el oráculo mide (RF-104); en DIgSILENT lo decide la simulación con los
    tipos leídos (``obras_pf._terna``), con la misma regla.
    """
    avisos = avisos if avisos is not None else []
    obra: dict[str, Any] = {'clase': 'terna', 'alimentador': alim, 'casos': [CON_PROYECTO],
                            'tramos': [t['nombre'] for t in tramos], 'nodos': _nodos(tramos)}

    def avisar(texto: str) -> None:
        if texto not in avisos:
            avisos.append(texto)

    if de_terna is None:
        avisar(f'{alim}: el perfil no da escalera.conductor_terna: la terna se añade del mismo tipo de cada tramo '
               '(042:RF-100).')
        return {**obra, **capacidad_de_tramos(tramos, ternas)}, 0.0
    for clave, clase in (('tipo', 'aereo'), ('tipo_cable', 'cable')):
        if de_terna.get(clase) is not None:
            obra[clave] = _ref_de(de_terna[clase])
    cambia: dict[str, str] = {}
    for t in tramos:
        clase = 'cable' if t.get('cable') else 'aereo'
        tipo = de_terna.get(clase)
        if tipo is None:
            avisar(f"{alim}: sin el conductor {clase} de escalera.conductor_terna en la biblioteca, la terna de "
                   f"{t['nombre']} se añade de su mismo tipo (042:RF-100).")
        elif not t.get('inom_a'):
            continue                       # sin su conductor leído, lo decide la simulación con el de DIgSILENT (RF-99)
        elif float(t['inom_a']) < _amperios(tipo):
            cambia[str(t['nombre'])] = str(tipo['nombre'])
        else:
            # 042:RF-99: «solo una terna debe ser 240 mm²»: un tramo que ya es de 240 añade la de su tipo, y se dice.
            avisar(f"{alim}: {t['nombre']} ya lleva igual o más corriente que {tipo['nombre']}: la terna se añade de "
                   'su mismo tipo (042:RF-99).')
    # 084:RF-16: la capacidad del fabricante es la del conductor con que queda el cable, no la del que tenía.
    obra.update(capacidad_de_tramos([{**t, 'tipo': cambia.get(str(t['nombre']), t.get('tipo'))} for t in tramos], ternas))
    if cambia:
        obra['cambia_tipo'] = cambia
    return obra, _km([t for t in tramos if str(t['nombre']) in cambia])


def _variante_terna(alim, tramos, p: Parametros, de_terna, avisos) -> Variante:
    obra, km_cambia = obra_terna(alim, tramos, p.ternas, de_terna, avisos)
    nombre = f"terna hasta {tramos[-1]['nombre']} ({_km(tramos):.2f} km)"
    if de_terna and (obra.get('tipo') or obra.get('tipo_cable')):
        nombre += ' en ' + ' y '.join(str(obra[k]['nombre']) for k in ('tipo', 'tipo_cable') if obra.get(k))
    # 042:RF-103: el conductor existente que cambia cuesta como un cambio de sección de esos tramos.
    return Variante(nombre, ('terna',), [obra], {'terna': _km(tramos), **({'seccion': km_cambia} if km_cambia else {})})


def _escalon_terna(alim, troncal, cargas, p: Parametros, de_terna=None, avisos=None) -> list[Variante]:
    return [_variante_terna(alim, tramos, p, de_terna, avisos) for tramos in _caminos(troncal, cargas)]  # 063:RF-32


def secciones_aptas(tipos, kv: float, corriente_a: float | None, p: Parametros) -> list[Mapping[str, Any]]:
    """042:RF-97: los conductores de un solo circuito que se prueban: los normalizados del perfil, hasta el mayor.

    PE102 (2026-11-07): el escalón de sección llega hasta 240 mm² en Electro Dunas porque es el mayor de su lista;
    la búsqueda del oráculo (087) tomaba todos los de la tensión y podía proponer uno que la empresa no instala.
    """
    return conductores_aptos(normalizados(tipos, p.secciones), kv, corriente_a)


def doble_con_seccion(v: Variante) -> bool:
    """042:RF-102: una sección y una terna sobre el mismo tramo, el doble circuito del conductor nuevo."""
    seccion = {t for o in v.obras if o.get('clase') == 'seccion' for t in o.get('tramos') or ()}
    return any(t in seccion for o in v.obras if o.get('clase') == 'terna' for t in o.get('tramos') or ())


def normalizados(tipos, secciones: Sequence[str]) -> list[Mapping[str, Any]]:
    """042:RF-27: solo los conductores normalizados, uno por código (el de ficha si existe); sin lista, todos."""
    if not secciones:
        return list(tipos)
    por_codigo: dict[tuple, Mapping[str, Any]] = {}
    for t in tipos:
        nombre = str(t.get('nombre') or '')
        codigo = next((s for s in secciones if nombre.upper().startswith(s.upper())), None)
        if codigo is None:
            continue
        clave = (codigo, round(float((t.get('datos') or {}).get('uline') or 0), 1))
        if clave not in por_codigo or nombre.upper().endswith('_FICHA'):
            por_codigo[clave] = t
    return list(por_codigo.values())


def conductores_aptos(tipos, kv, corriente_a) -> list[Mapping[str, Any]]:
    """Aéreos de la tensión del alimentador (±10 %) que llevan la corriente, de menor a mayor."""
    out = []
    for t in tipos:
        d = t.get('datos') or {}
        uline, sline = d.get('uline'), d.get('sline')
        if t.get('clase') != 'TypLne' or d.get('cohl_') != 1 or not isinstance(uline, (int, float)):
            continue
        if not isinstance(sline, (int, float)) or abs(float(uline) - kv) > 0.1 * kv:
            continue
        if corriente_a is None or float(sline) * 1000 >= corriente_a:
            out.append(t)
    return sorted(out, key=lambda t: (t['datos']['sline'], t['nombre']))


def _escalon_seccion(alim, kv, troncal, cargas, tipos, avisos) -> list[Variante]:
    out = []
    for tramos in _caminos(troncal, cargas):                               # 063:RF-32
        # 063:RF-30: cada conductor cambia solo los tramos más delgados que él, y tiene que llevar
        # su corriente; por eso aquí se piden todos los de la tensión, sin filtrar por la corriente
        # del tramo más cargado del camino (que ya es de mayor sección).
        delgados = [t for t in tramos if t.get('inom_a') is not None]
        corrientes = [float(t['corriente_a']) for t in tramos if t.get('corriente_a') is not None]
        aptos = conductores_aptos(tipos, kv, None if delgados else (max(corrientes) if corrientes else None))
        if not aptos:
            avisos.append(f"{alim}: ningún conductor aéreo de {kv:g} kV lleva la corriente hasta "
                          f"{tramos[-1]['nombre']}; no hay escalón de sección allí.")
            continue
        # 063:RF-27: todas las aptas, de menor a mayor: se sube de sección en sección y se queda
        # la menor que cumple (antes, las dos primeras; SM218 saltaba a AA 120 mm²).
        for tipo in aptos:
            ref = {'nombre': tipo['nombre'], 'clase': 'TypLne', 'origen': tipo.get('origen') or 'proyecto',
                   'proyecto': tipo.get('proyecto') or ''}
            # 063:RF-30: solo los tramos de menor corriente nominal que la del conductor nuevo; los
            # de igual o mayor sección se quedan. Sin el dato del tramo (una lectura anterior), todos.
            nueva_a = float(tipo['datos']['sline']) * 1000
            cambian = [t for t in tramos if t.get('inom_a') is None or float(t['inom_a']) < nueva_a]
            if not cambian or any(float(t.get('corriente_a') or 0) > nueva_a for t in cambian):
                continue
            out.append(Variante(f"sección {tipo['nombre']} en {len(cambian)} tramos hasta {tramos[-1]['nombre']} "
                                f"({_km(cambian):.2f} km)",
                                ('seccion',),
                                [{'clase': 'seccion', 'alimentador': alim, 'casos': [CON_PROYECTO],
                                  'tramos': [t['nombre'] for t in cambian], 'tipo': ref,
                                  'nodos': _nodos(cambian)}],
                                {'seccion': _km(cambian)}))
    return out


def _ternas_que_faltan(t: Mapping[str, Any], v: Variante, capacidades: Mapping[str, float], limite: float,
                       de_terna: Mapping[str, Mapping[str, Any]] | None = None) -> int:
    """Cuántas ternas más necesita el tramo ``t`` con la variante ``v`` para quedar bajo ``limite`` (042:RF-43).

    042:RF-98: con el conductor de la terna del perfil, el tramo más delgado pasa a él, y las ternas se cuentan con
    su corriente; aun así se pone una, porque es la obra de un cable o de lo que ninguna sección resuelve (RF-94).
    """
    k = max(1, int(t.get('nlnum') or 1))
    carga = float(t['carga_pct'])
    for o in v.obras:
        nueva = capacidades.get(str((o.get('tipo') or {}).get('nombre')))
        if o.get('clase') == 'seccion' and t['nombre'] in o.get('tramos', ()) and nueva and t.get('inom_a'):
            carga *= float(t['inom_a']) / float(nueva)
    minimo = 0
    nuevo = (de_terna or {}).get('cable' if t.get('cable') else 'aereo')
    if nuevo is not None and t.get('inom_a') and float(t['inom_a']) < _amperios(nuevo):
        minimo = 1 if carga > limite else 0
        carga *= float(t['inom_a']) / _amperios(nuevo)
    pedidas = max(minimo, math.ceil(k * carga / limite - 1e-9) - k)
    ya = sum(1 for o in v.obras if o.get('clase') == 'terna' and t['nombre'] in o.get('tramos', ()))
    return max(0, pedidas - ya)


def _seccion_que_basta(t: Mapping[str, Any], aptos: Sequence[Mapping[str, Any]], limite: float) -> Mapping[str, Any] | None:
    """042:RF-94: el menor conductor aéreo normalizado que deja el tramo ``t`` bajo ``limite``; ``None`` si es cable o ninguno basta."""
    if t.get('cable') or not t.get('inom_a'):
        return None
    actual, carga = float(t['inom_a']), float(t['carga_pct'])
    for tipo in aptos:                                           # de menor a mayor capacidad
        nueva = float((tipo.get('datos') or {}).get('sline') or 0.0) * 1000
        if nueva > actual and carga * actual / nueva <= limite:
            return tipo
    return None


def _con_refuerzo(v: Variante, alim: str, sobrecargados, capacidades, p: Parametros,
                  aptos: Sequence[Mapping[str, Any]] = (), de_terna: Mapping[str, Mapping[str, Any]] | None = None,
                  avisos: list[str] | None = None) -> Variante:
    """La variante con el refuerzo de los tramos sobrecargados, de cualquier ramal (042:RF-43).

    042:RF-94: un tramo aéreo sin obra de la variante cambia primero de sección, a la menor normalizada que lo
    deja bajo el límite; las ternas quedan para los cables y para lo que ninguna sección resuelve. PE102
    (2026-11-06): todo refuerzo era una terna y el usuario la cambió por la sección AA120 en SEC_1091_314817.
    """
    por_tipo: dict[str, tuple[Mapping[str, Any], list]] = {}
    con_terna = []
    for t in sobrecargados:
        tocado = any(t['nombre'] in o.get('tramos', ()) for o in v.obras if o.get('clase') in ('seccion', 'terna'))
        tipo = None if tocado else _seccion_que_basta(t, aptos, p.cargabilidad_max_pct)
        if tipo is None:
            con_terna.append(t)
        else:
            por_tipo.setdefault(str(tipo['nombre']), (tipo, []))[1].append(t)
    obras, km_seccion = [], 0.0
    for tipo, tramos in por_tipo.values():
        ref = {'nombre': tipo['nombre'], 'clase': 'TypLne', 'origen': tipo.get('origen') or 'proyecto',
               'proyecto': tipo.get('proyecto') or ''}
        obras.append({'clase': 'seccion', 'alimentador': alim, 'casos': [CON_PROYECTO],
                      'tramos': [t['nombre'] for t in tramos], 'tipo': ref, 'nodos': _nodos(tramos)})
        km_seccion += _km(tramos)
    faltan = [(t, _ternas_que_faltan(t, v, capacidades, p.cargabilidad_max_pct, de_terna)) for t in con_terna]
    km, km_por_tipo = 0.0, km_seccion
    # 042:RF-98: el conductor cambia una vez: en la primera terna del tramo, la de la variante si ya la tenía.
    con_tipo_nuevo = {t for o in v.obras if o.get('clase') == 'terna' for t in o.get('tramos') or ()}
    for i in range(1, max((m for _, m in faltan), default=0) + 1):
        tramos = [t for t, m in faltan if m >= i]
        obra, _km_cambia = obra_terna(alim, tramos, p.ternas, de_terna, avisos)
        cambia = {n: tipo for n, tipo in (obra.pop('cambia_tipo', None) or {}).items() if n not in con_tipo_nuevo}
        if cambia:
            obra['cambia_tipo'] = cambia
            km_seccion += _km([t for t in tramos if str(t['nombre']) in cambia])         # 042:RF-103
        con_tipo_nuevo |= {str(t['nombre']) for t in tramos}
        obras.append(obra)
        km += _km(tramos)
    if not obras:
        return v
    n = sum(len(ts) for _, ts in por_tipo.values()) + sum(1 for _, m in faltan if m)
    nombre = f'refuerzo de {n} tramos sobrecargados ({km + km_por_tipo:.2f} km)'
    escalones = v.escalones + (('seccion',) if por_tipo else ()) + (('terna',) if km or any(m for _, m in faltan) else ())
    cantidades = dict(v.cantidades)
    if km_seccion:
        cantidades['seccion'] = float(cantidades.get('seccion') or 0.0) + km_seccion
    if any(m for _, m in faltan):
        cantidades['terna'] = float(cantidades.get('terna') or 0.0) + km
    return Variante(f'{v.nombre} + {nombre}' if v.nombre else nombre, tuple(dict.fromkeys(escalones)),
                    v.obras + obras, cantidades, v.solo_evidencia)


def por_costo(variantes: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """042:RF-95: de menor a mayor ``costo_base``; las que no tienen costo, al final; entre iguales, el orden recibido.

    PE102 (2026-11-06): en el orden de la escalera se midieron 34 variantes en DIgSILENT antes de reunir las 3
    alternativas; medidas de la más barata a la más cara, las primeras que cumplen ya son las que se presentan.
    """
    return [v for _, v in sorted(enumerate(variantes), key=lambda iv: (iv[1].get('costo_base') is None,
                                                                       float(iv[1].get('costo_base') or 0.0), iv[0]))]


def mva_del_elevador(kv: float, corriente_a: float, p: Parametros) -> float | None:
    """042:RF-61: el menor normalizado con la corriente de salida bajo el límite; ``None`` si no hay ninguno (RF-62)."""
    necesarios = p.factor_sin_tasa * math.sqrt(3) * kv * corriente_a / 1000.0 / max(p.cargabilidad_max_pct / 100.0, 0.01)
    return next((m for m in MVA_ELEVADOR if m >= necesarios), None)


def _escalon_nivel(alim: str, kv: float, datos: Mapping[str, Any] | None, p: Parametros, avisos: list[str],
                   corriente_a: float = 0.0) -> list[Variante]:
    """042:RF-50 a RF-53: el alimentador entero a la tensión de destino, por una celda nueva o con su fuente."""
    if not datos or abs(kv - p.migrar_desde_kv) > 0.05 * p.migrar_desde_kv:
        return []
    km, seds = float(datos.get('km') or 0.0), float(datos.get('seds') or 0.0)
    comunes = {'alimentador': alim, 'casos': [CON_PROYECTO], 'kv_destino': p.migrar_a_kv}
    if datos.get('salida') and datos.get('nodo'):
        obra = {**comunes, 'clase': 'migracion', 'nodo': datos['nodo'], 'salida': datos['salida']}
        return [Variante(f"paso a {p.migrar_a_kv:g} kV por celda nueva en {datos['salida']} ({km:.2f} km, {seds:.0f} SED)",
                         ('nivel',), [obra], {'nivel': km, 'sed_nivel': seds, 'celda_nivel': 1.0})]
    if not datos.get('compartida'):
        return [Variante(f'cambio a {p.migrar_a_kv:g} kV con su fuente ({km:.2f} km, {seds:.0f} SED)', ('nivel',),
                         [{**comunes, 'clase': 'tension'}], {'nivel': km, 'sed_nivel': seds})]
    mva = mva_del_elevador(kv, corriente_a, p)
    if mva is not None and datos.get('nodo'):                                   # 042:RF-61
        obra = {**comunes, 'clase': 'migracion', 'nodo': datos['nodo'], 'elevador_mva': mva}
        return [Variante(f'paso a {p.migrar_a_kv:g} kV con elevador dedicado de {mva:g} MVA ({km:.2f} km, {seds:.0f} SED)',
                         ('nivel',), [obra], {'nivel': km, 'sed_nivel': seds, 'elevador_nivel': mva})]
    motivo = ('no se conoce el primer nodo de su salida' if mva is not None
              else f'el elevador pasaría de {MVA_ELEVADOR[-1]:g} MVA con {corriente_a:.0f} A de salida')
    avisos.append(f'{alim}: su SET no tiene barra de {p.migrar_a_kv:g} kV y comparte cabecera; {motivo}: '
                  'sigue la escalera hasta la SET nueva (042:RF-53, RF-62).')
    return []


def variantes(alimentador: str, kv: float, troncal: Sequence[Mapping[str, Any]],
              cargas: Sequence[Mapping[str, Any]], tipos: Sequence[Mapping[str, Any]], p: Parametros, *,
              banco_kvar: float | None, fuera_desde: int | None = None, modulos_valle: int | None = None,
              evidencia: bool = True, sobrecargados: Sequence[Mapping[str, Any]] | None = None,
              nivel: Mapping[str, Any] | None = None) -> tuple[list[Variante], list[str]]:
    """Las variantes de un alimentador en el orden de RF-44, con sus combinaciones (RF-49).

    ``troncal``: sus tramos desde la cabecera (``nombre``, ``largo_m``, ``corriente_a`` en
    «Con proyecto»). ``cargas``: las nuevas, con ``barra``, ``existe`` (si la barra está sin
    la carga: un banco en la que crea su variación dependería de ella) e ``indice_troncal``.
    ``fuera_desde``: índice del primer tramo cuya barra queda fuera de límites.
    ``modulos_valle``: cuántos módulos de banco admite el valle (073:RF-19); con ``evidencia`` se
    mide también uno más (RF-20), salvo que el tope lo ponga el perfil. Sin él, 073:RF-24.
    """
    avisos: list[str] = []
    barras = list(dict.fromkeys(str(c['barra']) for c in cargas if c.get('existe') and c.get('barra')))
    if not barras:
        avisos.append(f'{alimentador}: ninguna carga nueva está en una barra que exista sin ella; '
                      'no hay escalón de bancos.')
    elif not banco_kvar:
        avisos.append(f'{alimentador}: el perfil no da el tamaño de banco de {kv:g} kV; no hay escalón de bancos.')
    modulos = (modulos_valle if modulos_valle is not None
               else p.modulos_max if p.modulos_max is not None else MODULOS_SIN_VALLE)
    if modulos_valle is not None and barras and banco_kvar:
        avisos.append(f'{alimentador}: el valle admite {modulos_valle} módulos de {banco_kvar:g} kvar en cada barra (073:RF-19).'
                      if modulos_valle else
                      f'{alimentador}: el valle no admite ningún módulo de {banco_kvar:g} kvar (073:RF-19).')
    caminos = _caminos(troncal, cargas)
    largo_km = max((_km(c) for c in caminos), default=0.0) or _km(troncal)
    # 042:RF-49: caso extremo; en Pisco se planteaba en un camino de 9,4 km que resuelve la sección.
    extremo = largo_km > p.regulador_min_km
    if p.con_regulador and not extremo:
        avisos.append(f'{alimentador}: camino de {largo_km:.1f} km, sin regulador: es para más de '
                      f'{p.regulador_min_km:g} km (042:RF-49).')
    de_terna = tipos_de_terna(tipos, kv, p)                                          # 042:RF-98
    por_escalon = {
        'bancos': _escalon_bancos(alimentador, barras, banco_kvar, modulos),
        # 025:RF-44: el regulador entra, al final del orden; el perfil puede quitarlo.
        'regulador': (_escalon_regulador(alimentador, kv, troncal, fuera_desde, p, avisos, caminos)
                      if p.con_regulador and extremo else []),
        'terna': _escalon_terna(alimentador, troncal, cargas, p, de_terna, avisos),
        'seccion': _escalon_seccion(alimentador, kv, troncal, cargas, normalizados(tipos, p.secciones), avisos),
    }
    solas = [v for e in ORDEN for v in por_escalon[e]]
    if modulos_valle is not None and evidencia and barras and banco_kvar:
        solas.insert(len(por_escalon['bancos']), _bancos_en(alimentador, barras, banco_kvar, modulos + 1, True))
    combinadas, dobles = [], []
    for i, a in enumerate(ORDEN):
        for b in ORDEN[i + 1:]:
            for va in por_escalon[a]:
                for vb in por_escalon[b]:
                    v = Variante(f'{va.nombre} + {vb.nombre}', va.escalones + vb.escalones,
                                 va.obras + vb.obras, {**va.cantidades, **vb.cantidades})
                    if {a, b} == {'seccion', 'terna'}:
                        # 042:RF-30: sección y terna en caminos distintos no se refuerzan; en el mismo, son la
                        # doble terna del conductor nuevo, y van antes que el resto (el tope de variantes).
                        sec, ter = (va, vb) if a == 'seccion' else (vb, va)
                        if not set(sec.obras[0]['tramos']) <= set(ter.obras[0]['tramos']):
                            continue
                        dobles.append(v)
                    else:
                        combinadas.append(v)
    if caminos and largo_km >= p.linea_larga_km and banco_kvar:
        # 042:RF-37: en línea larga, también donde más rinde el banco; SI112 no tenía ninguno, su carga parte un tramo.
        nodo = nodo_a_dos_tercios(max(caminos, key=_km))
        if nodo and nodo not in barras:
            en_nodo = [_bancos_en(alimentador, [nodo], banco_kvar, n) for n in range(1, int(modulos) + 1)]
            for v in en_nodo:
                v.nombre = f'{v.nombre} a 2/3 de la línea en {nodo}'
            solas[len(por_escalon['bancos']):len(por_escalon['bancos'])] = en_nodo
    if por_escalon['regulador'] and largo_km >= p.linea_larga_km:
        # 042:RF-35: en línea larga, el regulador no puede quedar detrás del tope; también con la doble terna más larga.
        # 042:RF-102: con el conductor de la terna del perfil, el doble circuito es la terna misma.
        circuitos = por_escalon['terna'] if p.conductor_terna else dobles
        mas_largas = sorted(circuitos, key=lambda v: -float(v.cantidades.get('terna') or 0.0))[:3]
        triples = [Variante(f'{d.nombre} + {r.nombre}', d.escalones + r.escalones, d.obras + r.obras,
                            {**d.cantidades, **r.cantidades}) for d in mas_largas for r in por_escalon['regulador']]
        combinadas = (triples + [v for v in combinadas if 'regulador' in v.escalones]
                      + [v for v in combinadas if 'regulador' not in v.escalones])
        avisos.append(f'{alimentador}: línea de {largo_km:.1f} km: se plantean reguladores, también con la doble terna (042:RF-35).')
    # 042:RF-50: tras los bancos, y antes de la sección; no se combina.
    cuantos_bancos = next((i for i, v in enumerate(solas) if 'bancos' not in v.escalones), len(solas))
    salida_a = max((float(t.get('corriente_a') or 0.0) for t in troncal), default=0.0)
    solas[cuantos_bancos:cuantos_bancos] = _escalon_nivel(alimentador, kv, nivel, p, avisos, salida_a)
    # 042:RF-38: todas las obras integradas: de tres en tres y las cuatro, con sección y terna en el mismo camino.
    mayores = []
    for k in (3, 4):
        for grupo in itertools.combinations(ORDEN, k):
            for partes in itertools.product(*(por_escalon[e] for e in grupo)):
                sec = next((v for e, v in zip(grupo, partes) if e == 'seccion'), None)
                ter = next((v for e, v in zip(grupo, partes) if e == 'terna'), None)
                if sec is not None and ter is not None and not set(sec.obras[0]['tramos']) <= set(ter.obras[0]['tramos']):
                    continue
                mayores.append(Variante(' + '.join(v.nombre for v in partes), sum((v.escalones for v in partes), ()),
                                        [o for v in partes for o in v.obras],
                                        {c: n for v in partes for c, n in v.cantidades.items()}))
    vistas: set[str] = set()
    todas = [v for v in solas + dobles + combinadas + mayores if not (v.nombre in vistas or vistas.add(v.nombre))]
    if sobrecargados:
        # 042:RF-43: sin esto, un tramo sobrecargado de otro ramal hacía fallar todas las variantes.
        capacidades = {str(t['nombre']): float((t.get('datos') or {}).get('sline') or 0.0) * 1000 for t in tipos}
        aptos = secciones_aptas(tipos, kv, None, p)                                    # 042:RF-94, RF-97
        solo = _con_refuerzo(Variante('', (), [], {}), alimentador, sobrecargados, capacidades, p, aptos,
                             de_terna, avisos)
        # 042:RF-50: a 22,9 kV la corriente baja a menos de la mitad: el paso de tensión no lleva refuerzo.
        todas = [solo] + [v if v.solo_evidencia or 'nivel' in v.escalones
                          else _con_refuerzo(v, alimentador, sobrecargados, capacidades, p, aptos, de_terna, avisos)
                          for v in todas]
        avisos.append(f"{alimentador}: {len(sobrecargados)} tramos pasan de {p.cargabilidad_max_pct:g} % con las cargas nuevas; "
                      'cada variante los refuerza (042:RF-43).')
    if p.conductor_terna:
        # 042:RF-102: «solo una terna debe ser 240 mm²»: una sección y una terna en el mismo tramo darían dos
        # circuitos del conductor de la sección; los dos circuitos son los del conductor de la terna (RF-98).
        todas = [v for v in todas if not doble_con_seccion(v)]
    if len(todas) > p.max_variantes:
        avisos.append(f'{alimentador}: {len(todas)} variantes; se prueban las {p.max_variantes} primeras '
                      'en el orden de la escalera (escalera.max_variantes del perfil).')
    return todas[:p.max_variantes], avisos


# --------------------------------------------------------------------------- criterio
def cumple(sin: Mapping[str, Any], con: Mapping[str, Any], barras_cargas: Sequence[str],
           p: Parametros) -> tuple[bool, list[str]]:
    """Si un flujo con la variante cumple (RF-50): converge, cada carga nueva con su tensión
    y nada peor que en «Sin proyecto» con la misma demanda.

    ``sin`` y ``con``: ``converge``, ``u`` (barra → p.u.) y ``carga`` (elemento → %).
    """
    if not con.get('converge'):
        return False, ['no converge']
    motivos = []
    # 087:RF-42: ninguna obra deja una parte de la red separada o aislada (usuario, 2026-11-04: «no debe haber
    # separaciones o aislados»); solo cuentan las que no lo estaban ya sin la obra.
    if 'aisladas' in con and 'aisladas' in sin:
        nuevas = sorted(set(con['aisladas']) - set(sin['aisladas']))
        if nuevas:
            motivos.append(f"{len(nuevas)} barra(s) de media quedan aisladas, sin servicio: {', '.join(nuevas[:5])}")
    lo, hi = p.tension_min_pu, p.tension_max_pu
    u_con, u_sin = con.get('u') or {}, sin.get('u') or {}
    for b in barras_cargas:
        u = u_con.get(b)
        if u is None or not lo <= u <= hi:
            motivos.append(f'la carga nueva en {b} queda a {u if u is not None else "?"} p.u.')
    for b, u in u_con.items():
        s = u_sin.get(b)
        if s is None or b in barras_cargas:
            continue
        if lo <= s <= hi and not lo <= u <= hi:
            motivos.append(f'{b} sale de los límites: {s:.3f} → {u:.3f} p.u.')
        elif s < lo and u < s - p.tolerancia_pu:
            motivos.append(f'{b} baja más: {s:.3f} → {u:.3f} p.u.')
        elif s > hi and u > s + p.tolerancia_pu:
            motivos.append(f'{b} sube más: {s:.3f} → {u:.3f} p.u.')
    lim = p.cargabilidad_max_pct
    c_sin = sin.get('carga') or {}
    for e, c in (con.get('carga') or {}).items():
        s = c_sin.get(e)
        if s is None or s <= lim:
            if c > lim:
                motivos.append(f'{e} pasa al {c:.0f} %')
        elif c > s + p.tolerancia_carga_pct:
            motivos.append(f'{e} se carga más: {s:.0f} → {c:.0f} %')
    return not motivos, motivos[:5]


def hace_falta_seguir(fraccion: float, medidos: int, total: int, p: Parametros) -> bool:
    """042:RF-87: si la primera etapa queda cerca del criterio; lejos de él, los demás no cambiarían la decisión."""
    return medidos < total and p.sorteos_decide_no <= fraccion < p.sorteos_decide_si


def cumple_en_valle(sin: Mapping[str, Any], con: Mapping[str, Any], barras_cargas: Sequence[str],
                    p: Parametros) -> tuple[bool, list[str]]:
    """042:RF-85: como :func:`cumple`, pero subir por milésimas sobre el máximo en valle no es culpa de la obra.

    Solo por arriba y solo fuera de las barras de las cargas nuevas: una carga nueva tiene que quedar en límites.
    """
    hi, cargas, u_sin = p.tension_max_pu, set(barras_cargas), sin.get('u') or {}
    u_con = dict(con.get('u') or {})
    for b, u in u_con.items():
        s = u_sin.get(b)
        if b not in cargas and s is not None and u is not None and p.tension_min_pu <= s <= hi and hi < u <= s + p.tolerancia_pu:
            u_con[b] = hi
    return cumple(sin, {**con, 'u': u_con}, barras_cargas, p)


# --------------------------------------------------------------------------- sorteos
def sorteos(curva: Sequence[tuple[Any, Mapping[str, float]]], maximas: Mapping[str, float],
            n: int, semilla: int) -> list[dict[str, Any]]:
    """``n`` instantes de la curva de cabecera del año, con reemplazo, y el factor de cada
    alimentador: su potencia en ese instante entre su máxima (RF-51). Un instante común a
    todos los alimentadores del proyecto (021:RF-50); con la misma semilla, lo mismo (RF-58).
    """
    puntos = [(t, {f: float(kw) / float(maximas[f]) for f, kw in por.items()
                   if f in maximas and maximas[f] and kw is not None and math.isfinite(float(kw))})
              for t, por in curva]
    puntos = [(t, fs) for t, fs in puntos if set(fs) == set(maximas)]
    if not puntos:
        raise EscaleraError('la curva de cabecera del año no tiene ningún instante con todos los '
                            'alimentadores medidos: no se puede sortear (025:RF-51)')
    rng = random.Random(semilla)
    return [{'instante': str(t), 'factores': fs} for t, fs in rng.choices(puntos, k=int(n))]


def sorteos_o_maxima(curva: Sequence[tuple[Any, Mapping[str, float]]], maximas: Mapping[str, float],
                     n: int, semilla: int) -> tuple[list[dict[str, Any]], list[str]]:
    """042:RF-42: los sorteos de la curva; sin ningún instante con todos medidos, solo la máxima, y se dice."""
    try:
        return sorteos(curva, maximas, n, semilla), []
    except EscaleraError as exc:
        return [{'instante': 'máxima', 'factores': {}}], [f'{exc}: las obras se evalúan solo en la máxima (042:RF-42).']


# --------------------------------------------------------------------------- costo y elección
def _cantidad_en(unidad: str, cantidad: float, escalon: str) -> float:
    u = (unidad or '').strip().lower()
    if escalon in ('terna', 'seccion'):
        if u in ('m', 'metro', 'metros', 'ml'):
            return cantidad * 1000
        return cantidad                                                  # km, o sin unidad
    return cantidad


def costo(v: Variante, costos_alternativa: Mapping[str, Mapping[str, Any]], p: Parametros, *,
          perdidas_kw: float | None, factor_perdidas: float | None) -> dict[str, Any]:
    """Inversión con los costos unitarios del CAPEX y costo anual del art. 14 (RF-53)."""
    ci, avisos = 0.0, []
    for escalon, cantidad in v.cantidades.items():
        alt = ALTERNATIVA[escalon]
        c = costos_alternativa.get(alt)
        if not c or not c.get('costo_unitario'):
            raise EscaleraError(f'el libro CAPEX no tiene costo de «{alt}» para {escalon} (025:RF-57)')
        ci += _cantidad_en(c.get('unidad') or '', cantidad, escalon) * float(c['costo_unitario'])
    coym = ci * p.coym_pct_anual / 100 if p.coym_pct_anual is not None else None
    # Energía perdida en el año (kW de la máxima por el factor de pérdidas) a su precio, y la
    # potencia de la máxima a su precio por mes (precios en barra del perfil).
    cp = (perdidas_kw * factor_perdidas * HORAS_ANIO * p.precio_perdidas_kwh
          + perdidas_kw * 12 * (p.precio_perdidas_kw_mes or 0.0)
          if None not in (perdidas_kw, factor_perdidas, p.precio_perdidas_kwh) else None)
    if coym is None:
        avisos.append('sin COyM (escalera.coym_pct_anual del perfil)')
    if cp is None:
        avisos.append('sin costo de pérdidas (escalera.precio_perdidas_kwh del perfil o factor de pérdidas)')
    out = costo_anual(ci, coym, cp, tasa=p.tasa, vida=p.vida)
    return {**out, 'inversion': ci, 'avisos': avisos}


def plan_de_horizonte(alimentador: str, tasa: float | None, p: Parametros) -> dict[str, Any]:
    """042:RF-73, RF-74: los años que se miden y el factor de cada uno, del horizonte hacia abajo.

    Sin tasa solo hay un factor, sin años que distinguir: un único flujo.
    """
    h = p.horizonte_anios
    if tasa is None or tasa <= 0:
        return {'anios': [h], 'factores': {str(h): {alimentador: p.factor_sin_tasa}}, 'tasa': None}
    anios = sorted({h, max(h // 2, 1), max(h // 4, 1)}, reverse=True)
    return {'anios': anios, 'factores': {str(a): {alimentador: (1.0 + tasa) ** a} for a in anios}, 'tasa': tasa}


def definitiva(con: Mapping[str, Any], p: Parametros) -> tuple[bool, list[str]]:
    """042:RF-74: en absoluto, no respecto de otro caso: a 20 años no importa quién lo causó."""
    if not con.get('converge'):
        return False, ['no converge']
    motivos = [f'{b} a {u:.3f} p.u.' for b, u in sorted((con.get('u') or {}).items(), key=lambda x: x[1] or 0.0)
               if u is not None and u > 0.05 and not p.tension_min_pu <= u <= p.tension_max_pu]
    motivos += [f'{e} al {c:.0f} %' for e, c in (con.get('carga') or {}).items() if c > p.cargabilidad_max_pct]
    return not motivos, motivos[:3]


def alternativas(tabla: Sequence[Mapping[str, Any]], elegida: str | None, p: Parametros) -> list[dict[str, Any]]:
    """Hasta ``escalera.alternativas`` soluciones de obras distintas, de menor a mayor costo anual (042:RF-55, RF-58, RF-105).

    De cada clase de obra, la más barata que cumple con la máxima; la que los sorteos desmienten no es una solución,
    salvo que sea la elegida (063:RF-33). La elegida siempre está, aunque por costo quedase fuera.
    """
    por_clase: dict[frozenset, Mapping[str, Any]] = {}
    for t in tabla:
        if (not t.get('maxima') or t.get('valle') is False or (t.get('costo') or {}).get('costo_anual') is None
                or (t.get('fraccion') is not None and t['fraccion'] < p.cumplimiento and t.get('nombre') != elegida)):
            continue
        clase = frozenset(t.get('escalones') or ())
        if str(t.get('nombre') or '').startswith(PREFIJO_PERFIL):
            clase = clase | {'perfil'}                    # 094:RF-18: la más barata de bancos sigue como alternativa
        actual = por_clase.get(clase)
        if (actual is None or (t.get('nombre') == elegida)
                or (actual.get('nombre') != elegida and t['costo']['costo_anual'] < actual['costo']['costo_anual'])):
            por_clase[clase] = t
    orden = sorted(por_clase.values(), key=lambda t: (t['costo']['costo_anual'], t['nombre']))
    escogidas = orden[:p.alternativas]
    if elegida and not any(t['nombre'] == elegida for t in escogidas):
        escogidas = escogidas[:p.alternativas - 1] + [t for t in orden if t['nombre'] == elegida]

    def _es_definitiva(t):
        return (t.get('horizonte') or {}).get('definitiva') is True

    if not any(_es_definitiva(t) for t in escogidas):                           # 042:RF-93
        definitiva_barata = next((t for t in orden if _es_definitiva(t)), None)
        if definitiva_barata is not None:
            cabe = next((i for i in range(len(escogidas) - 1, -1, -1) if escogidas[i]['nombre'] != elegida), None)
            if len(escogidas) < p.alternativas:
                escogidas.append(definitiva_barata)
            elif cabe is not None:
                escogidas[cabe] = definitiva_barata
            escogidas.sort(key=lambda t: (t['costo']['costo_anual'], t['nombre']))
    return [{'numero': i, 'nombre': t['nombre'], 'escalones': list(t.get('escalones') or ()),
             'inversion': t['costo'].get('inversion'), 'costo_anual': t['costo']['costo_anual'],
             'perdidas_kw': t.get('perdidas_kw'), 'fraccion': t.get('fraccion'), 'valle': t.get('valle'),
             # 042:RF-75: sin medir, ninguna de las dos claves dice nada.
             'definitiva': (t.get('horizonte') or {}).get('definitiva'),
             'aguanta_anios': (t.get('horizonte') or {}).get('aguanta_anios'),
             'motivos_horizonte': (t.get('horizonte') or {}).get('motivos') or [],
             # 042:RF-72: solo donde se dimensionó con él.
             'factor': p.factor_sin_tasa if 'regulador' in (t.get('escalones') or ()) or 'elevador' in t['nombre'] else None,
             'elegida': t['nombre'] == elegida} for i, t in enumerate(escogidas, 1)]


def elegir(evaluadas: Sequence[Mapping[str, Any]], p: Parametros) -> dict[str, Any]:
    """La de menor costo anual entre las que cumplen con la máxima y en la fracción de sorteos
    del perfil (RF-52b, RF-53); si ninguna, la que más se acerca, sin aplicarla (RF-56).

    Cada evaluada: ``nombre``, ``maxima`` (cumple con la máxima), ``fraccion`` (de sorteos que
    cumplen; ``None`` sin sortear), ``costo`` (de :func:`costo`) y ``motivos``.
    """
    tabla = []
    for e in evaluadas:
        # 073:RF-17, RF-18: en valle se cumple o no; la fracción de sorteos no lo compensa. Sin valle
        # medido (``None``) no se bloquea, y queda dicho (RF-24).
        en_valle = e.get('valle')
        cumple_tec = bool(e.get('maxima')) and (e.get('fraccion') or 0) >= p.cumplimiento and en_valle is not False
        con_costo = (e.get('costo') or {}).get('costo_anual') is not None
        factible = cumple_tec and con_costo
        if e.get('maxima') and en_valle is False:
            motivo = ('cumple con la máxima; en valle no: ' + '; '.join(e.get('valle_motivos') or [])
                      + ' (073:RF-17)')
        elif factible:
            # 073:RF-40: bancos y proyectos: toda obra que se vaya a implementar.
            motivo = 'no comprobado en valle' if en_valle is None and e.get('escalones') else ''
        elif cumple_tec:
            motivo = 'cumple, pero sin costo: ' + str(e.get('sin_costo') or 'falta su costo unitario')
        elif e.get('maxima') and e.get('fraccion') is None:
            motivo = 'cumple con la máxima; ' + str(e.get('sin_sortear') or 'no se sorteó')    # RF-71
        elif not e.get('maxima'):
            motivo = 'no cumple con la máxima: ' + '; '.join(e.get('motivos') or [])
        else:
            motivo = (f"cumple en el {100 * (e.get('fraccion') or 0):.0f} % de los sorteos "
                      f"(pide {100 * p.cumplimiento:.0f} %)")
        tabla.append({**e, 'factible': factible, 'motivo': motivo})
    factibles = [t for t in tabla if t['factible']]
    if factibles:
        # 042:RF-56: la de menor costo anual. 063:RF-22 sigue en los bancos: en SM218 (2026-11-01) 128 m de
        # conductor salían más baratos, y el usuario pide los bancos si ya bastan.
        mejor = min(factibles, key=lambda t: (grupo_economico(t.get('escalones')), t['costo']['costo_anual'],
                                              t['nombre']))
        # 094:RF-18: los bancos ubicados según el perfil mandan si cumplen, aunque otra cueste menos. AL209
        # (2026-11-06): entre 2 bancos (lo más barato para 0,95 p.u.) y los 4 del perfil (~0,977 p.u.), el usuario
        # eligió los del perfil; la más barata queda como alternativa.
        del_perfil = [t for t in factibles if str(t['nombre']).startswith(PREFIJO_PERFIL)]
        if del_perfil:
            mejor = min(del_perfil, key=lambda t: (t['costo']['costo_anual'], t['nombre']))
        for t in factibles:
            if t is mejor:
                continue
            if grupo_economico(t.get('escalones')) > grupo_economico(mejor.get('escalones')):
                t['motivo'] = f"no hace falta: «{mejor['nombre']}» ya cumple en un escalón anterior"
            else:
                t['motivo'] = (f"cuesta más al año: {t['costo']['costo_anual']:,.0f} frente a "
                               f"{mejor['costo']['costo_anual']:,.0f}")
        return {'elegida': mejor['nombre'], 'mas_cercana': None, 'tabla': tabla, **_marcas_de_valle(mejor, tabla),
                'alternativas': alternativas(tabla, mejor['nombre'], p)}
    # 063:RF-33: si alguna cumple con la máxima en DIgSILENT y tiene costo, se elige la primera por
    # el orden de prioridad aunque los sorteos no la confirmen, y se avisa para revisarlos; no se
    # pasa a otras obras ni a la SET nueva. SM218 (2026-11-01): banco 450 kvar + AA 120 mm² cumplía
    # con la máxima y los sorteos daban 94,5 % por un defecto de la evaluación, y el flujo saltaba
    # a la SET nueva.
    # 073:RF-18: aquí no entra lo que no cumple en valle.
    # 087:RF-49: solo con los sorteos cerca del criterio, como el 94,5 % de SM218. Pisco (2026-11-04): la sección de
    # CHI201 cumplía con la máxima del instante coincidente y solo en el 60 % de los sorteos, porque su demanda propia
    # llega a 2,9 veces ese punto; la regla la daba por solución y no se probaba nada más. Usuario: «acotar la regla».
    con_maxima = [t for t in tabla if t.get('maxima') and t.get('valle') is not False
                  and (t.get('costo') or {}).get('costo_anual') is not None
                  and (t.get('fraccion') is None or t['fraccion'] >= p.sorteos_decide_no)
                  and not t.get('error')]                                      # 087:RF-51: un error no es «sin sortear»
    if con_maxima:
        mejor = min(con_maxima, key=lambda t: (grupo_economico(t.get('escalones')), t['costo']['costo_anual'],
                                               t['nombre']))
        mejor['motivo'] = (f"cumple con la máxima en DIgSILENT; los sorteos dieron "
                           f"{100 * (mejor.get('fraccion') or 0):.1f} % (pide {100 * p.cumplimiento:.0f} %): "
                           'se elige y hay que revisar los sorteos (063:RF-33)')
        return {'elegida': mejor['nombre'], 'mas_cercana': None, 'tabla': tabla, 'sin_confirmar_sorteos': True,
                **_marcas_de_valle(mejor, tabla), 'alternativas': alternativas(tabla, mejor['nombre'], p)}
    cercana = max(tabla, key=lambda t: (bool(t.get('maxima')) and t.get('valle') is not False, t.get('fraccion') or 0),
                  default=None)
    return {'elegida': None, 'mas_cercana': cercana['nombre'] if cercana else None, 'tabla': tabla,
            **_marcas_de_valle(None, tabla), 'alternativas': []}


def _marcas_de_valle(mejor: Mapping[str, Any] | None, tabla: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Lo que la elección dice del valle: la elegida sin comprobar (073:RF-24) y que el valle no
    aguanta los bancos que pide la máxima, con el hueco de los bancos por pasos (RF-20, RF-27)."""
    out: dict[str, Any] = {}
    if mejor is not None and mejor.get('valle') is None and mejor.get('escalones'):
        out['sin_comprobar_valle'] = True
    solo_bancos = [t for t in tabla if tuple(t.get('escalones') or ()) == ('bancos',)]
    if not any(t.get('factible') for t in solo_bancos):
        rechazadas = [t['nombre'] for t in solo_bancos if t.get('maxima') and t.get('valle') is False]
        if rechazadas:
            out['aviso_valle'] = (f"la máxima pide {', '.join(rechazadas)} y el valle no lo aguanta: sigue la escalera "
                                  '(073:RF-20). La obra de banco por pasos existe (011:RF-71, RF-72), pero esta '
                                  'escalera no la genera ni el oráculo la mide (073:RF-27).')
    return out
