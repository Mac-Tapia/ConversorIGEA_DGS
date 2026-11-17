"""Descubrimiento semántico de esquema (sección U4 y apartados D de VNR-GIS.md).

No hay que atarse a un esquema VNR histórico: los campos se resuelven en tiempo
de ejecución por alias, con clasificación ``SOURCE / DERIVED / CATALOG / MISSING``
y sin inventar nunca un valor.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

#: Alias por concepto canónico (sección U4). El orden importa: se prueba en el
#: orden en que se listan (exacto → alias conocido → alias normalizado).
CANONICAL_ALIASES: dict[str, list[str]] = {
    'company': ['CODEMP', 'EMPRESA', 'COD_EMPRESA', 'EMP'],
    'period': ['ANIO', 'AÑO', 'PERIODO', 'YEAR'],
    'system_id': ['SISTEMA', 'CODSISTEMA', 'COD_SISTEMA'],
    'system_name': ['SISTEMA0', 'NOM_SISTEMA', 'SISTEMA_ELECTRICO'],
    'feeder_id': ['CODSALIDAMT', 'ALIMENTADOR', 'COD_ALIMENTADOR'],
    'section_id': ['CODTRAMOMT', 'COD_TRAMO', 'TRAMO', 'SECTION_ID'],
    'sed_id': ['CODSED', 'COD_SED'],
    'set_id': ['CODSET', 'COD_SET'],
    'vnr_code': ['CODNORMA', 'COD_VNR', 'CODVNR'],
    'status': ['ESTADOVNR', 'ESTADO'],
    'length_source': ['LONGITUD', 'LENGTH'],
    'parent_section': ['CODTRAMOMTPADRE', 'parent_section'],
    'network_type': ['CODTIPORED', 'network_type'],
    'nominal_voltage_code': ['CODTENNOMI', 'nominal_voltage_code'],
    'standard_code': ['CODNORMA', 'standard_code'],
    # 080:RF-55: los campos que dicen el rol de las demás capas de un paquete.
    'section_bt_id': ['CODTRAMOBT', 'COD_TRAMO_BT', 'section_bt_id'],
    'node_id': ['CODNODOMT', 'COD_NODO', 'NODO', 'node_id'],
    'equipment_id': ['CODEQP', 'COD_EQUIPO', 'CODEQUIPO', 'equipment_id'],
    # 080:RF-55: los nodos de los extremos de un tramo, si la capa los trae: unen la red por el código
    # de la fuente, como la vía SQL, en lugar de por la cercanía de las geometrías.
    'from_node': ['CODNODOMT_INI', 'NODO_INI', 'CODNODOINI', 'from_node'],
    'to_node': ['CODNODOMT_FIN', 'NODO_FIN', 'CODNODOFIN', 'to_node'],
    # 080:RF-55: lo que leen las capas de SED, nodos y equipos.
    'connection_node': ['CODNODOMT', 'COD_NODO', 'NODO', 'connection_node'],
    'equipment_type': ['TIPO', 'TIPOEQP', 'TIPO_EQUIPO', 'equipment_type'],
    # 080:RF-55: lo que lee una capa de tramos BT además de su código, su SED y su norma.
    'bt_feeder_id': ['CODSALIDABT', 'COD_SALIDA_BT', 'bt_feeder_id'],
    'parent_section_bt': ['CODTRAMOBTPADRE', 'parent_section_bt'],
}

#: Alias de sección VNR específicos (apartado D), combinados con los universales.
SECTION_ALIASES: dict[str, list[str]] = {
    'section_id': ['CODTRAMOMT', 'COD_TRAMO', 'section_id'],
    'company': ['CODEMP', 'EMPRESA', 'company'],
    'feeder_id': ['CODSALIDAMT', 'ALIMENTADOR', 'feeder_id'],
    'parent_section': ['CODTRAMOMTPADRE', 'parent_section'],
    'network_type': ['CODTIPORED', 'network_type'],
    'nominal_voltage_code': ['CODTENNOMI', 'nominal_voltage_code'],
    'standard_code': ['CODNORMA', 'standard_code'],
    'length_source': ['LONGITUD', 'length_source'],
}

#: 080:RF-55: el rol de una capa por su nombre, cuando sus campos no lo dicen (en orden).
ROLES_POR_NOMBRE: tuple[tuple[str, str], ...] = (
    ('tramos_bt', r'TRAMO.?BT|BT.?TRAMO|RED.?BT'),
    ('tramos_mt', r'TRAMO.?MT|MT.?TRAMO|TRAMO|RED.?MT'),
    ('sed', r'\bSEDS?\b|SUBESTAC'),
    ('nodos', r'NODO|VERTICE'),
    ('equipos', r'EQUIPO|EQP|MANIOBRA|SECCIONADOR|INTERRUPTOR|RECONECTADOR|BANCO|REGULADOR'),
)


def rol_de_capa(nombre: str, campos: Sequence[str]) -> str | None:
    """080:RF-55: ``tramos_mt``, ``tramos_bt``, ``sed``, ``nodos`` o ``equipos``; None si no se reconoce.

    Primero por los campos (la misma tabla ``CANONICAL_ALIASES``), después por el nombre de la capa.
    Tramos MT: identificador de tramo y alimentador, como la vía de capas exige.
    """
    campos = list(campos)

    def tiene(canonico: str) -> bool:
        return resolve_alias(canonico, campos)[0] is not None

    if tiene('section_id') and tiene('feeder_id'):
        return 'tramos_mt'
    if tiene('section_bt_id'):
        return 'tramos_bt'
    if tiene('sed_id'):
        return 'sed'
    if tiene('equipment_id'):
        return 'equipos'
    if tiene('node_id'):
        return 'nodos'
    texto = nombre.upper()
    for rol, patron in ROLES_POR_NOMBRE:
        if re.search(patron, texto):
            return None if rol == 'tramos_mt' else rol      # un «tramo» sin sus campos no se puede leer
    return None


def _normalize(name: str) -> str:
    """Normaliza un nombre de campo: mayúsculas, sin acentos y compactando guiones.

    ``AÑO`` → ``ANO``, ``COD_TRAMO`` → ``CODTRAMO``, de modo que un alias escrito
    con o sin separador resuelva igual.
    """
    texto = name.strip().upper()
    texto = texto.replace('Á', 'A').replace('É', 'E').replace('Í', 'I')
    texto = texto.replace('Ó', 'O').replace('Ú', 'U').replace('Ü', 'U')
    texto = texto.replace('Ñ', 'N')
    texto = re.sub(r'[_\-\. ]', '', texto)
    return texto


@dataclass
class FieldLineage:
    """Linaje de un campo canónico resuelto (sección U4)."""

    canonical_field: str
    source_layer: str
    source_field: str
    resolution_method: str
    """``exact``, ``alias``, ``normalized_alias``, ``project_mapping``, ``missing``."""
    confidence: float
    transform: str = ''
    null_count: int = 0
    distinct_count: int = 0

    def as_dict(self) -> dict:
        return {
            'canonical_field': self.canonical_field,
            'source_layer': self.source_layer,
            'source_field': self.source_field,
            'resolution_method': self.resolution_method,
            'confidence': self.confidence,
            'transform': self.transform,
            'null_count': self.null_count,
            'distinct_count': self.distinct_count,
        }


def normalize_aliases(aliases: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    return {canonical: [a for a in alias_list] for canonical, alias_list in aliases.items()}


def resolve_alias(
    canonical_field: str,
    source_fields: Iterable[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
    project_mapping: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    """Devuelve ``(campo_fuente, método)`` para un campo canónico.

    Orden (sección U4): nombre canónico exacto → alias exacto → alias normalizado →
    mapeo del proyecto. Nunca se mapea solo por tipo de dato compatible.
    """
    if canonical_field in source_fields:
        return canonical_field, 'exact'

    alias_list = list(
        (aliases or CANONICAL_ALIASES).get(canonical_field, [])
    )
    source_set = set(source_fields)
    for alias in alias_list:
        if alias in source_set:
            return alias, 'alias'

    normalized_source = {_normalize(f): f for f in source_fields}
    for alias in alias_list:
        key = _normalize(alias)
        if key in normalized_source:
            return normalized_source[key], 'normalized_alias'

    if project_mapping and canonical_field in project_mapping:
        mapped = project_mapping[canonical_field]
        if mapped in source_set:
            return mapped, 'project_mapping'

    return None, 'missing'


def classify_field(method: str, value) -> str:
    """Clasifica un valor resuelto: SOURCE / DERIVED / CATALOG / MISSING."""
    if method == 'missing':
        return 'MISSING'
    if value is None or value == '':
        return 'MISSING'
    if method in ('exact', 'alias', 'normalized_alias', 'project_mapping'):
        return 'SOURCE'
    return 'DERIVED'


class SchemaResolver:
    """Resuelve el esquema de una capa/tabla a conceptos canónicos con linaje."""

    def __init__(
        self,
        aliases: Mapping[str, Sequence[str]] | None = None,
        project_mapping: Mapping[str, str] | None = None,
    ) -> None:
        self.aliases = normalize_aliases(aliases or CANONICAL_ALIASES)
        self.project_mapping = dict(project_mapping or {})

    def resolve_fields(
        self,
        source_fields: Iterable[str],
        *,
        layer: str = '',
        columns: Mapping[str, Sequence] | None = None,
    ) -> dict[str, FieldLineage]:
        """Devuelve el linaje de cada campo canónico conocido para la capa."""
        fields = list(source_fields)
        result: dict[str, FieldLineage] = {}
        columns = columns or {}
        for canonical in self.aliases:
            source_field, method = resolve_alias(
                canonical, fields, self.aliases, self.project_mapping)
            nulls = 0
            distinct = 0
            if source_field is not None and columns:
                values = list(columns.get(source_field, ()))
                nulls = sum(1 for v in values if v in (None, ''))
                distinct = len(set(values))
            result[canonical] = FieldLineage(
                canonical_field=canonical,
                source_layer=layer,
                source_field=source_field or '',
                resolution_method=method,
                confidence=0.0 if method == 'missing' else (0.8 if method == 'normalized_alias' else 1.0),
                null_count=nulls,
                distinct_count=distinct,
            )
        return result

    def missing_required(self, fields: dict[str, FieldLineage], required: Iterable[str]) -> list[str]:
        return [f for f in required if fields.get(f, FieldLineage(f, '', '', 'missing', 0.0)).resolution_method == 'missing']

    def suggest(self, source_fields: Iterable[str], unresolved: Iterable[str]) -> dict[str, list[str]]:
        """Sugerencias semánticas por similitud (solo informativas; requieren aprobación)."""
        suggestions: dict[str, list[str]] = {}
        for target in unresolved:
            key = _normalize(target)
            near = [f for f in source_fields if key and (_normalize(f) and key in _normalize(f) or _normalize(f) in key)]
            if near:
                suggestions[target] = sorted(set(near))
        return suggestions