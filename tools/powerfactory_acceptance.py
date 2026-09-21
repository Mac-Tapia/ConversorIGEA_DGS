#!/usr/bin/env python3
"""Runtime gate: import DGS into DigSilent PowerFactory via API and validate.

Uses the PowerFactory Python module (bundled under
``PowerFactory 20xx/Python/3.xx``). Prefer running with that interpreter, or set
``PYTHONPATH`` to the matching PF Python folder, with PowerFactory available
(``GetApplication`` / ``GetApplicationExt``).

Checks:
  - DGS file import into a new (or existing) project
  - Activate Study Case base + Operation Scenario (create if missing)
  - Element inventory: lines, loads, switches, SED transformers (ElmTr2),
    capacitors (ElmShnt), voltage regulators (ElmVoltreg)
  - Connectivity (StaCubic → ElmTerm)
  - Scaled GPS location vs geography manifest
  - Optional load-flow convergence (ComLdf) on the base study case
  - Optional diagnose + correction intents until LDF converges
    (aligned with User Manual ch. 24.6 + ComLdf attrs from PF Help)
  - Optional study suite (``--run-studies``): ComLdf + ComShc (+ registry)
  - After import / LDF: persist ``{feeder}.dgs`` (+ known sidecars) into the
    same convert ``out_dir`` used by GUI/CLI individual convert; optionally
    ComExport a ``{feeder}_pf_converged.dgs`` round-trip when LDF passes

DigSILENT Help sources used (PF 2024 install)::

    Help/UserManual_en.pdf  — ch. 12.8 Commands, 24 Load Flow, 24.6 Troubleshooting,
                              25 Short-Circuit; IntCase / IntScenario activation
    Help/PythonReference_en.pdf — Application.GetFromStudyCase, IsLdfValid,
                                  ComLdf.Execute (0/1/2), ComShc
    Help/DplReference_en.pdf — GetFromStudyCase creates command if missing;
                               Ldf:iopt_net = 0|1 (balanced|unbalanced)
    localisation/*/data.db — ComLdf attribute labels (iopt_lim, iopt_at, iopt_fl, …)
    Api/Example/src/ApiExample.cpp — ComImport + GetCaseObject(ComLdf) + IsLdfValid
                                     + ComExport / ExportDgsFile

Example::

    set PYTHONPATH=C:\\Program Files\\DIgSILENT\\PowerFactory 2024\\Python\\3.12
    python tools\\powerfactory_acceptance.py ^
      --import-dgs output\\gui\\AL104.dgs ^
      --manifest output\\gui\\AL104_geography.json ^
      --require-diagram --run-load-flow --fix-until-converge --run-studies
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Attribute / object helpers
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str, default=None):
    if obj is None:
        return default
    try:
        value = obj.GetAttribute(name)
        if value is not None:
            return value
    except Exception:
        pass
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _set_attr(obj: Any, name: str, value: Any) -> bool:
    try:
        obj.SetAttribute(name, value)
        return True
    except Exception:
        pass
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def _name(obj: Any) -> str:
    return str(_attr(obj, 'loc_name', '') or '')


def _classname(obj: Any) -> str:
    try:
        return str(obj.GetClassName())
    except Exception:
        return ''


def _contents(obj: Any, pattern: str) -> list[Any]:
    if obj is None:
        return []
    try:
        return list(obj.GetContents(pattern, 1) or [])
    except TypeError:
        try:
            return list(obj.GetContents(pattern) or [])
        except Exception:
            return []
    except Exception:
        return []


def _calc_objects(app: Any, pattern: str) -> list[Any]:
    try:
        return list(app.GetCalcRelevantObjects(pattern) or [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# PowerFactory connection
# ---------------------------------------------------------------------------

def connect_powerfactory(*, start_engine: bool = True, command_line: str | None = None) -> Any:
    """Return PF Application; prefer running instance, else start engine."""
    try:
        import powerfactory as pf  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            'Módulo powerfactory no disponible. Añada a PYTHONPATH la carpeta '
            r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12 '
            '(o la versión instalada) y use un Python compatible (3.10–3.12).'
        ) from exc

    app = pf.GetApplication()
    if app is not None:
        return app
    if not start_engine:
        raise RuntimeError('PowerFactory no está abierto (GetApplication devolvió None).')

    args = command_line or '-shared'
    for factory in (getattr(pf, 'GetApplicationExt', None), pf.GetApplication):
        if factory is None:
            continue
        try:
            app = factory(None, None, args)
        except TypeError:
            try:
                app = factory()
            except Exception:
                app = None
        except Exception:
            app = None
        if app is not None:
            return app
    raise RuntimeError(
        'No se pudo conectar a PowerFactory. Abra PF 2024 o ejecute con licencia '
        'y el API Python de la misma versión.'
    )


# ---------------------------------------------------------------------------
# Import DGS + Study Case / Scenario
# ---------------------------------------------------------------------------

def import_dgs_file(
    app: Any,
    dgs_path: Path,
    *,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Import ASCII DGS via ComImport into a new project (DigSilent API Example)."""
    dgs_path = Path(dgs_path).resolve()
    if not dgs_path.is_file():
        raise FileNotFoundError(f'DGS no encontrado: {dgs_path}')

    user = app.GetCurrentUser()
    if user is None:
        raise RuntimeError('GetCurrentUser() falló — sesión PF no válida')

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    prj = project_name or f'{stamp}_IGEA_{dgs_path.stem}'

    com = user.CreateObject('ComImport', f'DGSImport_{stamp}')
    if com is None:
        raise RuntimeError('No se pudo crear ComImport')

    # Official transfer order from ApiExample.cpp:
    # iopt_prj=0 (new project), targname, dgsFormat, fFile
    errors: list[str] = []
    try:
        app.DefineTransferAttributes('ComImport', 'iopt_prj,targname,dgsFormat,fFile')
        try:
            com.SetAttributes([0, prj, 'DGS File', str(dgs_path)])
        except Exception:
            # Fallback attribute-by-attribute (PF version differences).
            for name, value in (
                ('iopt_prj', 0),
                ('targname', prj),
                ('dgsFormat', 'DGS File'),
                ('fFile', str(dgs_path)),
                ('fName', str(dgs_path)),
            ):
                if not _set_attr(com, name, value):
                    errors.append(f'No se pudo asignar ComImport.{name}')
        rc = int(com.Execute())
        if rc != 0:
            errors.append(f'ComImport.Execute() returned {rc}')
    finally:
        try:
            com.Delete()
        except Exception:
            try:
                com.DeleteObject()
            except Exception:
                pass

    # Activate imported project if not already active.
    active = app.GetActiveProject()
    if active is None or _name(active) != prj:
        try:
            rc_act = int(app.ActivateProject(prj))
            if rc_act != 0:
                errors.append(f'ActivateProject({prj!r}) returned {rc_act}')
        except Exception as exc:
            errors.append(f'ActivateProject failed: {exc}')

    return {
        'project_name': prj,
        'dgs': str(dgs_path),
        'errors': errors,
        'ok': not errors,
    }


# ---------------------------------------------------------------------------
# Persist DGS into convert out_dir (+ optional ComExport after LDF)
# ---------------------------------------------------------------------------
# Individual convert (GUI ``out_dir`` / CLI ``--out-dir`` / ``convert_selection``)
# writes ``{feeder}.dgs`` and sidecars there. The PF gate imports from that path
# into a *new* PF project; corrections stay in-memory unless we export.
# These helpers guarantee the convert folder always holds the DGS used/validated.

_FEEDER_SIDECAR_NAMES = (
    '{feeder}_geography.json',
    '{feeder}_geography_validation.txt',
    '{feeder}_validation.json',
    '{feeder}_validation.txt',
    '{feeder}_preview.html',
    '{feeder}_preview.geojson',
    '{feeder}.xlsx',
)


def resolve_convert_out_dir(
    dgs_path: Path | str,
    persist_dir: Path | str | None = None,
) -> Path:
    """Convert output folder: explicit ``persist_dir`` or parent of the DGS."""
    if persist_dir is not None:
        return Path(persist_dir).resolve()
    return Path(dgs_path).resolve().parent


