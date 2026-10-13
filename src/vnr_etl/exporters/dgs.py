"""Adaptador DIgSILENT PowerFactory (secciones 15 y J de VNR-GIS.md).

El DGS lo escribe el motor ``igea_dgs``, no este módulo. Antes había aquí un segundo
escritor que se saltaba las reglas del proyecto, la validación estricta y la
auditoría de completitud: el mismo modelo daba un DGS distinto según se convirtiera
por la web o por ``vnr-etl export`` (spec 001, RF-10). Ahora el modelo canónico pasa
por el mismo puente que usa la web para los paquetes VNR-GIS
(:func:`vnr_etl.application.cymdist_bridge.canonical_to_cymdist`) y por
:func:`igea_dgs.batch.convert_group`, que une los alimentadores en una sola red,
valida y publica de forma atómica.

Un dato ausente no impide exportar (RF-17): antes del motor, el modelo pasa por
:func:`vnr_etl.application.reconstruccion.reconstruir_modelo` y el dataset por
:func:`igea_dgs.reconstruction_pipeline.reconstruir_seleccion`, que completa los
conductores con el catálogo de parámetros. Junto al DGS queda
``<red>_reconstruccion.json`` con cada valor completado (RF-21).

Este módulo conserva lo suyo: las puertas del perfil verificado y de la procedencia,
que no son datos de la red, y el manifiesto de procedencia junto al DGS.
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


def _catalogo_del_proyecto():
    from igea_dgs.reglas import catalogo_del_proyecto

    return catalogo_del_proyecto()


def _informe_reconstruccion(modelo, bridge, result, resolutions, catalogo) -> dict:
    """Cada valor reconstruido, con su origen, su confianza y el original (RF-21)."""
    decisiones = [d.to_dict() for d in modelo.decisiones]
    decisiones += [d.to_dict() for d in result.report.decisions]
    por_nivel = Counter(d['level'] for d in decisiones)
    return {
        'resumen': {
            'cambios': len(decisiones),
            'por_nivel': dict(sorted(por_nivel.items())),
            'catalogo_de_parametros': str(catalogo) if catalogo else None,
            'georreferenciado': modelo.include_geography,
            'working_crs': modelo.source_crs,
        },
        'decisiones': decisiones,
        'equipos_resueltos': {
            code: {'regla': item.rule, 'nivel': item.level.value,
                   'codigo_de_catalogo': item.source_code, 'candidatos': list(item.candidates)}
            for code, item in sorted(resolutions.items())
        },
        # Lo que ni la reconstrucción pudo ubicar (una carga sin red ni coordenadas, una
        # carga solo reactiva) no entra en el DGS, y se dice.
        'omitidos': list(bridge.issues),
        'avisos': list(modelo.avisos),
    }


@dataclass
class DgsExporter:
    profile: TargetProfile | None = None
    schema_profile: str = 'pf21_dgs_1_8_4'
    # Catálogo de parámetros (Excel) para completar conductores; sin él, el del proyecto.
    catalogo: Path | None = None

    def validate_mapping(self, model: CanonicalModel) -> list[str]:
        """Lo que impide exportar: solo lo que no es un dato de la red reconstruible.

        Fuente, nodos referenciados y parámetros de conductor ya no son errores: se
        reconstruyen al exportar (spec 001, RF-17). Queda la procedencia, que no se
        puede inventar sin falsear la trazabilidad, y un modelo sin nodos.
        """
        errors: list[str] = []
        if not model.nodes:
            errors.append('El modelo no tiene nodos.')
        missing_provenance = [name for name in PROVENANCE_FIELDS if not model.metadata.get(name)]
        if missing_provenance:
            errors.append(
                'Falta procedencia obligatoria: ' + ', '.join(missing_provenance)
            )
        return errors

    def export(self, model: CanonicalModel, output_dir: Path) -> list[Path]:
        # Ni el perfil de destino, ni la procedencia, ni la relectura impiden exportar
        # (spec 001, RF-22 a RF-24): se exporta y el manifiesto dice qué falló. Solo un
        # modelo sin ningún tramo se queda sin DGS, porque no hay red que escribir.
        avisos: list[str] = []
        verificado = bool(self.profile is not None and self.profile.verified)
        if not verificado:
            avisos.append('Perfil de destino no verificado: se usa el perfil de esquema del '
                          f'motor ({self.schema_profile}).')
        configured_schema = (self.profile.object_mapping.get('schema_profile')
                             if self.profile is not None else None)
        if configured_schema and configured_schema != self.schema_profile:
            avisos.append(f'El perfil declara {configured_schema!r}; se usa {self.schema_profile!r}.')
        from igea_dgs.batch import convert_group
        from igea_dgs.reconstruction_pipeline import catalogos_del_fichero, reconstruir_seleccion
        from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
        from vnr_etl.application.reconstruccion import reconstruir_modelo

        name = self._network_name(model)
        # Primero el modelo canónico (alimentadores, fuentes, tensión, fases, longitudes,
        # cargas, CRS) y después el dataset con el catálogo de parámetros (RF-17, RF-18).
        modelo = reconstruir_modelo(model, nombre=name)
        avisos = modelo.avisos + avisos
        bridge = canonical_to_cymdist(modelo.model, source_path=Path(f'{name}.vnr'))
        feeders = sorted(bridge.dataset.feeders)
        if not feeders:
            raise ExportBlocked('Export DGS bloqueado: el modelo no tiene ningún tramo que exportar.')
        catalogo = self.catalogo if self.catalogo is not None else _catalogo_del_proyecto()
        result, resolutions = reconstruir_seleccion(
            bridge.dataset, feeders, catalogos_del_fichero(catalogo),
        )
        if not modelo.include_geography:
            from igea_dgs.coordenadas import ORIGEN_SIN_CRS

            # Sin CRS las coordenadas no están en metros conocidos: dibujan la red, pero
            # la longitud eléctrica es la del modelo (RF-20).
            for row in result.dataset.nodes.values():
                row.setdefault('CoordOrigen', ORIGEN_SIN_CRS)

        output_root = Path(output_dir)
        final_dir = output_root / 'dgs'
        staging_root = output_root / '.staging'
        staging_root.mkdir(parents=True, exist_ok=True)
        stage_dir = Path(tempfile.mkdtemp(prefix='vnr-dgs-', dir=staging_root))
        try:
            engine = convert_group(
                result.dataset, feeders, stage_dir, name=name,
                schema_profile=self.schema_profile,
                source_crs=modelo.source_crs or 'EPSG:4326',
                include_geography=modelo.include_geography,
            )
            stage_dgs = stage_dir / f'{name}.dgs'
            if engine['status'] != 'ok' or not stage_dgs.is_file():
                raise ExportBlocked(
                    'Export DGS bloqueado por el motor: '
                    + str(engine.get('error') or engine['status'])
                )
            # El motor ya validó el DGS; la relectura es una segunda opinión y se informa.
            roundtrip_errors = self.roundtrip_errors(stage_dgs)
            avisos += [f'Relectura: {error}' for error in roundtrip_errors]
            from vnr_etl import __version__
            from igea_dgs.util import sha256_file

            informe = _informe_reconstruccion(modelo, bridge, result, resolutions, catalogo)
            informe['avisos'] = avisos
            stage_report = stage_dir / f'{name}_reconstruccion.json'
            stage_report.write_text(
                json.dumps(informe, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            stage_manifest = stage_dir / f'{name}.manifest.json'
            manifest = {
                field: modelo.model.metadata.get(field, '') for field in PROVENANCE_FIELDS
            }
            manifest.update({
                'target_profile_hash': self.profile.sample_hash if self.profile else None,
                'perfil_verificado': verificado,
                'procedencia_reconstruida': modelo.model.metadata.get('procedencia_reconstruida', []),
                'schema_profile': self.schema_profile,
                'converter_version': __version__,
                'artifact': stage_dgs.name,
                'artifact_sha256': sha256_file(stage_dgs),
                'roundtrip': 'BLOQUEADO_PERSISTENCIA' if roundtrip_errors else 'OK',
                'roundtrip_errors': roundtrip_errors,
                'avisos': avisos,
                'engine': 'igea_dgs.batch.convert_group',
                'feeders': engine['feeders'],
                'engine_manifest': f'{name}_manifest.json',
                'georreferenciado': modelo.include_geography,
                'working_crs': modelo.source_crs,
                'reconstruccion': {
                    'informe': stage_report.name,
                    'cambios': informe['resumen']['cambios'],
                    'por_nivel': informe['resumen']['por_nivel'],
                    'omitidos': len(informe['omitidos']),
                },
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
        from igea_dgs.validate import parse_dgs, total_fids

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
        for table, payload in tables.items():
            expected = len(payload['fields'])
            for index, row in enumerate(payload['rows'], start=1):
                if len(row) != expected:
                    errors.append(f'{table} fila {index}: aridad {len(row)} != {expected}.')
        # La misma regla de FID único que el validador del motor. Esta copia propia no
        # sabía que en «Matrix» el FID se repite en cada fila (spec 010) y daba por
        # roto todo DGS con trazado GPS.
        fids = [fid for fid, _tabla in total_fids(tables)]
        duplicates = sorted(fid for fid, count in Counter(fids).items() if fid and count > 1)
        if duplicates:
            errors.append('FID duplicados: ' + ', '.join(duplicates[:5]))
        return errors

    @staticmethod
    def _network_name(model: CanonicalModel) -> str:
        name = model.metadata.get('name') or model.metadata.get('company') or 'VNRGIS'
        return ''.join(c for c in str(name) if c.isalnum() or c in '_-')[:40] or 'VNRGIS'
