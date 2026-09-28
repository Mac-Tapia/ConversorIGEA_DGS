#!/usr/bin/env python3
"""Lista o elimina proyectos PowerFactory por nombre exacto.

No acepta patrones ni prefijos: la limpieza queda limitada a los nombres indicados
explícitamente por ``--project``. Sin ``--delete`` solo informa lo que encontraría.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
sys.path.insert(0, str(PROJECT_ROOT / 'tools'))

from powerfactory_acceptance import connect_powerfactory  # noqa: E402


def _name(obj) -> str:
    try:
        return str(obj.GetAttribute('loc_name') or '')
    except Exception:
        return str(getattr(obj, 'loc_name', '') or '')


def cleanup(app, names: list[str], *, delete: bool) -> dict:
    requested = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    user = app.GetCurrentUser()
    projects = list(user.GetContents('*.IntPrj') or []) if user is not None else []
    by_name = {_name(project): project for project in projects}
    result = {'requested': requested, 'found': [], 'deleted': [], 'missing': [], 'errors': []}
    active = app.GetActiveProject()
    for name in requested:
        project = by_name.get(name)
        if project is None:
            result['missing'].append(name)
            continue
        result['found'].append(name)
        if not delete:
            continue
        try:
            if active is not None and _name(active) == name:
                app.DeactivateProject()
                active = None
            rc = project.Delete()
            if rc not in (None, 0):
                raise RuntimeError(f'Delete devolvió {rc}')
            result['deleted'].append(name)
        except Exception as exc:
            result['errors'].append(f'{name}: {exc}')
    if delete:
        remaining = {_name(project) for project in (user.GetContents('*.IntPrj') or [])}
        not_removed = [name for name in result['deleted'] if name in remaining]
        if not_removed:
            result['errors'].append('Persisten después de Delete: ' + ', '.join(not_removed))
            result['deleted'] = [name for name in result['deleted'] if name not in not_removed]
    result['ok'] = not result['errors']
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', action='append', required=True,
                        help='Nombre exacto; se puede repetir.')
    parser.add_argument('--delete', action='store_true', help='Eliminar; sin esta opción solo lista.')
    args = parser.parse_args(argv)
    app = connect_powerfactory(start_engine=True)
    result = cleanup(app, args.project, delete=args.delete)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
