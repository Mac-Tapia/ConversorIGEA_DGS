"""Adaptador DIgSILENT PowerFactory (secciones 15 y J de VNR-GIS.md).

Reutiliza el **perfil de esquema versionado** del escritor DGS existente
(``igea_dgs.schemas/pf21_dgs_1_8_4.json``) para conocer los nombres/campos exactos
de las tablas DGS, y escribe el modelo canónico como un DGS eléctrico mínimo:
red, terminales, tipos de línea, líneas, cargas y fuentes. No se inventan clases
ni cabeceras DGS: todo sale del perfil.

Si el proyecto no aporta ``igea_dgs`` (módulo independiente), se bloquea con un
mensaje claro en lugar de escribir un DGS especulativo.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from vnr_etl.models import CanonicalModel

from .base import ExportBlocked, TargetProfile

PROVENANCE_FIELDS = (
    'source_publication_id', 'source_company', 'source_period', 'source_url',
    'source_sha256', 'retrieved_at', 'schema_fingerprint',
    'source_fingerprint', 'canonical_model_version',
)


def _fmt(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float):
        if not math.isfinite(value):
            return ''
        return format(value, '.12g')
    return str(value).replace(';', ',').replace('\r', ' ').replace('\n', ' ').strip()


def _load_schema(profile: str = 'pf21_dgs_1_8_4'):
    """Reutiliza el perfil DGS versionado del proyecto existente."""
    try:
        from igea_dgs.schema import load_schema
    except ImportError as exc:  # pragma: no cover - módulo independiente
        raise ExportBlocked(
            'El export DGS necesita el perfil DGS del proyecto (igea_dgs.schema). '
            'No se escribe un DGS especulativo.'
        ) from exc
    return load_schema(profile)


@dataclass
class DgsExporter:
    profile: TargetProfile | None = None
    schema_profile: str = 'pf21_dgs_1_8_4'

    def validate_mapping(self, model: CanonicalModel) -> list[str]:
        errors: list[str] = []
        nodes = model.nodes_by_id()
        if not model.sources:
            errors.append('El DGS necesita al menos una fuente/slack.')
        if not model.nodes:
            errors.append('El modelo no tiene nodos.')
        conductor = model.conductor_by_code()
        for section in model.sections:
            if section.from_node not in nodes or section.to_node not in nodes:
                errors.append(
                    f'Tramo {section.section_id} referencia nodos inexistentes.'
                )
            if section.conductor_code and (
                section.conductor_code not in conductor
                or conductor[section.conductor_code].r1_ohm_km is None
            ):
                errors.append(
                    f'Tramo {section.section_id} sin parámetros de conductor aprobados '
                    f'({section.conductor_code}).'
                )
        for load in model.loads:
            if load.connection_node not in nodes:
                errors.append(f'Carga {load.load_id} referencia nodo inexistente.')
        missing_provenance = [name for name in PROVENANCE_FIELDS if not model.metadata.get(name)]
        if missing_provenance:
            errors.append(
                'Falta procedencia obligatoria: ' + ', '.join(missing_provenance)
            )
        return errors

    def export(self, model: CanonicalModel, output_dir: Path) -> list[Path]:
        if self.profile is None or not self.profile.verified:
            raise ExportBlocked(
                'Export DGS bloqueado: falta un perfil verificado contra una '
                'muestra DGS conocida y sin alteraciones.'
            )
        configured_schema = self.profile.object_mapping.get('schema_profile')
        if configured_schema != self.schema_profile:
            raise ExportBlocked(
                f'Export DGS bloqueado: el perfil declara {configured_schema!r} '
                f'pero el exportador usa {self.schema_profile!r}.'
            )
        errors = self.validate_mapping(model)
        if errors:
            raise ExportBlocked(
                'Export DGS bloqueado: ' + '; '.join(errors[:5])
            )
        schema = _load_schema(self.schema_profile)
        output_root = Path(output_dir)
        final_dir = output_root / 'dgs'
        name = self._network_name(model)
        reg = _FidRegistry()
        nodes = model.nodes_by_id()
        conductor = model.conductor_by_code()

        rows: dict[str, list[str]] = {t: [] for t in schema.tables}

        def row(table: str, **values) -> str:
            fields = schema.fields(table)
            return '  ' + ';'.join(_fmt(values.get(f, '')) for f in fields)

        # RED
        general_fid = reg.new()
        net_fid = reg.new()
        rows['General'].append(row('General', FID=general_fid, Descr='Version', Val=schema.general_version))
        rows['ElmNet'].append(row(
            'ElmNet', FID=net_fid, OP='C', loc_name=name[:40], fold_id='', frnom=60,
        ))

        nominal_kv = self._nominal_kv(model)
        node_fids = {node_id: reg.new() for node_id in sorted(nodes)}
        for node_id in sorted(nodes):
            kv = nodes[node_id].nominal_kv or nominal_kv
            gps_lat, gps_lon = self._gps_for_node(model, nodes[node_id])
            rows['ElmTerm'].append(row(
                'ElmTerm', FID=node_fids[node_id], OP='C', loc_name=node_id[:40],
                fold_id=net_fid, typ_id='', systype=0, iUsage=1,
                uknom=kv, unknom=kv / math.sqrt(3.0), iminus=0, outserv=0,
                GPSlat=gps_lat, GPSlon=gps_lon,
            ))

        # Tipos de línea desde el catálogo de conductores.
        type_fids: dict[str, str] = {}
        for code in sorted(conductor):
            typ = conductor[code]
            fid = reg.new()
            type_fids[code] = fid
            rated_ka = (typ.ampacity_a or 0.0) / 1000.0
            rows['TypLne'].append(row(
                'TypLne', FID=fid, OP='C', loc_name=code[:40],
                uline=typ.nominal_kv or nominal_kv, sline=rated_ka, InomAir=rated_ka,
                cohl_=1, rline=typ.r1_ohm_km or 0.0, xline=typ.x1_ohm_km or 0.0,
                rline0=typ.r0_ohm_km or 0.0, xline0=typ.x0_ohm_km or 0.0,
                nlnph=3, nneutral=0, frnom=60,
            ))

        # Líneas + cubículos a ambos extremos.
        for section in sorted(model.sections, key=lambda s: s.section_id):
            line_fid = reg.new()
            length_km = (section.length_m or 0.0) / 1000.0
            typ_id = type_fids.get(section.conductor_code, '')
            rows['ElmLne'].append(row(
                'ElmLne', FID=line_fid, OP='C', loc_name=section.section_id[:40],
                fold_id=net_fid, typ_id=typ_id, dline=length_km, fline=1,
            ))
            for side, node_id in ((0, section.from_node), (1, section.to_node)):
                rows['StaCubic'].append(row(
                    'StaCubic', FID=reg.new(), OP='C',
                    loc_name=f'Cub{side + 1}_{section.section_id}'[:40],
                    fold_id=node_fids[node_id], obj_bus=side, obj_id=line_fid,
                ))

        # Cargas.
        for load in sorted(model.loads, key=lambda l: l.load_id):
            load_fid = reg.new()
            apparent = math.hypot(load.kw, load.kvar)
            rows['ElmLod'].append(row(
                'ElmLod', FID=load_fid, OP='C', loc_name=load.load_id[:40],
                fold_id=net_fid, typ_id='', mode_inp='PC', slini=apparent,
                plini=load.kw, qlini=load.kvar,
            ))
            rows['StaCubic'].append(row(
                'StaCubic', FID=reg.new(), OP='C', loc_name=f'Cub_{load.load_id}'[:40],
                fold_id=node_fids[load.connection_node], obj_bus=0, obj_id=load_fid,
            ))

        # Fuentes.
        for source in sorted(model.sources, key=lambda s: s.source_id):
            source_fid = reg.new()
            rows['ElmXnet'].append(row(
                'ElmXnet', FID=source_fid, OP='C',
                loc_name=f'External Grid {source.source_id}'[:40],
                fold_id=net_fid, bustp='SL',
            ))
            if source.node_id in node_fids:
                rows['StaCubic'].append(row(
                    'StaCubic', FID=reg.new(), OP='C',
                    loc_name=f'Cub_Source_{source.source_id}'[:40],
                    fold_id=node_fids[source.node_id], obj_bus=0, obj_id=source_fid,
                ))

        # El fichero DGS se escribe igual que el escritor existente: encabezado de
        # tabla (``$$Tabla;campo…``) seguido de las filas, en el orden del perfil.
        preamble = [
            '*' * 80,
            '*',
            '* vnr_etl → DIgSILENT DGS (modelo canónico universal)',
            f'* Compatibility profile: {schema.profile}',
            f'* Red: {name}',
            '*',
            '*' * 80,
            '',
        ]
        output = list(preamble)
        used_tables = {'General', 'ElmNet', 'ElmTerm', 'TypLne', 'ElmLne',
                       'ElmLod', 'ElmXnet', 'StaCubic'}
        for table in schema.table_order:
            if table not in used_tables or not rows[table]:
                continue
            output.append(schema.header(table))
            output.extend(rows[table])
            output.extend(['', ''])
        staging_root = output_root / '.staging'
        staging_root.mkdir(parents=True, exist_ok=True)
        stage_dir = Path(tempfile.mkdtemp(prefix='vnr-dgs-', dir=staging_root))
        stage_dgs = stage_dir / f'{name}.dgs'
        stage_manifest = stage_dir / f'{name}.manifest.json'
        try:
            stage_dgs.write_text('\n'.join(output), encoding='utf-8')
            roundtrip_errors = self.roundtrip_errors(stage_dgs)
            if roundtrip_errors:
                raise ExportBlocked(
                    'Export DGS bloqueado por round-trip: ' + '; '.join(roundtrip_errors[:5])
                )
            from vnr_etl import __version__
            from vnr_etl.discovery.download import sha256_of

            manifest = {
                field: model.metadata.get(field, '') for field in PROVENANCE_FIELDS
            }
            manifest.update({
                'target_profile_hash': self.profile.sample_hash,
                'schema_profile': self.schema_profile,
                'converter_version': __version__,
                'artifact': stage_dgs.name,
                'artifact_sha256': sha256_of(stage_dgs),
                'roundtrip': 'PASS',
            })
            stage_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            final_dir.mkdir(parents=True, exist_ok=True)
            final_dgs = final_dir / stage_dgs.name
            final_manifest = final_dir / stage_manifest.name
            os.replace(stage_dgs, final_dgs)
            os.replace(stage_manifest, final_manifest)
            return [final_dgs, final_manifest]
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    def roundtrip_errors(self, path: Path) -> list[str]:
        """Valida cabeceras, aridad y unicidad de FID releyendo el DGS escrito."""
        from igea_dgs.validate import parse_dgs

        schema = _load_schema(self.schema_profile)
        tables = parse_dgs(path)
        errors: list[str] = []
        required = ('General', 'ElmNet', 'ElmTerm', 'ElmLne', 'ElmLod', 'ElmXnet', 'StaCubic')
        for table in required:
            if table not in tables:
                errors.append(f'Falta tabla {table}.')
                continue
            if tables[table]['header'] != schema.header(table):
                errors.append(f'Cabecera inválida para {table}.')
        fids: list[str] = []
        for table, payload in tables.items():
            expected = len(payload['fields'])
            for index, row in enumerate(payload['rows'], start=1):
                if len(row) != expected:
                    errors.append(f'{table} fila {index}: aridad {len(row)} != {expected}.')
            if 'FID' in payload['fields']:
                fid_index = payload['fields'].index('FID')
                fids.extend(row[fid_index] for row in payload['rows'] if len(row) > fid_index)
        duplicates = sorted(fid for fid, count in Counter(fids).items() if fid and count > 1)
        if duplicates:
            errors.append('FID duplicados: ' + ', '.join(duplicates[:5]))
        return errors

    @staticmethod
    def _network_name(model: CanonicalModel) -> str:
        name = model.metadata.get('name') or model.metadata.get('company') or 'VNRGIS'
        return ''.join(c for c in str(name) if c.isalnum() or c in '_-')[:40] or 'VNRGIS'

    @staticmethod
    def _nominal_kv(model: CanonicalModel) -> float:
        values = [n.nominal_kv for n in model.nodes if n.nominal_kv]
        if values:
            return values[0]
        return 10.0

    @staticmethod
    def _gps_for_node(model: CanonicalModel, node) -> tuple[float | None, float | None]:
        if node.x is None or node.y is None:
            return None, None
        working_crs = model.metadata.get('working_crs')
        if not working_crs:
            return None, None
        try:
            import pyproj

            transformer = pyproj.Transformer.from_crs(
                working_crs, 'EPSG:4326', always_xy=True
            )
            lon, lat = transformer.transform(float(node.x), float(node.y))
        except (ImportError, ValueError, TypeError):
            return None, None
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return None, None
        return lat, lon


class _FidRegistry:
    def __init__(self) -> None:
        self._next = 1

    def new(self) -> str:
        value = str(self._next)
        self._next += 1
        return value
