"""Reconstrucción del modelo canónico VNR-GIS antes de pasarlo al motor.

Un paquete VNR-GIS real rara vez llega completo: tramos sin alimentador, una fuente
sin tensión, fases vacías, longitudes que solo están en la geometría, cargas colgadas
de un nodo que no toca ningún tramo, o coordenadas en grados. Tras la spec 001 (T10)
el export se negaba en esos casos y el usuario se quedaba sin red. El conversor tiene
que reconstruir y exportar (spec 001, RF-17), así que aquí se completa lo que el
puente (:mod:`vnr_etl.application.cymdist_bridge`) no puede traducir por sí solo.

Reglas:

* Nada se completa sin dejar constancia: cada cambio es una
  :class:`igea_dgs.reconstruction.ReconstructionDecision`, con el valor original, el
  aplicado, la regla y la confianza, en el mismo formato que la reconstrucción de la web.
* Determinista: todo se recorre en orden de identificador, para que el mismo paquete
  dé el mismo DGS (constitución P1).
* Lo que es del catálogo de conductores no se decide aquí: lo resuelve el motor
  (:func:`igea_dgs.reconstruction_pipeline.reconstruir_seleccion`), que usa el catálogo
  de parámetros antes que cualquier supuesto (RF-18).
* Ningún CRS ni tensión de una empresa concreta como valor por defecto (P13): la zona
  UTM sale de las propias coordenadas y la tensión provisional, de la política.
"""

from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from igea_dgs.reconstruction import EvidenceLevel, ReconstructionDecision, ReconstructionPolicy
from vnr_etl.gis.crs import parecen_grados
from vnr_etl.models import CanonicalModel, Source
from vnr_etl.pipeline import suggest_utm_crs

SUPUESTO = EvidenceLevel.ENGINEERING_ASSUMPTION
FASES_POR_DEFECTO = 'ABC'
LONGITUD_MINIMA_M = 1.0


@dataclass
class ModeloReconstruido:
    model: CanonicalModel
    decisiones: list[ReconstructionDecision] = field(default_factory=list)
    # CRS métrico con que el motor reproyecta a GPS, o None para exportar sin geografía.
    source_crs: str | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def include_geography(self) -> bool:
        return self.source_crs is not None

    def anotar(self, entity_type: str, entity_id: str, campo: str, antes: Any, despues: Any,
               regla: str, motivo: str, confianza: float, **procedencia: Any) -> None:
        decision = ReconstructionDecision(
            entity_type=entity_type, entity_id=str(entity_id), field=campo,
            original_value=deepcopy(antes), applied_value=deepcopy(despues),
            level=SUPUESTO, rule=regla, reason=motivo, confidence=confianza,
            provenance=procedencia,
        )
        decision.validate()
        self.decisiones.append(decision)


def reconstruir_modelo(
    model: CanonicalModel,
    *,
    nombre: str,
    policy: ReconstructionPolicy | None = None,
) -> ModeloReconstruido:
    """Devuelve una copia del modelo con los datos ausentes completados y anotados."""
    politica = policy or ReconstructionPolicy()
    out = ModeloReconstruido(model=CanonicalModel.from_dict(deepcopy(model.to_dict())))
    _procedencia(out, nombre)
    _crs(out)
    _alimentadores_de_tramos(out, nombre)
    _fuentes(out, politica)
    _fases(out)
    _longitudes(out)
    _cargas(out)
    return out


# --------------------------------------------------------------------------- procedencia
# Los campos que el manifiesto de procedencia exige (los de exporters.dgs.PROVENANCE_FIELDS).
CAMPOS_PROCEDENCIA = (
    'source_publication_id', 'source_company', 'source_period', 'source_url',
    'source_sha256', 'retrieved_at', 'schema_fingerprint',
    'source_fingerprint', 'canonical_model_version',
)
DESCONOCIDO = 'DESCONOCIDO'


