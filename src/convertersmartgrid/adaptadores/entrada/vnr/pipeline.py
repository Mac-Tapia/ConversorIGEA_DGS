"""Capa de aplicación compartida por CLI y Web (sección E24 de VNR-GIS.md).

CLI y Web importan estas funciones; ninguno implementa lógica de negocio propia.
Usa los conectores, el descubrimiento, el GIS/snapping y los exportadores, y
coordina la secuencia fuente → modelo canónico → validación → export.
"""

from __future__ import annotations

from convertersmartgrid.dominio.runtime_paths import staging_publicacion

import math
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from convertersmartgrid.adaptadores.entrada.vnr.connectors import resolve_adapter
from convertersmartgrid.adaptadores.entrada.vnr.discovery.schema import resolve_alias, rol_de_capa
from convertersmartgrid.adaptadores.entrada.vnr.gis.geometry import coords_from_geojson, polyline_length_m
from convertersmartgrid.adaptadores.entrada.vnr.gis.snapping import deterministic_node_id, snap_endpoints
from convertersmartgrid.adaptadores.entrada.vnr.models import (
    CanonicalModel, Capacitor, Lineage, Load, LowVoltageSection, Node, Regulator, Section, Switch)
from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import (
    SIN_REGLA_BT, anotar_sin_regla, estado_o_anota, medio_o_anota, texto_fuente)


@dataclass
class ExtractReport:
    source: Path
    destination: Path
    format: str
    files: list[Path]
    total_bytes: int


