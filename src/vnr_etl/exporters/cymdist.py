"""Adaptador CYMDIST (secciones 14 y E/F de VNR-GIS.md).

Genera ``CYM_SECTIONS.TXT``, ``CYM_LOADS.TXT`` y ``CYM_EQUIPMENT.TXT`` **solo**
contra un contrato organizacional verificado (``TargetProfile.verified``). Sin un
perfil con muestra verificada, el export queda bloqueado (no se escriben columnas
especulativas). El orden es determinista y las referencias de nodo/equipo se
validan antes de escribir.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vnr_etl.models import CanonicalModel

from .base import ExportBlocked, TargetProfile


@dataclass
class CymdistExporter:
    profile: TargetProfile | None = None

    def validate_mapping(self, model: CanonicalModel) -> list[str]:
        """Comprueba que cada referencia del modelo existe (sección 14)."""
        errors: list[str] = []
        nodes = model.nodes_by_id()
        conductor = model.conductor_by_code()
        for section in model.sections:
            if section.from_node not in nodes or section.to_node not in nodes:
                errors.append(
                    f'Tramo {section.section_id} referencia nodos inexistentes '
                    f'({section.from_node}, {section.to_node}).'
                )
            if section.conductor_code and section.conductor_code not in conductor:
                errors.append(
                    f'Tramo {section.section_id} usa conductor sin catálogo: '
                    f'{section.conductor_code}.'
                )
        for load in model.loads:
            if load.connection_node not in nodes:
                errors.append(
                    f'Carga {load.load_id} referencia nodo inexistente {load.connection_node}.'
                )
        return errors

    def export(self, model: CanonicalModel, output_dir: Path) -> list[Path]:
        profile = self.profile
        if profile is None or not profile.verified:
            raise ExportBlocked(
                'Export CYMDIST bloqueado: falta un contrato CYMDIST verificado '
                '(muestra o template conocido). Sección 14 de VNR-GIS.md.'
            )
        errors = self.validate_mapping(model)
        if errors:
            raise ExportBlocked(
                'Export CYMDIST bloqueado: referencias inválidas - ' + '; '.join(errors[:5])
            )
        output_dir = Path(output_dir) / 'cymdist'
        output_dir.mkdir(parents=True, exist_ok=True)
        mapping = profile.object_mapping
        written: list[Path] = []
        written.append(self._write_sections(model, output_dir, mapping.get('sections', {})))
        written.append(self._write_loads(model, output_dir, mapping.get('loads', {})))
        written.append(self._write_equipment(model, output_dir, mapping.get('equipment', {})))
        return written

    # --- escritores deterministas -------------------------------------------
    def _headers(self, spec: dict) -> list[str]:
        return list(spec.get('columns', ()))

    def _write_sections(self, model: CanonicalModel, spec: dict, output_dir: Path | None = None) -> Path:
        output_dir = Path(output_dir or Path.cwd())
        columns = self._headers(spec)
        delimiter = self.profile.delimiter if self.profile else ';'
        path = output_dir / 'CYM_SECTIONS.TXT'
        lines = [delimiter.join(columns)]
        for section in sorted(model.sections, key=lambda s: s.section_id):
            lines.append(self._row(section.__dict__, columns, delimiter))
        path.write_text('\n'.join(lines) + '\n', encoding=self.profile.encoding if self.profile else 'utf-8')
        return path

    def _write_loads(self, model: CanonicalModel, spec: dict, output_dir: Path | None = None) -> Path:
        output_dir = Path(output_dir or Path.cwd())
        columns = self._headers(spec)
        delimiter = self.profile.delimiter if self.profile else ';'
        path = output_dir / 'CYM_LOADS.TXT'
        lines = [delimiter.join(columns)]
        for load in sorted(model.loads, key=lambda l: l.load_id):
            lines.append(self._row(load.__dict__, columns, delimiter))
        path.write_text('\n'.join(lines) + '\n', encoding=self.profile.encoding if self.profile else 'utf-8')
        return path

    def _write_equipment(self, model: CanonicalModel, spec: dict, output_dir: Path | None = None) -> Path:
        output_dir = Path(output_dir or Path.cwd())
        columns = self._headers(spec)
        delimiter = self.profile.delimiter if self.profile else ';'
        path = output_dir / 'CYM_EQUIPMENT.TXT'
        lines = [delimiter.join(columns)]
        for equipment in sorted(model.conductor_types, key=lambda c: c.conductor_code):
            lines.append(self._row(equipment.__dict__, columns, delimiter))
        path.write_text('\n'.join(lines) + '\n', encoding=self.profile.encoding if self.profile else 'utf-8')
        return path

    @staticmethod
    def _row(values: dict, columns: list[str], delimiter: str) -> str:
        def fmt(v) -> str:
            return '' if v is None else str(v).replace(delimiter, ',').replace('\n', ' ')
        return delimiter.join(fmt(values.get(c, '')) for c in columns)