def _procedencia(out: ModeloReconstruido, nombre: str) -> None:
    """RF-22: la procedencia que falta se deriva del propio modelo y se marca.

    Un modelo armado a mano o por otra herramienta no trae la procedencia de una
    descarga oficial, y por eso se negaba el export. Lo que se puede calcular (la huella
    del modelo) se calcula; lo que no, queda como ``DESCONOCIDO``, nunca inventado.
    """
    import hashlib
    import json

    meta = out.model.metadata
    faltan = [campo for campo in CAMPOS_PROCEDENCIA if not meta.get(campo)]
    if not faltan:
        return
    contenido = {k: v for k, v in out.model.to_dict().items() if k != 'metadata'}
    huella = hashlib.sha256(json.dumps(
        contenido, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')).hexdigest()
    from vnr_etl import __version__

    derivables = {
        'source_fingerprint': huella,
        'source_sha256': huella,
        'schema_fingerprint': huella,
        'source_publication_id': f'DIRECT-{huella[:16]}',
        'canonical_model_version': __version__,
    }
    for campo in faltan:
        valor = derivables.get(campo, DESCONOCIDO)
        out.anotar('model', 'metadata', campo, meta.get(campo), valor,
                   'DERIVED_PROVENANCE' if campo in derivables else 'UNKNOWN_PROVENANCE',
                   'Procedencia ausente: huella del propio modelo.' if campo in derivables
                   else 'Procedencia ausente y no derivable: se marca como desconocida.',
                   0.9 if campo in derivables else 0.0)
        meta[campo] = valor
    meta['procedencia_reconstruida'] = sorted(faltan)
    out.avisos.append('Procedencia incompleta: ' + ', '.join(faltan) + ' (ver decisiones).')


# --------------------------------------------------------------------------- CRS
def _crs(out: ModeloReconstruido) -> None:
    """RF-20: CRS proyectado tal cual; geográfico → su zona UTM; desconocido → sin GPS."""
    meta = out.model.metadata
    crs = str(meta.get('working_crs') or '').strip()
    if crs and meta.get('working_crs_is_projected') is True:
        out.source_crs = crs
        return
    puntos = [(n.x, n.y) for n in out.model.nodes if _finito(n.x) and _finito(n.y)]
    try:
        from pyproj import CRS
    except ImportError:
        out.avisos.append('Sin pyproj no se puede reproyectar: se exporta sin georreferenciación.')
        return
    origen = None
    if crs:
        try:
            parsed = CRS.from_user_input(crs)
        except Exception:  # noqa: BLE001 - un CRS ilegible se trata como desconocido
            parsed = None
        if parsed is not None and parsed.is_projected:
            # Declarado proyectado por su definición aunque el paquete no lo marcara.
            out.source_crs = crs
            meta['working_crs_is_projected'] = True
            return
        if parsed is not None and parsed.is_geographic:
            origen = crs
    elif parecen_grados(puntos):
        origen = 'EPSG:4326'
    if origen is None or not puntos:
        out.avisos.append(
            'El modelo no declara un CRS proyectado y no se puede deducir: se exporta sin '
            'georreferenciación, con las longitudes del modelo.')
        out.anotar('model', 'metadata', 'working_crs', crs or None, '(sin georreferenciación)',
                   'EXPORT_WITHOUT_GEOGRAPHY', 'CRS desconocido o no proyectado.', 0.5)
        return
    lon = sum(p[0] for p in puntos) / len(puntos)
    lat = sum(p[1] for p in puntos) / len(puntos)
    destino = suggest_utm_crs(lon, lat)
    from igea_dgs.geography import make_transformer

    transformer = make_transformer(origen, destino)
    for node in out.model.nodes:
        if _finito(node.x) and _finito(node.y):
            node.x, node.y = transformer.transform(float(node.x), float(node.y))
    for section in out.model.sections:
        section.geometry = _reproyectar(section.geometry, transformer)
    meta['working_crs'] = destino
    meta['working_crs_is_projected'] = True
    out.source_crs = destino
    out.anotar('model', 'metadata', 'working_crs', crs or None, destino,
               'REPROJECT_TO_UTM',
               f'Coordenadas en grados ({origen}); se reproyectan a su zona UTM ({destino}) '
               'para medir longitudes en metros.',
               0.9 if crs else 0.6, origen=origen)


def _reproyectar(geometry: Any, transformer) -> Any:
    if isinstance(geometry, (list, tuple)) and geometry:
        if all(isinstance(p, (list, tuple)) and len(p) >= 2 and _finito(p[0]) and _finito(p[1])
               for p in geometry):
            return [list(transformer.transform(float(p[0]), float(p[1]))) for p in geometry]
        return [_reproyectar(part, transformer) for part in geometry]
    return geometry


# --------------------------------------------------------------------------- alimentadores
def _alimentadores_de_tramos(out: ModeloReconstruido, nombre: str) -> None:
    """Un tramo sin alimentador toma el del más cercano por la red; si no hay, uno nuevo."""
    sections = sorted(out.model.sections, key=lambda s: s.section_id)
    por_nodo: dict[str, list[int]] = defaultdict(list)
    for index, section in enumerate(sections):
        por_nodo[section.from_node].append(index)
        por_nodo[section.to_node].append(index)

    def vecinos(index: int):
        s = sections[index]
        for node in (s.from_node, s.to_node):
            for other in por_nodo[node]:
                if other != index:
                    yield other

    asignado = {i: s.feeder_id.strip() for i, s in enumerate(sections) if s.feeder_id.strip()}
    if len(asignado) == len(sections):
        return
    # Propagación por saltos, de todos los tramos con alimentador a la vez: gana el más
    # cercano y, a igual distancia, el de nombre menor. Es un BFS multiorigen ordenado.
    cola = [(0, asignado[i], i) for i in sorted(asignado)]
    heapq.heapify(cola)
    distancia = {i: 0 for i in asignado}
    while cola:
        d, feeder, index = heapq.heappop(cola)
        if asignado.get(index) != feeder or distancia.get(index, d) < d:
            continue
        for other in vecinos(index):
            if other in asignado and distancia[other] <= d + 1:
                continue
            asignado[other] = feeder
            distancia[other] = d + 1
            heapq.heappush(cola, (d + 1, feeder, other))

    # Lo que queda sin alimentador son islas sin ninguno: cada una, el suyo.
    sueltos = [i for i in range(len(sections)) if i not in asignado]
    fuentes_por_nodo: dict[str, list[Source]] = defaultdict(list)
    for source in sorted(out.model.sources, key=lambda s: s.source_id):
        fuentes_por_nodo[source.node_id].append(source)
    islas: list[list[int]] = []
    vistos: set[int] = set()
    for inicio in sueltos:
        if inicio in vistos:
            continue
        isla, pila = [], [inicio]
        vistos.add(inicio)
        while pila:
            index = pila.pop()
            isla.append(index)
            for other in vecinos(index):
                if other not in vistos and other not in asignado:
                    vistos.add(other)
                    pila.append(other)
        islas.append(sorted(isla))
    existentes = set(asignado.values())
    for numero, isla in enumerate(islas, start=1):
        fuente = next((f for i in isla for node in (sections[i].from_node, sections[i].to_node)
                       for f in fuentes_por_nodo.get(node, ())), None)
        if fuente is not None:
            feeder = (fuente.feeder_id or fuente.source_id).strip()
        elif not existentes and len(islas) == 1:
            feeder = nombre
        else:
            feeder = f'{nombre}_{numero}'
        for index in isla:
            asignado[index] = feeder
            distancia[index] = -1
    for index, section in enumerate(sections):
        if section.feeder_id.strip():
            continue
        section.feeder_id = asignado[index]
        propagado = distancia.get(index, -1) > 0
        out.anotar(
            'section', section.section_id, 'feeder_id', '', section.feeder_id,
            'FEEDER_BY_CONNECTIVITY' if propagado else 'FEEDER_FOR_ISLAND',
            ('Alimentador del tramo con alimentador más cercano por la red.' if propagado
             else 'Isla sin alimentador declarado: se le asigna uno propio.'),
            0.8 if propagado else 0.4,
        )


# --------------------------------------------------------------------------- fuentes y tensión
def _fuentes(out: ModeloReconstruido, politica: ReconstructionPolicy) -> None:
    model = out.model
    tramos_por_feeder: dict[str, list] = defaultdict(list)
    feeders_por_nodo: dict[str, set[str]] = defaultdict(set)
    for section in sorted(model.sections, key=lambda s: s.section_id):
        tramos_por_feeder[section.feeder_id].append(section)
        feeders_por_nodo[section.from_node].add(section.feeder_id)
        feeders_por_nodo[section.to_node].add(section.feeder_id)
    nodos = model.nodes_by_id()

    for source in sorted(model.sources, key=lambda s: s.source_id):
        if source.feeder_id.strip():
            continue
        candidatos = sorted(feeders_por_nodo.get(source.node_id, ()))
        if candidatos:
            source.feeder_id = candidatos[0]
            out.anotar('source', source.source_id, 'feeder_id', '', source.feeder_id,
                       'FEEDER_BY_CONNECTIVITY', 'Alimentador de los tramos que salen de la fuente.',
                       0.8 if len(candidatos) == 1 else 0.5, candidatos=candidatos)

    # El puente admite una fuente por alimentador: se conserva la primera y las demás
    # se anotan, en vez de que el export reviente con «más de una fuente».
    por_feeder: dict[str, list[Source]] = defaultdict(list)
    for source in sorted(model.sources, key=lambda s: s.source_id):
        por_feeder[source.feeder_id].append(source)
    conservadas = []
    for feeder, fuentes in sorted(por_feeder.items()):
        conservadas.append(fuentes[0])
        for extra in fuentes[1:]:
            out.anotar('source', extra.source_id, '__row__', extra.node_id, None,
                       'DROP_EXTRA_SOURCE',
                       f'El alimentador {feeder} ya tiene la fuente {fuentes[0].source_id}.', 0.5)
    model.sources = conservadas
    con_fuente = {s.feeder_id for s in model.sources}

    for feeder, tramos in sorted(tramos_por_feeder.items()):
        if feeder in con_fuente:
            continue
        destinos = {s.to_node for s in tramos}
        raices = sorted({s.from_node for s in tramos} - destinos)
        nodo = raices[0] if raices else tramos[0].from_node
        fuente = Source(source_id=f'SRC_{feeder}', node_id=nodo, feeder_id=feeder)
        model.sources.append(fuente)
        out.anotar('source', fuente.source_id, '__row__', None, {'node_id': nodo, 'feeder_id': feeder},
                   'RECOVER_SOURCE_AT_ROOT',
                   'El alimentador no tiene fuente: se pone en su nodo raíz (sale y no entra '
                   'ningún tramo).', 0.5 if len(raices) == 1 else 0.3, candidatos=raices)

    for source in sorted(model.sources, key=lambda s: s.source_id):
        if _positivo(source.nominal_kv):
            continue
        tensiones = Counter(
            v for v in [getattr(nodos.get(source.node_id), 'nominal_kv', None)]
            + [s.nominal_kv for s in tramos_por_feeder.get(source.feeder_id, ())]
            + [getattr(nodos.get(n), 'nominal_kv', None)
               for s in tramos_por_feeder.get(source.feeder_id, ()) for n in (s.from_node, s.to_node)]
            if _positivo(v))
        if tensiones:
            kv = sorted(tensiones.items(), key=lambda kv_n: (-kv_n[1], kv_n[0]))[0][0]
            regla, confianza = 'VOLTAGE_FROM_NETWORK', 0.8
        else:
            kv = politica.provisional_nominal_voltage_kv
            regla, confianza = 'PROVISIONAL_VOLTAGE', 0.3
        out.anotar('source', source.source_id, 'nominal_kv', source.nominal_kv, kv, regla,
                   'Tensión nominal más frecuente de la red del alimentador.'
                   if regla == 'VOLTAGE_FROM_NETWORK'
                   else 'Sin tensión en la red: tensión provisional de la política.', confianza)
        source.nominal_kv = kv


# --------------------------------------------------------------------------- fases y longitudes
def _fases(out: ModeloReconstruido) -> None:
    for section in sorted(out.model.sections, key=lambda s: s.section_id):
        if section.phases.strip():
            continue
        section.phases = FASES_POR_DEFECTO
        out.anotar('section', section.section_id, 'phases', '', FASES_POR_DEFECTO,
                   'PROVISIONAL_PHASES', 'Sin fases: se supone trifásico.', 0.5)


def _longitudes(out: ModeloReconstruido) -> None:
    nodos = out.model.nodes_by_id()
    metrico = out.include_geography
    for section in sorted(out.model.sections, key=lambda s: s.section_id):
        if _positivo(section.length_m):
            continue
        longitud = _longitud_geometria(section.geometry)
        regla, confianza = 'LENGTH_FROM_GEOMETRY', 0.9 if metrico else 0.4
        if longitud is None:
            a, b = nodos.get(section.from_node), nodos.get(section.to_node)
            if a and b and all(_finito(v) for v in (a.x, a.y, b.x, b.y)):
                longitud = math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))
                regla, confianza = 'LENGTH_FROM_NODES', 0.7 if metrico else 0.3
        if not longitud or longitud < LONGITUD_MINIMA_M:
            longitud, regla, confianza = LONGITUD_MINIMA_M, 'MINIMUM_LENGTH', 0.1
        out.anotar('section', section.section_id, 'length_m', section.length_m, longitud, regla,
                   'Longitud ausente: se mide sobre las coordenadas.'
                   + ('' if metrico else ' El CRS no se conoce: se suponen metros.'), confianza)
        section.length_m = longitud


