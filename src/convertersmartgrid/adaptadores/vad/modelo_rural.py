"""Modelo georreferenciado rural del Anexo 6 de los TdR del VAD: la red real, sin mover un vértice (spec 108, RF-5).

El Anexo 6 «mantiene inalterada la traza de la red real» y «considera los kilómetros reales de red en MT y BT,
diferenciando entre longitud de red troncal y derivaciones», con «los valores reales de cantidad de SED y su
capacidad instalada (kVA)» (regla ``vad.anexo6.traza_real`` de ``config/vad/anexo6_rural.json``, que completa a
``vad.anexo6.trazas``: «Se respetarán las trazas de las líneas de acuerdo a la situación existente»). Este módulo
copia esa red, en solo lectura, de una de dos fuentes:

- el VNR canónico (``adaptadores.entrada.vnr.models.canonical.CanonicalModel``), con la geometría GeoJSON de cada
  ``Section`` leída por ``gis.geometry.coords_from_geojson``;
- la vía TXT o MDB: cada ``FeederModel`` con su ``GeographyManifest`` de ``geography.build_geography``, cuyos puntos
  conservan la ``x`` y la ``y`` del CRS de origen.

Cada tramo lleva la huella de sus vértices (:func:`hash_vertices`), calculada sobre las coordenadas del CRS de
origen y nunca sobre WGS84, porque la reproyección cambia los últimos dígitos (plan de la 108, «Decisiones»). Un
tramo cuyos vértices no casan con su huella no se puede construir, y :func:`comprobar_trazas` rechaza un modelo cuya
traza ya no es la de su fuente. La troncal y las derivaciones salen de ``troncal.troncal`` (spec 016), por nivel de
tensión y por componente conexa. Un tramo sin geometría se nombra y no recibe vértices inventados. La parte urbana de
un sistema mixto queda «sin modelar (anexo 5 pendiente)». El equipamiento de la empresa modelo (conductor y potencia
de cada SED) no se decide aquí: es la T6, sobre este modelo.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..entrada.vnr.gis.geometry import (
    coords_from_geojson,
    polyline_length_m,
)
from ..entrada.vnr.models.canonical import CanonicalModel
from ..geography import GeographyManifest
from ...dominio.model import FeederModel
from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.troncal import Barra, Tramo, TroncalError, red_de, troncal
from ...aplicacion.vad import VadError

#: Regla del registro en la que se apoya el modelo: sin ella no se arma (108:RF-9).
REGLA_TRAZA = 'vad.anexo6.traza_real'
SIN_MODELAR_URBANO = 'sin modelar (anexo 5 pendiente)'
AMBITOS = ('rural', 'urbano')
#: Por debajo de esta tensión (kV) el tramo es de BT; desde ella, de MT.
KV_LIMITE_BT = 1.0

Vertice = tuple[float, float]


def hash_vertices(vertices: Sequence[Sequence[float]]) -> str:
    """SHA-256 de los vértices de un tramo, en su orden y con ``repr`` de cada ``float`` (108:RF-5).

    ``repr`` es la representación más corta que vuelve al mismo ``float``: dos trazas tienen la misma huella solo si
    cada coordenada es idéntica bit a bit. Un vértice no finito no tiene huella.
    """
    partes = []
    for i, punto in enumerate(vertices):
        if len(punto) != 2:
            raise VadError(f'el vértice {i} tiene {len(punto)} coordenadas; se esperan dos (x, y)')
        x, y = float(punto[0]), float(punto[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise VadError(f'el vértice {i} no es finito: ({x!r}, {y!r})')
        partes.append(f'{x!r},{y!r}')
    return hashlib.sha256(';'.join(partes).encode('ascii')).hexdigest()


@dataclass(frozen=True)
class TramoRural:
    """Un tramo de la red real, con su traza intacta y su huella."""

    tramo: str
    alimentador: str
    desde: str
    hasta: str
    nivel: str
    """``MT``, ``BT`` o ``sin_tension`` (la fuente no da la tensión del tramo)."""
    tension_kv: float | None
    fases: str
    longitud_m: float | None
    longitud_origen: str
    """``fuente`` (la longitud del VNR o del TXT), ``traza`` (calculada de los vértices) o ``sin_longitud``."""
    vertices: tuple[Vertice, ...]
    huella: str
    clase: str = ''
    """``troncal``, ``derivacion`` o ``sin_cabecera``; vacío para un tramo sin tensión."""
    en_servicio: bool = True

    def __post_init__(self) -> None:
        if self.vertices and hash_vertices(self.vertices) != self.huella:
            raise VadError(f'el tramo {self.tramo} tiene vértices que no son los de su huella: la traza real no se '
                           f'altera (vad.anexo6.trazas)')
        if not self.vertices and self.huella:
            raise VadError(f'el tramo {self.tramo} no tiene geometría y no puede tener huella')


@dataclass(frozen=True)
class SedRural:
    sed: str
    nodo: str
    alimentador: str
    kva: float | None
    """La potencia instalada real; ``None`` si la fuente no la da (hueco nombrado en ``huecos``)."""


@dataclass(frozen=True)
class ModeloRural:
    """La red rural real de la empresa, lista para el dimensionamiento de la T6."""

    tramos: tuple[TramoRural, ...]
    sed: tuple[SedRural, ...]
    crs_origen: str
    fuente: str
    """``vnr`` o ``txt``."""
    fundamento: str
    """Huella de la regla :data:`REGLA_TRAZA` con la que se armó."""
    sin_geometria: tuple[str, ...] = ()
    """Tramos que la fuente trae sin traza: se nombran y no reciben vértices."""
    sin_modelar: Mapping[str, str] = field(default_factory=dict)
    """Alimentador urbano → :data:`SIN_MODELAR_URBANO`."""
    sistemas_mixtos: tuple[str, ...] = ()
    huecos: tuple[str, ...] = ()

    @property
    def completo(self) -> bool:
        """Falso si algo queda sin modelar: el estudio de ese sistema no se emite como completo."""
        return not (self.sin_modelar or self.sin_geometria or self.huecos)

    def tramo(self, nombre: str) -> TramoRural:
        for t in self.tramos:
            if t.tramo == nombre:
                return t
        raise VadError(f'el tramo {nombre} no está en el modelo rural')

    def km(self) -> dict[tuple[str, str, str], float]:
        """(alimentador, nivel, clase) → km reales. Los tramos sin longitud no suman y están en ``huecos``."""
        out: dict[tuple[str, str, str], float] = {}
        for t in self.tramos:
            if t.longitud_m is not None:
                clave = (t.alimentador, t.nivel, t.clase)
                out[clave] = out.get(clave, 0.0) + t.longitud_m / 1000.0
        return out


@dataclass(frozen=True)
class _Crudo:
    tramo: str
    alimentador: str
    desde: str
    hasta: str
    tension_kv: float | None
    fases: str
    longitud_m: float | None
    vertices: tuple[Vertice, ...] | None
    en_servicio: bool


def _nivel(kv: float | None) -> str:
    if kv is None:
        return 'sin_tension'
    return 'BT' if kv < KV_LIMITE_BT else 'MT'


def _ambito_de(alimentador: str, ambito: Mapping[str, str] | None) -> str:
    if ambito is None:
        return 'rural'
    try:
        valor = ambito[alimentador]
    except KeyError:
        raise VadError(f'el alimentador {alimentador} no tiene ámbito (rural o urbano): sale del sector típico del '
                       f'perfil y no se supone') from None
    if valor not in AMBITOS:
        raise VadError(f'el alimentador {alimentador} tiene ámbito {valor!r}; los válidos son {AMBITOS}')
    return valor


def _componentes(crudos: Sequence[_Crudo]) -> list[list[_Crudo]]:
    """Componentes conexas por los extremos de los tramos, en un orden que no depende de la entrada."""
    padre: dict[str, str] = {}

    def raiz(n: str) -> str:
        while padre.setdefault(n, n) != n:
            padre[n] = padre[padre[n]]
            n = padre[n]
        return n

    for c in crudos:
        a, b = raiz(c.desde), raiz(c.hasta)
        if a != b:
            padre[max(a, b)] = min(a, b)
    grupos: dict[str, list[_Crudo]] = {}
    for c in crudos:
        grupos.setdefault(raiz(c.desde), []).append(c)
    return [sorted(g, key=lambda c: c.tramo) for _, g in sorted(grupos.items())]


def _clases(crudos: Sequence[_Crudo], cabeceras: Iterable[str]) -> dict[str, str]:
    """Tramo → ``troncal``, ``derivacion`` o ``sin_cabecera``, con ``troncal.troncal`` en cada componente."""
    cabeceras = set(cabeceras)
    out: dict[str, str] = {}
    for comp in _componentes(crudos):
        nodos = {c.desde for c in comp} | {c.hasta for c in comp}
        propias = sorted(nodos & cabeceras)
        if not propias:
            out.update((c.tramo, 'sin_cabecera') for c in comp)
            continue
        tramos = [Tramo(c.tramo, c.desde, c.hasta, c.longitud_m or 0.0, cerrado=c.en_servicio and c.longitud_m
                        is not None) for c in comp]
        try:
            del_troncal = set(troncal(red_de([Barra(n) for n in sorted(nodos)], tramos), propias[0]).tramos)
        except TroncalError as exc:
            raise VadError(f'troncal del componente de {propias[0]}: {exc}') from exc
        out.update((c.tramo, 'troncal' if c.tramo in del_troncal else 'derivacion') for c in comp)
    return out


def _armar(crudos: Sequence[_Crudo], sed: Sequence[SedRural], cabeceras_mt: Iterable[str], *,
           sistema_de: Mapping[str, str], ambito: Mapping[str, str] | None, crs: str, fuente: str,
           fundamento: str) -> ModeloRural:
    vistos: set[str] = set()
    for c in crudos:
        if c.tramo in vistos:
            raise VadError(f'el tramo {c.tramo} está dos veces en la fuente')
        vistos.add(c.tramo)
    huecos = [f'SED {s.sed}: su nodo {s.nodo} no está en ningún tramo; no se asigna a un alimentador'
              for s in sed if not s.alimentador]
    sed = [s for s in sed if s.alimentador]
    alimentadores = sorted({c.alimentador for c in crudos} | {s.alimentador for s in sed})
    ambitos = {a: _ambito_de(a, ambito) for a in alimentadores}
    sin_modelar = {a: SIN_MODELAR_URBANO for a in alimentadores if ambitos[a] == 'urbano'}
    por_sistema: dict[str, set[str]] = {}
    for a in alimentadores:
        por_sistema.setdefault(sistema_de.get(a, ''), set()).add(ambitos[a])
    mixtos = tuple(sorted(s for s, v in por_sistema.items() if s and len(v) > 1))
    rurales = [c for c in crudos if ambitos[c.alimentador] == 'rural']
    sed_rural = tuple(s for s in sed if ambitos[s.alimentador] == 'rural')
    clases: dict[str, str] = {}
    for nivel, cabeceras in (('MT', set(cabeceras_mt)), ('BT', {s.nodo for s in sed_rural})):
        clases.update(_clases([c for c in rurales if _nivel(c.tension_kv) == nivel], cabeceras))
    tramos = []
    for c in rurales:
        vertices = c.vertices or ()
        if c.longitud_m is not None:
            largo, origen = c.longitud_m, 'fuente'
        elif len(vertices) >= 2:
            largo, origen = polyline_length_m(vertices), 'traza'
        else:
            largo, origen = None, 'sin_longitud'
            huecos.append(f'tramo {c.tramo}: sin longitud ni traza; no suma km')
        nivel = _nivel(c.tension_kv)
        if nivel == 'sin_tension':
            huecos.append(f'tramo {c.tramo}: la fuente no da su tensión; no se sabe si es MT o BT')
        clase = clases.get(c.tramo, '')
        if clase == 'sin_cabecera':
            huecos.append(f'tramo {c.tramo}: su red {nivel} no llega a ninguna cabecera ni SED; no es troncal ni '
                          f'derivación')
        tramos.append(TramoRural(c.tramo, c.alimentador, c.desde, c.hasta, nivel, c.tension_kv, c.fases, largo,
                                 origen, vertices, hash_vertices(vertices) if vertices else '', clase, c.en_servicio))
    huecos.extend(f'SED {s.sed}: la fuente no da su potencia instalada (kVA)' for s in sed_rural if s.kva is None)
    sin_geometria = tuple(sorted(c.tramo for c in rurales if not c.vertices))
    return ModeloRural(tuple(sorted(tramos, key=lambda t: t.tramo)), tuple(sorted(sed_rural, key=lambda s: s.sed)),
                       crs, fuente, fundamento, sin_geometria, dict(sorted(sin_modelar.items())), mixtos,
                       tuple(huecos))


def _desde_vnr(vnr: CanonicalModel) -> tuple[list[_Crudo], list[SedRural], set[str], dict[str, str]]:
    crudos = []
    alimentador_de_nodo: dict[str, str] = {}
    for s in vnr.sections:
        vertices = tuple(coords_from_geojson(s.geometry)) if s.geometry is not None else ()
        crudos.append(_Crudo(s.section_id, s.feeder_id, s.from_node, s.to_node, s.nominal_kv, s.phases, s.length_m,
                             vertices or None, s.status == 'in_service'))
        for n in (s.from_node, s.to_node):
            alimentador_de_nodo.setdefault(n, s.feeder_id)
    sed = [SedRural(t.transformer_id, t.connection_node, alimentador_de_nodo.get(t.connection_node, ''), t.sn_kva)
           for t in vnr.transformers]
    sistema_de = {f.feeder_id: f.system_id for f in vnr.feeders}
    return crudos, sed, {f.node_id for f in vnr.sources}, sistema_de


def _desde_txt(redes: Iterable[tuple[FeederModel, GeographyManifest]]
               ) -> tuple[list[_Crudo], list[SedRural], set[str], dict[str, str], str]:
    crudos: list[_Crudo] = []
    sed: list[SedRural] = []
    cabeceras: set[str] = set()
    crs = set()
    for modelo, geo in redes:
        crs.add(geo.source_crs)
        cabeceras.add(modelo.source_node)
        for linea in modelo.lines:
            g = geo.lines.get(linea.section_id)
            vertices: tuple[Vertice, ...] | None = None
            if g is not None:
                if any(p.x is None or p.y is None for p in g.path):
                    raise VadError(f'el tramo {linea.section_id} trae puntos sin la x o la y del CRS de origen: la '
                                   f'huella no se calcula sobre WGS84')
                vertices = tuple((float(p.x), float(p.y)) for p in g.path)
            crudos.append(_Crudo(linea.section_id, modelo.name, linea.from_node, linea.to_node, modelo.nominal_kv,
                                 linea.phase, linea.length_m, vertices, True))
        sed.extend(SedRural(s.code, s.node_id, modelo.name, s.design_kva) for s in modelo.seds)
    if len(crs) > 1:
        raise VadError(f'las redes vienen en CRS distintos {sorted(crs)}: un modelo, un CRS de origen')
    return crudos, sed, cabeceras, {}, next(iter(crs), '')


def _fundamento(registro: RegistroNormativo) -> str:
    try:
        return registro.regla(REGLA_TRAZA).huella()
    except RegistroError as exc:
        raise VadError(f'el modelo rural se apoya en la regla {REGLA_TRAZA} del Anexo 6: {exc}') from exc


def armar_modelo_rural(fuente: CanonicalModel | Iterable[tuple[FeederModel, GeographyManifest]], *,
                       registro: RegistroNormativo, ambito: Mapping[str, str] | None = None,
                       sistema_de: Mapping[str, str] | None = None, crs_origen: str | None = None) -> ModeloRural:
    """La red real de la fuente, en solo lectura, con la huella de cada tramo y la troncal y las derivaciones (108:RF-5).

    ``fuente`` es el VNR canónico o los pares (``FeederModel``, ``GeographyManifest``) de la vía TXT o MDB.
    ``ambito`` da «rural» o «urbano» por alimentador (sale del sector típico del perfil); sin él, todo es rural. Los
    alimentadores urbanos quedan en ``sin_modelar``. ``sistema_de`` da el sistema eléctrico de cada alimentador
    cuando la fuente no lo trae (la vía TXT); el del VNR canónico sale de sus ``Feeder``. ``crs_origen`` es el del VNR canónico si su ``metadata`` no lo
    trae; en la vía TXT sale de la geografía.
    """
    fundamento = _fundamento(registro)
    if isinstance(fuente, CanonicalModel):
        crudos, sed, cabeceras, sistemas = _desde_vnr(fuente)
        crs = crs_origen or str(fuente.metadata.get('crs') or '')
        origen = 'vnr'
    else:
        crudos, sed, cabeceras, sistemas, crs = _desde_txt(fuente)
        crs = crs_origen or crs
        origen = 'txt'
    if not crs:
        raise VadError('el modelo rural necesita el CRS de origen de las trazas: la huella vale solo en ese CRS')
    return _armar(crudos, sed, cabeceras, sistema_de={**sistemas, **(sistema_de or {})}, ambito=ambito, crs=crs, fuente=origen,
                  fundamento=fundamento)


def comprobar_trazas(modelo: ModeloRural, fuente: CanonicalModel | Iterable[tuple[FeederModel, GeographyManifest]]
                     ) -> None:
    """Rechaza el modelo si la traza de algún tramo ya no es, bit a bit, la de la fuente (108:RF-5).

    Nombra los tramos cuya huella cambió y los que tienen traza en uno y no en la otra.
    """
    if isinstance(fuente, CanonicalModel):
        crudos = _desde_vnr(fuente)[0]
    else:
        crudos = _desde_txt(fuente)[0]
    esperadas = {c.tramo: hash_vertices(c.vertices) if c.vertices else '' for c in crudos}
    distintos = sorted(t.tramo for t in modelo.tramos if esperadas.get(t.tramo, None) != t.huella)
    if distintos:
        raise VadError(f'la traza de {len(distintos)} tramo(s) no es la de la fuente: {", ".join(distintos[:20])}'
                       f'{" …" if len(distintos) > 20 else ""}. Se respetarán las trazas (vad.anexo6.trazas)')
