"""Adaptador DIgSILENT PowerFactory (secciones 15 y J de VNR-GIS.md).

El DGS lo escribe el motor ``igea_dgs``, no este módulo. Antes había aquí un segundo
escritor que se saltaba las reglas del proyecto, la validación estricta y la
auditoría de completitud: el mismo modelo daba un DGS distinto según se convirtiera
por la web o por ``vnr-etl export`` (spec 001, RF-10). Ahora el modelo canónico pasa
por el mismo puente que usa la web para los paquetes VNR-GIS
(:func:`vnr_etl.application.cymdist_bridge.canonical_to_cymdist`) y por
:func:`igea_dgs.batch.convert_group`, que une los alimentadores en una sola red,
valida y publica de forma atómica.

Este módulo conserva lo suyo: las puertas del perfil verificado y de la procedencia,
y el manifiesto de procedencia junto al DGS.
"""

from __future__ import annotations

import json
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
        source_crs = str(model.metadata.get('working_crs') or '')
        if not source_crs or model.metadata.get('working_crs_is_projected') is not True:
            raise ExportBlocked(
                'Export DGS bloqueado: el modelo no declara un CRS de trabajo proyectado '
                '(working_crs), y sin él no hay longitudes ni coordenadas fiables.'
            )
        from igea_dgs.batch import convert_group
        from vnr_etl.application.cymdist_bridge import canonical_to_cymdist

        name = self._network_name(model)
        bridge = canonical_to_cymdist(model, source_path=Path(f'{name}.vnr'))
        # El puente deja fuera lo que no sabe ubicar (un tramo sin alimentador, una carga
        # sin tramo). Exportar igual daría un DGS al que le faltan elementos sin decirlo.
        if bridge.issues:
            detail = ', '.join(
                f"{issue['code']} {issue['source_id']}" for issue in bridge.issues[:5]
            )
            raise ExportBlocked(f'Export DGS bloqueado: el modelo no se puede mapear ({detail}).')
        blocked = {
            feeder: state['blocking_codes']
            for feeder, state in sorted(bridge.readiness.items()) if state['blocking_codes']
        }
        if blocked or not bridge.dataset.feeders:
            detail = '; '.join(
                f"{feeder}: {', '.join(codes)}" for feeder, codes in list(blocked.items())[:5]
            ) or 'ningún alimentador'
            raise ExportBlocked(f'Export DGS bloqueado: alimentadores no listos ({detail}).')

        output_root = Path(output_dir)
        final_dir = output_root / 'dgs'
        staging_root = output_root / '.staging'
        staging_root.mkdir(parents=True, exist_ok=True)
        stage_dir = Path(tempfile.mkdtemp(prefix='vnr-dgs-', dir=staging_root))
        try:
            engine = convert_group(
                bridge.dataset, sorted(bridge.dataset.feeders), stage_dir, name=name,
                schema_profile=self.schema_profile, source_crs=source_crs,
            )
            stage_dgs = stage_dir / f'{name}.dgs'
            if engine['status'] != 'ok' or not stage_dgs.is_file():
                raise ExportBlocked(
                    'Export DGS bloqueado por el motor: '
                    + str(engine.get('error') or engine['status'])
                )
            roundtrip_errors = self.roundtrip_errors(stage_dgs)
            if roundtrip_errors:
                raise ExportBlocked(
                    'Export DGS bloqueado por round-trip: ' + '; '.join(roundtrip_errors[:5])
                )
            from vnr_etl import __version__
            from igea_dgs.util import sha256_file

            stage_manifest = stage_dir / f'{name}.manifest.json'
            manifest = {
                field: model.metadata.get(field, '') for field in PROVENANCE_FIELDS
            }
            manifest.update({
                'target_profile_hash': self.profile.sample_hash,
                'schema_profile': self.schema_profile,
                'converter_version': __version__,
                'artifact': stage_dgs.name,
                'artifact_sha256': sha256_file(stage_dgs),
                'roundtrip': 'PASS',
                'engine': 'igea_dgs.batch.convert_group',
                'feeders': engine['feeders'],
                'engine_manifest': f'{name}_manifest.json',
            })
            stage_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            # El DGS va el último: quien vea el .dgs en «dgs/» ya tiene al lado su
            # validación y su procedencia.
            final_dir.mkdir(parents=True, exist_ok=True)
            for path in sorted(stage_dir.iterdir(), key=lambda p: p.name == stage_dgs.name):
                if path.is_file():
                    os.replace(path, final_dir / path.name)
            return [final_dir / stage_dgs.name, final_dir / stage_manifest.name]
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