def _longitud_geometria(geometry: Any) -> float | None:
    if not isinstance(geometry, (list, tuple)) or len(geometry) < 2:
        return None
    try:
        puntos = [(float(p[0]), float(p[1])) for p in geometry]
    except (TypeError, ValueError, IndexError):
        return None
    total = sum(math.dist(a, b) for a, b in zip(puntos, puntos[1:]))
    return total if total > 0 else None


# --------------------------------------------------------------------------- cargas
def _cargas(out: ModeloReconstruido) -> None:
    model = out.model
    feeders_por_nodo: dict[str, set[str]] = defaultdict(set)
    for section in model.sections:
        feeders_por_nodo[section.from_node].add(section.feeder_id)
        feeders_por_nodo[section.to_node].add(section.feeder_id)
    nodos = model.nodes_by_id()
    en_red = sorted(
        (node_id, float(nodos[node_id].x), float(nodos[node_id].y))
        for node_id in feeders_por_nodo
        if node_id in nodos and _finito(nodos[node_id].x) and _finito(nodos[node_id].y)
    )
    for load in sorted(model.loads, key=lambda item: item.load_id):
        if load.connection_node not in feeders_por_nodo:
            nodo = nodos.get(load.connection_node)
            if nodo is None or not (_finito(nodo.x) and _finito(nodo.y)) or not en_red:
                out.avisos.append(f'Carga {load.load_id}: su nodo no toca la red ni tiene '
                                  'coordenadas; queda fuera del DGS.')
                continue
            destino = min(en_red, key=lambda item: (
                math.hypot(item[1] - float(nodo.x), item[2] - float(nodo.y)), item[0]))[0]
            out.anotar('load', load.load_id, 'connection_node', load.connection_node, destino,
                       'SNAP_LOAD_TO_NETWORK',
                       'El nodo de la carga no toca ningún tramo: se conecta al nodo de la red '
                       'más cercano.', 0.5)
            load.connection_node = destino
        candidatos = sorted(feeders_por_nodo[load.connection_node])
        if load.feeder_id.strip() in candidatos:
            continue
        nuevo = candidatos[0]
        out.anotar('load', load.load_id, 'feeder_id', load.feeder_id, nuevo,
                   'FEEDER_BY_CONNECTIVITY', 'Alimentador de los tramos de su nodo.',
                   0.8 if len(candidatos) == 1 else 0.5, candidatos=candidatos)
        load.feeder_id = nuevo


def _finito(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _positivo(value: Any) -> bool:
    return _finito(value) and float(value) > 0
