"""Informes de estudio eléctrico y de factibilidad de suministro (spec 017).

El resultado de las specs 011, 014 y 015 se quedaba en DIgSILENT y en el JSON de cada
estudio, y el ingeniero lo copiaba a mano a un Word con el formato de la empresa. Este
módulo es la parte del informe que no necesita DIgSILENT: qué se usa del perfil de
empresa, los cálculos y la redacción. El guion ``tools/informes_pf.py`` mide y exporta
las imágenes, y ``informe_docx.py`` escribe el Word.

Nada de otra empresa se supone (P13). Sin modelo sale con una plantilla neutra y lo dice
(086:RF-31). La banda de tensión y el umbral de cargabilidad se piden en el formulario: los
±5 % por defecto de los estudios de la 011 no valen aquí, porque el informe concluye con ellos
ante el regulador. Las bandas de coloreado solo pintan: sin perfil ni operador salen de esa
banda, con aviso (086:RF-35).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from .estudios_pf import EstudiosError, Limites
from .instalacion_ternas import describir as describir_ternas
from .perfil_empresa import PerfilError, moneda_informes

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


def bandas_de_limites(limites: Limites) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Las bandas de coloreado que resultan de la banda de calidad y del umbral (086:RF-35).

    Antes eran constantes copiadas del modelo de una empresa. Salen de lo que el informe ya juzga:
    tensión, dos escalones bajo el mínimo, el mínimo y el máximo; cargabilidad, cinco fracciones del
    umbral, una por color de la paleta, y lo que lo pasa ya sale en rojo. Solo colorean: ninguna
    conclusión del informe depende de ellas.
    """
    minimo, maximo = round(limites.tension_min_pu * 100, 6), round(limites.tension_max_pu * 100, 6)
    umbral = float(limites.cargabilidad_max_pct)
    return ((round(minimo - 10, 6), round(minimo - 5, 6), minimo, maximo),
            tuple(round(umbral * f, 6) for f in (0.8, 0.9, 0.95, 1.05, 1.5)))


