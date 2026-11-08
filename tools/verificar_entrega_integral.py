"""Puerta integral de regresión de la entrega (065:RF-24; 086:RF-46).

Sin --ejecutar prepara el plan, sin lanzar pruebas, red ni motores. Consolida
backend, frontend y, en edición completa, ML. Un pase técnico no acredita por sí
solo aceptación eléctrica, científica, operativa ni autorización de publicación.
Completa exige --campana FAMILIA RUTA SHA256 para cada familia canónica; leer
esos recibos no ejecuta entrenamientos ni transforma un replay en campaña real.
Los resultados y temporales se conservan fuera de todos los checkouts.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
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


def plan_comprobaciones(raiz: Path, python: Path, edicion: str, evidencia: Path, *, campanas=()) -> list[dict]:
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
    agregar('frontend_lint', 'command', [node, frontend/'scripts/fronteras.mjs'], cwd=frontend)
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
        agregar('campanas', 'campanas', [], recibos=list(campanas))
    return filas


def admitir_campanas(referencias) -> dict:
    """065:RF-24 — verifica recibos explícitos; nunca ejecuta proveedores o promueve modelos."""
    from convertersmartgrid.adaptadores.fuentes_estables import abrir_fuente_estable
    from convertersmartgrid.evaluacion_harness.contratos import MINIMAS
    from convertersmartgrid.evaluacion_harness.ejecucion import validar_integridad
    from convertersmartgrid.evaluacion_harness.publicacion import leer_informe

    errores, familias, vistos = [], [], set()
    for familia, nombre, esperado in referencias:
        fila = {'familia': familia, 'ruta': str(Path(nombre).resolve()), 'sha256': esperado,
                'state': 'bloqueada', 'errors': [], 'aceptacion_cientifica': False,
                'aceptacion_electrica': False, 'aceptacion_operativa': False}
        familias.append(fila)
        try:
            if familia not in MINIMAS or familia in vistos:
                raise ValueError('familia desconocida o duplicada')
            vistos.add(familia)
            if not isinstance(esperado, str) or not re.fullmatch('[0-9a-f]{64}', esperado):
                raise ValueError('SHA256 explícito inválido')
            with abrir_fuente_estable(nombre) as fuente:
                if fuente.sha256 != esperado:
                    raise ValueError('SHA256 del recibo distinto del declarado')
                fila['integridad_antes'] = fuente.sha256
                informe = leer_informe(fuente.path)
                validar_integridad(informe)
                cfg = informe['configuracion']
                if cfg['familia'] != familia:
                    raise ValueError('familia del recibo distinta de la declarada')
                # bool es subclase de int: False no debe sustituir un conteo cero.
                if any(type(informe.get(k)) is not int for k in ('programados', 'completados', 'fallidos')):
                    raise ValueError('conteos de campaña deben ser enteros, no booleanos')
                operaciones = []
                for suite in cfg['suites']:
                    s = informe['suites'][suite['id']]
                    if (type(s.get('programados')) is not int or s['programados'] <= 0
                            or any(type(s.get(k)) is not bool for k in ('completa', 'aprobada', 'evidencia_real'))):
                        raise ValueError('conteo o estado de operación inválido')
                    operaciones.append({'id': suite['id'], 'tipo': suite['tipo'],
                        'obligatoria': suite['obligatoria'], 'programados': s['programados'],
                        'completa': s['completa'], 'aprobada_declarada': s['aprobada'],
                        'evidencia_real_declarada': s['evidencia_real'],
                        'implementacion': 'declarada_no_verificada_semanticamente',
                        'aceptacion_cientifica': False, 'aceptacion_operativa': False,
                        'aceptacion_electrica': False})
                fila.update(modo=informe['modo'], revision_captura=cfg['revision'], run_id=cfg['run_id'],
                    config_hash=informe['config_hash'], sello_informe=informe['sello_informe'],
                    datos={'dataset_hash': cfg['dataset_hash'], 'custodia': cfg['custodia']},
                    modelos=cfg['modelos'], operaciones=operaciones,
                    estados_modelos={rol: {'registro': 'no_consultado', 'artefactos_verificados': False,
                        'promovido_declarado': informe.get('modelo_promovido') if rol == 'candidato' else None,
                        'aceptacion_cientifica': False, 'aceptacion_operativa': False}
                        for rol in cfg['modelos']},
                    estado_declarado=informe['estado'], modelo_promovido_declarado=informe.get('modelo_promovido'),
                    mejora_demostrada_declarada=informe['mejora_demostrada'],
                    artefactos='identidades_declaradas_en_recibo_no_cargas_de_pesos',
                    implementacion='declarada_no_verificada_semanticamente')
                fuente.stream.seek(0)
                fila['integridad_despues'] = hashlib.file_digest(fuente.stream, 'sha256').hexdigest()
                if fila['integridad_despues'] != esperado:
                    raise ValueError('recibo cambió durante la validación')
                if informe['modo'] != 'runtime':
                    raise ValueError('campaña ejecutada exige runtime; contract/replay son diagnóstico')
                if (informe['estado'] != 'COMPLETA' or informe['programados'] <= 0
                        or informe['completados'] != informe['programados'] or informe['fallidos'] != 0
                        or any(f['estado'] != 'ok' or f['salida'].get('clase_evidencia') != 'real'
                               for f in informe['casos'])
                        or any(not s['completa'] or not s['evidencia_real_declarada'] for s in operaciones)):
                    raise ValueError('campaña u operaciones sin cobertura runtime completa')
                fila['state'] = 'aprobada'
        except (OSError, ValueError, TypeError, KeyError) as exc:
            fila['errors'].append(str(exc))
            errores.append(f'campanas:{familia}:{exc}')
    for familia in sorted(set(MINIMAS) - vistos):
        errores.append('campanas:recibo_ausente:' + familia)
        familias.append({'familia': familia, 'state': 'ausente', 'errors': ['recibo_ausente'],
                         'aceptacion_cientifica': False, 'aceptacion_electrica': False,
                         'aceptacion_operativa': False})
    return {'state': 'bloqueada' if errores else 'aprobada', 'errors': errores,
            'familias': familias, 'familias_obligatorias': sorted(MINIMAS),
            'aceptacion_cientifica': False, 'aceptacion_electrica': False, 'aceptacion_operativa': False}


def resumir_estados(registro: dict) -> dict:
    """Identidades declaradas y pruebas son niveles distintos de aceptación del dominio."""
    campanas = deepcopy(registro.get('campanas_antes') or registro.get('campanas_despues') or {'familias': []})
    posteriores = {f['familia']: f for f in registro.get('campanas_despues', {}).get('familias', [])}
    for familia in campanas['familias']:
        if familia['familia'] in posteriores:
            final = posteriores[familia['familia']]
            familia['state'], familia['errors'] = final['state'], final['errors']
            familia['validacion_posterior'] = {k: final.get(k) for k in
                ('state', 'errors', 'integridad_antes', 'integridad_despues')}
        familia['origen_identidades'] = ('recibo_leido_antes_de_las_puertas'
                                         if 'revision_captura' in familia else 'sin_identidades_verificadas')
    return {'implementacion': {'revision_validacion': registro['revision'],
                'candidate_hash': registro['candidate_before'], 'estado': 'codigo_identificado_no_aceptacion_semantica'},
            'pruebas': {r['id']: {'estado': r['state'], 'counts': r.get('counts'),
                                  'registro': r.get('registro'), 'stdout': r.get('stdout'),
                                  'artefactos_datos': r.get('artefactos_datos')}
                        for r in registro['results']},
            'datos': {f['familia']: f.get('datos') for f in campanas['familias']},
            'datos_backend': next((r.get('artefactos_datos') for r in registro['results']
                                   if r['id'] == 'backend'), None),
            'modelos': {f['familia']: f.get('modelos') for f in campanas['familias']},
            'salida': registro.get('output_dir'), 'familias': campanas['familias'], 'aceptacion_cientifica': False,
            'aceptacion_electrica': False, 'aceptacion_operativa': False}


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
        datos = {}
        for nombre in ('data_inputs_before.json', 'data_inputs_after.json'):
            ruta = registros[0].parent / nombre
            if not ruta.is_file():
                raise ValueError('Backend sin inventario de datos: ' + nombre)
            with ruta.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            datos[nombre] = {'path': str(ruta), 'sha256': digest}
        return {'counts': counts, 'registro': str(registros[0]), 'artefactos_datos': datos}
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
        if c['kind'] == 'campanas':
            campanas = admitir_campanas(c.get('recibos', ()))
            r['campanas'] = campanas
            r['errors'].extend(campanas['errors'])
            stdout.write_text(json.dumps(campanas, ensure_ascii=False, indent=2), encoding='utf-8')
            stderr.write_text('', encoding='utf-8')
            r.update(state='rechazada' if r['errors'] else 'aprobada', seconds=time.monotonic()-inicio)
            (destino/'resultado.json').write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            return r
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
    parser.add_argument('--campana', nargs=3, action='append', default=[], metavar=('FAMILIA', 'RUTA', 'SHA256'),
                        help='SHA256 de los bytes del archivo (no su sello interno); completa exige todas las familias de MINIMAS en runtime')
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
        plan = plan_comprobaciones(raiz, args.python, args.edicion, destino, campanas=args.campana)
        registro = {'format': 'verificacion-entrega-integral-v1', 'root': str(raiz), 'revision': revision,
                    'output_dir': str(destino),
                    'candidate_before': antes, 'candidate_after': None, 'edition': args.edicion,
                    'state': 'preparado', 'plan': plan, 'results': [],
                    **evaluar_entrega([], {c['id'] for c in plan})}
        if args.edicion == 'completa' or args.campana:
            registro['campanas_antes'] = admitir_campanas(args.campana)
        registro['estados'] = resumir_estados(registro)
        (destino/'resultado_entrega.json').write_text(json.dumps(registro, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if args.edicion == 'completa' and registro['campanas_antes']['errors']:
            raise ValueError('campanas: faltan recibos runtime íntegros; consulte campanas_antes')
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
        if args.edicion == 'completa' or args.campana:
            registro['campanas_despues'] = admitir_campanas(args.campana)
            if registro['campanas_despues']['errors']:
                registro['errors'].extend(registro['campanas_despues']['errors'])
                registro['technical_checks_passed'] = False
        despues, _inputs = trace.hash_candidato(raiz)
        registro['candidate_after'] = despues
        if despues != antes:
            registro['errors'].append('candidato_modificado')
            registro['technical_checks_passed'] = False
        if args.ejecutar:
            registro['state'] = 'regresion_integral_aprobada' if registro['technical_checks_passed'] else 'rechazado'
        elif registro['errors'] and registro.get('campanas_despues', {}).get('errors'):
            registro['state'] = 'rechazado'
        registro['estados'] = resumir_estados(registro)
        (destino/'resultado_entrega.json').write_text(json.dumps(registro, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(f'{registro["state"]}; aceptación de dominio pendiente; evidencia: {destino}')
        return 0 if registro['state'] == 'preparado' or registro['technical_checks_passed'] else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if registro is not None:
            registro.update(state='rechazado', technical_checks_passed=False)
            registro['errors'].append(str(exc))
            (destino/'resultado_entrega.json').write_text(json.dumps(registro, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Entrega rechazada: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
