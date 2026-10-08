"""Auditoría de solo lectura del proyecto anfitrión.

NO modifica el código de la aplicación: solo inspecciona y escribe los informes
en ``AUDIT/`` (sección 2). Identifica qué reutilizar, qué adaptar y qué falta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AUDIT_DIRECTORY = 'AUDIT'


@dataclass
class AuditFindings:
    project_dir: Path
    packages: list[str]
    deps: list[str]
    connectors: list[str]
    gis_modules: list[str]
    catalogs: list[str]
    dgs_profiles: list[str]
    exporters: list[str]
    tests: list[str]
    risks: list[str]

    def render(self) -> dict[str, str]:
        """Devuelve el contenido de cada fichero AUDIT/*.md."""
        offset = len(str(self.project_dir)) + 1
        return {
            'environment.md': _environment(self),
            'project_structure.md': _structure(self, offset),
            'connectors.md': _connectors(self),
            'gis_modules.md': _gis(self),
            'catalogs.md': _catalogs(self),
            'cymdist_contract.md': _cymdist(self),
            'dgs_contract.md': _dgs(self),
            'risks.md': _risks(self),
            'integration_plan.md': _plan(self),
        }


def _discover(project_dir: Path) -> AuditFindings:
    packages: list[str] = []
    connectors: list[str] = []
    gis_modules: list[str] = []
    catalogs: list[str] = []
    dgs_profiles: list[str] = []

    src = project_dir / 'src'
    if src.is_dir():
        for pkg in sorted(src.iterdir()):
            if pkg.is_dir() and (pkg / '__init__.py').is_file():
                packages.append(pkg.name)

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(project_dir)).replace('\\', '/')
        except ValueError:
            return str(p)

    for module in (src / 'vnr_etl' / 'connectors').glob('*.py') if (src / 'vnr_etl' / 'connectors').is_dir() else []:
        connectors.append(f'vnr_etl/connectors/{module.name}')
    for module in (src / 'vnr_etl' / 'gis').glob('*.py') if (src / 'vnr_etl' / 'gis').is_dir() else []:
        gis_modules.append(f'vnr_etl/gis/{module.name}')
    for module in (src / 'vnr_etl' / 'catalogs').glob('*.py') if (src / 'vnr_etl' / 'catalogs').is_dir() else []:
        catalogs.append(f'vnr_etl/catalogs/{module.name}')
    if (src / 'igea_dgs' / 'schemas').is_dir():
        dgs_profiles = [rel(p) for p in sorted((src / 'igea_dgs' / 'schemas').glob('*.json'))]

    exporters = []
    if (src / 'igea_dgs' / 'dgs.py').is_file():
        exporters.append('igea_dgs/dgs.py (write_dgs — reutilizar)')

    deps = _read_requirements(project_dir)
    tests = [rel(p) for p in sorted((project_dir / 'tests').glob('test_*.py'))] if (project_dir / 'tests').is_dir() else []
    risks = _known_risks(dgs_profiles)
    return AuditFindings(
        project_dir=project_dir,
        packages=packages,
        deps=deps,
        connectors=connectors,
        gis_modules=gis_modules,
        catalogs=catalogs,
        dgs_profiles=dgs_profiles,
        exporters=exporters,
        tests=tests,
        risks=risks,
    )


def _read_requirements(project_dir: Path) -> list[str]:
    lines: list[str] = []
    for name in ('requirements.txt', 'requirements-drivers.txt'):
        path = project_dir / name
        if path.is_file():
            lines.append(f'# {name}')
            lines.extend(
                ln for ln in path.read_text(encoding='utf-8').splitlines()
                if ln.strip() and not ln.lstrip().startswith('#')
            )
    return lines


def _known_risks(dgs_profiles: list[str]) -> list[str]:
    risks = [
        'El export final CYMDIST/DGS está bloqueado hasta verificar una muestra/template real (secciones 14-15).',
        'IGEA write-back deshabilitado hasta verificar el endpoint real de Osinergmin.',
        'El CRS/PSAD56/km de la empresa no se deduce; lo aporta la fuente.',
        'G/H (import/flujo) requieren el simulador y quedan pendientes sin él.',
    ]
    if not dgs_profiles:
        risks.append('No se encontró perfil DGS versionado en el proyecto.')
    return risks


# --------------------------------------------------------------------------- render
def _render(title: str, body: str) -> str:
    return f'# {title}\n\n{body.rstrip()}\n'


def _list_block(items: list[str]) -> str:
    return '\n'.join(f'- {i}' for i in items) or '- (ninguno)'


def _environment(self: AuditFindings) -> str:
    body = (
        '## Entorno\n\n'
        f'- Directorio del proyecto: `{self.project_dir}`\n'
        '- Python: 3.12 (fijado por `powerfactory.pyd` de PF 2024).\n'
        '## Dependencias detectadas\n\n' + _list_block(self.deps)
    )
    return _render('Entorno (AUDIT/environment.md)', body)


def _structure(self: AuditFindings, offset: int) -> str:
    body = '## Paquetes Python\n\n' + _list_block(self.packages)
    body += '\n## Pruebas\n\n' + _list_block(self.tests)
    body += '\n\nLa estructura la descubre `setuptools` con `where = ["src"]`: ' \
        '`vnr_etl` se añade como paquete adicional sin tocar `igea_dgs`.'
    return _render('Estructura del proyecto (AUDIT/project_structure.md)', body)


def _connectors(self: AuditFindings) -> str:
    body = '## Conectores del módulo adicional\n\n' + _list_block(self.connectors)
    body += '\n## Escritores existentes (reutilizar)\n\n' + _list_block(self.exporters)
    return _render('Conectores (AUDIT/connectors.md)', body)


def _gis(self: AuditFindings) -> str:
    body = '## Módulos GIS\n\n' + _list_block(self.gis_modules)
    return _render('Módulos GIS (AUDIT/gis_modules.md)', body)


def _catalogs(self: AuditFindings) -> str:
    body = '## Catálogos\n\n' + _list_block(self.catalogs)
    return _render('Catálogos (AUDIT/catalogs.md)', body)


def _cymdist(self: AuditFindings) -> str:
    body = (
        'Los TXT CYMDIST de entrada existen en `igea_dgs` (RED/CARGA/BD_Equipo) y el '
        'export CYMDIST de salida de `vnr_etl` queda bloqueado hasta aportar un '
        'contrato organizacional verificado (columnas/delimitador/unidades).'
    )
    return _render('Contrato CYMDIST (AUDIT/cymdist_contract.md)', body)


def _dgs(self: AuditFindings) -> str:
    body = '## Perfiles DGS versionados\n\n' + _list_block(self.dgs_profiles)
    body += '\n\nEl exportador DGS de `vnr_etl` reutiliza estos perfiles para los ' \
        'nombres/tablas/campos exactos; no asume un DGS v4.0 sin verificar.'
    return _render('Contrato DGS (AUDIT/dgs_contract.md)', body)


def _risks(self: AuditFindings) -> str:
    return _render('Riesgos (AUDIT/risks.md)', '\n'.join(f'- {r}' for r in self.risks))


def _plan(self: AuditFindings) -> str:
    body = (
        'El módulo `vnr_etl` se integra como paquete **adicional** (`src/vnr_etl/`), '
        'sin modificar `igea_dgs`. Se reutiliza:\n\n'
        '- `igea_dgs/schemas/pf21_dgs_1_8_4.json` — perfiltablas/campos DGS (escritor DGS).\n'
        '- Convenciones de `igea_dgs/web` (FastAPI + colas) — referencia para la web del módulo.\n\n'
        'Se implementa solo lo faltante: descubrimiento, adaptadores, modelo canónico, '
        'CRS/snapping, topología, enriquecimiento, puertas y CLI. El export final queda '
        'estricto y bloqueado sin muestra verificada.'
    )
    return _render('Plan de integración (AUDIT/integration_plan.md)', body)


def run_audit(project_dir: Path | str, output_dir: Path | str | None = None) -> dict[str, Path]:
    """Ejecuta la auditoría (solo lectura) y escribe AUDIT/*.md."""
    project_dir = Path(project_dir)
    output_dir = Path(output_dir) if output_dir else project_dir / AUDIT_DIRECTORY
    output_dir.mkdir(parents=True, exist_ok=True)
    findings = _discover(project_dir)
    written: dict[str, Path] = {}
    for name, content in findings.render().items():
        path = output_dir / name
        path.write_text(content, encoding='utf-8')
        written[name] = path
    return written