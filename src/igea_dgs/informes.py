"""Informes de estudio eléctrico y de factibilidad de suministro (spec 017).

El resultado de las specs 011, 014 y 015 se quedaba en DIgSILENT y en el JSON de cada
estudio, y el ingeniero lo copiaba a mano a un Word con el formato de la empresa. Este
módulo es la parte del informe que no necesita DIgSILENT: qué se usa del perfil de
empresa, los cálculos y la redacción. El guion ``tools/informes_pf.py`` mide y exporta
las imágenes, y ``informe_docx.py`` escribe el Word.

Nada se supone (P13): sin modelo no hay informe de ese tipo, y sin banda de tensión o
umbral de cargabilidad se piden en el formulario. Los ±5 % por defecto de los estudios
de la 011 no valen aquí, porque el informe concluye con ellos ante el regulador.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .estudios_pf import EstudiosError, Limites

#: Los dos tipos de informe (RF-1, RF-1b).
TIPOS = ('factibilidad', 'estudio')
#: Clave del perfil con la configuración de los informes.
CLAVE_PERFIL = 'informes'
#: Clave del perfil con la banda y el umbral, la misma de los estudios de la 011.
CLAVE_LIMITES = 'estudios'
_LIMITES = ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct')
_BANDAS = ('bandas_tension_pct', 'bandas_cargabilidad_pct')


class InformeError(ValueError):
    """El informe no se puede generar con lo que hay; el mensaje dice qué falta."""


def _bandas(valor: Any, clave: str) -> tuple[float, ...]:
    """Límites de las bandas de un coloreado: números positivos y crecientes."""
    if (not isinstance(valor, (list, tuple)) or not valor
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   or v <= 0 for v in valor)):
        raise InformeError(f'{CLAVE_PERFIL}.{clave} tiene que ser una lista de números positivos: {valor!r}.')
    if any(b <= a for a, b in zip(valor, valor[1:])):
        raise InformeError(f'{CLAVE_PERFIL}.{clave} tiene que ir de menor a mayor: {valor!r}.')
    return tuple(float(v) for v in valor)


@dataclass(frozen=True)
class ConfigInforme:
    """Lo que el informe toma del perfil de empresa (RF-4, RF-13, RF-115).

    Un campo en None es que el perfil no lo da; :meth:`faltan` dice cuáles impiden
    generar cada tipo.
    """

    modelos: Mapping[str, Path | None] = field(default_factory=dict)
    limites: Limites | None = None
    bandas_tension_pct: tuple[float, ...] | None = None
    bandas_cargabilidad_pct: tuple[float, ...] | None = None
    #: Proyecto de DIgSILENT de transmisión, para el transformador de la SET (RF-65).
    proyecto_transmision: str | None = None
    #: Rótulos de las celdas de la cabecera del modelo donde van el n.º y la referencia;
    #: sin ellos la cabecera queda como en el modelo.
    rotulos_cabecera: Mapping[str, str] = field(default_factory=dict)
    #: Norma de calidad y regulador que citan los textos («NTCSE», «Osinergmin»); sin
    #: ellos, los textos no nombran ninguno.
    norma: str | None = None
    regulador: str | None = None
    #: Valores de banda y umbral que el perfil da a medias: el formulario los completa.
    limites_parciales: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def de_perfil(cls, datos: Mapping[str, Any], raiz: Path) -> 'ConfigInforme':
        """La configuración de un perfil ya leído (``perfil_empresa.datos_perfil``).

        Las rutas relativas de los modelos son relativas a ``raiz``, la carpeta del
        proyecto, como el resto de rutas del perfil.
        """
        seccion = datos.get(CLAVE_PERFIL) or {}
        if not isinstance(seccion, Mapping):
            raise InformeError(f'La clave {CLAVE_PERFIL!r} del perfil tiene que ser un objeto.')
        modelos: dict[str, Path | None] = {}
        for tipo in TIPOS:
            valor = seccion.get(f'modelo_{tipo}')
            if valor in (None, ''):
                modelos[tipo] = None
            elif not isinstance(valor, str):
                raise InformeError(f'{CLAVE_PERFIL}.modelo_{tipo} tiene que ser una ruta: {valor!r}.')
            else:
                ruta = Path(valor)
                modelos[tipo] = ruta if ruta.is_absolute() else Path(raiz) / ruta
        tension, carga = (_bandas(seccion[c], c) if seccion.get(c) is not None else None for c in _BANDAS)
        proyecto = seccion.get('proyecto_transmision')
        if proyecto is not None and (not isinstance(proyecto, str) or not proyecto.strip()):
            raise InformeError(f'{CLAVE_PERFIL}.proyecto_transmision tiene que ser un nombre: {proyecto!r}.')
        rotulos = seccion.get('cabecera') or {}
        if (not isinstance(rotulos, Mapping) or set(rotulos) - {'numero', 'referencia'}
                or not all(isinstance(v, str) and v.strip() for v in rotulos.values())):
            raise InformeError(f'{CLAVE_PERFIL}.cabecera tiene que dar los rótulos «numero» y '
                               f'«referencia» de la cabecera del modelo: {rotulos!r}.')
        textos = {}
        for clave in ('norma', 'regulador'):
            valor = seccion.get(clave)
            if valor is not None and (not isinstance(valor, str) or not valor.strip()):
                raise InformeError(f'{CLAVE_PERFIL}.{clave} tiene que ser un texto: {valor!r}.')
            textos[clave] = valor or None
        limites_perfil = datos.get(CLAVE_LIMITES) or {}
        parciales = {k: limites_perfil[k] for k in _LIMITES
                     if isinstance(limites_perfil, Mapping) and limites_perfil.get(k) is not None}
        config = cls(modelos=modelos, proyecto_transmision=proyecto or None, rotulos_cabecera=dict(rotulos), **textos,
                     limites_parciales=parciales, bandas_tension_pct=tension,
                     bandas_cargabilidad_pct=carga)
        return config.con_limites() if len(parciales) == len(_LIMITES) else config

    def con_limites(self, **operador: float | None) -> 'ConfigInforme':
        """La banda y el umbral, con lo que escriba el operador sobre lo del perfil (RF-14).

        Mientras falte uno de los tres, ``limites`` sigue en None: no se completa con un
        valor por defecto.
        """
        valores = {**self.limites_parciales, **{k: v for k, v in operador.items() if v is not None}}
        desconocidos = set(valores) - set(_LIMITES)
        if desconocidos:
            raise InformeError(f'Límites desconocidos: {", ".join(sorted(desconocidos))}.')
        if len(valores) < len(_LIMITES):
            return replace(self, limites=None, limites_parciales=valores)
        try:
            limites = Limites(**valores, origen='operador' if operador else 'perfil')
        except (EstudiosError, TypeError) as exc:
            raise InformeError(str(exc)) from exc
        return replace(self, limites=limites, limites_parciales=valores)

    def faltan(self, tipo: str) -> list[str]:
        """Claves del perfil que faltan para generar un informe de ``tipo`` (RF-5, RF-14).

        Las de banda y umbral se pueden dar en el formulario; el modelo y las bandas de
        coloreado, solo en el perfil. El proyecto de transmisión no está: sin él, la
        sección del transformador queda señalada y sale el resto (RF-70).
        """
        if tipo not in TIPOS:
            raise InformeError(f'Tipo de informe desconocido: {tipo!r} (son {", ".join(TIPOS)}).')
        faltan = []
        if self.modelos.get(tipo) is None:
            faltan.append(f'{CLAVE_PERFIL}.modelo_{tipo}')
        faltan += [f'{CLAVE_PERFIL}.{c}' for c in _BANDAS if getattr(self, c) is None]
        if self.limites is None:
            faltan += [f'{CLAVE_LIMITES}.{k}' for k in _LIMITES if k not in self.limites_parciales]
        return faltan

    def modelo(self, tipo: str) -> Path:
        """El ``.docx`` modelo de ``tipo``; error con la clave que falta si no lo hay."""
        faltan = self.faltan(tipo)
        if faltan:
            raise InformeError(f'No se puede generar el informe de {tipo}: falta en el perfil de '
                               f'empresa {", ".join(faltan)}.')
        ruta = self.modelos[tipo]
        if ruta is None or not ruta.is_file():
            raise InformeError(f'No existe el modelo del informe de {tipo}: {ruta} '
                               f'({CLAVE_PERFIL}.modelo_{tipo} del perfil de empresa).')
        return ruta


# --------------------------------------------------------------------------- casos
#: Fases del flujo desequilibrado; en el equilibrado hay una sola tensión «trifásica».
FASES = ('A', 'B', 'C')
TRIFASICA = 'trifásica'


@dataclass(frozen=True)
class Potencia:
    """kW y kvar de la fuente o de las pérdidas; kVA y factor de potencia se derivan (RF-15)."""

    kw: float
    kvar: float

    @property
    def kva(self) -> float:
        return math.hypot(self.kw, self.kvar)

    @property
    def fp_pct(self) -> float | None:
        """Factor de potencia en %; None sin potencia aparente."""
        return 100.0 * abs(self.kw) / self.kva if self.kva else None


@dataclass(frozen=True)
class Extremo:
    """Un valor extremo y dónde se da: la tensión mínima en su nodo, la cargabilidad en su tramo."""

    valor: float
    donde: str


@dataclass(frozen=True)
class Caso:
    """Lo que mide el guion en un caso o una etapa: el contrato JSON con ``tools/informes_pf.py``.

    ``tension_min`` va por fase (A, B y C) en el flujo desequilibrado y con una sola
    clave «trifásica» en el equilibrado (RF-17, RF-18). Sin convergencia no hay valores
    (RF-24).
    """

    nombre: str
    converge: bool
    fuente: Potencia | None = None
    perdidas: Potencia | None = None
    tension_min: Mapping[str, Extremo] = field(default_factory=dict)
    tension_max: Extremo | None = None
    nodos_fuera: int = 0
    cargabilidad_max: Extremo | None = None
    tramos_sobre: int = 0
    #: El transformador más cargado: en CA101 (2026-10-15) era TR_SE20701 al 518 % y el
    #: informe lo llamaba «tramo» y «conductor». Va aparte de los tramos.
    trafo_max: Extremo | None = None

    def __post_init__(self) -> None:
        if self.converge and self.fuente is None:
            raise InformeError(f'El caso {self.nombre!r} convergió pero no trae la potencia de la fuente.')
        fases = set(self.tension_min)
        if fases and fases not in ({TRIFASICA}, set(FASES)):
            raise InformeError(f'Tensión mínima del caso {self.nombre!r} con fases {sorted(fases)}: '
                               f'tienen que ser A, B y C, o solo «{TRIFASICA}».')

    @property
    def desequilibrado(self) -> bool:
        return set(self.tension_min) == set(FASES)

    @property
    def minima(self) -> Extremo | None:
        """La menor de las fases, la que se compara con la banda (RF-16)."""
        return min(self.tension_min.values(), key=lambda e: e.valor) if self.tension_min else None

    @classmethod
    def desde_json(cls, datos: Mapping[str, Any]) -> 'Caso':
        def potencia(d):
            return Potencia(float(d['kw']), float(d['kvar'])) if d else None

        def extremo(d):
            return Extremo(float(d['valor']), str(d['donde'])) if d else None

        try:
            return cls(nombre=str(datos['nombre']), converge=bool(datos['converge']),
                       fuente=potencia(datos.get('fuente')), perdidas=potencia(datos.get('perdidas')),
                       tension_min={str(k): extremo(v) for k, v in (datos.get('tension_min') or {}).items()},
                       tension_max=extremo(datos.get('tension_max')),
                       nodos_fuera=int(datos.get('nodos_fuera') or 0),
                       cargabilidad_max=extremo(datos.get('cargabilidad_max')),
                       tramos_sobre=int(datos.get('tramos_sobre') or 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise InformeError(f'Caso mal formado en el JSON del guion: {exc!r}') from exc

    @classmethod
    def desde_medida(cls, nombre: str, medida: Mapping[str, Any], limites: Limites) -> 'Caso':
        """El caso con lo que mide el paso de estudios de la web en un alimentador (spec 011).

        El informe se arma con lo que guardan los estudios al ejecutar «Sin proyecto» y
        «Con proyecto» desde la web, no con una ejecución aparte de DIgSILENT (el usuario,
        2026-10-15). Nodos fuera de banda y tramos sobre el umbral se cuentan aquí con los
        límites del informe.
        """
        if not medida.get('converge'):
            return cls(nombre, False)
        fuente = (Potencia(float(medida['cabecera_kw']), float(medida['cabecera_kvar']))
                  if medida.get('cabecera_kw') is not None and medida.get('cabecera_kvar') is not None
                  else None)
        perdidas = (Potencia(float(medida['perdidas_kw']), float(medida['perdidas_kvar']))
                    if medida.get('perdidas_kw') is not None and medida.get('perdidas_kvar') is not None
                    else None)
        fases = medida.get('vm_min_fases')
        if fases:
            tension_min = {f: Extremo(float(fases[f][0]), str(fases[f][1])) for f in FASES}
        elif medida.get('vm_min') is not None:
            tension_min = {TRIFASICA: Extremo(float(medida['vm_min']), str(medida['vm_min_barra']))}
        else:
            tension_min = {}
        barras = medida.get('barras') or []
        lineas = [e for e in (medida.get('elementos') or []) if e[1] == 'ElmLne']
        trafos = [e for e in (medida.get('elementos') or []) if e[1] == 'ElmTr2']
        if lineas:
            peor_linea = max(lineas, key=lambda e: e[2])
            carga_max = Extremo(float(peor_linea[2]), str(peor_linea[0]))
        elif medida.get('cargabilidad_max') is not None and not trafos:
            carga_max = Extremo(float(medida['cargabilidad_max']), str(medida['mas_cargado']))
        else:
            carga_max = None
        peor_trafo = max(trafos, key=lambda e: e[2]) if trafos else None
        return cls(
            nombre, True, fuente=fuente, perdidas=perdidas, tension_min=tension_min,
            tension_max=(Extremo(float(medida['vm_max']), str(medida['vm_max_barra']))
                         if medida.get('vm_max') is not None else None),
            nodos_fuera=sum(1 for _, u in barras
                            if u is not None and not limites.tension_min_pu <= u <= limites.tension_max_pu),
            cargabilidad_max=carga_max,
            tramos_sobre=sum(1 for _, _, c in lineas if c > limites.cargabilidad_max_pct),
            trafo_max=Extremo(float(peor_trafo[2]), str(peor_trafo[0])) if peor_trafo else None)

    def cumple_tension(self, limites: Limites) -> bool:
        if not self.converge or self.nodos_fuera:
            return False
        minima = self.minima
        if minima is not None and minima.valor < limites.tension_min_pu:
            return False
        return self.tension_max is None or self.tension_max.valor <= limites.tension_max_pu

    def cumple_cargabilidad(self, limites: Limites) -> bool:
        if not self.converge or self.tramos_sobre:
            return False
        if self.trafo_max is not None and self.trafo_max.valor > limites.cargabilidad_max_pct:
            return False
        carga = self.cargabilidad_max
        return carga is None or carga.valor <= limites.cargabilidad_max_pct

    def cumple(self, limites: Limites) -> bool:
        """Banda de tensión y umbral de cargabilidad (RF-31, RF-43). Sin flujo no cumple."""
        return self.cumple_tension(limites) and self.cumple_cargabilidad(limites)


# --------------------------------------------------------------------------- etapas
#: Etapas de obras del informe de estudio, en el orden de RF-32.
ETAPAS = ('bancos_existentes', 'bancos_nuevos', 'reguladores', 'conductor', 'migracion')
NOMBRE_ETAPA = {
    'bancos_existentes': 'Bancos de condensadores existentes',
    'bancos_nuevos': 'Bancos de condensadores propuestos',
    'reguladores': 'Reguladores de tensión',
    'conductor': 'Cambio de conductor de la troncal',
    'migracion': 'Migración a otra tensión',
}


@dataclass(frozen=True)
class Etapa:
    """Una etapa evaluada, sumada a las anteriores (RF-32), o el motivo de no evaluarla."""

    clave: str
    caso: Caso | None = None
    motivo: str | None = None
    obras: tuple[Mapping[str, Any], ...] = ()
    anio: int | None = None

    def __post_init__(self) -> None:
        if self.clave not in ETAPAS:
            raise InformeError(f'Etapa desconocida: {self.clave!r} (son {", ".join(ETAPAS)}).')
        if (self.caso is None) == (self.motivo is None):
            raise InformeError(f'La etapa {self.clave!r} tiene que traer su caso o el motivo de no evaluarla.')

    @property
    def evaluada(self) -> bool:
        return self.caso is not None


def seguir_evaluando(actual: Caso, etapas: list[Etapa], limites: Limites, evaluar_todas: bool) -> bool:
    """Si el guion pasa a la etapa siguiente (RF-31, RF-33).

    Con el estado actual en regla no se evalúa ninguna; con una etapa que ya cumple, se
    para, salvo que el operador pida evaluarlas todas.
    """
    if actual.cumple(limites):
        return False
    if evaluar_todas:
        return True
    return not any(e.caso is not None and e.caso.cumple(limites) for e in etapas)


@dataclass(frozen=True)
class Recomendacion:
    """Qué dice el informe de estudio de las obras (RF-31, RF-33, RF-34)."""

    actual_cumple: bool
    etapa: Etapa | None
    #: Por etapa evaluada, si cumple (RF-43).
    cumplen: Mapping[str, bool]


def etapa_recomendada(actual: Caso, etapas: list[Etapa], limites: Limites) -> Recomendacion:
    """La primera etapa, en el orden de RF-32, que hace cumplir banda y umbral; o ninguna."""
    cumplen = {e.clave: e.caso.cumple(limites) for e in etapas if e.caso is not None}
    primera = next((e for e in sorted(etapas, key=lambda e: ETAPAS.index(e.clave))
                    if cumplen.get(e.clave)), None)
    return Recomendacion(actual.cumple(limites), primera, cumplen)


# --------------------------------------------------------------------------- pérdidas
#: Horas del año con que el libro de pérdidas de la empresa anualiza (RF-54, RF-56).
HORAS_ANIO = 8760


def factor_de_carga(curva: list[tuple[Any, float, Any]]) -> float | None:
    """Energía entre máxima por horas del periodo, con la curva de cabecera del mes (RF-60).

    Con un registro cada intervalo fijo, eso es la media de la curva entre su máxima. La
    curva es la de ``demanda_medida.curva_de_registros``, ya recortada al mes. Sin
    registros, o con máxima no positiva, None: el formulario lo pide (RF-61).
    """
    potencias = [p for _, p, *_ in curva if p is not None and math.isfinite(p)]
    if not potencias or max(potencias) <= 0:
        return None
    return sum(potencias) / len(potencias) / max(potencias)


def factor_de_perdidas(fc: float) -> float:
    """0,3·FC + 0,7·FC², la fórmula del libro de pérdidas de la empresa (RF-55)."""
    if not 0 < fc <= 1:
        raise InformeError(f'El factor de carga tiene que estar entre 0 y 1: {fc}.')
    return 0.3 * fc + 0.7 * fc * fc


@dataclass(frozen=True)
class PerdidasAnuales:
    """RF-54 a RF-58 de un estado. Lo que falta del libro de la empresa queda en None (RF-64)."""

    maxima_kw: float
    energia_kwh: float
    factor_perdidas: float
    perdidas_kwh: float
    perdidas_pct: float
    no_reconocida_soles: float | None


def perdida_no_reconocida(perdidas_kwh: float, energia_kwh: float, reconocido_kwh_pct: float,
                          precio: float) -> float:
    """(pérdidas − % reconocido en energía × energía) × precio de compra, al año (RF-58).

    Negativa cuando la red pierde menos de lo que el regulador reconoce.
    """
    return (perdidas_kwh - reconocido_kwh_pct / 100.0 * energia_kwh) * precio


def perdidas_anuales(maxima_kw: float, perdidas_kw: float, fc: float,
                     reconocido_kwh_pct: float | None = None, precio: float | None = None) -> PerdidasAnuales:
    """Las pérdidas de un estado con la máxima y las pérdidas del flujo (RF-54 a RF-58)."""
    if maxima_kw <= 0:
        raise InformeError(f'La máxima demanda desde la fuente tiene que ser positiva: {maxima_kw} kW.')
    fp = factor_de_perdidas(fc)
    energia = maxima_kw * HORAS_ANIO * fc
    perdidas = perdidas_kw * HORAS_ANIO * fp
    no_reconocida = (perdida_no_reconocida(perdidas, energia, reconocido_kwh_pct, precio)
                     if reconocido_kwh_pct is not None and precio is not None else None)
    return PerdidasAnuales(maxima_kw, energia, fp, perdidas, 100.0 * perdidas / energia, no_reconocida)


# --------------------------------------------------------------------------- factibilidad
@dataclass(frozen=True)
class Devanado:
    """Cargabilidad de un devanado del transformador de la SET, sin y con proyecto (RF-66)."""

    kv: float
    sin_pct: float | None
    con_pct: float | None


@dataclass(frozen=True)
class Veredicto:
    factible: bool
    #: Cada límite superado: qué, dónde y en cuánto (RF-72).
    excesos: tuple[str, ...]


def veredicto_factibilidad(proyectado: Caso, devanados: list[Devanado] | None,
                           limites: Limites) -> Veredicto:
    """Factible solo si el proyectado cumple banda y umbral y la SET no pasa del 100 % (RF-71).

    Sin datos del transformador (RF-70) no se puede afirmar que la SET la admite, así
    que no es factible y se dice por qué.
    """
    excesos = []
    if not proyectado.converge:
        excesos.append('el flujo de carga del estado proyectado no converge')
    else:
        minima = proyectado.minima
        if minima is not None and minima.valor < limites.tension_min_pu:
            excesos.append(f'tensión mínima de {_pu(minima.valor)} en {minima.donde}, '
                           f'{_pu(limites.tension_min_pu - minima.valor)} por debajo de '
                           f'{_pu(limites.tension_min_pu)}')
        maxima = proyectado.tension_max
        if maxima is not None and maxima.valor > limites.tension_max_pu:
            excesos.append(f'tensión máxima de {_pu(maxima.valor)} en {maxima.donde}, '
                           f'{_pu(maxima.valor - limites.tension_max_pu)} por encima de '
                           f'{_pu(limites.tension_max_pu)}')
        carga = proyectado.cargabilidad_max
        if carga is not None and carga.valor > limites.cargabilidad_max_pct:
            excesos.append(f'cargabilidad de {numero(carga.valor, 1)} % en {carga.donde}, '
                           f'{numero(carga.valor - limites.cargabilidad_max_pct, 1)} puntos sobre el '
                           f'{_g(limites.cargabilidad_max_pct)} %')
        if proyectado.nodos_fuera and (minima is None or minima.valor >= limites.tension_min_pu):
            excesos.append(f'{proyectado.nodos_fuera} nodos fuera de la banda de tensión')
        if proyectado.tramos_sobre and (carga is None or carga.valor <= limites.cargabilidad_max_pct):
            excesos.append(f'{proyectado.tramos_sobre} tramos sobre el umbral de cargabilidad')
    if not devanados or all(d.con_pct is None for d in devanados):
        excesos.append('no se obtuvo la cargabilidad del transformador de la SET')
    else:
        for d in devanados:
            if d.con_pct is not None and d.con_pct > 100.0:
                excesos.append(f'devanado de {_g(d.kv)} kV del transformador de la SET al '
                               f'{numero(d.con_pct, 2)} %, {numero(d.con_pct - 100, 2)} puntos sobre su capacidad')
    return Veredicto(not excesos, tuple(excesos))



# --------------------------------------------------------------------------- redacción
# Las frases salen de los números y de la banda o el umbral; nada que los resultados no
# digan (RF-20). En EMAPICA el texto decía «el color naranja indica…» aunque la figura
# no estuviera coloreada así: aquí el texto nombra valores, no colores. Y como el Word va
# al destinatario tal cual, nada nombra los casos de DIgSILENT («Sin proyecto», «Con
# proyecto») ni el orden en que se evaluaron las obras: el usuario lo pidió el 2026-10-15,
# «no debe ir ningún paso o algo propio del proyecto o de este conversor».

def numero(v: float, decimales: int) -> str:
    """Con coma decimal, como escribe la empresa en sus informes («22,9 kV»)."""
    return f'{v:.{decimales}f}'.replace('.', ',')


def _pu(v: float) -> str:
    return f'{numero(v, 3)} p.u.'


def _g(v: float) -> str:
    """Sin ceros de más: 300 kvar, 22,9 kV."""
    return f'{v:g}'.replace('.', ',')


def banda_texto(limites: Limites) -> str:
    """La banda como la dice el modelo: «±5 % de la tensión nominal» si es simétrica."""
    abajo, arriba = 1.0 - limites.tension_min_pu, limites.tension_max_pu - 1.0
    if abs(abajo - arriba) < 1e-9 and abajo > 0:
        return f'±{_g(round(abajo * 100, 3))} % de la tensión nominal'
    return f'entre {_pu(limites.tension_min_pu)} y {_pu(limites.tension_max_pu)}'


def _fecha_larga(fecha: date) -> str:
    meses = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
             'septiembre', 'octubre', 'noviembre', 'diciembre')
    return f'{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}'


@dataclass(frozen=True)
class Encabezado:
    """Campos del encabezado que escribe el operador (RF-22, RF-79)."""

    fecha: date
    asunto: str
    destinatario: str
    antecedentes: str = ''
    lugar: str = ''

    @property
    def fecha_texto(self) -> str:
        return f'{self.lugar}, {_fecha_larga(self.fecha)}' if self.lugar else _fecha_larga(self.fecha)


def asunto_propuesto(tipo: str, alimentadores: list[str], cliente: str = '') -> str:
    """El asunto que propone el formulario, editable (RF-80)."""
    lista = ', '.join(alimentadores)
    if tipo == 'factibilidad':
        return f'FACTIBILIDAD Y PUNTO DE DISEÑO{" - " + cliente if cliente else ""} ({lista})'
    return f'ESTUDIO ELÉCTRICO DE LOS ALIMENTADORES {lista}'


def redactar_tension(caso: Caso, limites: Limites, norma: str | None = None) -> str:
    """Análisis de caída de tensión de un estado (RF-20)."""
    if not caso.converge:
        return 'El flujo de carga no converge: no se obtienen resultados de tensión.'
    minima = caso.minima
    if minima is None:
        return 'El flujo de carga no dio la tensión de los nodos.'
    texto = f'La tensión mínima del alimentador es de {_pu(minima.valor)} en el nodo {minima.donde}'
    if caso.desequilibrado:
        texto += ' (fase ' + next(f for f, e in caso.tension_min.items() if e == minima) + ')'
    segun = f', conforme a lo establecido en la {norma}' if norma else ''
    if caso.cumple_tension(limites):
        return (texto + ': la caída de tensión se encuentra dentro de los parámetros permitidos '
                f'({banda_texto(limites)}){segun}.')
    fuera = f'{caso.nodos_fuera} nodos se encuentran' if caso.nodos_fuera else 'hay nodos'
    return (texto + f', y {fuera} fuera de los parámetros permitidos ({banda_texto(limites)})'
            + (f' que establece la {norma}' if norma else '')
            + ': el alimentador presenta problemas de calidad de tensión.')


def redactar_cargabilidad(caso: Caso, limites: Limites) -> str:
    """Análisis de cargabilidad de un estado (RF-20)."""
    if not caso.converge:
        return 'El flujo de carga no converge: no se obtienen resultados de cargabilidad.'
    umbral = f'{_g(limites.cargabilidad_max_pct)} %'
    carga = caso.cargabilidad_max
    if carga is None:
        return 'El flujo de carga no dio la cargabilidad de los tramos.'
    texto = (f'La cargabilidad máxima del conductor es de {numero(carga.valor, 1)} % en el tramo '
             f'{carga.donde}')
    if carga.valor <= limites.cargabilidad_max_pct and not caso.tramos_sobre:
        texto += f', por debajo del {umbral}, dentro de los límites operativos aceptables.'
    else:
        sobre = f'{caso.tramos_sobre} tramos superan' if caso.tramos_sobre else 'hay tramos que superan'
        texto += f', y {sobre} el {umbral}: el alimentador presenta problemas de cargabilidad.'
    trafo = caso.trafo_max
    if trafo is not None and trafo.valor > limites.cargabilidad_max_pct:
        texto += (f' El transformador {trafo.donde} alcanza una cargabilidad de {numero(trafo.valor, 1)} %, '
                  f'por encima del {umbral} de su capacidad.')
    return texto


def describir_obra(obra: Mapping[str, Any]) -> str:
    """Una obra del detalle y de las conclusiones, con lo que pide RF-44."""
    tipo = obra.get('tipo')
    if tipo == 'banco':
        que = ('Poner en servicio el banco de condensadores existente' if obra.get('existente')
               else 'Instalar un banco de condensadores')
        return f'{que} de {_g(obra["kvar"])} kvar en el nodo {obra["nodo"]}.'
    if tipo == 'regulador':
        return f'Instalar un regulador de tensión en el nodo {obra["nodo"]}.'
    if tipo == 'conductor':
        if obra.get('km') is None:
            return f'Renovar la troncal con conductor {obra["conductor"]}.'
        return f'Renovar {numero(obra["km"], 2)} km de la troncal con conductor {obra["conductor"]}.'
    if tipo == 'migracion':
        return (f'Migrar la troncal a {_g(obra["kv"])} kV y acondicionar {obra["transformadores"]} '
                f'transformadores de distribución para operar a {_g(obra["kv"])} kV.')
    return str(obra.get('descripcion') or obra)


#: Etapa del informe (RF-32) de cada clase de obra de la spec 011; las que no son de
#: calidad de tensión (reconectador, terna, enlace) no la cambian.
_ETAPA_DE_CLASE = {'condensador': 'bancos_nuevos', 'regulador': 'reguladores', 'seccion': 'conductor',
                   'tension': 'migracion', 'migracion': 'migracion'}


def obra_para_informe(obra: Mapping[str, Any]) -> dict[str, Any]:
    """Una obra guardada por la web (``obras_pf.Obra.a_dict``) como la describe el informe."""
    clase = obra.get('clase')
    nodo = obra.get('barra') or obra.get('tramo') or obra.get('nodo') or ''
    if clase == 'condensador':
        return {'tipo': 'banco', 'nodo': nodo, 'kvar': float(obra.get('q_kvar') or 0)}
    if clase == 'regulador':
        return {'tipo': 'regulador', 'nodo': nodo}
    if clase == 'seccion':
        tipo = (obra.get('tipo') or {}).get('nombre', '')
        return {'tipo': 'conductor', 'km': obra.get('km'), 'conductor': tipo}
    if clase in ('tension', 'migracion'):
        return {'tipo': 'migracion', 'kv': float(obra.get('kv_destino') or 0),
                'transformadores': obra.get('transformadores', 0)}
    return {'descripcion': f'Obra de {clase} en {nodo or obra.get("alimentador", "")}.'}


def etapa_de_obras(obras: list[Mapping[str, Any]]) -> str | None:
    """La etapa más avanzada (RF-32) entre las obras activas de «Con proyecto»."""
    claves = [_ETAPA_DE_CLASE[o.get('clase')] for o in obras if o.get('clase') in _ETAPA_DE_CLASE]
    return max(claves, key=ETAPAS.index) if claves else None


def obras_a_ejecutar(rec: Recomendacion, etapas: list[Etapa]) -> list[Etapa]:
    """Las etapas cuyas obras se proponen: hasta la recomendada, o todas si ninguna basta."""
    evaluadas = sorted((e for e in etapas if e.evaluada), key=lambda e: ETAPAS.index(e.clave))
    if rec.etapa is None:
        return evaluadas
    return [e for e in evaluadas if ETAPAS.index(e.clave) <= ETAPAS.index(rec.etapa.clave)]


def conclusiones_estudio(alimentadores: list[str], actual: Caso, rec: Recomendacion,
                         etapas: list[Etapa], limites: Limites, norma: str | None = None) -> list[str]:
    """Borrador de conclusiones del informe de estudio, editable en el Word (RF-21).

    Como el modelo: qué hay que hacer para superar la mala calidad, una línea por obra,
    y qué se logra con ellas.
    """
    lista = ', '.join(alimentadores)
    segun = f', conforme a lo establecido en la {norma}' if norma else ''
    if rec.actual_cumple:
        return [f'En el estado actual, el alimentador {lista} se encuentra dentro de los parámetros '
                f'permitidos de tensión ({banda_texto(limites)}){segun} y por debajo del '
                f'{_g(limites.cargabilidad_max_pct)} % de cargabilidad: no se requieren obras de mejora.']
    puntos = [f'En el estado actual, el alimentador {lista} presenta '
              + _incumplimientos(actual, limites) + '.']
    a_ejecutar = obras_a_ejecutar(rec, etapas)
    obras = [describir_obra(o) for e in a_ejecutar for o in e.obras]
    if obras:
        puntos.append(f'Para superar la mala calidad del servicio en el alimentador {lista}, es '
                      'necesario efectuar las siguientes actividades:')
        puntos += obras
    final = a_ejecutar[-1].caso if a_ejecutar else None
    if rec.etapa is not None and final is not None and final.minima is not None:
        puntos.append(f'Con la implementación de estas obras se logrará una tensión mínima de '
                      f'{_pu(final.minima.valor)}, dentro del {banda_texto(limites)}{segun}, '
                      'mejorando la calidad del servicio eléctrico.')
    elif final is not None and final.converge:
        puntos.append('Con las obras evaluadas el alimentador todavía presenta '
                      + _incumplimientos(final, limites) + ': se requieren obras adicionales.')
    elif not a_ejecutar:
        puntos.append('Se requiere evaluar obras de mejora para superar la mala calidad del servicio.')
    else:
        puntos.append('Ninguna de las obras evaluadas permite superar la mala calidad del servicio.')
    return puntos


def _incumplimientos(caso: Caso, limites: Limites) -> str:
    if not caso.converge:
        return 'un flujo de carga que no converge'
    partes = []
    if not caso.cumple_tension(limites):
        m = caso.minima
        partes.append(f'una tensión mínima de {_pu(m.valor)} en el nodo {m.donde}, fuera del '
                      f'{banda_texto(limites)}' if m else 'nodos fuera de los parámetros de tensión')
    if not caso.cumple_cargabilidad(limites):
        c, tr = caso.cargabilidad_max, caso.trafo_max
        if c is not None and (c.valor > limites.cargabilidad_max_pct or caso.tramos_sobre):
            partes.append(f'una cargabilidad de {numero(c.valor, 1)} % en el tramo {c.donde}')
        if tr is not None and tr.valor > limites.cargabilidad_max_pct:
            partes.append(f'el transformador {tr.donde} al {numero(tr.valor, 1)} % de su capacidad')
        if not partes or (c is None and tr is None):
            partes.append('tramos sobrecargados')
    return ' y '.join(partes) or 'límites no satisfechos'


@dataclass(frozen=True)
class Solicitud:
    """Datos de la solicitud de la carga nueva (RF-51)."""

    cliente: str
    ubicacion: str
    tipo_solicitud: str
    potencia_kw: float
    fecha_solicitud: date
    alimentador: str
    set_nombre: str
    tension_kv: float
    transformador: str
    expediente: str
    #: Si el predio está en el área de concesión, según el operador (RF-125).
    en_concesion: bool | None = None


def antecedentes_factibilidad(s: Solicitud) -> list[str]:
    """Los antecedentes con las frases del modelo de la empresa (RF-107)."""
    return [
        f'Con fecha {_fecha_larga(s.fecha_solicitud)} se solicita evaluación de {s.tipo_solicitud} en '
        f'media tensión, predio ubicado en {s.ubicacion}.',
        f'La solicitud está registrada con {s.expediente}.',
        f'El interesado solicita {s.tipo_solicitud} para {_g(s.potencia_kw)} kW.',
        f'El interesado se encuentra próximo al alimentador {s.alimentador}.',
        f'El transformador de la SET {s.set_nombre} tiene las siguientes características: {s.transformador}.',
    ]


def descripcion_factibilidad(s: Solicitud, fuentes: list[str]) -> list[str]:
    """Fuentes de información del análisis y zona de influencia (RF-108)."""
    return [f'Para realizar el análisis se ha considerado {", ".join(fuentes)}.',
            f'El interesado se encuentra dentro de la zona de influencia del alimentador {s.alimentador}.']


#: Frase de las cargas en bloque del estado proyectado (RF-50).
SOLICITUDES_VIGENTES = ('Para la evaluación se consideran las cargas (kW) de las solicitudes que se '
                        'encuentran vigentes.')


def texto_transformador(s: Solicitud, devanado: Devanado | None, caso_transmision: str,
                        proyecto: str) -> str:
    """El análisis del transformador de la SET, sin y con proyecto (RF-121)."""
    if devanado is None or devanado.sin_pct is None or devanado.con_pct is None:
        return (f'No se obtuvo la cargabilidad del transformador de la SET {s.set_nombre} del proyecto de '
                f'transmisión {proyecto or "(no indicado)"}.')
    estado = ('por debajo de su capacidad nominal' if devanado.con_pct <= 100
              else 'por encima de su capacidad nominal')
    return (f'Con el caso de estudio «{caso_transmision}» del proyecto de transmisión {proyecto}, el '
            f'transformador de potencia de la SET {s.set_nombre} alcanza una cargabilidad de '
            f'{numero(devanado.sin_pct, 2)} % en el devanado de {_g(devanado.kv)} kV en el escenario sin proyecto '
            f'y de {numero(devanado.con_pct, 2)} % en el escenario con proyecto, {estado}.')


def conclusiones_factibilidad(s: Solicitud, veredicto: Veredicto, punto_diseno: str,
                              devanado: Devanado | None) -> list[str]:
    """Conclusiones en apartados a) a d), como el modelo (RF-122)."""
    if s.en_concesion is None:
        concesion = '[A CONFIRMAR POR EL OPERADOR: si el predio está en el área de concesión]'
    else:
        concesion = ('se encuentra dentro' if s.en_concesion else 'no se encuentra dentro') + \
            ' del área de concesión de la empresa distribuidora'
    a = (f'a) La solicitud de {s.tipo_solicitud} presentada por {s.cliente}, para una demanda de '
         f'{_g(s.potencia_kw)} kW, {concesion}.')
    alimentador = [x for x in veredicto.excesos if 'transformador' not in x]
    b = (f'b) El alimentador {s.alimentador} admite la carga en el estado proyectado, con la tensión '
         'dentro de la banda admitida y sin tramos sobre el umbral de cargabilidad.' if not alimentador
         else f'b) El alimentador {s.alimentador} no admite la carga: ' + '; '.join(alimentador) + '.')
    trafo = [x for x in veredicto.excesos if 'transformador' in x]
    c = (f'c) El transformador de potencia de la SET {s.set_nombre} tiene capacidad disponible '
         f'({numero(devanado.con_pct, 2)} % con proyecto).' if not trafo and devanado is not None
         else f'c) Transformador de la SET {s.set_nombre}: ' + '; '.join(trafo) + '.')
    d = (f'd) Se recomienda asignar el punto de diseño en la estructura de media tensión {punto_diseno}.'
         if veredicto.factible else
         f'd) No se recomienda asignar punto de diseño en el alimentador {s.alimentador} mientras no se '
         'resuelvan los límites indicados.')
    return [a, b, c, d]