def persist_feeder_dgs(
    dgs_path: Path | str,
    *,
    out_dir: Path | str | None = None,
    copy_sidecars: bool = True,
) -> dict[str, Any]:
    """Idempotently ensure ``{feeder}.dgs`` (+ known sidecars) live in convert out_dir.

    When ``dgs_path`` already is ``out_dir/{feeder}.dgs``, this is a no-op check.
    When the gate imported from another location, copies into ``out_dir``.
    """
    src = Path(dgs_path).resolve()
    dest_dir = resolve_convert_out_dir(src, out_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    feeder = src.stem
    dest_dgs = dest_dir / f'{feeder}.dgs'
    info: dict[str, Any] = {
        'ok': False,
        'feeder': feeder,
        'out_dir': str(dest_dir),
        'dgs': str(dest_dgs),
        'source_dgs': str(src),
        'copied_dgs': False,
        'already_in_place': False,
        'sidecars': [],
        'actions': [],
        'errors': [],
        'warnings': [],
    }
    if not src.is_file():
        info['errors'].append(f'Source DGS missing: {src}')
        return info

    try:
        if dest_dgs.resolve() == src.resolve():
            info['already_in_place'] = True
            info['actions'].append(f'DGS already in convert out_dir: {dest_dgs}')
        else:
            shutil.copy2(src, dest_dgs)
            info['copied_dgs'] = True
            info['actions'].append(f'Copied DGS -> {dest_dgs}')
    except OSError as exc:
        info['errors'].append(f'Failed to persist DGS: {exc}')
        return info

    if copy_sidecars:
        src_dir = src.parent
        for pattern in _FEEDER_SIDECAR_NAMES:
            name = pattern.format(feeder=feeder)
            src_side = src_dir / name
            dest_side = dest_dir / name
            if not src_side.is_file():
                continue
            try:
                if dest_side.resolve() == src_side.resolve():
                    info['sidecars'].append({'name': name, 'status': 'already_in_place'})
                    continue
                shutil.copy2(src_side, dest_side)
                info['sidecars'].append({'name': name, 'status': 'copied', 'path': str(dest_side)})
                info['actions'].append(f'Copied sidecar -> {dest_side}')
            except OSError as exc:
                info['warnings'].append(f'Sidecar {name}: {exc}')

    info['ok'] = dest_dgs.is_file() and not info['errors']
    if not info['ok'] and not info['errors']:
        info['errors'].append(f'DGS not present after persist: {dest_dgs}')
    return info


def _find_dgs_export_definitions(app: Any) -> Any | None:
    """Locate user IntFolder whose name contains 'DGS' and 'Definition' (ApiExample)."""
    try:
        user = app.GetCurrentUser()
    except Exception:
        return None
    if user is None:
        return None
    folders = _contents(user, '*.IntFolder')
    if not folders:
        # Shallow children only
        try:
            folders = list(user.GetContents('*.IntFolder') or [])
        except Exception:
            folders = []
    for folder in folders:
        name = _name(folder)
        if 'DGS' in name.upper() and 'DEFINITION' in name.upper():
            return folder
    return None


def export_dgs_file(app: Any, dest_path: Path | str) -> dict[str, Any]:
    """Best-effort ComExport of the active project to ``dest_path``.

    Mirrors DigSilent ``ApiExample.cpp`` ``ExportDgsFile`` (ComExport + optional
    export-definition folder). Fragile across PF setups — callers must fall back
    to ``persist_feeder_dgs`` when this fails.
    """
    dest = Path(dest_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    info: dict[str, Any] = {
        'ok': False,
        'path': str(dest),
        'method': None,
        'return_code': None,
        'errors': [],
        'warnings': [],
        'help_refs': ['Api/Example/src/ApiExample.cpp — ExportDgsFile / ComExport'],
    }

    cmd = None
    try:
        cmd = app.GetFromStudyCase('ComExport')
    except Exception:
        cmd = None
    if cmd is None:
        try:
            cmd = app.GetCaseObject('ComExport')
        except Exception:
            cmd = None
    if cmd is None:
        try:
            user = app.GetCurrentUser()
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            cmd = user.CreateObject('ComExport', f'DGSExport_{stamp}') if user else None
        except Exception as exc:
            info['errors'].append(f'Could not create ComExport: {exc}')
            return info
    if cmd is None:
        info['errors'].append('ComExport unavailable (GetFromStudyCase / CreateObject failed)')
        return info

    export_defs = _find_dgs_export_definitions(app)
    formats_tried: list[str] = []
    for fmt in ('DGS File', 'ASCII File'):
        formats_tried.append(fmt)
        applied = {}
        for name, value in (
            ('dgsFormat', fmt),
            ('fFile', str(dest)),
            ('fName', str(dest)),
        ):
            if _set_attr(cmd, name, value):
                applied[name] = value
        if export_defs is not None and _set_attr(cmd, 'pPer', export_defs):
            applied['pPer'] = _name(export_defs)
        # Optional version hint from ApiExample
        _set_attr(cmd, 'dgsVer', 'V5.00')
        try:
            # Bulk transfer when API supports it (ApiExample pattern)
            try:
                app.DefineTransferAttributes('ComExport', 'dgsVer,dgsFormat,fFile,pPer')
                if export_defs is not None:
                    cmd.SetAttributes(['V5.00', fmt, str(dest), export_defs])
            except Exception:
                pass
            rc = int(cmd.Execute())
            info['return_code'] = rc
            if rc == 0 and dest.is_file() and dest.stat().st_size > 0:
                info['ok'] = True
                info['method'] = f'ComExport:{fmt}'
                info['attrs'] = applied
                break
            if rc != 0:
                info['warnings'].append(f'ComExport({fmt}).Execute returned {rc}')
            elif not dest.is_file() or dest.stat().st_size == 0:
                info['warnings'].append(f'ComExport({fmt}) produced empty/missing file')
        except Exception as exc:
            info['warnings'].append(f'ComExport({fmt}) failed: {exc}')

    if not info['ok']:
        info['errors'].append(
            'ComExport did not produce a non-empty DGS '
            f'(tried formats: {", ".join(formats_tried)}; '
            f'export_defs={"yes" if export_defs else "no"})'
        )
    return info


def persist_after_pf_gate(
    dgs_path: Path | str,
    *,
    out_dir: Path | str | None = None,
    app: Any | None = None,
    export_converged: bool = True,
    converged: bool = False,
) -> dict[str, Any]:
    """Ensure convert-folder DGS; optionally ComExport ``{feeder}_pf_converged.dgs``.

    Preference order (per product decision):
      1. Always persist/copy converter ``{feeder}.dgs`` into out_dir (idempotent).
      2. If ``converged`` and ``export_converged`` and ``app`` given, try ComExport
         into ``{feeder}_pf_converged.dgs`` in the same folder.
      3. If export fails, keep converter DGS and record a warning (do not invent
         a fake converged file).
    """
    persist = persist_feeder_dgs(dgs_path, out_dir=out_dir)
    report: dict[str, Any] = {
        'ok': bool(persist.get('ok')),
        'persist': persist,
        'export_converged': None,
        'errors': list(persist.get('errors') or []),
        'warnings': list(persist.get('warnings') or []),
        'out_dir': persist.get('out_dir'),
        'dgs': persist.get('dgs'),
        'converged_dgs': None,
    }
    if not persist.get('ok'):
        return report

    if export_converged and converged and app is not None:
        feeder = persist['feeder']
        dest = Path(persist['out_dir']) / f'{feeder}_pf_converged.dgs'
        export_info = export_dgs_file(app, dest)
        report['export_converged'] = export_info
        if export_info.get('ok'):
            report['converged_dgs'] = export_info.get('path')
            report['warnings'].extend(export_info.get('warnings') or [])
        else:
            report['warnings'].append(
                'ComExport of converged project failed — converter DGS remains in '
                f"{persist['out_dir']} as {Path(persist['dgs']).name}. "
                'PF in-memory corrections (outserv/load scale) are not on disk.'
            )
            report['warnings'].extend(export_info.get('warnings') or [])
            for err in export_info.get('errors') or []:
                report['warnings'].append(f'export: {err}')
    elif export_converged and converged and app is None:
        report['warnings'].append(
            'Converged export requested but no PF app handle — only converter DGS persisted'
        )

    report['ok'] = bool(persist.get('ok')) and not report['errors']
    return report


def _pick_named(objects: list[Any], *, prefer_substrings: tuple[str, ...]) -> Any | None:
    if not objects:
        return None
    lowered = [(obj, _name(obj).casefold()) for obj in objects]
    for needle in prefer_substrings:
        for obj, name in lowered:
            if needle in name:
                return obj
    return objects[0]


def activate_base_study_and_scenario(app: Any) -> dict[str, Any]:
    """Activate Study Case base + Operation Scenario base when present."""
    info: dict[str, Any] = {
        'study_case': None,
        'scenario': None,
        'study_activated': False,
        'scenario_activated': False,
        'errors': [],
        'warnings': [],
    }

    study_folder = None
    scen_folder = None
    try:
        study_folder = app.GetProjectFolder('study')
    except Exception:
        pass
    try:
        scen_folder = app.GetProjectFolder('scen')
    except Exception:
        pass

    cases = _contents(study_folder, '*.IntCase') if study_folder else []
    if not cases:
        cases = _calc_objects(app, '*.IntCase')
    scenarios = _contents(scen_folder, '*.IntScenario') if scen_folder else []
    if not scenarios:
        scenarios = _calc_objects(app, '*.IntScenario')

    case = _pick_named(
        cases,
        prefer_substrings=('base', 'estudio base', 'study case', 'caso base', 'grund'),
    )
    scenario = _pick_named(
        scenarios,
        prefer_substrings=('base', 'operacion', 'operation', 'escenario base', 'betrieb'),
    )

    if case is None:
        info['warnings'].append('No IntCase found — using whatever study case PF left active')
    else:
        info['study_case'] = _name(case)
        try:
            rc = int(case.Activate())
            active_after = app.GetActiveStudyCase()
            already = active_after is not None and _name(active_after) == _name(case)
            # DigSilent may return 1 when the case is already active.
            info['study_activated'] = rc == 0 or already
            if not info['study_activated']:
                info['errors'].append(f'StudyCase.Activate() returned {rc}')
            elif rc != 0:
                info['warnings'].append(
                    f'StudyCase.Activate() returned {rc} but active case is {_name(active_after)!r} (treated OK)'
                )
        except Exception as exc:
            info['errors'].append(f'StudyCase.Activate failed: {exc}')

    if scenario is None:
        info['warnings'].append(
            'No IntScenario found — operation scenario not activated '
            '(PF may still run LDF on default state)'
        )
    else:
        info['scenario'] = _name(scenario)
        try:
            rc = int(scenario.Activate())
            active_after = app.GetActiveScenario()
            already = active_after is not None and _name(active_after) == _name(scenario)
            info['scenario_activated'] = rc == 0 or already
            if not info['scenario_activated']:
                info['errors'].append(f'Scenario.Activate() returned {rc}')
            elif rc != 0:
                info['warnings'].append(
                    f'Scenario.Activate() returned {rc} but active scenario is {_name(active_after)!r} (treated OK)'
                )
        except Exception as exc:
            info['errors'].append(f'Scenario.Activate failed: {exc}')

    active_case = app.GetActiveStudyCase()
    active_scen = app.GetActiveScenario()
    info['active_study_case'] = _name(active_case) if active_case else None
    info['active_scenario'] = _name(active_scen) if active_scen else None
    return info


def ensure_operation_scenario(
    app: Any,
    *,
    name: str = 'Operation Scenario',
) -> dict[str, Any]:
    """Find an IntScenario or create one, then activate it.

    DigSilent DGS imports often leave Study Case present but no operation
    scenario; load flow can still run, but GUI/acceptance expect an explicit
    IntScenario for operating state.
    """
    info: dict[str, Any] = {
        'scenario': None,
        'created': False,
        'activated': False,
        'errors': [],
        'warnings': [],
    }

    scen_folder = None
    try:
        scen_folder = app.GetProjectFolder('scen')
    except Exception:
        pass

    scenarios = _contents(scen_folder, '*.IntScenario') if scen_folder else []
    if not scenarios:
        scenarios = _calc_objects(app, '*.IntScenario')

    scenario = _pick_named(
        scenarios,
        prefer_substrings=('base', 'operacion', 'operation', 'escenario', 'betrieb'),
    )

    if scenario is None:
        parent = scen_folder
        if parent is None:
            try:
                parent = app.GetActiveProject()
            except Exception:
                parent = None
        if parent is None:
            info['errors'].append('No scenario folder / active project to create IntScenario')
            return info
        try:
            scenario = parent.CreateObject('IntScenario', name)
            if scenario is None:
                info['errors'].append(f'CreateObject(IntScenario, {name!r}) returned None')
                return info
            info['created'] = True
        except Exception as exc:
            info['errors'].append(f'CreateObject(IntScenario) failed: {exc}')
            return info

    info['scenario'] = _name(scenario)
    try:
        rc = int(scenario.Activate())
        active_after = app.GetActiveScenario()
        already = active_after is not None and _name(active_after) == _name(scenario)
        info['activated'] = rc == 0 or already
        if not info['activated']:
            info['errors'].append(f'Scenario.Activate() returned {rc}')
        elif rc != 0:
            info['warnings'].append(
                f'Scenario.Activate() returned {rc} but active scenario is '
                f'{_name(active_after)!r} (treated OK)'
            )
    except Exception as exc:
        info['errors'].append(f'Scenario.Activate failed: {exc}')

    active_scen = app.GetActiveScenario()
    info['active_scenario'] = _name(active_scen) if active_scen else None
    return info


# ---------------------------------------------------------------------------
# Load flow + non-convergence corrections
# ---------------------------------------------------------------------------
# Correction order follows DigSILENT User Manual §24.6 (Troubleshooting Load
# Flow Calculation Problems): relax regulation/limits → restore sources →
# remove unsupplied loads → shed/scale load → isolate islands → restore scale.
# Attribute names from PF Help localisation (ComLdf.*) and User Manual ch. 24.3.

CORRECTION_INTENTS: tuple[str, ...] = (
    'relaxed_ldf_options',
    'source_in_service',
    'disconnect_floating_loads',
    'scale_loads_50',
    'island_out_of_service',
    'scale_loads_75',
    'scale_loads_100',
)

# ComLdf.Execute return codes — PythonReference §5.4.23 ComLdf.Execute
_COMLDF_RC_MEANING: dict[int, str] = {
    0: 'OK',
    1: 'divergence of inner loops (often voltage stability / excess load)',
    2: 'divergence of outer loops (taps / Q-limits / shunt switching)',
}

# Documented ComLdf options applied for “relaxed” retries (User Manual §24.6.5
# and §24.3.1: disable reactive limits, disable auto taps; §24.4.5 flat start;
# Automatic Model Adaptation for Convergence = iopt_lev).
_RELAXED_COMLDF_ATTRS: tuple[tuple[str, Any], ...] = (
    ('iopt_lim', 0),       # Consider reactive power limits = off
    ('iopt_plim', 0),      # Consider active power limits = off
    ('iopt_at', 0),        # Automatic tap adjustment of transformers = off
    ('iopt_asht', 0),      # Automatic tap adjustment of shunts = off
    ('iPST_at', 0),        # Automatic tap adjustment of phase shifters = off
    ('iopt_pq', 0),        # Consider Voltage Dependency of Loads = off
    ('iopt_fl', 1),        # Flat Start = on (default AC initialisation)
    ('iopt_lev', 1),       # Automatic Model Adaptation for Convergence = on
    ('iopt_noinit', 0),    # do not force start-from-last-results
)


def _configure_comldf(
    cmd: Any,
    *,
    relaxed: bool = False,
    iopt_net: int | None = None,
    iopt_pq: int | None = None,
    iopt_lim: int | None = None,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Set ComLdf attributes per DigSILENT Help; return applied map."""
    applied: dict[str, Any] = {}
    # User Manual §24.3.1.1 / DPL: iopt_net=0 balanced AC, 1 unbalanced, …
    net_opt = 0 if iopt_net is None else iopt_net
    if _set_attr(cmd, 'iopt_net', net_opt):
        applied['iopt_net'] = net_opt

    if relaxed:
        for name, value in _RELAXED_COMLDF_ATTRS:
            if _set_attr(cmd, name, value):
                applied[name] = value
        # Caller overrides win when explicitly provided.
        if iopt_lim is not None and _set_attr(cmd, 'iopt_lim', iopt_lim):
            applied['iopt_lim'] = iopt_lim
        if iopt_pq is not None and _set_attr(cmd, 'iopt_pq', iopt_pq):
            applied['iopt_pq'] = iopt_pq
    else:
        # Standard MV feeder defaults: balanced AC; keep vendor defaults for
        # regulation unless the caller overrides.
        if iopt_lim is not None and _set_attr(cmd, 'iopt_lim', iopt_lim):
            applied['iopt_lim'] = iopt_lim
        if iopt_pq is not None and _set_attr(cmd, 'iopt_pq', iopt_pq):
            applied['iopt_pq'] = iopt_pq

    if show_progress and _set_attr(cmd, 'iopt_show', 1):
        # User Manual §24.6.4 — Show Convergence Progress Report
        applied['iopt_show'] = 1
    return applied


def execute_load_flow(
    app: Any,
    *,
    relaxed: bool = False,
    iopt_net: int | None = None,
    iopt_pq: int | None = None,
    iopt_lim: int | None = None,
    show_progress: bool = False,
) -> dict[str, Any]:
    """Execute ComLdf on the active study case and report IsLdfValid.

    Uses ``GetFromStudyCase('ComLdf')`` (creates command if missing — DPL /
    PythonReference). Validates with ``Application.IsLdfValid()``
    (ApiExample.cpp / PythonReference).
    """
    result: dict[str, Any] = {
        'pass': False,
        'return_code': None,
        'return_meaning': None,
        'ldf_valid': None,
        'relaxed': relaxed,
        'comldf_attrs': {},
        'errors': [],
        'help_refs': [
            'UserManual §24.3 ComLdf options / §24.6 troubleshooting',
            'PythonReference §5.4.23 ComLdf.Execute / Application.IsLdfValid',
        ],
    }
    try:
        # DPL GetFromStudyCase*: creates the command when absent (study-case
        # pattern — User Manual §12.8 Commands).
        cmd = app.GetFromStudyCase('ComLdf')
        if cmd is None:
            result['errors'].append('ComLdf not found/created in active study case')
            return result
        result['comldf_attrs'] = _configure_comldf(
            cmd,
            relaxed=relaxed,
            iopt_net=iopt_net,
            iopt_pq=iopt_pq,
            iopt_lim=iopt_lim,
            show_progress=show_progress,
        )
        rc = int(cmd.Execute())
        result['return_code'] = rc
        result['return_meaning'] = _COMLDF_RC_MEANING.get(rc, f'unknown return code {rc}')
        ldf_valid = None
        try:
            ldf_valid = int(app.IsLdfValid()) == 1
        except Exception:
            try:
                ldf_valid = bool(app.Execute('IsLdfValid'))
            except Exception:
                ldf_valid = rc == 0
        result['ldf_valid'] = ldf_valid
        result['pass'] = rc == 0 and bool(ldf_valid)
        if rc != 0:
            result['errors'].append(
                f'Load flow ComLdf.Execute returned {rc} '
                f'({result["return_meaning"]})'
            )
        elif not ldf_valid:
            result['errors'].append('Load flow executed but IsLdfValid is false (no convergence)')
    except Exception as exc:
        result['errors'].append(f'Load flow execution failed: {exc}')
    return result


def _is_out_of_service(obj: Any) -> bool:
    val = _attr(obj, 'outserv', 0)
    try:
        return int(val) != 0
    except (TypeError, ValueError):
        return bool(val)


def _set_outserv(obj: Any, value: int) -> bool:
    return _set_attr(obj, 'outserv', value)


def _scale_load_powers(load: Any, factor: float, originals: dict[int, dict[str, float]]) -> bool:
    """Scale plini/qlini (or plinir/…) by factor relative to first-seen originals."""
    key = id(load)
    attrs = ('plini', 'qlini', 'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit')
    if key not in originals:
        snap: dict[str, float] = {}
        for name in attrs:
            raw = _attr(load, name, None)
            if raw is None:
                continue
            try:
                snap[name] = float(raw)
            except (TypeError, ValueError):
                continue
        originals[key] = snap
    snap = originals[key]
    if not snap:
        return False
    ok = False
    for name, base in snap.items():
        if _set_attr(load, name, base * factor):
            ok = True
    return ok


def _load_has_terminal(load: Any) -> bool:
    cub = _one_terminal_cubicle(load)
    return _terminal_of_cubicle(cub) is not None


def _sources(app: Any) -> list[Any]:
    found = _calc_objects(app, '*.ElmXnet')
    found.extend(_calc_objects(app, '*.ElmVac'))
    return found


def _loads(app: Any) -> list[Any]:
    return _calc_objects(app, '*.ElmLod')


def diagnose_nonconvergence(app: Any, *, last_ldf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect likely causes when ComLdf does not converge.

    Grounded in User Manual §24.6 (unsupplied areas / islands, excess demand,
    outer-loop tap/Q-limit issues) and the PF object model (``outserv``,
    ElmXnet/ElmVac sources, ElmLod cubicle→terminal connectivity).
    """
    sources = _sources(app)
    loads = _loads(app)
    sources_oos = [_name(s) for s in sources if _is_out_of_service(s)]
    sources_ok = [_name(s) for s in sources if not _is_out_of_service(s)]
    floating = [_name(ld) for ld in loads if not _load_has_terminal(ld)]
    loads_oos = [_name(ld) for ld in loads if _is_out_of_service(ld)]
    loads_in = [ld for ld in loads if not _is_out_of_service(ld)]

    messages: list[str] = []
    try:
        # Best-effort: recent output window text (API varies by PF version).
        for method_name in ('GetOutputWindow', 'GetOutputWindowContent'):
            method = getattr(app, method_name, None)
            if method is None:
                continue
            try:
                text = method()
            except TypeError:
                text = method(0)
            if text:
                messages.append(str(text)[:2000])
            break
    except Exception:
        pass

    issues: list[str] = []
    if last_ldf and last_ldf.get('return_code') not in (None, 0):
        meaning = last_ldf.get('return_meaning') or _COMLDF_RC_MEANING.get(
            int(last_ldf['return_code']), ''
        )
        issues.append(
            f"ComLdf.Execute rc={last_ldf.get('return_code')} — {meaning} "
            '(PythonReference §5.4.23)'
        )
        if int(last_ldf.get('return_code') or 0) == 1:
            issues.append(
                'Inner-loop divergence hint (User Manual §24.6.4): excess P demand, '
                'weak feed, or voltage collapse — try load scaling / shed floating loads'
            )
        if int(last_ldf.get('return_code') or 0) == 2:
            issues.append(
                'Outer-loop divergence hint (User Manual §24.6.5): disable auto taps '
                '(iopt_at) and reactive limits (iopt_lim) — relaxed ComLdf options'
            )
    if not sources:
        issues.append('No ElmXnet/ElmVac voltage source found (no slack / external grid)')
    if sources_oos and not sources_ok:
        issues.append(
            f'All voltage sources out of service (outserv≠0): {sources_oos[:10]} '
            '(User Manual: calculations only on in-service equipment)'
        )
    elif sources_oos:
        issues.append(f'Some sources out of service (outserv≠0): {sources_oos[:10]}')
    if floating:
        issues.append(
            f'Loads without terminal connection (unsupplied / floating — §24.6.3): '
            f'{floating[:15]}'
        )
    if loads_in and not sources_ok:
        issues.append('Loads in service but no in-service source → unsupplied area (§24.6.3)')
    if not issues:
        issues.append(
            'No structural issue detected; try relaxed ComLdf options '
            '(iopt_lim/iopt_at/iopt_fl/iopt_lev) or load scaling (§24.6)'
        )

    return {
        'issues': issues,
        'sources_total': len(sources),
        'sources_in_service': sources_ok,
        'sources_out_of_service': sources_oos,
        'loads_total': len(loads),
        'loads_out_of_service': loads_oos,
        'floating_loads': floating,
        'pf_messages_sample': messages[:3],
        'help_refs': [
            'UserManual §24.6 Troubleshooting Load Flow Calculation Problems',
            'Element attribute outserv = Out of Service (localisation)',
        ],
    }


def apply_correction_intent(
    app: Any,
    intent: str,
    diagnosis: dict[str, Any],
    *,
    load_scale_originals: dict[int, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Apply one correction intent; returns description of the solution applied.

    Intents mirror DigSILENT-documented countermeasures (User Manual §24.6):
    relax ComLdf regulation/limits, restore sources (``outserv=0``), take
    unsupplied loads out of service, scale/shed load, handle islands.
    """
    originals = load_scale_originals if load_scale_originals is not None else {}
    applied: dict[str, Any] = {
        'intent': intent,
        'ok': False,
        'solution': '',
        'actions': [],
        'errors': [],
        'help_refs': [],
    }

    if intent == 'relaxed_ldf_options':
        applied['ok'] = True
        applied['solution'] = (
            'Reintentar ComLdf con opciones documentadas: iopt_lim=0, iopt_at=0, '
            'iopt_fl=1 (flat start), iopt_lev=1 (Automatic Model Adaptation).'
        )
        applied['actions'].append(
            'next Execute uses _RELAXED_COMLDF_ATTRS '
            '(User Manual §24.3.1 / §24.6.5 / localisation ComLdf.*)'
        )
        applied['help_refs'] = [
            'UserManual §24.6.5 — load flow without reactive limits / without auto taps',
            'localisation: ComLdf.iopt_lim / iopt_at / iopt_fl / iopt_lev',
        ]
        return applied

    if intent == 'source_in_service':
        changed = []
        for src in _sources(app):
            if _is_out_of_service(src) and _set_outserv(src, 0):
                changed.append(_name(src))
        applied['ok'] = True
        applied['solution'] = (
            'Poner fuentes de tensión (ElmXnet/ElmVac) en servicio (outserv=0).'
        )
        applied['actions'] = [f'outserv=0 → {n}' for n in changed] or ['ninguna fuente estaba fuera']
        applied['help_refs'] = ['Element attribute outserv = Out of Service']
        return applied

    if intent == 'disconnect_floating_loads':
        floating_names = set(diagnosis.get('floating_loads') or [])
        changed = []
        for ld in _loads(app):
            if _name(ld) in floating_names or not _load_has_terminal(ld):
                if _set_outserv(ld, 1):
                    changed.append(_name(ld))
        applied['ok'] = True
        applied['solution'] = (
            'Sacar de servicio cargas sin conexión a terminal (áreas no alimentadas §24.6.3).'
        )
        applied['actions'] = [f'outserv=1 → {n}' for n in changed] or ['no había cargas flotantes']
        applied['help_refs'] = ['UserManual §24.6.3 — unsupplied areas']
        return applied

    if intent in ('scale_loads_50', 'scale_loads_75', 'scale_loads_100'):
        factor = {'scale_loads_50': 0.5, 'scale_loads_75': 0.75, 'scale_loads_100': 1.0}[intent]
        changed = 0
        for ld in _loads(app):
            if _is_out_of_service(ld):
                continue
            if _scale_load_powers(ld, factor, originals):
                changed += 1
        applied['ok'] = True
        applied['solution'] = (
            f'Escalar potencias de cargas activas al {int(factor * 100)}% del valor original '
            '(load shedding / rebalance — User Manual §24.6.4).'
        )
        applied['actions'].append(f'scaled {changed} loads to {factor}')
        applied['help_refs'] = [
            'UserManual §24.6.4 — load shedding for voltage stability',
            'ElmLod plini/qlini (or phasewise plinir…)',
        ]
        return applied

    if intent == 'island_out_of_service':
        # User Manual §24.6.3: unsupplied / isolated areas need a slack or must
        # be taken out of service. We OOS floating loads and restore sources.
        changed = []
        for ld in _loads(app):
            if _is_out_of_service(ld):
                continue
            if not _load_has_terminal(ld):
                if _set_outserv(ld, 1):
                    changed.append(_name(ld))
        for src in _sources(app):
            if _is_out_of_service(src) and _set_outserv(src, 0):
                changed.append(f'source:{_name(src)}')
        applied['ok'] = True
        applied['solution'] = (
            'Sacar de servicio elementos claramente desconectados; asegurar fuente en servicio '
            '(islas / unsupplied areas — User Manual §24.6.3).'
        )
        applied['actions'] = [f'oos/restore → {n}' for n in changed] or ['sin cambios adicionales']
        applied['help_refs'] = ['UserManual §24.6.3 — isolated / unsupplied areas']
        return applied

    applied['errors'].append(f'Unknown correction intent: {intent}')
    return applied


def run_load_flow_until_converged(
    app: Any,
    *,
    max_intents: int = 7,
    intents: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run ComLdf; on failure diagnose and apply correction intents until pass or exhausted."""
    sequence = list(intents or CORRECTION_INTENTS)[:max_intents]
    load_scale_originals: dict[int, dict[str, float]] = {}
    attempts: list[dict[str, Any]] = []

    first = execute_load_flow(app, relaxed=False)
    attempts.append({
        'attempt': 0,
        'phase': 'initial',
        'load_flow': first,
        'diagnosis': None,
        'correction': None,
    })
    if first.get('pass'):
        return {
            'pass': True,
            'attempts': attempts,
            'final_load_flow': first,
            'converged_after_intent': None,
        }

    diagnosis = diagnose_nonconvergence(app, last_ldf=first)
    attempts[-1]['diagnosis'] = diagnosis

    for idx, intent in enumerate(sequence, start=1):
        correction = apply_correction_intent(
            app,
            intent,
            diagnosis,
            load_scale_originals=load_scale_originals,
        )
        relaxed = intent == 'relaxed_ldf_options'
        ldf = execute_load_flow(app, relaxed=relaxed, show_progress=(idx == 1))
        entry = {
            'attempt': idx,
            'phase': 'correction',
            'intent': intent,
            'diagnosis': diagnosis,
            'correction': correction,
            'load_flow': ldf,
        }
        attempts.append(entry)
        if ldf.get('pass'):
            return {
                'pass': True,
                'attempts': attempts,
                'final_load_flow': ldf,
                'converged_after_intent': intent,
            }
        diagnosis = diagnose_nonconvergence(app, last_ldf=ldf)
        entry['diagnosis_after'] = diagnosis

    return {
        'pass': False,
        'attempts': attempts,
        'final_load_flow': attempts[-1]['load_flow'],
        'converged_after_intent': None,
        'exhausted': True,
        'final_diagnosis': diagnosis,
    }


# ---------------------------------------------------------------------------
# Study suite (extensible Com* runners for MV feeders)
# ---------------------------------------------------------------------------
# Registry of calculation modules. Each runner uses GetFromStudyCase(<Com*>)
# per User Manual §12.8 / DPL GetFromStudyCase*. Add new studies by registering
# a callable — do not claim modules that are not wired.

DEFAULT_STUDY_SUITE: tuple[str, ...] = (
    'load_flow',
    'short_circuit',
)

# Documented stubs — not executed until a runner is registered.
STUDY_SUITE_GAPS: dict[str, str] = {
    'contingency': 'ComContingency / ComSimoutage - not wired (needs contingency set)',
    'opf': 'ComOpf - not wired (optimisation licence / objective setup)',
    'rms': 'ComInc + ComSim - not wired (dynamic models beyond steady-state feeder gate)',
    'harmonics': 'ComHldf / harmonics - not wired',
    'reliability': 'ComNmink - not wired',
}


def execute_short_circuit(
    app: Any,
    *,
    all_busbars: bool = True,
    max_currents: bool = True,
    three_phase: bool = True,
) -> dict[str, Any]:
    """Execute ComShc (short-circuit) on the active study case.

    Attribute names from PF Help localisation (ComShc.iopt_*). Method defaults
    prefer IEC 60909 when the flag exists; values are applied defensively so
    missing licence / older schemas still report a clear status.

    Help: User Manual ch. 25 Short-Circuit Analysis; PythonReference §5.4.43 ComShc.
    """
    result: dict[str, Any] = {
        'study': 'short_circuit',
        'command': 'ComShc',
        'pass': False,
        'available': False,
        'return_code': None,
        'comshc_attrs': {},
        'fault_type': None,
        'errors': [],
        'warnings': [],
        'help_refs': [
            'UserManual ch. 25 Short-Circuit Analysis',
            'PythonReference §5.4.43 ComShc',
            'localisation: ComShc.iopt_mde / iopt_allbus / iopt_max / iopt_3psc',
        ],
    }
    try:
        cmd = app.GetFromStudyCase('ComShc')
    except Exception as exc:
        result['errors'].append(f'GetFromStudyCase(ComShc) failed: {exc}')
        result['warnings'].append(
            'ComShc unavailable — short-circuit module missing, not licensed, '
            'or API rejected creation (check PF licence)'
        )
        return result
    if cmd is None:
        result['errors'].append('ComShc not found/created in active study case')
        result['warnings'].append(
            'ComShc unavailable — likely missing short-circuit licence/module'
        )
        return result
    result['available'] = True

    # Defensive attribute set (only applied when SetAttribute succeeds).
    desired: list[tuple[str, Any]] = []
    # Method: prefer IEC 60909 flag when present; else leave vendor default.
    desired.append(('iopt_iec', 1))
    if all_busbars:
        # localisation: At: User Selection | Busbars and Junction Nodes | All Busbars
        desired.append(('iopt_allbus', 2))
    if max_currents:
        desired.append(('iopt_max', 1))
        desired.append(('iopt_min', 0))
    if three_phase:
        desired.append(('iopt_3psc', 1))
        desired.append(('iopt_shc', 0))  # Fault Type enum — 3ph when supported
    applied: dict[str, Any] = {}
    for name, value in desired:
        if _set_attr(cmd, name, value):
            applied[name] = value
    result['comshc_attrs'] = applied

    try:
        fault = None
        try:
            fault = int(cmd.GetFaultType())
        except Exception:
            fault = _attr(cmd, 'iopt_shc', None)
        result['fault_type'] = fault
    except Exception:
        pass

    try:
        rc = int(cmd.Execute())
        result['return_code'] = rc
        result['pass'] = rc == 0
        if rc != 0:
            msg = (
                f'ComShc.Execute returned {rc} — calculation failed or module '
                'not licensed for this project'
            )
            result['errors'].append(msg)
            # Common licence / method failures surface as non-zero rc.
            err_l = msg.lower()
            if 'licen' in err_l or rc in (1, 2, 3):
                result['warnings'].append(
                    'If the short-circuit licence is missing, PF still exposes ComShc '
                    'but Execute fails — see licence manager / Help licence extensions'
                )
    except Exception as exc:
        result['errors'].append(f'ComShc.Execute failed: {exc}')
        result['warnings'].append(
            'Short-circuit execution raised — often licence/module or incomplete '
            'fault setup on imported DGS feeder'
        )
    return result


def _run_study_load_flow(
    app: Any,
    *,
    fix_until_converge: bool = True,
    max_intents: int = 7,
) -> dict[str, Any]:
    if fix_until_converge:
        loop = run_load_flow_until_converged(app, max_intents=max_intents)
    else:
        ldf = execute_load_flow(app, relaxed=False)
        loop = {
            'pass': bool(ldf.get('pass')),
            'attempts': [{'attempt': 0, 'phase': 'initial', 'load_flow': ldf}],
            'final_load_flow': ldf,
            'converged_after_intent': None,
        }
    return {
        'study': 'load_flow',
        'command': 'ComLdf',
        'pass': bool(loop.get('pass')),
        'available': True,
        'load_flow_loop': loop,
        'errors': [] if loop.get('pass') else ['Load flow did not converge'],
        'warnings': [],
        'help_refs': [
            'UserManual §12.8 / §24 ComLdf',
            'PythonReference §5.4.23 ComLdf',
        ],
    }


def _run_study_short_circuit(app: Any, **_kwargs: Any) -> dict[str, Any]:
    return execute_short_circuit(app)


# study_id → runner(app, **kwargs) -> dict
STUDY_REGISTRY: dict[str, Any] = {
    'load_flow': _run_study_load_flow,
    'short_circuit': _run_study_short_circuit,
}


def list_study_suite() -> dict[str, Any]:
    """Describe runnable studies and documented gaps (for CLI/docs/tests)."""
    return {
        'default': list(DEFAULT_STUDY_SUITE),
        'registered': sorted(STUDY_REGISTRY.keys()),
        'gaps': dict(STUDY_SUITE_GAPS),
    }


def run_study_suite(
    app: Any,
    studies: tuple[str, ...] | list[str] | None = None,
    *,
    fix_until_converge: bool = True,
    max_intents: int = 7,
) -> dict[str, Any]:
    """Run a coherent study suite on the active project/study case.

    Default: load_flow (ComLdf, optional fix-until-converge) then short_circuit
    (ComShc). Unknown study ids are reported; known gaps are documented without
    claiming execution.
    """
    wanted = list(studies or DEFAULT_STUDY_SUITE)
    report: dict[str, Any] = {
        'ok': True,
        'studies_requested': wanted,
        'results': [],
        'errors': [],
        'warnings': [],
        'gaps_noted': [],
        'registry': list_study_suite(),
    }
    for study_id in wanted:
        if study_id in STUDY_SUITE_GAPS and study_id not in STUDY_REGISTRY:
            note = STUDY_SUITE_GAPS[study_id]
            report['gaps_noted'].append({'study': study_id, 'note': note})
            report['warnings'].append(f'Study {study_id!r} not wired: {note}')
            continue
        runner = STUDY_REGISTRY.get(study_id)
        if runner is None:
            report['errors'].append(f'Unknown study {study_id!r} — not in STUDY_REGISTRY')
            report['ok'] = False
            continue
        try:
            result = runner(
                app,
                fix_until_converge=fix_until_converge,
                max_intents=max_intents,
            )
        except Exception as exc:
            result = {
                'study': study_id,
                'pass': False,
                'available': False,
                'errors': [f'Study runner crashed: {exc}'],
                'warnings': [],
            }
        report['results'].append(result)
        report['warnings'].extend(result.get('warnings') or [])
        if not result.get('pass'):
            # Short-circuit may be unavailable (licence) without failing the
            # whole suite hard — mark warning but keep ok=False only for LDF
            # failure or hard errors.
            if study_id == 'load_flow':
                report['ok'] = False
                report['errors'].extend(result.get('errors') or [])
            elif not result.get('available'):
                report['warnings'].append(
                    f'{study_id}: module not available / not licensed — skipped as FAIL soft'
                )
            else:
                report['ok'] = False
                report['errors'].extend(result.get('errors') or [])
    return report


def run_import_activate_flow(
    app: Any,
    dgs_path: Path,
    *,
    project_name: str | None = None,
    ensure_scenario: bool = True,
    run_load_flow_flag: bool = True,
    fix_until_converge: bool = True,
    max_intents: int = 7,
    run_studies: bool = False,
    studies: tuple[str, ...] | None = None,
    persist_dgs: bool = True,
    persist_dir: Path | str | None = None,
    export_converged_dgs: bool = True,
) -> dict[str, Any]:
    """Import DGS, activate study/scenario, run load flow and optional study suite.

    After a successful import, persists ``{feeder}.dgs`` into the convert out_dir
    (``persist_dir`` or parent of ``dgs_path``). When LDF converges, optionally
    tries ComExport to ``{feeder}_pf_converged.dgs`` in the same folder.
    """
    report: dict[str, Any] = {
        'dgs': str(Path(dgs_path).resolve()),
        'ok': False,
        'import': None,
        'study_scenario': None,
        'scenario_ensure': None,
        'load_flow_loop': None,
        'study_suite': None,
        'dgs_persist': None,
        'errors': [],
        'warnings': [],
    }

    try:
        import_info = import_dgs_file(app, Path(dgs_path), project_name=project_name)
    except Exception as exc:
        report['errors'].append(f'DGS import failed: {exc}')
        return report
    report['import'] = import_info
    time.sleep(0.5)
    if not import_info.get('ok'):
        report['errors'].extend(import_info.get('errors') or [])
        return report

    study_info = activate_base_study_and_scenario(app)
    report['study_scenario'] = study_info
    report['warnings'].extend(study_info.get('warnings') or [])
    report['errors'].extend(study_info.get('errors') or [])

    if ensure_scenario and not study_info.get('scenario_activated'):
        scen_info = ensure_operation_scenario(app)
        report['scenario_ensure'] = scen_info
        report['warnings'].extend(scen_info.get('warnings') or [])
        report['errors'].extend(scen_info.get('errors') or [])
        # Refresh study_scenario active fields for callers.
        if scen_info.get('activated'):
            study_info['scenario'] = scen_info.get('scenario')
            study_info['scenario_activated'] = True
            study_info['active_scenario'] = scen_info.get('active_scenario')

    if run_studies:
        suite = run_study_suite(
            app,
            studies=studies,
            fix_until_converge=fix_until_converge,
            max_intents=max_intents,
        )
        report['study_suite'] = suite
        # Prefer attaching LDF loop from suite for callers.
        for res in suite.get('results') or []:
            if res.get('study') == 'load_flow':
                report['load_flow_loop'] = res.get('load_flow_loop')
                break
        report['warnings'].extend(suite.get('warnings') or [])
        if not suite.get('ok'):
            report['errors'].extend(suite.get('errors') or [])
    elif run_load_flow_flag:
        if fix_until_converge:
            loop = run_load_flow_until_converged(app, max_intents=max_intents)
        else:
            ldf = execute_load_flow(app, relaxed=False)
            loop = {
                'pass': bool(ldf.get('pass')),
                'attempts': [{'attempt': 0, 'phase': 'initial', 'load_flow': ldf}],
                'final_load_flow': ldf,
                'converged_after_intent': None,
            }
        report['load_flow_loop'] = loop
        if not loop.get('pass'):
            report['errors'].append('Load flow did not converge after corrections')
            final_diag = loop.get('final_diagnosis') or (
                (loop.get('attempts') or [{}])[-1].get('diagnosis')
            )
            if final_diag and final_diag.get('issues'):
                for issue in final_diag['issues']:
                    report['warnings'].append(f'LDF diagnosis: {issue}')

    if persist_dgs:
        converged = bool((report.get('load_flow_loop') or {}).get('pass'))
        # Persist even when LDF was not requested (import-only validation).
        if not run_load_flow_flag and not run_studies:
            converged = False
        persist_report = persist_after_pf_gate(
            Path(dgs_path),
            out_dir=persist_dir,
            app=app,
            export_converged=export_converged_dgs,
            converged=converged,
        )
        report['dgs_persist'] = persist_report
        report['warnings'].extend(persist_report.get('warnings') or [])
        if not persist_report.get('ok'):
            report['errors'].extend(persist_report.get('errors') or [])
            report['errors'].append(
                'DGS was not persisted into the convert out_dir after PowerFactory gate'
            )

    report['ok'] = not report['errors']
    return report


# ---------------------------------------------------------------------------
# Network finders / connectivity
# ---------------------------------------------------------------------------

def _find_network(app: Any, feeder: str):
    candidates: list[Any] = []
    try:
        folder = app.GetProjectFolder('netdat')
        candidates.extend(_contents(folder, '*.ElmNet'))
    except Exception:
        pass
    if not candidates:
        candidates.extend(_calc_objects(app, '*.ElmNet'))
    exact = [x for x in candidates if _name(x) == feeder]
    if exact:
        return exact[0]
    folded = [x for x in candidates if _name(x).casefold() == feeder.casefold()]
    return folded[0] if folded else (candidates[0] if len(candidates) == 1 else None)


def _terminal_of_cubicle(cub: Any):
    if cub is None:
        return None
    term = _attr(cub, 'cterm')
    if term is not None:
        return term
    try:
        parent = cub.GetParent()
        if parent is not None and _classname(parent) == 'ElmTerm':
            return parent
    except Exception:
        pass
    return None


def _branch_cubicle(obj: Any, side: int):
    attr_name = 'bus1' if side == 0 else 'bus2'
    cub = _attr(obj, attr_name)
    if cub is not None:
        return cub
    for method_name in ('GetCubicle', 'GetBus'):
        try:
            method = getattr(obj, method_name)
            candidate = method(side)
            if candidate is not None:
                return candidate
        except Exception:
            continue
    return None


def _one_terminal_cubicle(obj: Any):
    cub = _attr(obj, 'bus1')
    if cub is not None:
        return cub
    for method_name in ('GetCubicle', 'GetBus'):
        try:
            candidate = getattr(obj, method_name)(0)
            if candidate is not None:
                return candidate
        except Exception:
            continue
    return None


def inventory_network(net: Any) -> dict[str, int]:
    """Count DigSilent elements relevant to IGEA→DGS acceptance."""
    all_terms = _contents(net, '*.ElmTerm')
    # SED triangles add internal MT/BT ElmTerm children — not TXT network buses.
    net_term_count = 0
    sed_internal_terms = 0
    for term in all_terms:
        try:
            parent = term.GetParent()
            parent_cls = _classname(parent) if parent is not None else ''
        except Exception:
            parent_cls = ''
        if parent_cls == 'ElmSubstat':
            sed_internal_terms += 1
        else:
            net_term_count += 1

    return {
        'nodes': net_term_count,
        'nodes_total_including_sed_internal': len(all_terms),
        'nodes_sed_internal': sed_internal_terms,
        'lines': len(_contents(net, '*.ElmLne')),
        'loads': len(_contents(net, '*.ElmLod')),
        'switches': len(_contents(net, '*.StaSwitch')),
        'sources': len(_contents(net, '*.ElmXnet')),
        'transformers': len(_contents(net, '*.ElmTr2')) + len(_contents(net, '*.ElmTr3')),
        'transformers_2w': len(_contents(net, '*.ElmTr2')),
        'transformers_3w': len(_contents(net, '*.ElmTr3')),
        'substations_sed': len(_contents(net, '*.ElmSubstat')),
        'capacitors': len(_contents(net, '*.ElmShnt')),
        'regulators': len(_contents(net, '*.ElmVoltreg')),
        'feeders': len(_contents(net, '*.ElmFeeder')),
        'couplers': len(_contents(net, '*.ElmCoup')),
    }


# ---------------------------------------------------------------------------
# Acceptance core
# ---------------------------------------------------------------------------

def run_acceptance(
    app: Any,
    manifest_path: Path,
    *,
    run_load_flow: bool = False,
    fix_until_converge: bool = False,
    max_intents: int = 7,
    require_diagram: bool = False,
    export_wmf: str | None = None,
    require_equipment: bool = True,
) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    feeder = manifest['feeder']
    expected = dict(manifest.get('expected_counts') or {})
    errors: list[str] = []
    warnings: list[str] = []

    if manifest.get('equipment_scope_note'):
        warnings.append(str(manifest['equipment_scope_note']))

    net = _find_network(app, feeder)
    if net is None:
        errors.append(f'ElmNet {feeder!r} not found in the active project/network data folder')
        return {
            'feeder': feeder,
            'powerfactory_runtime_pass': False,
            'geographic_diagram_pass': False,
            'convergence_pass': None,
            'location_scale_pass': False,
            'connectivity_pass': False,
            'equipment_pass': False,
            'expected_counts': expected,
            'actual_counts': {},
            'gps': {'valid': 0, 'total': expected.get('nodes', 0), 'coverage_pct': 0.0},
            'connectivity': {'valid_lines': 0, 'total_lines': expected.get('lines', 0)},
            'diagram': {'object_name': None, 'render_evidence': None},
            'load_flow': {'requested': run_load_flow, 'pass': None, 'return_code': None},
            'errors': errors,
            'warnings': warnings,
        }

    actual = inventory_network(net)
    actual['intermediate_points'] = expected.get('intermediate_points')

    # Core electrical counts
    for key in ('nodes', 'lines', 'loads', 'switches', 'sources'):
        if key in expected and actual.get(key) != expected.get(key):
            errors.append(f'{key} count mismatch: expected {expected.get(key)}, actual {actual.get(key)}')

    # Equipment (SED trafos / capacitors / regulators)
    equipment_errors: list[str] = []
    for key in ('transformers', 'substations_sed', 'capacitors', 'regulators'):
        if key not in expected:
            continue
        if actual.get(key) != expected.get(key):
            msg = f'{key} count mismatch: expected {expected.get(key)}, actual {actual.get(key)}'
            if require_equipment:
                equipment_errors.append(msg)
            else:
                warnings.append(msg)
    if expected.get('capacitors', 0) == 0 and actual.get('capacitors', 0) == 0:
        warnings.append(
            'Sin bancos de condensadores en DGS: el RED export no trae CAPACITOR SETTING '
            '(solo catálogo BD_Equipo).'
        )
    if expected.get('regulators', 0) == 0 and actual.get('regulators', 0) == 0:
        warnings.append(
            'Sin reguladores de tensión en DGS: el RED export no trae REGULATOR SETTING '
            '(solo catálogo BD_Equipo).'
        )
    errors.extend(equipment_errors)
    equipment_pass = not equipment_errors

    # GPS / scaled location
    terms = _contents(net, '*.ElmTerm')
    lines = _contents(net, '*.ElmLne')
    loads = _contents(net, '*.ElmLod')
    sources = _contents(net, '*.ElmXnet')

    valid_gps = 0
    bad_gps: list[str] = []
    for term in terms:
        lat = _attr(term, 'GPSlat')
        lon = _attr(term, 'GPSlon')
        try:
            latf, lonf = float(lat), float(lon)
            ok = math.isfinite(latf) and math.isfinite(lonf) and -90 <= latf <= 90 and -180 <= lonf <= 180
        except (TypeError, ValueError):
            ok = False
        if ok:
            valid_gps += 1
        else:
            bad_gps.append(_name(term))
    gps_coverage = (100.0 * valid_gps / len(terms)) if terms else 0.0
    if valid_gps != len(terms):
        errors.append(f'{len(terms) - valid_gps} ElmTerm objects have invalid GPSlat/GPSlon')

    expected_geo = {str(k)[:40]: v for k, v in manifest.get('nodes', {}).items()}
    if len(expected_geo) != len(manifest.get('nodes', {})):
        warnings.append(
            'Some source node names collide after 40-character DGS loc_name truncation; '
            'per-name GPS comparison skipped for those collisions.'
        )
    imported_by_name = {_name(t): t for t in terms}
    coordinate_mismatches = 0
    compared = 0
    for name, point in expected_geo.items():
        term = imported_by_name.get(name)
        if term is None:
            continue
        compared += 1
        try:
            latf = float(_attr(term, 'GPSlat'))
            lonf = float(_attr(term, 'GPSlon'))
            if not (
                math.isclose(latf, float(point['lat']), rel_tol=0.0, abs_tol=1e-7)
                and math.isclose(lonf, float(point['lon']), rel_tol=0.0, abs_tol=1e-7)
            ):
                coordinate_mismatches += 1
        except Exception:
            coordinate_mismatches += 1
    if coordinate_mismatches:
        errors.append(f'{coordinate_mismatches} ElmTerm GPS coordinates differ from the conversion manifest')
    location_scale_pass = coordinate_mismatches == 0 and valid_gps == len(terms) and len(terms) > 0

    # Connectivity
    valid_lines = 0
    for line in lines:
        c1 = _branch_cubicle(line, 0)
        c2 = _branch_cubicle(line, 1)
        if (
            c1 is not None
            and c2 is not None
            and _terminal_of_cubicle(c1) is not None
            and _terminal_of_cubicle(c2) is not None
        ):
            valid_lines += 1
    if valid_lines != len(lines):
        errors.append(f'{len(lines) - valid_lines} ElmLne objects do not resolve to two valid terminal cubicles')

    unconnected_single = 0
    for obj in [*loads, *sources]:
        if _terminal_of_cubicle(_one_terminal_cubicle(obj)) is None:
            unconnected_single += 1
    if unconnected_single:
        errors.append(f'{unconnected_single} load/source objects do not resolve to a terminal cubicle')
    connectivity_pass = valid_lines == len(lines) and unconnected_single == 0

    # Diagram
    diagram = _attr(net, 'pDiagram')
    diagram_name = _name(diagram) if diagram is not None else None
    graphic_count = None
    graphic_connector_count = None
    if diagram is not None:
        try:
            graphic_count = len(_contents(diagram, '*.IntGrf'))
            graphic_connector_count = len(_contents(diagram, '*.IntGrfcon'))
        except Exception:
            pass
    diagram_pass = diagram is not None
    if require_diagram and diagram is None:
        errors.append('ElmNet.pDiagram is empty/unresolved; required geographic/single-line diagram was not materialised')

    render_evidence = None
    if export_wmf:
        target = Path(export_wmf)
        target.parent.mkdir(parents=True, exist_ok=True)
        if diagram is None:
            errors.append('Cannot export rendering evidence because ElmNet.pDiagram is unresolved')
        else:
            try:
                board = app.GetGraphicsBoard()
                try:
                    diagram.Show()
                except Exception:
                    board.Show(diagram)
                board.WriteWMF(str(target))
                if target.exists() and target.stat().st_size > 0:
                    render_evidence = str(target)
                else:
                    errors.append('Graphics Board did not produce a non-empty WMF rendering')
            except Exception as exc:
                errors.append(f'Network diagram rendering/export failed: {exc}')
        diagram_pass = diagram_pass and render_evidence is not None

    if require_diagram and graphic_count == 0:
        errors.append('Associated diagram exposes zero IntGrf objects')
        diagram_pass = False

    # Load flow convergence on active study case
    load_flow: dict[str, Any] = {
        'requested': run_load_flow,
        'pass': None,
        'return_code': None,
        'ldf_valid': None,
    }
    load_flow_loop = None
    convergence_pass = None
    if run_load_flow:
        if fix_until_converge:
            load_flow_loop = run_load_flow_until_converged(app, max_intents=max_intents)
            final = load_flow_loop.get('final_load_flow') or {}
            load_flow['pass'] = bool(load_flow_loop.get('pass'))
            load_flow['return_code'] = final.get('return_code')
            load_flow['ldf_valid'] = final.get('ldf_valid')
            load_flow['converged_after_intent'] = load_flow_loop.get('converged_after_intent')
            load_flow['attempts'] = len(load_flow_loop.get('attempts') or [])
            convergence_pass = load_flow['pass']
            if not convergence_pass:
                errors.append('Load flow did not converge after correction intents')
                for err in final.get('errors') or []:
                    errors.append(err)
                final_diag = load_flow_loop.get('final_diagnosis')
                if final_diag:
                    for issue in final_diag.get('issues') or []:
                        warnings.append(f'LDF diagnosis: {issue}')
        else:
            ldf = execute_load_flow(app, relaxed=False)
            load_flow['pass'] = ldf.get('pass')
            load_flow['return_code'] = ldf.get('return_code')
            load_flow['ldf_valid'] = ldf.get('ldf_valid')
            convergence_pass = bool(ldf.get('pass'))
            for err in ldf.get('errors') or []:
                errors.append(err)

    powerfactory_runtime_pass = not errors
    return {
        'feeder': feeder,
        'network_id': manifest.get('network_id'),
        'powerfactory_runtime_pass': powerfactory_runtime_pass,
        'geographic_diagram_pass': diagram_pass,
        'convergence_pass': convergence_pass,
        'location_scale_pass': location_scale_pass,
        'connectivity_pass': connectivity_pass,
        'equipment_pass': equipment_pass,
        'expected_counts': expected,
        'actual_counts': actual,
        'gps': {
            'valid': valid_gps,
            'total': len(terms),
            'coverage_pct': round(gps_coverage, 9),
            'invalid_names_sample': bad_gps[:20],
            'coordinate_mismatches': coordinate_mismatches,
            'compared_terminals': compared,
        },
        'connectivity': {'valid_lines': valid_lines, 'total_lines': len(lines)},
        'diagram': {
            'object_name': diagram_name,
            'graphic_objects': graphic_count,
            'graphic_connections': graphic_connector_count,
            'render_evidence': render_evidence,
            'require_diagram': require_diagram,
        },
        'load_flow': load_flow,
        'load_flow_loop': load_flow_loop,
        'errors': errors,
        'warnings': warnings,
    }


def _write_reports(report: dict, json_path: Path, txt_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = [
        f"POWERFACTORY RUNTIME ACCEPTANCE: {report['feeder']}",
        '=' * 78,
        f"PowerFactory runtime PASS: {report['powerfactory_runtime_pass']}",
        f"Connectivity PASS:         {report.get('connectivity_pass')}",
        f"Location/scale PASS:       {report.get('location_scale_pass')}",
        f"Equipment PASS:            {report.get('equipment_pass')}",
        f"Geographic diagram PASS:   {report.get('geographic_diagram_pass')}",
        f"Convergence PASS:          {report.get('convergence_pass')}",
        f"Load flow executed:         {(report.get('load_flow') or {}).get('requested')}",
        f"Load flow PASS:             {(report.get('load_flow') or {}).get('pass')}",
        '',
        'COUNTS (expected vs DigSilent)',
    ]
    for key in sorted(set(report.get('expected_counts', {})) | set(report.get('actual_counts', {}))):
        lines.append(
            f"  {key}: expected={report.get('expected_counts', {}).get(key)} "
            f"actual={report.get('actual_counts', {}).get(key)}"
        )
    lines += [
        '',
        f"GPS terminals: {report['gps']['valid']}/{report['gps']['total']} ({report['gps']['coverage_pct']} %)",
        f"GPS mismatches vs manifest: {report['gps'].get('coordinate_mismatches')}",
        f"Lines with two valid terminal connections: "
        f"{report['connectivity']['valid_lines']}/{report['connectivity']['total_lines']}",
        f"Diagram object: {report['diagram']['object_name']}",
        f"Rendered evidence: {report['diagram']['render_evidence']}",
        '',
        f"ERRORS: {len(report['errors'])}",
    ]
    lines.extend(f'  - {x}' for x in report['errors'])
    lines.append(f"WARNINGS: {len(report['warnings'])}")
    lines.extend(f'  - {x}' for x in report['warnings'])
    if report.get('import'):
        lines += ['', 'IMPORT', json.dumps(report['import'], ensure_ascii=False, indent=2)]
    if report.get('study_scenario'):
        lines += ['', 'STUDY / SCENARIO', json.dumps(report['study_scenario'], ensure_ascii=False, indent=2)]
    if report.get('scenario_ensure'):
        lines += ['', 'SCENARIO ENSURE', json.dumps(report['scenario_ensure'], ensure_ascii=False, indent=2)]
    if report.get('load_flow_loop'):
        loop = report['load_flow_loop']
        lines += [
            '',
            'LOAD FLOW CORRECTIONS',
            f"  pass={loop.get('pass')} converged_after={loop.get('converged_after_intent')!r}",
        ]
        for att in loop.get('attempts') or []:
            intent = att.get('intent') or att.get('phase')
            lf = att.get('load_flow') or {}
            corr = att.get('correction') or {}
            lines.append(
                f"  attempt {att.get('attempt')}: {intent} → ldf_pass={lf.get('pass')} "
                f"solution={corr.get('solution') or '-'}"
            )
            diag = att.get('diagnosis') or {}
            for issue in (diag.get('issues') or [])[:3]:
                lines.append(f"    diagnosis: {issue}")
    if report.get('study_suite'):
        suite = report['study_suite']
        lines += [
            '',
            'STUDY SUITE',
            f"  ok={suite.get('ok')} requested={suite.get('studies_requested')}",
        ]
        for res in suite.get('results') or []:
            lines.append(
                f"  - {res.get('study')}: pass={res.get('pass')} "
                f"available={res.get('available', True)} "
                f"command={res.get('command')}"
            )
            for err in (res.get('errors') or [])[:3]:
                lines.append(f"      error: {err}")
            for warn in (res.get('warnings') or [])[:3]:
                lines.append(f"      warn: {warn}")
        for gap in suite.get('gaps_noted') or []:
            lines.append(f"  gap: {gap.get('study')}: {gap.get('note')}")
    if report.get('dgs_persist'):
        persist = report['dgs_persist']
        lines += [
            '',
            'DGS PERSIST (convert out_dir)',
            f"  ok={persist.get('ok')} out_dir={persist.get('out_dir')}",
            f"  dgs={persist.get('dgs')}",
            f"  converged_dgs={persist.get('converged_dgs')}",
        ]
        for action in (persist.get('persist') or {}).get('actions') or []:
            lines.append(f"  - {action}")
        export_info = persist.get('export_converged') or {}
        if export_info:
            lines.append(
                f"  export: ok={export_info.get('ok')} method={export_info.get('method')!r} "
                f"path={export_info.get('path')}"
            )
    txt_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Import DGS into DigSilent PowerFactory and validate connectivity/convergence/GPS'
    )
    p.add_argument(
        '--manifest',
        help='Generated <FEEDER>_geography.json (optional if --import-dgs alone for import+LDF)',
    )
    p.add_argument(
        '--import-dgs',
        help='Path to .dgs — imports via ComImport into a new PF project before checks',
    )
    p.add_argument('--project-name', help='Optional PF project name for ComImport')
    p.add_argument(
        '--activate-base',
        action='store_true',
        default=True,
        help='Activate Study Case base + Operation Scenario base (default: on)',
    )
    p.add_argument('--no-activate-base', action='store_true', help='Skip study/scenario activation')
    p.add_argument(
        '--ensure-scenario',
        action='store_true',
        default=True,
        help='Create IntScenario if missing and activate it (default: on)',
    )
    p.add_argument('--no-ensure-scenario', action='store_true', help='Do not create IntScenario')
    p.add_argument('--run-load-flow', action='store_true', help='Execute ComLdf and require convergence')
    p.add_argument(
        '--fix-until-converge',
        action='store_true',
        help='On LDF failure: diagnose and apply correction intents until convergence',
    )
    p.add_argument('--max-intents', type=int, default=7, help='Max correction intents (default 7)')
    p.add_argument(
        '--run-studies',
        action='store_true',
        help=(
            'After import/activate, run the study suite (default: ComLdf + ComShc). '
            'Implies load-flow; see --studies'
        ),
    )
    p.add_argument(
        '--studies',
        default='',
        help=(
            'Comma-separated study ids for --run-studies '
            f'(default: {",".join(DEFAULT_STUDY_SUITE)}). '
            f'Registered: {",".join(sorted(STUDY_REGISTRY))}'
        ),
    )
    p.add_argument(
        '--list-studies',
        action='store_true',
        help='Print registered study suite / gaps and exit (no PF connection)',
    )
    p.add_argument('--require-diagram', action='store_true', help='Require ElmNet.pDiagram + IntGrf')
    p.add_argument(
        '--require-equipment',
        action='store_true',
        default=True,
        help='Fail if transformer/capacitor/regulator counts mismatch manifest (default)',
    )
    p.add_argument('--no-require-equipment', action='store_true')
    p.add_argument('--export-wmf', help='Optional WMF path for diagram rendering evidence')
    p.add_argument('--output-json', help='Runtime acceptance JSON report')
    p.add_argument('--output-txt', help='Runtime acceptance text report')
    p.add_argument(
        '--persist-dir',
        help=(
            'Convert out_dir where {feeder}.dgs must remain after the gate '
            '(default: parent of --import-dgs, same as GUI/CLI individual convert)'
        ),
    )
    p.add_argument(
        '--no-persist-dgs',
        action='store_true',
        help='Do not copy/ensure DGS into convert out_dir after import/LDF',
    )
    p.add_argument(
        '--export-converged-dgs',
        action='store_true',
        default=True,
        help=(
            'After LDF convergence, try ComExport to {feeder}_pf_converged.dgs '
            'in the persist/convert folder (default: on)'
        ),
    )
    p.add_argument(
        '--no-export-converged-dgs',
        action='store_true',
        help='Skip ComExport of converged project (still persist converter DGS)',
    )
    p.add_argument('--no-start-engine', action='store_true', help='Do not call GetApplicationExt')
    p.add_argument('--pf-args', default='', help='Args for GetApplicationExt (default empty)')
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.list_studies:
        print(json.dumps(list_study_suite(), indent=2, ensure_ascii=False))
        return 0

    ensure_scenario = args.ensure_scenario and not args.no_ensure_scenario
    manifest_path = Path(args.manifest) if args.manifest else None
    studies_arg = tuple(
        s.strip() for s in (args.studies or '').split(',') if s.strip()
    ) or None
    run_studies = bool(args.run_studies)
    want_flow = bool(args.run_load_flow or args.fix_until_converge or run_studies)

    if manifest_path is None and not args.import_dgs:
        print('ERROR: provide --manifest and/or --import-dgs', file=sys.stderr)
        return 1
    if manifest_path is not None and not manifest_path.is_file():
        print(f'ERROR: manifest not found: {manifest_path}', file=sys.stderr)
        return 1

    try:
        app = connect_powerfactory(
            start_engine=not args.no_start_engine,
            command_line=args.pf_args,
        )
    except (ImportError, RuntimeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 3

    import_info = None
    study_info = None
    scenario_ensure = None
    flow_only_report = None
    dgs_persist_report = None
    want_persist = not args.no_persist_dgs
    want_export_converged = bool(args.export_converged_dgs) and not args.no_export_converged_dgs
    persist_dir = Path(args.persist_dir) if args.persist_dir else None

    if args.import_dgs and (manifest_path is None or args.fix_until_converge or run_studies):
        # GUI / one-shot path: import → scenario → LDF (+ optional study suite).
        try:
            flow_only_report = run_import_activate_flow(
                app,
                Path(args.import_dgs),
                project_name=args.project_name,
                ensure_scenario=ensure_scenario,
                run_load_flow_flag=want_flow and not run_studies,
                fix_until_converge=bool(args.fix_until_converge),
                max_intents=args.max_intents,
                run_studies=run_studies,
                studies=studies_arg,
                persist_dgs=want_persist,
                persist_dir=persist_dir,
                export_converged_dgs=want_export_converged,
            )
            import_info = flow_only_report.get('import')
            study_info = flow_only_report.get('study_scenario')
            scenario_ensure = flow_only_report.get('scenario_ensure')
            dgs_persist_report = flow_only_report.get('dgs_persist')
            if import_info:
                print(f"Imported DGS into project: {import_info.get('project_name')}")
            if study_info:
                print(
                    f"StudyCase={study_info.get('active_study_case')!r} "
                    f"Scenario={study_info.get('active_scenario')!r}"
                )
            if scenario_ensure:
                print(
                    f"Scenario ensure: created={scenario_ensure.get('created')} "
                    f"name={scenario_ensure.get('scenario')!r} "
                    f"activated={scenario_ensure.get('activated')}"
                )
            loop = flow_only_report.get('load_flow_loop') or {}
            print(f"Load flow converge: {loop.get('pass')} after={loop.get('converged_after_intent')!r}")
            for att in loop.get('attempts') or []:
                corr = att.get('correction') or {}
                lf = att.get('load_flow') or {}
                if corr.get('solution'):
                    print(f"  intent {att.get('intent')}: {corr.get('solution')} → pass={lf.get('pass')}")
            suite = flow_only_report.get('study_suite')
            if suite:
                print(f"Study suite ok={suite.get('ok')} requested={suite.get('studies_requested')}")
                for res in suite.get('results') or []:
                    print(
                        f"  study {res.get('study')}: pass={res.get('pass')} "
                        f"available={res.get('available', True)}"
                    )
            if dgs_persist_report:
                print(
                    f"DGS persist: ok={dgs_persist_report.get('ok')} "
                    f"out_dir={dgs_persist_report.get('out_dir')} "
                    f"dgs={dgs_persist_report.get('dgs')}"
                )
                if dgs_persist_report.get('converged_dgs'):
                    print(f"DGS converged export: {dgs_persist_report.get('converged_dgs')}")
            if not flow_only_report.get('ok') and manifest_path is None:
                for err in flow_only_report.get('errors') or []:
                    print(f'ERROR: {err}', file=sys.stderr)
                feeder = Path(args.import_dgs).stem
                report = {
                    'feeder': feeder,
                    'powerfactory_runtime_pass': False,
                    'connectivity_pass': None,
                    'location_scale_pass': None,
                    'equipment_pass': None,
                    'geographic_diagram_pass': None,
                    'convergence_pass': (flow_only_report.get('load_flow_loop') or {}).get('pass'),
                    'load_flow': {
                        'requested': True,
                        'pass': (flow_only_report.get('load_flow_loop') or {}).get('pass'),
                    },
                    'load_flow_loop': flow_only_report.get('load_flow_loop'),
                    'study_suite': flow_only_report.get('study_suite'),
                    'import': import_info,
                    'study_scenario': study_info,
                    'scenario_ensure': scenario_ensure,
                    'dgs_persist': dgs_persist_report,
                    'errors': list(flow_only_report.get('errors') or []),
                    'warnings': list(flow_only_report.get('warnings') or []),
                    'expected_counts': {},
                    'actual_counts': {},
                    'gps': {'valid': 0, 'total': 0, 'coverage_pct': 0.0},
                    'connectivity': {'valid_lines': 0, 'total_lines': 0},
                    'diagram': {'object_name': None, 'render_evidence': None},
                }
                dgs_path = Path(args.import_dgs)
                json_path = Path(args.output_json) if args.output_json else dgs_path.with_name(
                    f'{feeder}_powerfactory_acceptance.json'
                )
                txt_path = Path(args.output_txt) if args.output_txt else dgs_path.with_name(
                    f'{feeder}_powerfactory_acceptance.txt'
                )
                _write_reports(report, json_path, txt_path)
                return 2
        except Exception as exc:
            print(f'ERROR: import/activate/flow failed: {exc}', file=sys.stderr)
            return 2
    elif args.import_dgs:
        try:
            import_info = import_dgs_file(
                app,
                Path(args.import_dgs),
                project_name=args.project_name,
            )
            time.sleep(0.5)
            if not import_info['ok']:
                print('ERROR: DGS import reported issues:', file=sys.stderr)
                for err in import_info['errors']:
                    print(f'  - {err}', file=sys.stderr)
                return 2
            print(f"Imported DGS into project: {import_info['project_name']}")
        except Exception as exc:
            print(f'ERROR: DGS import failed: {exc}', file=sys.stderr)
            return 2

        if args.activate_base and not args.no_activate_base:
            study_info = activate_base_study_and_scenario(app)
            for err in study_info.get('errors') or []:
                print(f'WARN study/scenario: {err}', file=sys.stderr)
            print(
                f"StudyCase={study_info.get('active_study_case')!r} "
                f"Scenario={study_info.get('active_scenario')!r}"
            )
            if ensure_scenario and not study_info.get('scenario_activated'):
                scenario_ensure = ensure_operation_scenario(app)
                for err in scenario_ensure.get('errors') or []:
                    print(f'WARN ensure-scenario: {err}', file=sys.stderr)
                print(
                    f"Scenario ensure: created={scenario_ensure.get('created')} "
                    f"name={scenario_ensure.get('scenario')!r}"
                )
        if run_studies:
            suite = run_study_suite(
                app,
                studies=studies_arg,
                fix_until_converge=bool(args.fix_until_converge),
                max_intents=args.max_intents,
            )
            flow_only_report = {
                'ok': suite.get('ok'),
                'load_flow_loop': next(
                    (
                        r.get('load_flow_loop')
                        for r in suite.get('results') or []
                        if r.get('study') == 'load_flow'
                    ),
                    None,
                ),
                'study_suite': suite,
                'errors': list(suite.get('errors') or []),
                'warnings': list(suite.get('warnings') or []),
            }
            print(f"Study suite ok={suite.get('ok')}")
            for res in suite.get('results') or []:
                print(f"  study {res.get('study')}: pass={res.get('pass')}")
        if want_persist and dgs_persist_report is None:
            loop = (flow_only_report or {}).get('load_flow_loop') or {}
            dgs_persist_report = persist_after_pf_gate(
                Path(args.import_dgs),
                out_dir=persist_dir,
                app=app,
                export_converged=want_export_converged,
                converged=bool(loop.get('pass')),
            )
            print(
                f"DGS persist: ok={dgs_persist_report.get('ok')} "
                f"out_dir={dgs_persist_report.get('out_dir')} "
                f"dgs={dgs_persist_report.get('dgs')}"
            )
    else:
        # Manifest-only: activate existing project state.
        if args.activate_base and not args.no_activate_base:
            study_info = activate_base_study_and_scenario(app)
            print(
                f"StudyCase={study_info.get('active_study_case')!r} "
                f"Scenario={study_info.get('active_scenario')!r}"
            )
            if ensure_scenario and not study_info.get('scenario_activated'):
                scenario_ensure = ensure_operation_scenario(app)
        if run_studies:
            suite = run_study_suite(
                app,
                studies=studies_arg,
                fix_until_converge=bool(args.fix_until_converge),
                max_intents=args.max_intents,
            )
            flow_only_report = {
                'ok': suite.get('ok'),
                'load_flow_loop': next(
                    (
                        r.get('load_flow_loop')
                        for r in suite.get('results') or []
                        if r.get('study') == 'load_flow'
                    ),
                    None,
                ),
                'study_suite': suite,
                'errors': list(suite.get('errors') or []),
                'warnings': list(suite.get('warnings') or []),
            }

    if (
        want_persist
        and dgs_persist_report is None
        and args.import_dgs is None
        and manifest_path is not None
    ):
        feeder_guess = manifest_path.stem
        if feeder_guess.endswith('_geography'):
            feeder_guess = feeder_guess[: -len('_geography')]
        sibling = manifest_path.with_name(f'{feeder_guess}.dgs')
        if sibling.is_file():
            loop = (flow_only_report or {}).get('load_flow_loop') or {}
            dgs_persist_report = persist_after_pf_gate(
                sibling,
                out_dir=persist_dir or manifest_path.parent,
                app=app,
                export_converged=want_export_converged,
                converged=bool(loop.get('pass')),
            )

    if manifest_path is None:
        # Import+flow only (no geography acceptance).
        feeder = Path(args.import_dgs).stem if args.import_dgs else 'unknown'
        report = {
            'feeder': feeder,
            'powerfactory_runtime_pass': bool(flow_only_report and flow_only_report.get('ok')),
            'connectivity_pass': None,
            'location_scale_pass': None,
            'equipment_pass': None,
            'geographic_diagram_pass': None,
            'convergence_pass': ((flow_only_report or {}).get('load_flow_loop') or {}).get('pass'),
            'load_flow': {
                'requested': want_flow,
                'pass': ((flow_only_report or {}).get('load_flow_loop') or {}).get('pass'),
                'return_code': ((flow_only_report or {}).get('load_flow_loop') or {})
                .get('final_load_flow', {})
                .get('return_code'),
            },
            'load_flow_loop': (flow_only_report or {}).get('load_flow_loop'),
            'study_suite': (flow_only_report or {}).get('study_suite'),
            'import': import_info,
            'study_scenario': study_info,
            'scenario_ensure': scenario_ensure,
            'dgs_persist': dgs_persist_report,
            'errors': list((flow_only_report or {}).get('errors') or []),
            'warnings': list((flow_only_report or {}).get('warnings') or []),
            'expected_counts': {},
            'actual_counts': {},
            'gps': {'valid': 0, 'total': 0, 'coverage_pct': 0.0},
            'connectivity': {'valid_lines': 0, 'total_lines': 0},
            'diagram': {'object_name': None, 'render_evidence': None},
        }
        if dgs_persist_report and not dgs_persist_report.get('ok'):
            report['errors'].extend(dgs_persist_report.get('errors') or [])
            report['powerfactory_runtime_pass'] = False
        dgs_path = Path(args.import_dgs)
        json_path = Path(args.output_json) if args.output_json else dgs_path.with_name(
            f'{feeder}_powerfactory_acceptance.json'
        )
        txt_path = Path(args.output_txt) if args.output_txt else dgs_path.with_name(
            f'{feeder}_powerfactory_acceptance.txt'
        )
        _write_reports(report, json_path, txt_path)
        print(f"PowerFactory runtime PASS: {report['powerfactory_runtime_pass']}")
        print(f"Convergence PASS: {report.get('convergence_pass')}")
        if dgs_persist_report:
            print(
                f"DGS persist: ok={dgs_persist_report.get('ok')} "
                f"out_dir={dgs_persist_report.get('out_dir')}"
            )
        print(f"JSON: {json_path}")
        print(f"TXT: {txt_path}")
        return 0 if report['powerfactory_runtime_pass'] else 2

    # If we already ran import+flow via run_import_activate_flow, skip re-running LDF
    # inside acceptance unless --run-load-flow without fix (already done). Prefer
    # attaching the loop and only running static/geo checks.
    already_flowed = flow_only_report is not None
    report = run_acceptance(
        app,
        manifest_path,
        run_load_flow=want_flow and not already_flowed,
        fix_until_converge=bool(args.fix_until_converge) and not already_flowed,
        max_intents=args.max_intents,
        require_diagram=args.require_diagram,
        export_wmf=args.export_wmf,
        require_equipment=args.require_equipment and not args.no_require_equipment,
    )
    if import_info is not None:
        report['import'] = import_info
    if study_info is not None:
        report['study_scenario'] = study_info
        for err in study_info.get('errors') or []:
            report['errors'].append(err)
    if scenario_ensure is not None:
        report['scenario_ensure'] = scenario_ensure
        for err in scenario_ensure.get('errors') or []:
            report['errors'].append(err)
    if already_flowed and flow_only_report is not None:
        loop = flow_only_report.get('load_flow_loop')
        report['load_flow_loop'] = loop
        report['study_suite'] = flow_only_report.get('study_suite')
        report['load_flow'] = {
            'requested': True,
            'pass': bool(loop and loop.get('pass')),
            'return_code': (loop or {}).get('final_load_flow', {}).get('return_code'),
            'ldf_valid': (loop or {}).get('final_load_flow', {}).get('ldf_valid'),
            'converged_after_intent': (loop or {}).get('converged_after_intent'),
            'attempts': len((loop or {}).get('attempts') or []),
        }
        report['convergence_pass'] = bool(loop and loop.get('pass'))
        if not report['convergence_pass']:
            report['errors'].append('Load flow did not converge after correction intents')
        for err in flow_only_report.get('errors') or []:
            if err not in report['errors']:
                report['errors'].append(err)
        for warn in flow_only_report.get('warnings') or []:
            if warn not in report['warnings']:
                report['warnings'].append(warn)
    if dgs_persist_report is not None:
        report['dgs_persist'] = dgs_persist_report
        for warn in dgs_persist_report.get('warnings') or []:
            if warn not in report['warnings']:
                report['warnings'].append(warn)
        if not dgs_persist_report.get('ok'):
            for err in dgs_persist_report.get('errors') or []:
                if err not in report['errors']:
                    report['errors'].append(err)
    report['powerfactory_runtime_pass'] = not report['errors']

    feeder = report['feeder']
    json_path = Path(args.output_json) if args.output_json else manifest_path.with_name(
        f'{feeder}_powerfactory_acceptance.json'
    )
    txt_path = Path(args.output_txt) if args.output_txt else manifest_path.with_name(
        f'{feeder}_powerfactory_acceptance.txt'
    )
    _write_reports(report, json_path, txt_path)

    print(f"PowerFactory runtime PASS: {report['powerfactory_runtime_pass']}")
    print(f"Connectivity PASS: {report.get('connectivity_pass')}")
    print(f"Location/scale PASS: {report.get('location_scale_pass')}")
    print(f"Equipment PASS: {report.get('equipment_pass')}")
    print(f"Geographic diagram PASS: {report['geographic_diagram_pass']}")
    print(f"Convergence PASS: {report.get('convergence_pass')}")
    if dgs_persist_report:
        print(
            f"DGS persist: ok={dgs_persist_report.get('ok')} "
            f"out_dir={dgs_persist_report.get('out_dir')} "
            f"dgs={dgs_persist_report.get('dgs')}"
        )
        if dgs_persist_report.get('converged_dgs'):
            print(f"DGS converged export: {dgs_persist_report.get('converged_dgs')}")
    print(f"JSON: {json_path}")
    print(f"TXT: {txt_path}")
    return 0 if report['powerfactory_runtime_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