def safe_extract_package(source: Path | str, destination: Path | str) -> ExtractReport:
    """Materializa un paquete en staging y lo publica solo tras extracción segura."""
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import safe_extract_rar, safe_extract_zip

    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(f'La carpeta derivada ya existe: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(destination) as staging:
        staging.mkdir()
        suffix = source.suffix.lower()
        if suffix == '.zip':
            safe_extract_zip(source, staging, uncompressed_limit_bytes=8 * 1024**3)
            package_format = 'zip'
        elif suffix == '.rar':
            safe_extract_rar(source, staging, uncompressed_limit_bytes=8 * 1024**3)
            package_format = 'rar'
        elif source.is_file():
            target = staging / source.name
            shutil.copy2(source, target)
            package_format = source.suffix.lower().lstrip('.') or 'file'
        else:
            raise ValueError(f'Paquete VNR inexistente o no soportado: {source}')
        # Enumerar desde el mismo objeto ``staging`` evita que Windows compare el
        # alias 8.3 del directorio temporal con la ruta larga devuelta por zipfile.
        files = sorted(path for path in staging.rglob('*') if path.is_file())
        if destination.exists():
            raise FileExistsError(f'La carpeta derivada ya existe: {destination}')
        staging.rename(destination)
        published = [destination / path.relative_to(staging) for path in files]
        return ExtractReport(
            source=source,
            destination=destination,
            format=package_format,
            files=published,
            total_bytes=sum(path.stat().st_size for path in published),
        )


def geojson_rows(path: Path) -> tuple[list[dict], str]:
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
        raise ValueError(f'{path.name} no es un FeatureCollection GeoJSON.')
    crs = 'EPSG:4326'
    crs_raw = payload.get('crs') or {}
    name = ((crs_raw.get('properties') or {}).get('name') if isinstance(crs_raw, Mapping) else '')
    if isinstance(name, str) and name:
        crs = name.rsplit(':', 1)[-1]
        crs = f'EPSG:{crs}' if crs.isdigit() else name
    return list(payload['features']), crs


#: 080:RF-55: los campos de un tramo MT que la vía de capas lee, con su nombre canónico.
CAMPOS_DE_TRAMO = ('section_id', 'feeder_id', 'standard_code', 'length_source', 'status', 'network_type',
                   'company', 'period', 'from_node', 'to_node')

#: 080:RF-55: los roles de capa que la vía de capas modela (los demás se anotan ``CAPA_SIN_MODELAR``).
ROLES_MODELADOS = ('tramos_mt', 'nodos', 'sed', 'equipos', 'tramos_bt')
#: 080:RF-55: el TIPO de una capa de equipos y la lista del canónico que le toca (el que escribe
#: ``exporters.capas``, y las palabras de cualquier empresa). Otro TIPO no se adivina: se anota.
TIPOS_DE_EQUIPO = (
    ('switches', re.compile(r'MANIOBRA|SECCIONADOR|INTERRUPTOR|RECONECTADOR|SWITCH|CUCHILLA', re.I)),
    ('capacitors', re.compile(r'BANCO|CAPACITOR|CONDENSADOR', re.I)),
    ('regulators', re.compile(r'REGULADOR|REGULATOR', re.I)),
)


def _capas_del_paquete(package_root) -> tuple[list[tuple[str, list[dict], str]], list[str]]:
    """``[(nombre de la capa, filas, CRS)]`` de TODAS las capas del paquete, y los errores de lectura."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.registry import iter_supported_sources

    capas: list[tuple[str, list[dict], str]] = []
    errors: list[str] = []
    for path in iter_supported_sources(package_root):
        try:
            if path.suffix.lower() in ('.geojson', '.json'):
                rows, crs = geojson_rows(path)
                capas.append((path.name, rows, crs))
                continue
            adapter = resolve_adapter(str(path))
            for layer in adapter.list_layers():
                capas.append((f'{path.name}:{layer.name}', adapter.read_layer(layer.name), layer.crs or ''))
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f'{path.name}: {exc}')
    return capas, errors


def _al_nombre_canonico(rows: list[dict], fields: list[str], capa: str) -> list[dict]:
    """Las filas de una capa de tramos con los campos de ``CAMPOS_DE_TRAMO`` por su nombre canónico."""
    origen = {c: resolve_alias(c, fields)[0] for c in CAMPOS_DE_TRAMO}
    salida = []
    for row in rows:
        fila = normalize_feature_record(row)
        for canonico, campo in origen.items():
            if campo and campo != canonico:
                fila[canonico] = fila.get(campo)
        fila['__capa__'] = capa
        salida.append(fila)
    return salida


def canonicalize_vnr_package(
    package_root: Path | str,
    *,
    company: str | None = None,
    period: str | None = None,
) -> tuple[CanonicalizeResult, dict[str, str]]:
    """Lee TODAS las capas del paquete y asigna a cada una su rol por sus campos y su nombre (080:RF-55).

    Las capas de tramos MT (una o varias, como Tramo_MT_Aereo y Tramo_MT_Subterraneo) se unen, cada
    tramo con su capa en ``source_layer``; si traen los nodos de sus extremos (``CODNODOMT_INI`` y
    ``CODNODOMT_FIN``), la red se une por ellos, como en la vía SQL. Las de nodos, SED, equipos y tramos
    BT se leen al canónico (:func:`_leer_capas_de_red`). Las de un rol que la vía de capas no modela se
    anotan con ``CAPA_SIN_MODELAR``, y las que no se reconocen con ``CAPA_NO_RECONOCIDA``, con su nombre y
    su recuento: ninguna se descarta en silencio.
    """
    capas, errors = _capas_del_paquete(package_root)
    tramos: list[tuple[str, list[dict], str, list[str]]] = []
    de_red: list[tuple[str, str, list[dict], str, list[str]]] = []
    otras: list[dict] = []
    for nombre, rows, crs in capas:
        fields = sorted({str(key) for row in rows for key in normalize_feature_record(row)})
        rol = rol_de_capa(nombre.rsplit(':', 1)[-1], fields)
        if rol == 'tramos_mt':
            tramos.append((nombre, rows, crs, fields))
        elif rol in ROLES_MODELADOS:
            de_red.append((rol, nombre, rows, crs, fields))
        else:
            otras.append({'code': 'CAPA_SIN_MODELAR' if rol else 'CAPA_NO_RECONOCIDA',
                          'capa': nombre, 'rol': rol or '', 'registros': len(rows)})
    if not tramos:
        detail = '; '.join(errors[:5])
        raise ValueError(
            'El paquete no contiene una capa con section_id/CODTRAMOMT y '
            f'feeder_id/CODSALIDAMT.{" " + detail if detail else ""}'
        )
    crs_distintos = sorted({crs or '' for _n, _r, crs, _f in tramos})
    if len(crs_distintos) > 1:
        raise ValueError('Las capas de tramos del paquete tienen CRS distintos; no se mezclan: '
                         + ', '.join(f'{n} ({crs or "sin CRS"})' for n, _r, crs, _f in tramos))
    rows: list[dict] = []
    for nombre, filas, _crs, fields in tramos:
        rows.extend(_al_nombre_canonico(filas, fields, nombre))
    layer = ', '.join(n for n, _r, _c, _f in tramos)
    scoped, scope = select_source_scope(rows, company=company, period=period)
    result = canonicalize_sections(
        scoped,
        section_id_field='section_id',
        feeder_field='feeder_id',
        conductor_field='standard_code' if any(resolve_alias('standard_code', f)[0] for *_x, f in tramos) else None,
        length_field='length_source' if any(resolve_alias('length_source', f)[0] for *_x, f in tramos) else None,
        source_crs=crs_distintos[0] or None,
        source_layer=layer,
        from_node_field='from_node' if all(resolve_alias('from_node', f)[0] for *_x, f in tramos) else None,
        to_node_field='to_node' if all(resolve_alias('to_node', f)[0] for *_x, f in tramos) else None,
    )
    result.model.metadata.update({'company': scope['company'], 'period': scope['period']})
    _leer_capas_de_red(result, de_red)
    result.model.metadata['capas'] = (
        [{'capa': n, 'rol': 'tramos_mt', 'registros': len(r)} for n, r, _c, _f in tramos]
        + [{'capa': n, 'rol': rol, 'registros': len(r)} for rol, n, r, _c, _f in de_red]
        + [{'capa': o['capa'], 'rol': o['rol'], 'registros': o['registros']} for o in otras])
    if otras:
        result.model.metadata['capas_sin_modelar'] = otras
        result.warnings.extend(f"{o['code']}: {o['capa']} ({o['rol'] or 'sin rol'}, {o['registros']} registros)"
                               for o in otras)
    return result, scope


def _campo(fila: Mapping[str, Any], fields: Sequence[str], canonico: str) -> Any:
    """El valor del campo ``canonico`` de la fila, con el nombre que le dé la capa (``resolve_alias``)."""
    nombre = resolve_alias(canonico, fields)[0]
    return fila.get(nombre) if nombre else None


def _real(valor: Any) -> float | None:
    """Un número de la capa, o None si falta (NaN incluido)."""
    numero = _parse_float(texto_fuente(valor))
    return None if numero is None or math.isnan(numero) else numero


def _entero(valor: Any, defecto: int) -> int:
    numero = _real(valor)
    return defecto if numero is None else int(numero)


def _punto(fila: Mapping[str, Any], crs: str | None, metadata: Mapping[str, Any]) -> tuple[float, float] | None:
    """El punto de un objeto de la capa en el CRS de trabajo del modelo."""
    puntos = coords_from_geojson(fila.get('geometry') or fila.get('__geometry__'))
    if not puntos:
        return None
    x, y = _transform_points(puntos[:1], crs or metadata.get('source_crs'), metadata.get('working_crs'))[0]
    return float(x), float(y)


def _leer_capas_de_red(result: CanonicalizeResult, capas: Sequence[tuple[str, str, list[dict], str, list[str]]]
                       ) -> None:
    """080:RF-55: las capas de nodos, SED, equipos y tramos BT de un paquete, al canónico, como la vía SQL.

    Un nodo que ya dio un tramo toma la posición y la tensión de su capa; uno que no, se añade. Una SED
    es una carga en su nodo (``CODNODOMT``). Un equipo va a maniobras, bancos o reguladores según su
    TIPO (``TIPOS_DE_EQUIPO``); un TIPO sin regla se anota en ``valores_sin_regla['tipo_equipo']`` y
    con ``EQUIPO_SIN_REGLA``, nunca se pierde en silencio. Un tramo BT va a ``sections_bt``
    (:func:`_anadir_tramo_bt`).
    """
    modelo = result.model
    meta = modelo.metadata
    nodos = {n.node_id: n for n in modelo.nodes}
    for rol, capa, rows, crs, fields in sorted(capas, key=lambda c: ROLES_MODELADOS.index(c[0])):
        for row in rows:
            fila = normalize_feature_record(row)
            if rol == 'nodos':
                ident = texto_fuente(_campo(fila, fields, 'node_id'))
                if not ident:
                    continue
                nodo = nodos.get(ident)
                if nodo is None:
                    nodo = nodos[ident] = Node(node_id=ident, source_id=ident)
                    modelo.nodes.append(nodo)
                if (punto := _punto(fila, crs, meta)) is not None:
                    nodo.x, nodo.y = punto
                nodo.nominal_kv = _real(fila.get('TENSION_KV')) if 'TENSION_KV' in fields else nodo.nominal_kv
                nodo.phases = texto_fuente(fila.get('FASES')) or nodo.phases
                nodo.source_layer = capa
            elif rol == 'sed':
                modelo.loads.append(Load(
                    load_id=texto_fuente(_campo(fila, fields, 'sed_id')),
                    connection_node=texto_fuente(_campo(fila, fields, 'connection_node')),
                    kw=_real(fila.get('KW')) or 0.0, kvar=_real(fila.get('KVAR')) or 0.0,
                    phases=texto_fuente(fila.get('FASES')),
                    feeder_id=texto_fuente(_campo(fila, fields, 'feeder_id')),
                    etiqueta=texto_fuente(fila.get('ETIQUETA')),
                    connected_kva=_real(fila.get('POTINSTALADA')),
                    source_layer=capa, source_id=texto_fuente(_campo(fila, fields, 'sed_id'))))
            elif rol == 'tramos_bt':
                _anadir_tramo_bt(modelo, fila, fields, capa, crs)
            else:
                _anadir_equipo(result, fila, fields, capa)


def _anadir_tramo_bt(modelo: CanonicalModel, fila: Mapping[str, Any], fields: Sequence[str], capa: str,
                     crs: str | None) -> None:
    """080:RF-55: un registro de una capa de tramos BT, a ``sections_bt``, con las reglas de estado y medio de MT.

    Lo que no tiene regla se cuenta en ``valores_sin_regla_bt``, como en la vía SQL. Sin ``LONGITUD``, la
    longitud es la de su geometría.
    """
    ident = texto_fuente(_campo(fila, fields, 'section_bt_id'))
    if not ident:
        return
    meta = modelo.metadata
    puntos = coords_from_geojson(fila.get('geometry') or fila.get('__geometry__'))
    puntos = [(float(x), float(y)) for x, y in
              _transform_points(puntos, crs or meta.get('source_crs'), meta.get('working_crs'))]
    largo = _real(_campo(fila, fields, 'length_source'))
    if largo is None and len(puntos) >= 2:
        largo = round(sum(math.dist(a, b) for a, b in zip(puntos, puntos[1:])), 3)
    estado = texto_fuente(_campo(fila, fields, 'status'))
    tipo = texto_fuente(_campo(fila, fields, 'network_type'))
    modelo.sections_bt.append(LowVoltageSection(
        section_id=ident, sed_id=texto_fuente(_campo(fila, fields, 'sed_id')),
        bt_feeder_id=texto_fuente(_campo(fila, fields, 'bt_feeder_id')),
        feeder_id=texto_fuente(_campo(fila, fields, 'feeder_id')),
        parent_id=texto_fuente(_campo(fila, fields, 'parent_section_bt')),
        conductor_code=texto_fuente(_campo(fila, fields, 'standard_code')), length_m=largo, geometry=puntos,
        status=estado_o_anota(meta, estado, clave=SIN_REGLA_BT), overhead=medio_o_anota(meta, tipo, clave=SIN_REGLA_BT),
        source_status=estado, source_network_type=tipo, source_layer=capa, source_id=ident))


def _anadir_equipo(result: CanonicalizeResult, fila: Mapping[str, Any], fields: Sequence[str], capa: str) -> None:
    """080:RF-55: un registro de una capa de equipos, a la lista del canónico que dice su TIPO."""
    modelo = result.model
    ident = texto_fuente(_campo(fila, fields, 'equipment_id'))
    tipo = texto_fuente(_campo(fila, fields, 'equipment_type'))
    nodo = texto_fuente(_campo(fila, fields, 'connection_node'))
    tramo = texto_fuente(fila.get('TRAMO'))
    lista = next((nombre for nombre, patron in TIPOS_DE_EQUIPO if patron.search(tipo)), None)
    if lista == 'switches':
        modelo.switches.append(Switch(switch_id=ident, connection_node=nodo, section_id=tramo,
                                      on_off=_entero(fila.get('ON_OFF'), 1), source_layer=capa, source_id=ident))
    elif lista == 'capacitors':
        modelo.capacitors.append(Capacitor(capacitor_id=ident, connection_node=nodo,
                                           kvar=_real(fila.get('KVAR')) or 0.0,
                                           status=texto_fuente(fila.get('ESTADO')) or 'in_service',
                                           source_layer=capa, source_id=ident))
    elif lista == 'regulators':
        modelo.regulators.append(Regulator(regulator_id=ident, connection_node=nodo, section_id=tramo,
                                           on_off=_entero(fila.get('ON_OFF'), 1), source_layer=capa,
                                           source_id=ident))
    else:
        cuenta = modelo.metadata.get('valores_sin_regla', {}).get('tipo_equipo', {})
        if not cuenta.get(tipo):
            result.warnings.append(f'EQUIPO_SIN_REGLA: {capa} trae equipos de tipo «{tipo or "sin tipo"}», '
                                   'que la vía de capas no modela; se anotan con su recuento.')
        anotar_sin_regla(modelo.metadata, 'tipo_equipo', tipo)


def probe_source(source: str) -> dict:
    adapter = resolve_adapter(source)
    return adapter.probe(source).as_dict()


def discover_layers(source: str) -> list[dict]:
    adapter = resolve_adapter(source)
    return [layer.as_dict() for layer in adapter.list_layers()]


def read_layer(source: str, layer, filters: Mapping[str, Any] | None = None) -> list[dict]:
    adapter = resolve_adapter(source)
    return adapter.read_layer(layer, filters=filters)


def list_companies(source: str) -> list[str]:
    adapter = resolve_adapter(source)
    try:
        return adapter.available_companies()
    finally:
        adapter.close()


def list_periods(source: str, company: str | None = None) -> list[str]:
    adapter = resolve_adapter(source)
    try:
        return adapter.available_periods(company=company)
    finally:
        adapter.close()


def buscar_capa_de_tramos(layers: Sequence[Mapping[str, Any]]) -> dict | None:
    """La capa de tramos MT: por el nombre o, si no, la primera de polilíneas.

    Era del CLI; la web buscaba solo «tramo» en el nombre, y una capa subida, que se
    guarda con un nombre opaco, nunca se encontraba (spec 001, RF-25).
    """
    for layer in layers:
        name = (layer.get('name') or '').lower()
        if 'tramo' in name or 'section' in name or 'line' in name:
            return dict(layer)
    for layer in layers:
        gtype = (layer.get('geometry_type') or '').lower()
        if 'polyline' in gtype or 'linestring' in gtype or 'multiline' in gtype:
            return dict(layer)
    return None


def deducir_crs_de_tramos(section_rows: Sequence[Mapping[str, Any]]) -> tuple[str | None, str]:
    """:func:`convertersmartgrid.adaptadores.entrada.vnr.gis.crs.deducir_crs` sobre las geometrías de una capa de tramos."""
    from convertersmartgrid.adaptadores.entrada.vnr.gis.crs import deducir_crs
    from convertersmartgrid.adaptadores.entrada.vnr.gis.geometry import coords_from_geojson

    puntos: list[tuple[float, float]] = []
    for row in section_rows:
        normal = normalize_feature_record(row)
        geometry = normal.get('geometry') or normal.get('__geometry__')
        if geometry:
            puntos.extend(coords_from_geojson(geometry))
    return deducir_crs(puntos)


def suggest_utm_crs(lon: float, lat: float) -> str:
    """CRS UTM WGS84 para un punto, como CRS de **trabajo** métrico.

    No deduce el *datum* de la empresa (PSAD56/SIRGAS), solo una zona UTM WGS84
    coherente con las coordenadas, que es lo único que el snapping métrico necesita
    y lo único que estas coordenadas permiten deducir sin adivinar.
    """
    zone = math.floor((lon + 180.0) / 6.0) + 1
    zone = max(1, min(60, zone))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f'EPSG:{epsg}'


def _transform_points(points, source_crs, working_crs):
    """Reproyecta puntos; devuelve la misma lista si no hay pyproj o ya coinciden."""
    if not source_crs or not working_crs or source_crs == working_crs:
        return points
    from convertersmartgrid.adaptadores.geography import make_transformer

    try:
        transformer = make_transformer(source_crs, working_crs)
    except ImportError:  # pragma: no cover
        raise RuntimeError('Reproyección requiere «pyproj».') from None
    return [transformer.transform(x, y) for x, y in points]


@dataclass
class CanonicalizeResult:
    model: CanonicalModel
    warnings: list[str] = field(default_factory=list)
    length_report: list[dict] = field(default_factory=list)
    snap_report: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            'counts': self.model.counts(),
            'warnings': self.warnings,
            'length_report': self.length_report,
            'snap_report': self.snap_report,
        }


def normalize_feature_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normaliza un registro plano o una entidad GeoJSON a un único contrato.

    ArcGIS ``f=geojson`` guarda los atributos en ``properties`` y la geometría
    en el nivel superior. Los demás conectores ya entregan registros planos.
    Conservar ambos formatos aquí evita que la capa canónica dependa del origen.
    """
    if not isinstance(row, Mapping):
        raise TypeError('Cada registro de la fuente debe ser un objeto/mapping.')
    properties = row.get('properties')
    if properties is None:
        return dict(row)
    if not isinstance(properties, Mapping):
        raise TypeError('Entidad GeoJSON inválida: «properties» debe ser un objeto.')
    record = dict(properties)
    for key, value in row.items():
        if key not in ('properties', 'type'):
            record[key] = value
    return record


def select_source_scope(
    rows: Sequence[Mapping[str, Any]],
    *,
    company: str | None = None,
    period: str | None = 'latest_available',
) -> tuple[list[dict], dict[str, str]]:
    """Selecciona una sola empresa/periodo sin mezclar entregas silenciosamente."""
    normalized = [normalize_feature_record(row) for row in rows]
    fields = sorted({str(key) for row in normalized for key in row})
    company_field, _ = resolve_alias('company', fields)
    period_field, _ = resolve_alias('period', fields)

    companies = sorted({
        str(row.get(company_field)).strip() for row in normalized
        if company_field and row.get(company_field) not in (None, '')
    })
    selected_company = (company or '').strip()
    if not selected_company:
        if len(companies) > 1:
            raise ValueError(
                'La fuente contiene múltiples empresas; indique --company para evitar mezclarlas.'
            )
        selected_company = companies[0] if companies else ''
    if companies and selected_company not in companies:
        raise ValueError(f'Empresa no encontrada en la fuente: {selected_company}')
    selected = [
        row for row in normalized
        if not company_field or not selected_company
        or str(row.get(company_field, '')).strip() == selected_company
    ]

    periods = sorted({
        str(row.get(period_field)).strip() for row in selected
        if period_field and row.get(period_field) not in (None, '')
    }, key=period_key)
    requested_period = (period or '').strip()
    if not requested_period and len(periods) > 1:
        raise ValueError(
            'La fuente contiene múltiples periodos; indique --period para evitar mezclarlos.'
        )
    selected_period = (
        periods[-1] if requested_period == 'latest_available' and periods
        else periods[0] if not requested_period and len(periods) == 1
        else requested_period
    )
    if requested_period not in ('', 'latest_available') and periods and requested_period not in periods:
        raise ValueError(f'Periodo no encontrado para {selected_company or "la fuente"}: {requested_period}')
    if selected_period:
        selected = [
            row for row in selected
            if not period_field or str(row.get(period_field, '')).strip() == selected_period
        ]
    if not selected:
        raise ValueError('La selección empresa/periodo no produjo registros.')
    return selected, {'company': selected_company, 'period': selected_period}


def period_key(value: str) -> tuple:
    numbers = tuple(int(item) for item in re.findall(r'\d+', value))
    return (*numbers, value)


def canonicalize_sections(
    section_rows: Sequence[Mapping[str, Any]],
    *,
    section_id_field: str = 'CODTRAMOMT',
    feeder_field: str | None = 'CODSALIDAMT',
    conductor_field: str | None = 'CODNORMA',
    length_field: str | None = 'LONGITUD',
    source_crs: str | None = 'EPSG:4326',
    working_crs: str | None = None,
    snap_tolerance_m: float = 0.5,
    source_layer: str = 'sections',
    status_field: str | None = None,
    network_type_field: str | None = None,
    from_node_field: str | None = None,
    to_node_field: str | None = None,
) -> CanonicalizeResult:
    """Convierte tramos polilínea en nodos + tramos canónicos (secciones E y G).

    Reconstruye los nodos desde los extremos de la geometría, rellena longitudes
    métricas y las cruza con ``LONGITUD`` cuando es parseable. La geometría se
    guarda en el CRS de trabajo (metros) y se conservan el CRS de origen y el
    origen de cada tramo.
    """
    normalized_rows = [normalize_feature_record(row) for row in section_rows]
    # 080:RF-55, RF-53: el estado (ESTADO/ESTADOVNR) y el tipo de red (CODTIPORED) del tramo, si
    # la capa los trae, como en la copia de SQL Server; sin ellos, en servicio y medio por deducir.

    campos = sorted({str(key) for row in normalized_rows for key in row})
    status_field = status_field or resolve_alias('status', campos)[0]
    network_type_field = network_type_field or resolve_alias('network_type', campos)[0]
    # Auto-elegir CRS de trabajo métrico si venía en grados.
    resolved_working = working_crs
    if source_crs == 'EPSG:4326' and not resolved_working:
        # La geometría puede venir como «geometry» o «__geometry__» (ArcGIS), igual que
        # en el bucle de abajo; mirando solo la primera, una capa ArcGIS en grados se
        # quedaba trabajando en grados y medía longitudes en grados.
        first = next((row.get('geometry') or row.get('__geometry__')
                      for row in normalized_rows
                      if row.get('geometry') or row.get('__geometry__')), None)
        pts = coords_from_geojson(first) if first else []
        if pts:
            resolved_working = suggest_utm_crs(pts[0][0], pts[0][1])
    resolved_working = resolved_working or source_crs
    model = CanonicalModel(metadata={
        'source_crs': source_crs,
        'working_crs': resolved_working,
        'working_crs_is_projected': _is_projected_crs(resolved_working),
        'source_layer': source_layer,
        'input_section_count': len(normalized_rows),
    })

    anchors: list[tuple[str, float, float]] = []
    sections: list[Section] = []
    warnings: list[str] = []
    length_report: list[dict] = []

    prepared: list[dict] = []
    seen_section_ids: set[str] = set()
    for row in normalized_rows:
        section_id = str(row.get(section_id_field) or '').strip()
        if not section_id:
            raise ValueError(
                f'Tramo sin identificador obligatorio «{section_id_field}»; '
                'la ingestión se bloquea para evitar pérdida o colisión de datos.'
            )
        if section_id in seen_section_ids:
            raise ValueError(f'Identificador de tramo duplicado: {section_id}')
        seen_section_ids.add(section_id)
        geometry = row.get('geometry') or row.get('__geometry__')
        if not geometry:
            warnings.append(f'Tramo sin geometría, se omite: {section_id}')
            continue
        raw_coords = coords_from_geojson(geometry)
        if len(raw_coords) < 2:
            warnings.append(f'Tramo sin geometría de línea, se omite: {section_id}')
            continue
        prepared.append({'row': row, 'raw_coords': raw_coords, 'section_id': section_id})

    for item in prepared:
        row = item['row']
        raw_coords = item['raw_coords']
        section_id = item['section_id']
        # Reproyectar a metros.
        coords = _transform_points(raw_coords, source_crs, resolved_working)
        geom = [[x, y] for x, y in coords]
        length_m = polyline_length_m(coords)
        source_length = _parse_float(row.get(length_field)) if length_field else None
        if source_length is not None and source_length > 0:
            length_report.append({
                'section_id': section_id,
                'gis_m': round(length_m, 3),
                'source_m': round(source_length, 3),
                'delta_pct': round(100.0 * abs(length_m - source_length) / source_length, 3),
            })
        start, end = coords[0], coords[-1]
        anchors.append((f'{section_id}:from', start[0], start[1]))
        anchors.append((f'{section_id}:to', end[0], end[1]))
        sections.append(Section(
            section_id=section_id,
            from_node='',  # se rellena tras el snapping
            to_node='',
            conductor_code=str(row.get(conductor_field) or '') if conductor_field else '',
            phases='',
            nominal_kv=None,
            length_m=length_m,
            status=estado_o_anota(model.metadata, texto_fuente(row.get(status_field) if status_field else None)),
            overhead=medio_o_anota(model.metadata,
                                    texto_fuente(row.get(network_type_field) if network_type_field else None)),
            source_status=texto_fuente(row.get(status_field) if status_field else None),
            source_network_type=texto_fuente(row.get(network_type_field) if network_type_field else None),
            geometry=geom,
            source_layer=row.get('__capa__') or source_layer,
            source_id=section_id,
            feeder_id=str(row.get(feeder_field) or '') if feeder_field else '',
            lineage=Lineage(
                source_layer=row.get('__capa__') or source_layer,
                source_id=section_id,
                source_field=section_id_field,
                resolution_method='SOURCE',
            ),
        ))

    # 080:RF-55: si TODOS los tramos traen los nodos de sus extremos, la red se une por ellos (como la
    # vía SQL) y no por la cercanía de las geometrías; cada nodo, en el primer extremo que lo nombra.
    explicitos = [(texto_fuente(item['row'].get(from_node_field)), texto_fuente(item['row'].get(to_node_field)))
                  for item in prepared] if from_node_field and to_node_field else []
    if sections and len(explicitos) == len(sections) and all(a and b for a, b in explicitos):
        posicion: dict[str, tuple[float, float]] = {}
        for i, (section, (desde, hasta)) in enumerate(zip(sections, explicitos)):
            section.from_node, section.to_node = desde, hasta
            posicion.setdefault(desde, (anchors[2 * i][1], anchors[2 * i][2]))
            posicion.setdefault(hasta, (anchors[2 * i + 1][1], anchors[2 * i + 1][2]))
        model.nodes = [Node(node_id=n, x=x, y=y, source_layer=source_layer, source_id=n)
                       for n, (x, y) in posicion.items()]
        model.sections = sections
        model.metadata['output_section_count'] = len(sections)
        model.metadata['topologia'] = 'nodos_de_la_fuente'
        return CanonicalizeResult(model=model, warnings=warnings, length_report=length_report,
                                  snap_report={'count': 0, 'mean_m': 0.0, 'max_m': 0.0, 'excessive': 0})

    snap = snap_endpoints(anchors, snap_tolerance_m)
    # Re-mapear IDs de tramo → nodo de origen/destino.
    anchor_index = 0
    for section in sections:
        from_key = (round(anchors[anchor_index][1], 9), round(anchors[anchor_index][2], 9))
        to_key = (round(anchors[anchor_index + 1][1], 9), round(anchors[anchor_index + 1][2], 9))
        section.from_node = snap.node_ids.get(from_key, deterministic_node_id([from_key]))
        section.to_node = snap.node_ids.get(to_key, deterministic_node_id([to_key]))
        anchor_index += 2

    for node_id, (x, y) in snap.node_coords.items():
        model.nodes.append(Node(
            node_id=node_id, x=x, y=y, source_layer='topology', source_id=node_id,
        ))
    model.sections = sections
    model.metadata['output_section_count'] = len(sections)
    return CanonicalizeResult(
        model=model,
        warnings=warnings,
        length_report=length_report,
        snap_report=snap.displacement_report(),
    )


def _parse_float(value) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_projected_crs(crs: str | None) -> bool:
    if not crs:
        return False
    try:
        import pyproj

        return bool(pyproj.CRS.from_user_input(crs).is_projected)
    except (ImportError, ValueError):
        return False
