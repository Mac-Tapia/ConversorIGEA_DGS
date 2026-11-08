"""Puerta integral de regresión de la entrega (065:RF-24; 086:RF-46).

Sin --ejecutar prepara el plan, sin lanzar pruebas, red ni motores. Consolida
backend, frontend y, en edición completa, ML. Un pase técnico no acredita por sí
solo aceptación eléctrica, científica, operativa ni autorización de publicación.
Los resultados y temporales se conservan fuera de todos los checkouts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

RAIZ = Path(__file__).resolve().parents[1]


def _herramienta(nombre: str):
    ruta = Path(__file__).with_name(nombre + '.py')
    spec = importlib.util.spec_from_file_location('entrega_' + nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def plan_comprobaciones(raiz: Path, python: Path, edicion: str, evidencia: Path) -> list[dict]:
    """065:RF-24 — el alcance completo añade ML; nunca reemplaza la regresión del núcleo."""
    if edicion not in ('nucleo', 'completa'):
        raise ValueError('Edición de validación desconocida')
    raiz, evidencia, python = Path(raiz).resolve(), Path(evidencia).resolve(), Path(python).resolve()
    node = shutil.which('node') or 'node'
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm') or 'npm'
    frontend = raiz / 'frontend'
    filas = []

    def agregar(id, kind, command, *, cwd=raiz, **extra):
        filas.append({'id': id, 'kind': kind, 'command': [str(p) for p in command],
                      'cwd': str(cwd), 'timeout_s': 21600, **extra})

    agregar('python_check', 'command', [python, '-B', '-m', 'pip', 'check'])
    agregar('backend', 'backend', [python, '-B', raiz/'tools/verificar_candidato.py', '--root', raiz,
        '--output-dir', evidencia/'backend_regresion', '--python', python, '--ejecutar',
        '--suite-completa', '--hash-datos'], artifact=str(evidencia/'backend_regresion'))
    agregar('frontend_tests', 'tap', [node, '--test', '--test-reporter=tap', 'test/*.test.mjs'], cwd=frontend)
    agregar('frontend_types', 'command', [node, frontend/'node_modules/typescript/bin/tsc',
        '--noEmit', '--incremental', 'false', '-p', frontend/'tsconfig.json'], cwd=frontend)
    agregar('frontend_build', 'frontend_build', [node, frontend/'scripts/build.mjs'],
        cwd=frontend, artifact=str(frontend/'dist'))
    agregar('python_audit', 'pip_audit', [python, '-B', '-m', 'pip_audit', '--strict',
        '--disable-pip', '--no-deps', '-r', raiz/'requirements-nucleo.lock', '--format=json'])
    agregar('frontend_audit', 'npm_audit', [npm, 'audit', '--json', '--package-lock-only',
        '--ignore-scripts'], cwd=frontend)
    if edicion == 'completa':
        agregar('ml', 'pytest', [python, '-B', '-m', 'pytest', '-q', '-rs', 'tests_ml',
            '--basetemp', evidencia/'ml_tmp', '--junitxml', evidencia/'ml.xml'], artifact=str(evidencia/'ml.xml'))
    return filas


def evaluar_entrega(resultados: list[dict], obligatorias: set[str]) -> dict:
    """065:RF-24 — faltantes, duplicados y no ejecutados no se heredan como pases."""
    errores = []
    por_id = {}
    for r in resultados:
        id = r.get('id')
        if id in por_id:
            errores.append(f'puerta_duplicada:{id}')
        por_id[id] = r
    if not obligatorias:
        errores.append('sin_puertas_obligatorias')
    for id in sorted(obligatorias):
        if id not in por_id:
            errores.append(f'puerta_ausente:{id}')
        elif por_id[id].get('state') != 'aprobada':
            errores.append(f'puerta_no_aprobada:{id}')
    return {'technical_checks_passed': not errores, 'errors': errores,
            'production_ready_core': False, 'project_complete': False,
            'pending': ['aceptacion_electrica', 'aceptacion_cientifica', 'aceptacion_operativa',
                        'revision_semantica_requisitos', 'autorizacion_publicacion']}


def _validar_resultado(c: dict, stdout: Path) -> dict:
    kind = c['kind']
    if kind == 'command':
        return {}
    if kind == 'pytest':
        r = _herramienta('verificar_candidato').resumir_junit(Path(c['artifact']))
        counts = r['counts']
        if not counts['pass'] or any(counts[k] for k in ('fail', 'error', 'skip', 'xfail')):
            raise ValueError('JUnit sin pase íntegro: ' + json.dumps(counts))
        return {'counts': counts}
    if kind == 'tap':
        texto = stdout.read_text(encoding='utf-8', errors='replace')
        campos = ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo')
        counts = {}
        for nombre in campos:
            valores = re.findall(r'^# ' + nombre + r' (\d+)\s*$', texto, re.M)
            if len(valores) != 1:
                raise ValueError('TAP sin contador único: ' + nombre)
            counts[nombre] = int(valores[0])
        if (not counts['tests'] or counts['tests'] != counts['pass']
                or any(counts[k] for k in ('fail', 'cancelled', 'skipped', 'todo'))):
            raise ValueError('TAP con fallos u omisiones: ' + json.dumps(counts))
        return {'counts': counts}
    if kind == 'backend':
        registros = list(Path(c['artifact']).glob('*/registro.json'))
        if len(registros) != 1:
            raise ValueError('Backend sin registro único de esta ejecución')
        r = json.loads(registros[0].read_text(encoding='utf-8'))
        if (r.get('state') != 'regresion_aprobada' or r.get('scope') != 'suite_completa'
                or r.get('data_hash_mode') != 'sha256' or r.get('missing_inputs')
                or not re.fullmatch('[0-9a-f]{64}', str(r.get('source_hash_before', '')))
                or r.get('returncode') != 0
                or r.get('source_hash_before') != r.get('source_hash_after') or r.get('errors')):
            raise ValueError('Regresión backend incompleta o modificada')
        counts = (r.get('results') or {}).get('counts', {})
        if not counts.get('pass') or any(counts.get(k, 1) for k in ('fail', 'error', 'skip', 'xfail')):
            raise ValueError('Backend sin resultados completos')
        return {'counts': counts, 'registro': str(registros[0])}
    if kind == 'frontend_build':
        if str(RAIZ/'src') not in sys.path:
            sys.path.insert(0, str(RAIZ/'src'))
        from convertersmartgrid.web.runtime import integridad_del_front
        motivo = integridad_del_front(Path(c['artifact']))
        if motivo:
            raise ValueError('Frontend incompleto: ' + motivo)
        return {'dist': c['artifact']}
    dato = json.loads(stdout.read_text(encoding='utf-8'))
    if kind == 'pip_audit':
        deps = dato.get('dependencies') if isinstance(dato, dict) else None
        if (not isinstance(deps, list) or not deps or any(not isinstance(d, dict)
                or not d.get('name') or not d.get('version') or d.get('skip_reason')
                or d.get('vulns') != [] for d in deps)):
            raise ValueError('Auditoría Python incompleta o con vulnerabilidades')
        return {'dependencies_audited': len(deps)}
    if kind == 'npm_audit':
        meta = dato.get('metadata') if isinstance(dato, dict) else None
        if (not isinstance(dato, dict) or dato.get('error') or not isinstance(meta, dict)
                or not (meta.get('dependencies') or {}).get('total')
                or (meta.get('vulnerabilities') or {}).get('total') != 0):
            raise ValueError('Auditoría frontend incompleta o con vulnerabilidades')
        return {'metadata': meta}
    raise ValueError('Comprobación no reconocida: ' + str(kind))


def ejecutar_comprobacion(c: dict, evidencia: Path, env: dict | None = None) -> dict:
    """065:RF-24 — procesos reales, plazo finito y registros duraderos de cada intento."""
    id = c['id']
    if not re.fullmatch(r'[a-z][a-z0-9_]*', id):
        raise ValueError('Identificador de comprobación inválido')
    destino = Path(evidencia)/id
    destino.mkdir(parents=True, exist_ok=False)
    stdout, stderr = destino/'stdout.log', destino/'stderr.log'
    r = {'id': id, 'state': 'en_ejecucion', 'command': c['command'], 'cwd': c['cwd'],
         'returncode': None, 'errors': [], 'stdout': str(stdout), 'stderr': str(stderr)}
    inicio = time.monotonic()
    try:
        timeout = float(c['timeout_s'])
        if timeout <= 0 or not c['command'] or not isinstance(c['command'], list):
            raise ValueError('Comando o presupuesto de tiempo inválido')
        with stdout.open('wb') as out, stderr.open('wb') as err:
            opciones = {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)} if os.name=='nt' else {'start_new_session': True}
            proceso = subprocess.Popen(c['command'], cwd=c['cwd'], env=env, stdout=out, stderr=err, **opciones)
            try:
                r['returncode'] = proceso.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Solo el árbol del proceso que este intento acaba de crear; nunca el motor de otra sesión.
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(proceso.pid), '/T', '/F'],
                                   stdout=err, stderr=err, check=False,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                else:
                    try:
                        os.killpg(proceso.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                proceso.wait()
                r['errors'].append('timeout')
        if r['returncode'] != 0:
            r['errors'].append('exit:' + str(r['returncode']))
        if not r['errors']:
            r.update(_validar_resultado(c, stdout))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        r['errors'].append(str(exc))
    r.update(state='rechazada' if r['errors'] else 'aprobada', seconds=time.monotonic()-inicio)
    (destino/'resultado.json').write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return r


def ejecutar_plan(plan: list[dict], evidencia: Path, env: dict | None = None) -> list[dict]:
    """065:RF-24 — se conserva el primer fallo y el resto queda explícitamente sin ejecutar."""
    resultados, continuar = [], True
    for c in plan:
        if continuar:
            r = ejecutar_comprobacion(c, evidencia, env)
            continuar = r['state'] == 'aprobada'
        else:
            r = {'id': c['id'], 'state': 'no_ejecutada', 'errors': ['puerta_previa_rechazada']}
        resultados.append(r)
    return resultados


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=RAIZ)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--edicion', choices=('nucleo', 'completa'), default='completa')
    parser.add_argument('--ejecutar', action='store_true', help='Ejecutar las puertas; sin esto solo prepara')
    args = parser.parse_args(argv)
    registro, destino = None, None
    try:
        raiz = args.root.resolve()
        if not (raiz/'tests').is_dir() or not (raiz/'frontend/package.json').is_file():
            raise ValueError('El candidato debe contener tests y frontend')
        trace = _herramienta('trazabilidad_candidato')
        runner = _herramienta('verificar_candidato')
        with runner._git_local():
            base = trace.validar_salida(args.output_dir, raiz)
            revision = trace.revision(raiz)
        antes, _inputs = trace.hash_candidato(raiz)
        destino = base/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex)
        destino.mkdir(parents=True, exist_ok=False)
        plan = plan_comprobaciones(raiz, args.python, args.edicion, destino)
        registro = {'format': 'verificacion-entrega-integral-v1', 'root': str(raiz), 'revision': revision,
                    'candidate_before': antes, 'candidate_after': None, 'edition': args.edicion,
                    'state': 'preparado', 'plan': plan, 'results': [],
                    **evaluar_entrega([], {c['id'] for c in plan})}
        (destino/'resultado_entrega.json').write_text(json.dumps(registro, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if args.ejecutar:
            env = runner._entorno(destino, {})
            env.update(PYTHONPATH=str(raiz/'src'), CSG_AUTOENTRENAMIENTO='0')
            runtime = runner._runtime(args.python.resolve(), raiz, env)
            minimos = _herramienta('fijar_entorno').leer_minimos_seguridad(raiz/'config/entrega.json')
            from packaging.utils import canonicalize_name
            from packaging.version import Version
            paquetes = {canonicalize_name(n): v for n, v in runtime['packages'].items()}
            if any(n not in paquetes or Version(paquetes[n]) < Version(v) for n,v in minimos.items()):
                raise ValueError('El intérprete candidato no cumple los mínimos de seguridad')
            (destino/'runtime.json').write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')
            registro['results'] = ejecutar_plan(plan, destino, env)
            registro.update(evaluar_entrega(registro['results'], {c['id'] for c in plan}))
        despues, _inputs = trace.hash_candidato(raiz)
        registro['candidate_after'] = despues
        if despues != antes:
            registro['errors'].append('candidato_modificado')
            registro['technical_checks_passed'] = False
        if args.ejecutar:
            registro['state'] = 'regresion_integral_aprobada' if registro['technical_checks_passed'] else 'rechazado'
        (destino/'resultado_entrega.json').write_text(json.dumps(registro, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(f'{registro["state"]}; aceptación de dominio pendiente; evidencia: {destino}')
        return 0 if not args.ejecutar or registro['technical_checks_passed'] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if registro is not None:
            registro.update(state='rechazado', technical_checks_passed=False)
            registro['errors'].append(str(exc))
            (destino/'resultado_entrega.json').write_text(json.dumps(registro, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Entrega rechazada: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