@dataclass(frozen=True)
class ConfigInforme:
    """Lo que el informe toma del perfil de empresa (RF-4, RF-13, RF-115).

    Un campo en None es que el perfil no lo da; :meth:`faltan` dice cuáles hay que pedir
    antes de generar cada tipo.
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
    #: 086:RF-28: el rótulo de la moneda de los informes; sin ella no se escribe la de nadie.
    moneda: str | None = None
    #: 086:RF-35: lo que se tomó sin que lo dijera el perfil, para decirlo al operador.
    avisos_perfil: tuple[str, ...] = ()

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
        try:
            moneda = moneda_informes(datos)
        except PerfilError as exc:
            raise InformeError(str(exc)) from exc
        config = cls(modelos=modelos, proyecto_transmision=proyecto or None, rotulos_cabecera=dict(rotulos), **textos,
                     limites_parciales=parciales, bandas_tension_pct=tension,
                     bandas_cargabilidad_pct=carga, moneda=moneda)
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

    def con_bandas(self, *, tension: Any = None, carga: Any = None) -> 'ConfigInforme':
        """Las bandas de coloreado: lo del operador, si no lo del perfil, si no las de los límites (086:RF-35).

        Sin límites todavía no se deriva nada: los pide el formulario, y ya se volverá aquí.
        Volver a llamarla no repite el aviso.
        """
        cambios: dict[str, Any] = {}
        for clave, operador in ((_BANDAS[0], tension), (_BANDAS[1], carga)):
            if operador not in (None, [], ()):
                cambios[clave] = _bandas(operador, clave)
        nueva = replace(self, **cambios) if cambios else self
        if nueva.limites is None or None not in (nueva.bandas_tension_pct, nueva.bandas_cargabilidad_pct):
            return nueva
        de_tension, de_carga = bandas_de_limites(nueva.limites)
        # Solo las que de verdad se derivaron: con una escrita en la web, el aviso general decía algo falso.
        derivadas = [c for c in _BANDAS if getattr(nueva, c) is None]
        aviso = (f'Bandas de coloreado derivadas de los límites del informe: ni el perfil ni el formulario dan '
                 f'{", ".join(f"{CLAVE_PERFIL}.{c}" for c in derivadas)}.')
        return replace(nueva, bandas_tension_pct=nueva.bandas_tension_pct or de_tension,
                       bandas_cargabilidad_pct=nueva.bandas_cargabilidad_pct or de_carga,
                       avisos_perfil=(*nueva.avisos_perfil, aviso))

    def faltan(self, tipo: str) -> list[str]:
        """Lo que hay que pedir para generar un informe de ``tipo`` (RF-14).

        Solo la banda y el umbral, porque el informe concluye con ellos. Lo demás no bloquea:
        sin modelo sale con plantilla neutra (086:RF-31), sin bandas de coloreado se derivan
        (086:RF-35), y sin proyecto de transmisión queda señalada su sección (RF-70).
        """
        if tipo not in TIPOS:
            raise InformeError(f'Tipo de informe desconocido: {tipo!r} (son {", ".join(TIPOS)}).')
        if self.limites is None:
            return [f'{CLAVE_LIMITES}.{k}' for k in _LIMITES if k not in self.limites_parciales]
        return []

    def modelo(self, tipo: str) -> Path | None:
        """El ``.docx`` modelo de ``tipo``; ``None`` si la empresa no trae, y va la plantilla neutra (086:RF-31).

        Una ruta declarada que no existe sigue siendo un error: la empresa cree tener su modelo y el
        informe saldría con otra forma sin que nadie lo hubiera pedido.
        """
        faltan = self.faltan(tipo)
        if faltan:
            raise InformeError(f'No se puede generar el informe de {tipo}: falta en el perfil de '
                               f'empresa {", ".join(faltan)}.')
        ruta = self.modelos.get(tipo)
        if ruta is None:
            return None
        if not ruta.is_file():
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
        barras = _barras_juzgadas(medida)
        lineas =[e for e in (medida.get('elementos') or []) if e[1] == 'ElmLne']
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
# RF-126 (usuario, 2026-10-16): la terna y el enlace son la etapa de refuerzo de la red,
# entre el cambio de conductor y la migración.
ETAPAS = ('bancos_existentes', 'bancos_nuevos', 'reguladores', 'conductor', 'refuerzo',
          'migracion')
NOMBRE_ETAPA = {
    'bancos_existentes': 'Bancos de condensadores existentes',
    'bancos_nuevos': 'Bancos de condensadores propuestos',
    'reguladores': 'Reguladores de tensión',
    'conductor': 'Cambio de sección del conductor de la troncal',
    'refuerzo': 'Refuerzo de la red (ternas y enlaces)',
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
    #: 073:RF-32: lo medido en valle, de la escalera; sin él, «no comprobado en valle».
    valle: Mapping[str, Any] | None = None
    #: 086:RF-49: sus barras bajas, según quién las dejó así (``clasificar_bajo_limite``).
    bajo_limite: Mapping[str, Any] | None = None

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


#: Palabras que nombran un trámite o una forma de sociedad, no a un cliente (063:RF-49).
_GENERICAS = frozenset({'AMPC', 'AMPLIACION', 'CARGA', 'NUEVA', 'SUMINISTRO', 'EMPRESA', 'SOCIEDAD', 'SERVICIO'})


def _palabras_de_nombre(nombre: str) -> set[str]:
    limpio = ''.join(c for c in unicodedata.normalize('NFD', nombre or '') if not unicodedata.combining(c)).upper()
    return {p for p in re.split(r'[^A-Z0-9]+', limpio) if len(p) >= 4 and p not in _GENERICAS}


def cliente_ajeno(carga: str, cliente: str) -> bool:
    """El cliente no comparte ningún nombre con la carga (063:RF-49).

    T7 en SM218: «AMPC INKA'S BERRIES S.A.C.» salió con el cliente, el NIS y la potencia de Minera Santa
    María, del formulario guardado. Una carga con solo un código no dice de quién es: no se afirma nada.
    """
    de_la_carga, del_cliente = _palabras_de_nombre(carga), _palabras_de_nombre(cliente)
    return bool(de_la_carga and del_cliente and not de_la_carga & del_cliente)


# --------------------------------------------------------------------------- 086:RF-48 a RF-50
#: Por debajo de esto una barra no tiene tensión: es una isla sin fuente, no una caída (063:RF-43).
_SIN_TENSION_PU = 0.1
#: Qué es cada barra bajo el límite, en el orden en que se cuenta.
_TITULOS_BAJO_LIMITE = (('causado', 'Lo que causa la carga o la obra'),
                        ('previo', 'Déficit previo, fuera de esta obra'),
                        ('sin_comparacion', 'Bajo el límite, sin comparación disponible'))


def _barras_juzgadas(medida: Mapping[str, Any]) -> list[tuple[str, float]]:
    """Las barras que se juzgan de una medida guardada por los estudios.

    063:RF-43, RF-44: las islas sin tensión no son nodos fuera de banda, y se juzga la media
    tensión si la medida dice cuál es (una guardada antes no lo dice: todas).
    """
    sin_tension = set(medida.get('sin_tension') or ())
    mt = set(medida.get('barras_mt') or ())
    return [(n, u) for n, u in medida.get('barras') or [] if n not in sin_tension and (not mt or n in mt)]


def clasificar_bajo_limite(u_sin: Mapping[str, float], u_con: Mapping[str, float], barras_cargas: Sequence[str],
                           tension_min_pu: float, tolerancia_pu: float) -> dict[str, Any]:
    """Cada barra bajo el límite, según quién la dejó así (086:RF-48, RF-49).

    SI112 (2026-11-04), con su obra: la carga nueva a 0,963 p.u. y un ramal a 0,9449 p.u., con límite 0,95. El
    criterio de la escalera (``escalera_optima.cumple``, 025:RF-50) lo da por bueno porque el ramal no empeora: ese
    criterio no cambia, y esto usa su misma regla para decir qué queda. ``causado``: la barra de una carga nueva, la
    que entra bajo el límite o la que baja más que la tolerancia, lo que la escalera rechaza. ``previo``: ya estaba
    baja y no empeora. ``sin_comparacion``: no hay su tensión sin el proyecto, y entonces no se sabe.

    Recorre lo ya medido de un flujo, una vez por flujo: no pregunta nada a la red.
    """
    fuera: dict[str, Any] = {clave: [] for clave, _ in _TITULOS_BAJO_LIMITE}
    cargas = set(barras_cargas)
    for barra, u in u_con.items():
        if u is None or u <= _SIN_TENSION_PU or u >= tension_min_pu:
            continue
        s = u_sin.get(barra)
        s = s if s is not None and s > _SIN_TENSION_PU else None
        if barra in cargas:
            clase = 'causado'
        elif s is None:
            clase = 'sin_comparacion'
        elif s < tension_min_pu and u >= s - tolerancia_pu:
            clase = 'previo'
        else:
            clase = 'causado'
        fuera[clase].append({'barra': barra, 'u': u, 'sin': s})
    for filas in fuera.values():
        filas.sort(key=lambda f: (f['u'], f['barra']))
    fuera['tolerancia_pu'] = tolerancia_pu
    return fuera


def bajo_limite(sin: Mapping[str, Any], con: Mapping[str, Any], limites: Limites, *,
                barras_cargas: Sequence[str] = (), tolerancia_pu: float = 0.0) -> dict[str, Any] | None:
    """:func:`clasificar_bajo_limite` con dos medidas guardadas; ``None`` si el flujo con obra no dio tensiones."""
    if not con.get('converge'):
        return None
    u_con: dict[str, float] = {}
    for barra, u in _barras_juzgadas(con):
        # Dos barras con el mismo nombre: cuenta la más baja, para no tapar una con la otra.
        if u is not None and (barra not in u_con or u < u_con[barra]):
            u_con[barra] = u
    u_sin = dict(_barras_juzgadas(sin)) if sin.get('converge') else {}
    return clasificar_bajo_limite(u_sin, u_con, barras_cargas, limites.tension_min_pu, tolerancia_pu)


def queda_deficit(fuera: Mapping[str, Any] | None) -> bool:
    """Si queda alguna barra baja que la carga no causa, y por tanto no se puede decir que esté en norma (RF-50)."""
    return bool(fuera and (fuera.get('previo') or fuera.get('sin_comparacion')))


def frases_bajo_limite(fuera: Mapping[str, Any] | None) -> list[str]:
    """Una frase por clase, con cada barra y su tensión (RF-48, RF-49). Sin barras bajas, ninguna.

    Con cuatro decimales: 0,9499 p.u. saldría «0,950», igual al límite que no alcanza.
    """
    def barra(f: Mapping[str, Any]) -> str:
        antes = f' ({numero(f["sin"], 4)} p.u. sin el proyecto)' if f.get('sin') is not None else ''
        return f'{f["barra"]} a {numero(f["u"], 4)} p.u.{antes}'

    return [f'{titulo}: {_lista([barra(f) for f in fuera[clave]])}.'
            for clave, titulo in _TITULOS_BAJO_LIMITE if fuera and fuera.get(clave)]


def baja_ajena_a_la_carga(caso: Caso, actual: Caso, fuera: Mapping[str, Any] | None, limites: Limites) -> bool:
    """Si lo único que ``caso`` incumple son barras bajas que la carga no causa (RF-50).

    Es tan estricto como el criterio de la escalera solo en la tensión baja: una sobrecarga o una sobretensión no se
    disculpan, y lo que no cuadra con la lista, tampoco.
    """
    if fuera is None or not caso.converge or not queda_deficit(fuera) or fuera.get('causado'):
        return False
    if not caso.cumple_cargabilidad(limites):
        return False
    if caso.tension_max is not None and caso.tension_max.valor > limites.tension_max_pu:
        return False
    listadas = {f['barra'] for clave in ('previo', 'sin_comparacion') for f in fuera[clave]}
    # Más nodos fuera que barras bajas: los demás están sobre la banda.
    if caso.nodos_fuera > len(listadas):
        return False
    minima = caso.minima
    if minima is not None and minima.valor < limites.tension_min_pu and minima.donde not in listadas:
        return False
    # La lista va por barra, y en el desequilibrado la mínima es de una fase: esa también tiene que no empeorar.
    if caso.desequilibrado and minima is not None:
        previa = actual.minima
        if previa is None or minima.valor < previa.valor - float(fuera.get('tolerancia_pu') or 0.0):
            return False
    return True


def veredicto_factibilidad(proyectado: Caso, devanados: list[Devanado] | None,
                           limites: Limites, *, exigir_transformador: bool = True,
                           actual: Caso | None = None, bajo_limite: Mapping[str, Any] | None = None) -> Veredicto:
    """Factible solo si el proyectado cumple banda y umbral y la SET no pasa del 100 % (RF-71).

    Sin datos del transformador (RF-70) no se puede afirmar que la SET la admite, así
    que no es factible y se dice por qué, salvo que el informe lo deje fuera (063:RF-46).
    Con ``actual`` y ``bajo_limite``, las barras bajas que la carga no causa no cuentan
    como exceso: se dicen aparte (086:RF-48).
    """
    excesos = []
    if not proyectado.converge:
        excesos.append('el flujo de carga del estado proyectado no converge')
    else:
        minima = proyectado.minima
        ajena = actual is not None and baja_ajena_a_la_carga(proyectado, actual, bajo_limite, limites)
        if minima is not None and minima.valor < limites.tension_min_pu and not ajena:
            excesos.append(f'tensión mínima de {formato_pu(minima.valor)} en {minima.donde}, '
                           f'{formato_pu(limites.tension_min_pu - minima.valor)} por debajo de '
                           f'{formato_pu(limites.tension_min_pu)}')
        maxima = proyectado.tension_max
        if maxima is not None and maxima.valor > limites.tension_max_pu:
            excesos.append(f'tensión máxima de {formato_pu(maxima.valor)} en {maxima.donde}, '
                           f'{formato_pu(maxima.valor - limites.tension_max_pu)} por encima de '
                           f'{formato_pu(limites.tension_max_pu)}')
        carga = proyectado.cargabilidad_max
        if carga is not None and carga.valor > limites.cargabilidad_max_pct:
            excesos.append(f'cargabilidad de {numero(carga.valor, 1)} % en {carga.donde}, '
                           f'{numero(carga.valor - limites.cargabilidad_max_pct, 1)} puntos sobre el '
                           f'{_g(limites.cargabilidad_max_pct)} %')
        if proyectado.nodos_fuera and not ajena and (minima is None or minima.valor >= limites.tension_min_pu):
            excesos.append(f'{proyectado.nodos_fuera} nodos fuera de la banda de tensión')
        if proyectado.tramos_sobre and (carga is None or carga.valor <= limites.cargabilidad_max_pct):
            excesos.append(f'{proyectado.tramos_sobre} tramos sobre el umbral de cargabilidad')
    if not devanados or all(d.con_pct is None for d in devanados):
        if exigir_transformador:
            excesos.append('no se obtuvo la cargabilidad del transformador de la SET')
    else:
        for d in devanados:
            if d.con_pct is not None and d.con_pct > 100.0:
                excesos.append(f'devanado de {_g(d.kv)} kV del transformador de la SET al '
                               f'{numero(d.con_pct, 2)} %, {numero(d.con_pct - 100, 2)} puntos sobre su capacidad')
    return Veredicto(not excesos, tuple(excesos))


@dataclass(frozen=True)
class Conclusion:
    """Lo que concluye el informe con los tres casos (063:RF-7 a RF-11).

    ``clave``: ``sin_obras``, ``con_obras``, ``con_obras_deficit`` (la obra basta para la carga y quedan
    barras bajas que ella no causa, 086:RF-48), ``requiere_refuerzo``, ``obras_insuficientes`` o
    ``no_converge``. ``violaciones`` dice qué motivó las obras, por caso; ``elementos``, qué
    nodos y tramos las requieren.
    """

    factible: bool
    clave: str
    violaciones: tuple[str, ...] = ()
    elementos: tuple[str, ...] = ()


def _elementos_fuera(caso: Caso, limites: Limites) -> list[str]:
    """Los nodos y tramos de ``caso`` que pasan un límite: los que requieren la obra (063:RF-10)."""
    if not caso.converge:
        return []
    out = []
    m = caso.minima
    if m is not None and m.valor < limites.tension_min_pu:
        out.append(m.donde)
    if caso.tension_max is not None and caso.tension_max.valor > limites.tension_max_pu:
        out.append(caso.tension_max.donde)
    for e in (caso.cargabilidad_max, caso.trafo_max):
        if e is not None and e.valor > limites.cargabilidad_max_pct:
            out.append(e.donde)
    return out


def _elementos_a_corregir(con: Caso, limites: Limites, fuera: Mapping[str, Any] | None) -> list[str]:
    """Lo que hay que corregir en «Con proyecto»: nunca una barra que ya estaba baja, sino lo que causa la carga."""
    elementos = _elementos_fuera(con, limites)
    if not fuera:
        return elementos
    ajenas = {f['barra'] for clave in ('previo', 'sin_comparacion') for f in fuera.get(clave) or ()}
    causadas = [f['barra'] for f in fuera.get('causado') or ()]
    return list(dict.fromkeys(causadas + [e for e in elementos if e not in ajenas]))


def conclusion_factibilidad(actual: Caso, cargas: Caso, con: Caso | None, limites: Limites, *,
                            con_proyecto_verificado: bool = False,
                            bajo_limite: Mapping[str, Any] | None = None) -> Conclusion:
    """Factible, con o sin obras, a partir del estado actual, el de la carga y «Con proyecto».

    063:RF-8 a RF-11. Las obras solo se justifican si el estado actual o el de la carga violan
    un límite (usuario, 2026-11-01): si los dos cumplen, factible sin obras. Con violaciones,
    decide «Con proyecto» si tiene obras (``con`` no es ``None``); sin obras, no es factible
    sin refuerzo. INKA'S BERRIES en SM218: el estado actual ya tenía un cuello de botella al
    131 % y con la carga el punto de diseño bajaba a 0,934 p.u.

    086:RF-48: con ``bajo_limite``, una barra baja que la carga no causa no hace insuficiente la
    obra. SI112 (2026-11-04) elegía su obra en la escalera, porque ese ramal no empeora, y este
    informe la declaraba insuficiente por el mismo ramal.
    """
    casos =[('estado actual', actual), ('con la carga', cargas)] + ([('con proyecto', con)] if con else [])
    sin_flujo = [f'el flujo {nombre} no converge ({caso.nombre})' for nombre, caso in casos if not caso.converge]
    if sin_flujo:
        # RF-38: la certificación nativa del estado final puede sustentar las obras aunque
        # la referencia completa sin refuerzos no tenga solución de flujo. El valor por
        # defecto conserva RF-11; esta excepción no acepta datos parciales del estado final.
        if (con_proyecto_verificado and actual.converge and not cargas.converge
                and con is not None and con.converge and con.minima is not None
                and con.tension_max is not None
                and (con.cargabilidad_max is not None or con.trafo_max is not None)):
            motivos = tuple(sin_flujo) + ((f'estado actual: {_incumplimientos(actual, limites)}',)
                                         if not actual.cumple(limites) else ())
            if con.cumple(limites) or baja_ajena_a_la_carga(con, actual, bajo_limite, limites):
                return Conclusion(True, 'con_obras_verificadas', motivos,
                                  tuple(_elementos_fuera(actual, limites)))
            return Conclusion(False, 'obras_insuficientes', motivos, tuple(_elementos_a_corregir(con, limites, bajo_limite)))
        return Conclusion(False, 'no_converge', tuple(sin_flujo))
    if actual.cumple(limites) and cargas.cumple(limites):
        return Conclusion(True, 'sin_obras')
    violaciones = tuple(f'{nombre}: {_incumplimientos(caso, limites)}'
                        for nombre, caso in casos[:2] if not caso.cumple(limites))
    elementos = tuple(dict.fromkeys(_elementos_fuera(cargas, limites) + _elementos_fuera(actual, limites)))
    if con is None:
        return Conclusion(False, 'requiere_refuerzo', violaciones, elementos)
    if con.cumple(limites):
        return Conclusion(True, 'con_obras', violaciones, elementos)
    if baja_ajena_a_la_carga(con, actual, bajo_limite, limites):
        return Conclusion(True, 'con_obras_deficit', violaciones, elementos)
    return Conclusion(False, 'obras_insuficientes', violaciones,
                      tuple(_elementos_a_corregir(con, limites, bajo_limite)) or elementos)



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


def formato_pu(v: float) -> str:
    return f'{numero(v, 3)} p.u.'


def _g(v: float) -> str:
    """Sin ceros de más: 300 kvar, 22,9 kV."""
    return f'{v:g}'.replace('.', ',')


def banda_texto(limites: Limites) -> str:
    """La banda como la dice el modelo: «±5 % de la tensión nominal» si es simétrica."""
    abajo, arriba = 1.0 - limites.tension_min_pu, limites.tension_max_pu - 1.0
    if abs(abajo - arriba) < 1e-9 and abajo > 0:
        return f'±{_g(round(abajo * 100, 3))} % de la tensión nominal'
    return f'entre {formato_pu(limites.tension_min_pu)} y {formato_pu(limites.tension_max_pu)}'


def fecha_larga(fecha: date) -> str:
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
        return f'{self.lugar}, {fecha_larga(self.fecha)}' if self.lugar else fecha_larga(self.fecha)


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
    texto = f'La tensión mínima del alimentador es de {formato_pu(minima.valor)} en el nodo {minima.donde}'
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


def _lista(cosas: Sequence[str]) -> str:
    """«a, b y c»."""
    cosas = list(cosas)
    return cosas[0] if len(cosas) == 1 else ', '.join(cosas[:-1]) + ' y ' + cosas[-1]


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
        trechos = list(obra.get('trechos') or [])
        if trechos:                                                        # RF-132
            partes = []
            for t in trechos:
                hoy = f', hoy con {_lista(t["actuales"])}' if t.get('actuales') else ''
                partes.append(f'desde la barra {t["desde"]} hasta la barra {t["hasta"]} '
                              f'({numero(t["km"], 2)} km en {len(t["tramos"])} {"tramo" if len(t["tramos"]) == 1 else "tramos"}{hoy})')
            km = sum(float(t['km']) for t in trechos)
            return (f'Cambiar la sección del conductor de la troncal a {obra["conductor"]} en '
                    f'{numero(km, 2)} km: ' + '; '.join(partes) + '.')
        if obra.get('km') is None:
            return f'Renovar la troncal con conductor {obra["conductor"]}.'
        # 084:RF-30: sin trecho no se calla: la geografía del flujo es lo que lo da (017:RF-131).
        return (f'Renovar {numero(obra["km"], 2)} km de la troncal con conductor {obra["conductor"]}. '
                'Trecho desde–hasta sin datos: el flujo guardado no trae su geografía.')
    if tipo == 'terna':                                                    # RF-127
        tramos = list(obra.get('tramos') or [])
        donde = f'los tramos {", ".join(tramos)}' if tramos else 'toda la troncal'
        texto = f'Tender una terna más en {donde} del alimentador {obra.get("alimentador", "")}.'
        # 084:RF-17: la configuración y la capacidad para ella, por tipo de cable y sin citar la norma.
        return ' '.join([texto, *dict.fromkeys(describir_ternas(i) for i in obra.get('instalaciones') or [])])
    if tipo == 'enlace':
        via = 'por la vía pública' if obra.get('por_via') else 'en recta (sin trazado por la vía)'
        return (f'Construir el enlace de {numero(obra["km"], 2)} km con conductor '
                f'{obra["conductor"]} entre {obra["desde"]} ({obra["recibe"]}) y {obra["hasta"]} '
                f'({obra["cede"]}), {via}.')
    if tipo == 'migracion':
        donde = f' hasta la SED {obra["hasta"]}' if obra.get('hasta') else ''
        texto = (f'Migrar la troncal{donde} a {_g(obra["kv"])} kV y acondicionar {obra["transformadores"]} '
                 f'transformadores de distribución para operar a {_g(obra["kv"])} kV.')
        fuera = obra.get('sin_alimentar') or {}
        if obra.get('ramales'):                                                  # 017:RF-42f
            kw = f', {numero(fuera["kw"], 1)} kW' if fuera.get('kw') is not None else ''
            texto += (f' Se abren {obra["ramales"]} ramales, que dejan sin alimentar {fuera.get("seds", 0)} SED{kw}: '
                      'hay que alimentarlas por otra vía.')
        return texto
    return str(obra.get('descripcion') or obra)


#: Etapa del informe (RF-32) de cada clase de obra de la spec 011; el reconectador no la
#: cambia. La terna y el enlace son el refuerzo de la red (RF-126).
_ETAPA_DE_CLASE = {'condensador': 'bancos_nuevos', 'regulador': 'reguladores', 'seccion': 'conductor',
                   'terna': 'refuerzo', 'enlace': 'refuerzo',
                   'tension': 'migracion', 'migracion': 'migracion',
                   # 019:RF-12: la consigna de cabecera es regulación de tensión.
                   'consigna': 'reguladores'}


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
        return {'tipo': 'conductor', 'km': obra.get('km'), 'conductor': tipo,
                'tramos': list(obra.get('tramos') or [])}
    if clase == 'consigna':
        return {'descripcion': f"Llevar la tensión de la barra de cabecera a "
                               f"{numero(float(obra.get('consigna_pu') or 0), 2)} p.u."}
    if clase == 'terna':                                                   # RF-127
        return {'tipo': 'terna', 'tramos': list(obra.get('tramos') or []),
                'alimentador': obra.get('alimentador', ''),
                **({'instalaciones': list(obra['instalaciones'])} if obra.get('instalaciones') else {})}
    if clase == 'enlace':
        # El largo, los extremos y el trazado son los de la obra aplicada (017:RF-35).
        e = obra.get('enlace') or {}
        return {'tipo': 'enlace', 'km': float(e.get('largo_m') or 0) / 1000.0,
                'conductor': (obra.get('tipo') or {}).get('nombre', ''),
                'desde': (e.get('origen') or {}).get('barra_final', ''),
                'hasta': (e.get('destino') or {}).get('barra_final', ''),
                'recibe': obra.get('alimentador', ''), 'cede': obra.get('cede', ''),
                'por_via': bool((e.get('trazado') or {}).get('por_via'))}
    if clase in ('tension', 'migracion'):
        return {'tipo': 'migracion', 'kv': float(obra.get('kv_destino') or 0),
                'transformadores': obra.get('transformadores', 0), 'hasta': obra.get('hasta', ''),
                'ramales': obra.get('ramales', 0), 'sin_alimentar': obra.get('sin_alimentar')}
    return {'descripcion': f'Obra de {clase} en {nodo or obra.get("alimentador", "")}.'}


def etapa_de_obras(obras: list[Mapping[str, Any]]) -> str | None:
    """La etapa más avanzada (RF-32) entre las obras activas de «Con proyecto»."""
    claves = [_ETAPA_DE_CLASE[o.get('clase')] for o in obras if o.get('clase') in _ETAPA_DE_CLASE]
    return max(claves, key=ETAPAS.index) if claves else None


#: 042:RF-65, RF-68: las filas de la obra que no paga la carga, en la tabla de alternativas.
ETIQUETA_PREVIO = 'déficit previo'
ETIQUETA_SIN_COMPARACION = 'sin comparación'


def notas_alternativas_escalera(por_alimentador) -> list[str]:
    """Lo que hay que saber para leer esas filas: no son efecto de una obra aplicada (042:RF-67)."""
    etiquetas = [e for e in (ETIQUETA_PREVIO, ETIQUETA_SIN_COMPARACION) if any(f.endswith(f'· {e}') for f in por_alimentador)]
    notas = []
    if etiquetas:
        notas.append(f"Las filas «{'» y «'.join(etiquetas)}» son obras presentadas aparte: no están en «Con proyecto» ni en sus "
                     'flujos, y sus cifras no son efecto de ninguna obra aplicada. Se midieron con la demanda máxima, sin sorteos.')
    if any(a.get('definitiva') is not None for lista in por_alimentador.values() for a in lista):      # 042:RF-75
        tasas = sorted({float(a['tasa_horizonte']) for lista in por_alimentador.values() for a in lista if a.get('tasa_horizonte')})
        con_tasa = f" con {' y '.join(f'{100 * t:.2f}'.replace('.', ',') for t in tasas)} % al año de largo plazo" if tasas else ''
        notas.append(f'Definitiva: con la demanda proyectada al horizonte de vida útil{con_tasa}, medida en DIgSILENT, el flujo converge, '
                     'todas las barras quedan en límites y ningún tramo pasa del límite de planeamiento. Las cargas nuevas se '
                     'mantienen en su potencia solicitada. El alcance no cambia el orden, que es por costo anual.')
    factores = sorted({float(a['factor']) for lista in por_alimentador.values() for a in lista if a.get('factor')})
    if factores:                                                                # 042:RF-72
        cuales = ' y '.join(f'{x:g}'.replace('.', ',') for x in factores)
        notas.append(f'Los reguladores y elevadores se dimensionaron con un factor de {cuales} sobre la corriente medida, '
                     'por el crecimiento de la demanda que no se cuenta.')
    return notas


def filas_alternativas_escalera(por_alimentador) -> tuple[tuple[str, ...], list[list[str]]]:
    """La tabla de hasta 3 alternativas por alimentador, de menor a mayor costo anual (042:RF-58)."""
    def cifra(x):
        return f'{float(x):,.0f}' if x is not None else ''

    def sorteos(a):
        return f"{100 * float(a['fraccion']):.0f} %" if a.get('fraccion') is not None else 'sin sortear'

    def en_valle(a):
        return 'cumple' if a.get('valle') is True else 'no comprobado'

    def alcance(a):
        if a.get('definitiva') is None:
            return 'sin medir'
        if a['definitiva']:
            return f"definitiva, {a.get('aguanta_anios')} años"
        return f"temporal, aguanta {a['aguanta_anios']} años" if a.get('aguanta_anios') else 'temporal'

    filas = [[str(f), str(a.get('numero')), str(a.get('nombre')), cifra(a.get('inversion')), cifra(a.get('costo_anual')),
              sorteos(a), en_valle(a), alcance(a), 'Sí' if a.get('elegida') else 'No']
             for f, lista in sorted(por_alimentador.items())
             for a in sorted(lista, key=lambda x: float(x.get('costo_anual') or 0.0))]
    return ('Alimentador', 'Alternativa', 'Obras', 'Inversión US$', 'Costo anual US$', 'Sorteos que cumplen', 'En valle', 'Alcance', 'Se aplica'), filas


def alternativas_de_obras(aplicadas: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Las alternativas del informe con las obras activas de «Con proyecto» (RF-128, RF-129).

    ``aplicadas``: ``{'variacion', 'obra'}`` de cada obra. Una alternativa por etapa de
    RF-32 con obras, cada una sumada a las anteriores. La consigna de cabecera no es obra:
    va con la etapa siguiente, o con la última. En CA101 (2026-10-16): 1, los dos bancos;
    2, el cambio de sección con los bancos y la consigna.
    """
    por_etapa: dict[str, list[str]] = {}
    consignas: list[str] = []
    for a in aplicadas:
        clase = (a.get('obra') or {}).get('clase')
        if clase == 'consigna':
            consignas.append(str(a['variacion']))
        elif clase in _ETAPA_DE_CLASE:
            por_etapa.setdefault(_ETAPA_DE_CLASE[clase], []).append(str(a['variacion']))
    claves = sorted(por_etapa, key=ETAPAS.index)
    if not claves:
        return [{'clave': 'reguladores', 'variaciones': sorted(consignas)}] if consignas else []
    # La consigna se aplica desde la primera etapa posterior a la de reguladores.
    destino = next((c for c in claves if ETAPAS.index(c) > ETAPAS.index('reguladores')), claves[-1])
    if consignas:
        por_etapa[destino] = por_etapa[destino] + consignas
    out, acumuladas = [], []
    for clave in claves:
        acumuladas = acumuladas + por_etapa[clave]
        out.append({'clave': clave, 'variaciones': sorted(acumuladas)})
    return out


