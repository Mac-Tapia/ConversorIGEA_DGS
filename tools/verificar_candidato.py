"""Prepara o ejecuta la regresión trazable del candidato integrado (spec 065).

Sin --ejecutar solo prepara registro y matriz; --help usa la biblioteca estándar.
La regresión no acredita instalación, build, arranque, aceptación eléctrica ni
científica: cada uno conserva su evidencia y sus pendientes propios.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[1]
ENTRADAS = {
    'red': 'CSG_RED', 'cargas': 'CSG_LOADS', 'equipos': 'CSG_EQUIPMENT',
    'mdb': 'CSG_MDB', 'equipos_mdb': 'CSG_EQUIPMENT_MDB',
    'demanda_dir': 'CSG_DEMANDA_DIR', 'vnr_bak': 'CSG_VNR_BAK',
    'solicitud_pdf': 'CSG_SOLICITUD_PDF', 'solicitud_dir': 'CSG_SOLICITUD_DIR',
}
DIRECTORIOS_DATOS = {'CSG_DEMANDA_DIR', 'CSG_SOLICITUD_DIR'}


def _trazabilidad():
    ruta = Path(__file__).with_name('trazabilidad_candidato.py')
    spec = importlib.util.spec_from_file_location('trazabilidad_runner', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@contextmanager
def _git_local():
    # Los helpers canónicos usan Git por cwd: GIT_DIR heredado puede cambiar su identidad.
    anteriores = {k: v for k, v in os.environ.items() if k.upper().startswith('GIT_')}
    for clave in anteriores:
        del os.environ[clave]
    try:
        yield
    finally:
        os.environ.update(anteriores)


def _json(ruta: Path, valor) -> None:
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def resumir_junit(ruta: Path) -> dict:
    """065:RF-24 — rechaza XML incompleto y conserva cada resultado con su razón."""
    try:
        arbol = ET.parse(ruta)
        raiz = arbol.getroot()
        if raiz.tag not in {'testsuites', 'testsuite'}:
            raise ValueError('raíz JUnit desconocida')
        suites = [s for s in raiz.iter('testsuite') if s.find('testsuite') is None]
        if not suites:
            raise ValueError('JUnit sin suites')
        casos, counts = [], dict.fromkeys(('pass', 'fail', 'error', 'skip', 'xfail'), 0)
        for suite in suites:
            locales = dict.fromkeys(counts, 0)
            for caso in suite.findall('testcase'):
                marcas = [m for m in caso if m.tag in {'failure', 'error', 'skipped'}]
                if len(marcas) > 1:
                    raise ValueError('testcase con resultados contradictorios')
                marca = marcas[0] if marcas else None
                estado = 'pass'
                if marca is not None:
                    estado = {'failure': 'fail', 'error': 'error', 'skipped': 'skip'}[marca.tag]
                    if estado == 'skip' and 'xfail' in (marca.get('type', '') + marca.get('message', '')).lower():
                        estado = 'xfail'
                locales[estado] += 1
                casos.append({'classname': caso.get('classname', ''), 'name': caso.get('name', ''),
                              'outcome': estado, 'duration': caso.get('time'),
                              'message': marca.get('message', '') if marca is not None else '',
                              'detail': marca.text if marca is not None else None})
            declarados = {k: int(suite.attrib[k]) for k in ('tests', 'failures', 'errors', 'skipped')}
            observados = {'tests': sum(locales.values()), 'failures': locales['fail'],
                          'errors': locales['error'], 'skipped': locales['skip'] + locales['xfail']}
            if declarados != observados:
                raise ValueError('contadores JUnit no coinciden con los testcases')
            for estado in counts:
                counts[estado] += locales[estado]
        if not casos:
            raise ValueError('JUnit sin testcases')
        return {'counts': counts, 'cases': casos}
    except (ET.ParseError, KeyError, OSError, ValueError) as exc:
        raise ValueError(f'JUnit rechazado: {exc}') from exc


def evaluar_resultado(returncode: int, informe: dict, antes: str, despues: str,
                      datos_antes: dict, datos_despues: dict, completa: bool) -> list[str]:
    """065:RF-1/24 — código cero no salva cambios de entradas ni omisiones completas."""
    errores = []
    if returncode:
        errores.append(f'pytest_exit_{returncode}')
    if antes != despues:
        errores.append('candidato_modificado')
    if datos_antes != datos_despues:
        errores.append('datos_modificados')
    counts = informe['counts']
    if counts['fail'] or counts['error']:
        errores.append('pruebas_fallidas')
    if completa and (counts['skip'] or counts['xfail']):
        errores.append('omisiones')
    return errores


def inventariar_datos(entradas: dict[str, Path], hash_datos: bool) -> dict:
    """065:RF-1/24 — metadata por archivo; SHA streaming solo mediante opción explícita."""
    informe = {}
    for variable, origen in entradas.items():
        archivos = sorted(p for p in origen.rglob('*') if p.is_file()) if origen.is_dir() else [origen]
        filas = []
        for archivo in archivos:
            stat = archivo.stat()
            fila = {'path': archivo.relative_to(origen).as_posix() if origen.is_dir() else archivo.name,
                    'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
            if hash_datos:
                digest = hashlib.sha256()
                with archivo.open('rb') as fuente:
                    for bloque in iter(lambda: fuente.read(1024 * 1024), b''):
                        digest.update(bloque)
                fila['sha256'] = digest.hexdigest()
                # Solo tamaño y modificación: leer el fichero mueve su hora de acceso, y compararla daba
                # «la fuente cambió» de forma intermitente con el equipo cargado (suite del 2026-11-03).
                despues = archivo.stat()
                if (despues.st_size, despues.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                    raise ValueError(f'La fuente cambió durante su hash: {variable}')
            filas.append(fila)
        informe[variable] = {'root': str(origen), 'mode': 'sha256' if hash_datos else 'metadata_no_criptografica',
                             'files': filas}
    return informe


def _validar_entradas(args) -> tuple[dict, list]:
    entradas, faltantes, invalidas = {}, [], []
    for opcion, variable in ENTRADAS.items():
        valor = getattr(args, opcion) or os.environ.get(variable, '').strip()
        if not valor:
            faltantes.append(variable)
            continue
        ruta = Path(valor).expanduser().resolve()
        valida = ruta.is_dir() if variable in DIRECTORIOS_DATOS else ruta.is_file()
        if not valida:
            invalidas.append(variable)
        else:
            entradas[variable] = ruta
    problemas = []
    if invalidas:
        problemas.append('Fuentes inexistentes o de tipo incorrecto: ' + ', '.join(invalidas))
    if args.suite_completa and faltantes:
        problemas.append('Faltan entradas para suite completa: ' + ', '.join(faltantes))
    if problemas:
        raise ValueError('; '.join(problemas))
    return entradas, faltantes


def _entorno(ejecucion: Path, entradas: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('GIT_', 'PYTEST_'))
           and k.upper() not in {'PYTHONPATH', 'PYTHONHOME', 'CSG_RUTAS_AUTOMATICAS'}}
    env.update({k: str(v) for k, v in entradas.items()})
    env.update(PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1', PYTHONUTF8='1')
    # 065:RF-24: una ruta heredada de la web activa prevalece sobre runtime_home y haría
    # que las pruebas escribieran datos o modelos del operador. Las nueve entradas
    # explícitas se conservan; los destinos y cachés pertenecen a esta ejecución.
    rutas = {'CSG_RUNTIME_HOME': 'runtime', 'CSG_CACHE_HOME': 'cache', 'CSG_TEMP_HOME': 'tmp',
             'CSG_DATOS_HOME': 'runtime/data', 'CSG_WEB_DATA': 'runtime/data/web',
             'CSG_ASISTENTE_DATA': 'runtime/data/asistente', 'CSG_TWIN_DATA': 'runtime/data/twin',
             'CSG_WEB_SESIONES': 'runtime/sesiones_web',
             'TEMP': 'tmp', 'TMP': 'tmp', 'TMPDIR': 'tmp', 'PYTHONPYCACHEPREFIX': 'cache/python',
             'RUFF_CACHE_DIR': 'cache/ruff', 'npm_config_cache': 'cache/npm',
             'TORCH_HOME': 'cache/torch', 'TORCHINDUCTOR_CACHE_DIR': 'cache/torchinductor',
             'TRITON_CACHE_DIR': 'cache/triton', 'HF_HOME': 'cache/huggingface',
             'HF_HUB_CACHE': 'cache/huggingface/hub', 'XDG_CACHE_HOME': 'cache/xdg',
             'NUMBA_CACHE_DIR': 'cache/numba', 'MPLCONFIGDIR': 'cache/matplotlib',
             'CUDA_CACHE_PATH': 'cache/cuda', 'TORCH_EXTENSIONS_DIR': 'cache/torch_extensions'}
    for variable, relativo in rutas.items():
        ruta = ejecucion / relativo
        ruta.mkdir(parents=True, exist_ok=True)
        env[variable] = str(ruta)
    # El perfil es un fichero opcional, no un directorio ni el perfil real del puesto.
    env['CSG_PERFIL_EMPRESA'] = str(ejecucion / 'runtime/data/perfil_empresa.json')
    return env


def _runtime(python: Path, raiz: Path, env: dict) -> dict:
    codigo = ('import sys,platform,json,importlib.metadata as m; '
              'print(json.dumps({"executable":sys.executable,"version":sys.version,'
              '"version_info":list(sys.version_info[:3]),"platform":platform.platform(),'
              '"packages":{d.metadata["Name"]:d.version for d in m.distributions()}}))')
    proceso = subprocess.run([str(python), '-B', '-c', codigo], cwd=raiz, env=env,
                             capture_output=True, text=True, encoding='utf-8', check=False)
    if proceso.returncode:
        raise ValueError('No se pudo consultar el intérprete Python seleccionado')
    informe = json.loads(proceso.stdout)
    if informe['version_info'][:2] != [3, 12]:
        raise ValueError('La regresión integrada requiere Python 3.12 exacto')
    return informe


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=RAIZ, help='checkout candidato a leer')
    parser.add_argument('--output-dir', type=Path, required=True, help='raíz de evidencia externa; cada intento crea un UUID')
    parser.add_argument('--python', type=Path, default=Path(sys.executable), help='intérprete Python 3.12 con pytest instalado')
    parser.add_argument('--ejecutar', action='store_true', help='ejecutar pytest; sin esta opción solo prepara')
    parser.add_argument('--suite-completa', action='store_true', help='exigir las nueve entradas y rechazar skip/xfail; sin selección parcial')
    parser.add_argument('--prueba', action='append', default=[], help='ruta/nodeid de pytest dentro del candidato; repetible para fase core')
    parser.add_argument('--hash-datos', action='store_true', help='leer todos los bytes de las fuentes dos veces para calcular SHA-256 (puede tardar con GB)')
    for opcion, variable in ENTRADAS.items():
        parser.add_argument('--' + opcion.replace('_', '-'), type=Path, help=f'fuente explícita; alternativa: {variable}')
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    registro, ejecucion = None, None
    try:
        raiz = args.root.resolve()
        if not (raiz / 'tests').is_dir() or not (raiz / 'specs').is_dir():
            raise ValueError('El candidato debe contener tests/ y specs/')
        if args.suite_completa and args.prueba:
            raise ValueError('--suite-completa no permite seleccionar --prueba')
        entradas, faltantes = _validar_entradas(args)
        pruebas = args.prueba or ['tests']
        for seleccion in pruebas:
            ruta = (raiz / seleccion.split('::', 1)[0]).resolve()
            if not ruta.is_relative_to(raiz) or not ruta.exists() or seleccion.startswith('-'):
                raise ValueError('La selección de pruebas debe existir dentro del candidato')
        trazabilidad = _trazabilidad()
        with _git_local():
            destino = trazabilidad.validar_salida(args.output_dir, raiz)
            revision_id = trazabilidad.revision(raiz)
        for variable, origen in entradas.items():
            if origen.is_dir() and destino.is_relative_to(origen):
                raise ValueError(f'La salida no puede estar dentro de la fuente: {variable}')
        # Todas las validaciones anteriores ocurren antes de crear cualquier salida.
        ejecucion = destino / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex)
        ejecucion.mkdir(parents=True, exist_ok=False)
        env = _entorno(ejecucion, entradas)
        junit = ejecucion / 'junit.xml'
        comando = [str(args.python.resolve()), '-B', '-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider',
                   '--junitxml', str(junit), '--basetemp', str(ejecucion / ('pytest_' + uuid.uuid4().hex)), *pruebas]
        antes, inputs_antes = trazabilidad.hash_candidato(raiz)
        datos_antes = inventariar_datos(entradas, args.hash_datos)
        _json(ejecucion / 'source_inputs_before.json', inputs_antes)
        _json(ejecucion / 'data_inputs_before.json', datos_antes)
        registro = {'format': 'verificacion-candidato-v1', 'root': str(raiz), 'revision': revision_id,
                    'state': 'preparado', 'scope': 'suite_completa' if args.suite_completa else 'regresion_parcial',
                    'command': comando, 'source_hash_before': antes, 'source_hash_after': None,
                    'missing_inputs': faltantes, 'data_hash_mode': 'sha256' if args.hash_datos else 'metadata_no_criptografica',
                    'returncode': None, 'results': None, 'errors': [],
                    'pending': ['instalacion_reproducible', 'frontend_build', 'arranque_aislado',
                                'aceptacion_nativa', 'aceptacion_cientifica']}
        _json(ejecucion / 'registro.json', registro)
        manifiestos = []
        if args.ejecutar:
            _json(ejecucion / 'runtime.json', _runtime(args.python.resolve(), raiz, env))
            registro['state'] = 'en_ejecucion'
            _json(ejecucion / 'registro.json', registro)
            print(f'Ejecutando regresión. Evidencia: {ejecucion}', flush=True)
            with (ejecucion / 'stdout.log').open('wb') as stdout, (ejecucion / 'stderr.log').open('wb') as stderr:
                proceso = subprocess.run(comando, cwd=raiz, env=env, stdout=stdout, stderr=stderr, check=False)
            despues, inputs_despues = trazabilidad.hash_candidato(raiz)
            datos_despues = inventariar_datos(entradas, args.hash_datos)
            _json(ejecucion / 'source_inputs_after.json', inputs_despues)
            _json(ejecucion / 'data_inputs_after.json', datos_despues)
            registro.update(returncode=proceso.returncode, source_hash_after=despues)
            try:
                registro['results'] = resumir_junit(junit)
            except ValueError as exc:
                registro['errors'].append(str(exc))
            informe = registro['results'] or {'counts': dict.fromkeys(('pass', 'fail', 'error', 'skip', 'xfail'), 0)}
            registro['errors'].extend(evaluar_resultado(proceso.returncode, informe, antes, despues,
                                                      datos_antes, datos_despues, args.suite_completa))
            if registro['results'] is not None:
                manifiesto = trazabilidad.manifiesto_ejecucion(raiz, junit, subprocess.list2cmdline(comando), revision_id, antes)
                _json(ejecucion / 'manifiesto_ejecucion.json', manifiesto)
                manifiestos = ['--manifest', str(ejecucion / 'manifiesto_ejecucion.json')]
            registro['state'] = 'rechazado' if registro['errors'] else 'regresion_aprobada'
        with _git_local():
            matriz_codigo = trazabilidad.main(['--root', str(raiz), '--output-dir', str(ejecucion / 'matriz'),
                                              '--comprobar', *(['--junit', str(junit)] if manifiestos else []),
                                              *manifiestos])
        if matriz_codigo:
            registro['errors'].append('matriz_rechazada')
        final, _ = trazabilidad.hash_candidato(raiz)
        if final != antes and 'candidato_modificado' not in registro['errors']:
            registro['errors'].append('candidato_modificado')
        if registro['errors']:
            registro['state'] = 'rechazado'
        _json(ejecucion / 'registro.json', registro)
        print(f'{registro["state"]}; entradas faltantes: {", ".join(faltantes) or "ninguna"}; evidencia: {ejecucion}')
        return 1 if registro['errors'] else 0
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        if registro is not None:
            registro['state'] = 'rechazado'
            registro['errors'].append(str(exc))
            _json(ejecucion / 'registro.json', registro)
        print(f'Verificación rechazada: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