@dataclass(frozen=True)
class Trecho:
    """Un trecho continuo del cambio de conductor (RF-132)."""

    desde: str
    hasta: str
    tramos: tuple[str, ...]
    km: float
    #: Conductor que hay hoy en cada tramo, sin repetir y en el orden del trecho.
    actuales: tuple[str, ...] = ()
    desde_gps: tuple[float, float] | None = None
    hasta_gps: tuple[float, float] | None = None


def _km_de(pts: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for (a1, o1), (a2, o2) in zip(pts, pts[1:]):
        dx = math.radians(o2 - o1) * math.cos(math.radians((a1 + a2) / 2))
        total += 6371.0 * math.hypot(dx, math.radians(a2 - a1))
    return total


def _generica(nombre: str) -> bool:
    """Barra con el nombre que pone DIgSILENT a una barra creada a mano («Terminal(1)»)."""
    return nombre.split('(')[0].strip().lower() in ('terminal', 'node', 'nodo', 'bus')


def trechos_de_conductor(geo: Mapping[str, Any], tramos: Sequence[str],
                         geo_actual: Mapping[str, Any] | None = None) -> list[Trecho]:
    """Los trechos continuos de ``tramos`` con su inicio y fin, del lado de la cabecera al
    lado de la cola (RF-132).

    ``geo`` es la geografía del flujo (RF-131): cada tramo ``[nombre, pts, carga, barra1,
    barra2, tipo, km]`` y los acoples cerrados ``[nombre, barra1, barra2]``, que unen
    barras sin ser tramo: un seccionador no corta el trecho. El conductor actual sale de
    ``geo_actual`` (el de «Sin proyecto»), porque en la geografía proyectada ya es el
    nuevo. Sin las barras (una geografía guardada antes de RF-131) no hay trechos.
    """
    filas = {t[0]: t for t in geo.get('tramos') or [] if len(t) >= 5 and t[3] and t[4]}
    elegidos = [n for n in dict.fromkeys(tramos) if n in filas]
    if not elegidos:
        return []
    # Las barras unidas por acoples son un mismo punto de la red.
    raiz: dict[str, str] = {}

    def nodo(b: str) -> str:
        while raiz.get(b, b) != b:
            b = raiz[b]
        return b
    for _n, b1, b2 in geo.get('acoples') or []:
        r1, r2 = nodo(b1), nodo(b2)
        if r1 != r2:
            raiz[max(r1, r2)] = min(r1, r2)
    nombres: dict[str, list[str]] = {}
    for t in filas.values():
        for b in (t[3], t[4]):
            nombres.setdefault(nodo(b), [])
            if b not in nombres[nodo(b)]:
                nombres[nodo(b)].append(b)
    # Profundidad de cada punto desde la cabecera por la red entera: así el trecho va de
    # la cabecera hacia la cola, como lo recorre la cuadrilla.
    vecinos: dict[str, list[str]] = {}
    for t in filas.values():
        a, b = nodo(t[3]), nodo(t[4])
        vecinos.setdefault(a, []).append(b)
        vecinos.setdefault(b, []).append(a)
    prof: dict[str, int] = {}
    cabecera = nodo(geo['cabecera']) if geo.get('cabecera') else None
    if cabecera in vecinos:
        prof[cabecera] = 0
        cola = [cabecera]
        for b in cola:
            for v in vecinos[b]:
                if v not in prof:
                    prof[v] = prof[b] + 1
                    cola.append(v)
    lejos = len(prof) + len(vecinos)
    gps_barra = {b[0]: (b[1], b[2]) for b in geo.get('barras') or [] if b[1] is not None}

    def rotulo(punto: str) -> tuple[str, tuple[float, float] | None]:
        """El nombre con que se da un punto: el propio antes que «Terminal», y su GPS."""
        lista = sorted(nombres.get(punto) or [punto], key=lambda b: (_generica(b), b not in gps_barra, b))
        gps = next((gps_barra[b] for b in lista if b in gps_barra), None)
        return lista[0], gps
    tipo_hoy = {t[0]: t[5] for t in (geo_actual or {}).get('tramos') or [] if len(t) >= 6}
    extremos = {n: (nodo(filas[n][3]), nodo(filas[n][4])) for n in elegidos}
    pendientes = set(elegidos)
    trechos = []
    while pendientes:
        semilla = min(pendientes, key=lambda n: (min(prof.get(p, lejos) for p in extremos[n]), n))
        grupo, puntos, cola = [], set(), [semilla]
        pendientes.discard(semilla)
        while cola:
            n = cola.pop()
            grupo.append(n)
            puntos |= set(extremos[n])
            for m in sorted(m for m in pendientes if puntos & set(extremos[m])):
                pendientes.discard(m)
                cola.append(m)
        grupo.sort(key=lambda n: (max(prof.get(p, lejos) for p in extremos[n]), n))
        desde = min(puntos, key=lambda b: (prof.get(b, lejos), b))
        hasta = max(puntos, key=lambda b: (prof.get(b, -1), b))
        km = sum(float(filas[n][6]) if len(filas[n]) > 6 and filas[n][6] is not None
                 else _km_de(filas[n][1]) for n in grupo)
        actuales = tuple(dict.fromkeys(tipo_hoy[n] for n in grupo if tipo_hoy.get(n)))
        (d_nombre, d_gps), (h_nombre, h_gps) = rotulo(desde), rotulo(hasta)
        trechos.append((prof.get(desde, lejos), Trecho(d_nombre, h_nombre, tuple(grupo), km, actuales,
                                                       d_gps, h_gps)))
    return [t for _p, t in sorted(trechos, key=lambda x: (x[0], x[1].desde))]



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
    evaluadas = sorted((e for e in etapas if e.evaluada), key=lambda e: ETAPAS.index(e.clave))
    if len(evaluadas) > 1:                                                 # RF-134
        puntos += [resumen_alternativa(i, e, limites) for i, e in enumerate(evaluadas, 1)]
        if rec.etapa is not None:
            n = evaluadas.index(rec.etapa) + 1
            puntos.append(f'Se recomienda la alternativa {n} ({NOMBRE_ETAPA[rec.etapa.clave].lower()}), '
                          'la primera que cumple la banda de tensión y el umbral de cargabilidad.')
    a_ejecutar = obras_a_ejecutar(rec, etapas)
    obras = [describir_obra(o) for e in a_ejecutar for o in e.obras]
    if obras:
        puntos.append(f'Para superar la mala calidad del servicio en el alimentador {lista}, es '
                      'necesario efectuar las siguientes actividades:')
        puntos += obras
    final = a_ejecutar[-1].caso if a_ejecutar else None
    if rec.etapa is not None and final is not None and final.minima is not None:
        puntos.append(f'Con la implementación de estas obras se logrará una tensión mínima de '
                      f'{formato_pu(final.minima.valor)}, dentro del {banda_texto(limites)}{segun}, '
                      'mejorando la calidad del servicio eléctrico.')
    elif final is not None and final.converge:
        puntos.append('Con las obras evaluadas el alimentador todavía presenta '
                      + _incumplimientos(final, limites) + ': se requieren obras adicionales.')
    elif not a_ejecutar:
        puntos.append('Se requiere evaluar obras de mejora para superar la mala calidad del servicio.')
    else:
        puntos.append('Ninguna de las obras evaluadas permite superar la mala calidad del servicio.')
    return puntos


def resumen_alternativa(n: int, etapa: Etapa, limites: Limites) -> str:
    """Qué logra la alternativa ``n`` (RF-134): tensión mínima, cargabilidad y si cumple."""
    caso = etapa.caso
    que = f'Alternativa {n} ({NOMBRE_ETAPA[etapa.clave].lower()})'
    if caso is None or not caso.converge:
        return f'{que}: el flujo de carga no converge.'
    datos = []
    if caso.minima is not None:
        datos.append(f'una tensión mínima de {formato_pu(caso.minima.valor)} en {caso.minima.donde}')
    if caso.cargabilidad_max is not None:
        datos.append(f'una cargabilidad máxima de {numero(caso.cargabilidad_max.valor, 1)} %')
    logra = f' logra {" y ".join(datos)}' if datos else ''
    if caso.cumple(limites):
        return f'{que}:{logra}; cumple la banda de tensión y el umbral de cargabilidad.'
    return f'{que}:{logra}; no basta, porque el alimentador sigue con ' + _incumplimientos(caso, limites) + '.'


def _incumplimientos(caso: Caso, limites: Limites) -> str:
    if not caso.converge:
        return 'un flujo de carga que no converge'
    partes = []
    if not caso.cumple_tension(limites):
        m = caso.minima
        partes.append(f'una tensión mínima de {formato_pu(m.valor)} en el nodo {m.donde}, fuera del '
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
    #: 063:RF-14 y RF-18: potencia previa y suministro de una ampliación.
    potencia_actual_kw: float | None = None
    nis: str = ''


def antecedentes_factibilidad(s: Solicitud) -> list[str]:
    """Los antecedentes con las frases del modelo de la empresa (RF-107)."""
    return [
        f'Con fecha {fecha_larga(s.fecha_solicitud)} se solicita evaluación de {s.tipo_solicitud} en '
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
                              devanado: Devanado | None, *, bajo_limite: Mapping[str, Any] | None = None) -> list[str]:
    """Conclusiones en apartados a) a d), como el modelo (RF-122)."""
    if s.en_concesion is None:
        concesion = '[A CONFIRMAR POR EL OPERADOR: si el predio está en el área de concesión]'
    else:
        concesion = ('se encuentra dentro' if s.en_concesion else 'no se encuentra dentro') + \
            ' del área de concesión de la empresa distribuidora'
    a = (f'a) La solicitud de {s.tipo_solicitud} presentada por {s.cliente}, para una demanda de '
         f'{_g(s.potencia_kw)} kW, {concesion}.')
    alimentador = [x for x in veredicto.excesos if 'transformador' not in x]
    # 086:RF-50: con barras bajas que la carga no causa, admite la carga, pero la tensión no queda en la banda.
    tension = ('sin tramos sobre el umbral de cargabilidad, aunque el alimentador sigue con barras bajo el '
               'límite de tensión' if queda_deficit(bajo_limite)
               else 'con la tensión dentro de la banda admitida y sin tramos sobre el umbral de cargabilidad')
    b = (f'b) El alimentador {s.alimentador} admite la carga en el estado proyectado, {tension}.' if not alimentador
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


# --------------------------------------------------------------------------- 063:RF-56
def _reparto_cola(cola: Mapping[str, Any]) -> str:
    partes = [f'{numero(kw, 0)} kW en {nombre}' for nombre, kw in (cola.get('por_alimentador') or {}).items()]
    return f' ({_lista(partes)})' if partes else ''


def _resultado_cola(cola: Mapping[str, Any]) -> str:
    """Lo que dio el flujo con toda la cola sin obras; solo lo medido."""
    if not cola.get('converge'):
        return ('Con todas ellas y sin obras, el flujo no converge: en el modelo, la red existente no puede '
                'atender esa demanda y no es posible conectarlas')
    if cola.get('cumple'):
        return 'Con todas ellas y sin obras, el flujo converge y cumple los límites evaluados'
    return 'Con todas ellas y sin obras, el flujo converge pero incumple los límites evaluados'


def desarrollo_cola(cola: Mapping[str, Any]) -> list[str]:
    """El desarrollo del caso sin obras: la cola de conexión y su flujo (063:RF-56)."""
    textos = [f'Además de la carga analizada hay otros clientes con solicitud: en total, {cola["cantidad"]} cargas, '
              f'incluida la analizada, esperan conexión y suman {numero(cola["kw"], 0)} kW{_reparto_cola(cola)}.']
    if cola.get('demanda_actual_kw'):
        textos.append(f'La demanda nominal actual de la red es de {numero(cola["demanda_actual_kw"], 0)} kW: con la cola '
                      f'alcanzaría {numero(cola["demanda_actual_kw"] + cola["kw"], 0)} kW, '
                      f'{numero((cola["demanda_actual_kw"] + cola["kw"]) / cola["demanda_actual_kw"], 2)} veces la actual.')
    resultado = f'{_resultado_cola(cola)}.'
    if cola.get('motivo'):
        resultado += f' {cola["motivo"]}'
    textos.append(resultado)
    return textos


def conclusion_cola(cola: Mapping[str, Any]) -> str:
    """La conclusión sobre la cola de conexión; justifica la obra solo si el flujo lo muestra (063:RF-56)."""
    texto = (f'La carga analizada no es la única: {cola["cantidad"]} cargas, incluida ella, esperan conexión y suman '
             f'{numero(cola["kw"], 0)} kW{_reparto_cola(cola)}. {_resultado_cola(cola)}.')
    if cola.get('obra') and not cola.get('cumple'):
        texto += f' Esta cantidad de demanda es lo que justifica {cola["obra"]}.'
    return texto


# --------------------------------------------------------------------------- 063:RF-54, RF-55
@dataclass(frozen=True)
class FuenteMedida:
    """Una fuente con su inyección medida en el flujo: red externa, generador o alimentador."""

    nombre: str
    kw: float
    kvar: float = 0.0


def fuentes_del_caso(caso: Caso, alimentador: str) -> tuple[FuenteMedida, ...]:
    """Sin datos por fuente, la inyección del caso con el nombre del alimentador (063:RF-55)."""
    if not caso.converge or caso.fuente is None:
        return ()
    return (FuenteMedida(alimentador, caso.fuente.kw, caso.fuente.kvar),)


def _caso_cuantitativo(titulo: str, caso: Caso, limites: Limites, nominal: float | None) -> str:
    """Las cifras de un caso, o solo su demanda nominal si no converge: sin valores inventados."""
    if not caso.converge:
        demanda = f' Su demanda nominal es de {numero(nominal, 0)} kW.' if nominal is not None else ''
        return (f'{titulo}: el flujo no converge, de modo que no hay tensiones, cargabilidades ni pérdidas '
                f'que informar.{demanda}')
    partes = [f'{titulo}: el flujo converge con una inyección de {numero(caso.fuente.kw, 0)} kW y '
              f'{numero(caso.fuente.kvar, 0)} kvar']
    if caso.perdidas is not None:
        pct = f' ({numero(100 * caso.perdidas.kw / caso.fuente.kw, 2)} %)' if caso.fuente.kw > 0 else ''
        partes.append(f' y pérdidas de {numero(caso.perdidas.kw, 0)} kW{pct}')
    if nominal is not None:
        partes.append(f', para una demanda nominal de {numero(nominal, 0)} kW')
    partes.append('.')
    if caso.minima is not None:
        partes.append(f' La tensión mínima es de {formato_pu(caso.minima.valor)} en {caso.minima.donde}')
        if caso.tension_max is not None:
            partes.append(f' y la máxima de {formato_pu(caso.tension_max.valor)} en {caso.tension_max.donde}')
        partes.append(f'; {caso.nodos_fuera} nodos quedan fuera de {_g(limites.tension_min_pu)}–'
                      f'{_g(limites.tension_max_pu)} p.u.')
    if caso.cargabilidad_max is not None:
        partes.append(f' La mayor cargabilidad de línea es de {numero(caso.cargabilidad_max.valor, 1)} % en '
                      f'{caso.cargabilidad_max.donde} ({caso.tramos_sobre} tramos sobre '
                      f'{_g(limites.cargabilidad_max_pct)} %).')
    if caso.trafo_max is not None:
        partes.append(f' El transformador más cargado llega a {numero(caso.trafo_max.valor, 1)} % en '
                      f'{caso.trafo_max.donde}.')
    partes.append(' Cumple los límites evaluados.' if caso.cumple(limites) else ' No cumple los límites evaluados.')
    return ''.join(partes)


def conclusiones_por_caso(actual: Caso, cargas: Caso, proyectado: Caso, limites: Limites, *,
                          nominal_kw: Mapping[str, float] | None = None) -> list[str]:
    """Un párrafo por caso con sus resultados y su comparación con el estado actual (063:RF-54)."""
    nominal = nominal_kw or {}
    textos = [_caso_cuantitativo('Estado actual (Sin proyecto)', actual, limites, nominal.get('actual')),
              _caso_cuantitativo('Con la carga analizada, sin obras (Cargas nuevas)', cargas, limites, nominal.get('cargas')),
              _caso_cuantitativo('Con las obras (Con proyecto)', proyectado, limites, nominal.get('proyectado'))]
    if not (actual.converge and proyectado.converge and actual.minima and proyectado.minima):
        textos.append('Frente al estado actual no se compara el estado proyectado: falta un flujo convergido.')
        return textos
    cambio = proyectado.minima.valor - actual.minima.valor
    verbo = 'sube' if cambio >= 0 else 'baja'
    texto = (f'Frente al estado actual, con las obras la tensión mínima {verbo} {numero(abs(cambio), 3)} p.u. '
             f'(de {formato_pu(actual.minima.valor)} a {formato_pu(proyectado.minima.valor)}) y los nodos fuera de la banda '
             f'pasan de {actual.nodos_fuera} a {proyectado.nodos_fuera}.')
    if cargas.converge and cargas.minima:
        solo = cargas.minima.valor - actual.minima.valor
        texto += (f' Solo con la carga analizada y sin obras, la tensión mínima sería de {formato_pu(cargas.minima.valor)}, '
                  f'{numero(abs(solo), 3)} p.u. {"más" if solo >= 0 else "menos"} que en el estado actual.')
    textos.append(texto)
    return textos


def _variacion(antes: float, despues: float) -> str:
    if abs(antes) < 0.5:
        return ''
    return f' ({numero(100 * (despues - antes) / antes, 1)} %)'


def demanda_antes_despues(antes: Sequence[FuenteMedida], despues: Sequence[FuenteMedida]
                          ) -> tuple[list[list[str]], list[str]]:
    """Filas y conclusiones de la demanda por fuente antes y después del proyecto (063:RF-55).

    Filas: fuente, kW y kvar antes, kW y kvar después, variación en kW y en %.
    """
    previa = {f.nombre: f for f in antes}
    posterior = {f.nombre: f for f in despues}
    nombres = list(previa) + [n for n in posterior if n not in previa]
    filas, textos = [], []
    for n in nombres:
        a, d = previa.get(n), posterior.get(n)
        kw_a, kw_d = a.kw if a else 0.0, d.kw if d else 0.0
        var = 100 * (kw_d - kw_a) / kw_a if a and abs(kw_a) >= 0.5 else None
        filas.append([n, numero(kw_a, 0) if a else '—', numero(a.kvar, 0) if a else '—',
                      numero(kw_d, 0) if d else '—', numero(d.kvar, 0) if d else '—',
                      numero(kw_d - kw_a, 0), numero(var, 1) if var is not None else '—'])
        if a is None or abs(kw_a) < 0.5:
            textos.append(f'{n} entra al servicio con {numero(kw_d, 0)} kW y {numero(d.kvar, 0)} kvar.')
        elif d is None or abs(kw_d) < 0.5:
            textos.append(f'{n} deja de inyectar los {numero(kw_a, 0)} kW que aportaba antes del proyecto.')
        else:
            verbo = 'baja' if kw_d < kw_a else 'sube'
            textos.append(f'{n} {verbo} de {numero(kw_a, 0)} kW a {numero(kw_d, 0)} kW{_variacion(kw_a, kw_d)}.')
    total_a, total_d = sum(f.kw for f in antes), sum(f.kw for f in despues)
    q_a, q_d = sum(f.kvar for f in antes), sum(f.kvar for f in despues)
    var = 100 * (total_d - total_a) / total_a if abs(total_a) >= 0.5 else None
    filas.append(['Total', numero(total_a, 0), numero(q_a, 0), numero(total_d, 0), numero(q_d, 0),
                  numero(total_d - total_a, 0), numero(var, 1) if var is not None else '—'])
    textos.append(f'En conjunto, la inyección pasa de {numero(total_a, 0)} kW a {numero(total_d, 0)} kW'
                  f'{_variacion(total_a, total_d)}.')
    return filas, textos


def demanda_por_alimentador(filas: Sequence[Mapping[str, Any]]) -> tuple[list[list[str]], list[str]]:
    """Lo que atiende cada alimentador antes y después, por su cabecera y por la SET nueva (063:RF-55).

    Tras trasladar ramas, la cabecera sola engaña: NA203 pasó de 10 061 kW a 341 kW por la suya,
    pero su zona atiende más demanda que antes, por las salidas de COPARA (2026-11-02).
    """
    tabla, textos = [], []
    for f in filas:
        total = f['cabecera_kw'] + f['salidas_kw']
        tabla.append([f['alimentador'], numero(f['antes_kw'], 0), numero(f['cabecera_kw'], 0), numero(f['salidas_kw'], 0),
                      numero(total, 0), numero(total - f['antes_kw'], 0), numero(f.get('nuevas_kw', 0.0), 0)])
        pct = numero(100 * f['salidas_kw'] / total, 1) if total > 0 else '0'
        textos.append(f'{f["alimentador"]}: antes del proyecto se atendían {numero(f["antes_kw"], 0)} kW en su zona. '
                      f'Después se atienden {numero(total, 0)} kW: {numero(f["cabecera_kw"], 0)} kW por su cabecera y '
                      f'{numero(f["salidas_kw"], 0)} kW ({pct} %) por las salidas de la SET nueva'
                      + (f', con {numero(f["nuevas_kw"], 0)} kW de cargas nuevas.' if f.get('nuevas_kw') else '.'))
    return tabla, textos
