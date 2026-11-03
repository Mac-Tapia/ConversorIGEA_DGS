"""Genera la matriz de RF, implementación, pruebas, ejecución y pendientes (spec 065).

Uso: python tools/trazabilidad_candidato.py --output-dir <directorio externo>
     --junit <resultado.xml> --manifest <ejecucion.json> --comprobar

La evidencia formal y una aserción son indicios estructurales: nunca acreditan por sí
solos semántica, aceptación eléctrica ni calidad científica. Solo utiliza la biblioteca
estándar y el lector canónico estado_specs; --help no conecta motores ni modelos.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

try:
    import estado_specs as ES
except ModuleNotFoundError:
    _spec = importlib.util.spec_from_file_location('estado_specs', Path(__file__).with_name('estado_specs.py'))
    ES = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ES)

FORMATO = 'trazabilidad-candidato-v1'
# Selección explícita y versionada: excluye datos empresariales, modelos, dist y runtime.
DIRECTORIOS = ('src', 'tools', 'tests', 'frontend/src', 'frontend/test', 'frontend/scripts',
               'specs', 'config', '.github/workflows', '.claude/skills', '.agents/coordination')
EXTENSIONES = {'.py', '.ts', '.tsx', '.js', '.mjs', '.json', '.toml', '.yaml', '.yml',
               '.md', '.txt', '.bat', '.ps1', '.css', '.html', '.ini', '.cfg'}
FIJOS = ('CODIGO_FUENTE.md', 'CLAUDE.md', 'README.md', 'pyproject.toml', 'run_gui.bat',
         'requirements.txt', 'requirements-drivers.txt', 'constraints-python312-win.txt',
         'docs/constitution.md', 'docs/implementacion065/deuda_arquitectura.json',
         'frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.ts',
         'frontend/tsconfig.json', 'frontend/index.html', 'frontend/.npmrc')
EXCLUIDOS = {'__pycache__', '.pytest_cache', 'node_modules', '.git', 'dist', 'output'}


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def hash_candidato(raiz: Path) -> tuple[str, dict[str, str]]:
    """API M10 estable: SHA-256 de {format,inputs}; rutas POSIX relativas y bytes actuales.

    Incluye archivos nuevos de las superficies declaradas, no solo git HEAD. El runner
    debe llamar antes y después del comando y conservar ambos valores; crear un
    manifiesto después de ejecutar no demuestra que el código no cambió durante ella.
    """
    raiz = Path(raiz).resolve()
    rutas = {raiz / r for r in FIJOS if (raiz / r).is_file()}
    for directorio in DIRECTORIOS:
        rutas.update(p for p in (raiz / directorio).rglob('*') if p.is_file()
                     and p.suffix.lower() in EXTENSIONES
                     and not (set(p.relative_to(raiz).parts) & EXCLUIDOS))
    inputs = {p.relative_to(raiz).as_posix(): sha256(p) for p in sorted(rutas)}
    contenido = json.dumps({'format': FORMATO, 'inputs': inputs}, sort_keys=True,
                           ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(contenido).hexdigest(), inputs


def revision(raiz: Path) -> str:
    resultado = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz, capture_output=True,
                               text=True, encoding='utf-8', check=False)
    return resultado.stdout.strip() if resultado.returncode == 0 else 'sin_revision_git'


def manifiesto_ejecucion(raiz: Path, junit: Path, command: str, revision_id: str,
                         source_hash_before: str | None = None) -> dict:
    """Prepara identidad con el hash capturado antes del test (065:RF-20, 065:RF-24).

    Suponerlo igual al actual dejaba acreditar un JUnit anterior sobre código cambiado después.
    """
    if not source_hash_before:
        raise ValueError('Falta el hash anterior a la ejecución: sin él no se acredita el JUnit.')
    digest, inputs = hash_candidato(raiz)
    return {'format': FORMATO, 'candidate_sha256': digest, 'inputs': inputs,
            'revision': revision_id, 'command': command, 'junit_sha256': sha256(junit),
            'source_hash_before': source_hash_before, 'source_hash_after': digest}


def validar_salida(destino: Path, raiz: Path) -> Path:
    """Rechaza cualquier salida bajo el checkout actual, el principal o sus worktrees."""
    destino, raiz = Path(destino).resolve(), Path(raiz).resolve()
    prohibidos = {raiz, ES.RAIZ.resolve()}
    for origen in {raiz, ES.RAIZ.resolve()}:
        resultado = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                   cwd=origen, capture_output=True, text=True, check=False)
        if resultado.returncode == 0:
            comun = Path(resultado.stdout.strip())
            if comun.name == '.git':
                prohibidos.add(comun.parent.resolve())
    for checkout in prohibidos:
        if destino == checkout or destino.is_relative_to(checkout):
            raise ValueError(f'La salida debe ser externa a los checkouts: {destino}')
    return destino


def _nodeid(classname: str, nombre: str, archivo: str = '') -> str:
    partes = classname.split('.')
    clases = []
    while partes and partes[-1].startswith('Test'):
        clases.insert(0, partes.pop())
    ruta = archivo.replace('\\', '/') or '/'.join(partes) + '.py'
    return '::'.join([ruta, *clases, nombre])


def leer_junit(ruta: Path) -> list[dict]:
    """Conserva cada testcase y resultado, incluyendo skip/xfail/error y parámetros."""
    arbol = ET.parse(ruta)
    resultados = []
    for caso in arbol.iter('testcase'):
        estado = 'pass'
        if caso.find('failure') is not None:
            estado = 'fail'
        elif caso.find('error') is not None:
            estado = 'error'
        elif caso.find('skipped') is not None:
            omitido = caso.find('skipped')
            estado = 'xfail' if 'xfail' in (omitido.get('type', '') + omitido.get('message', '')).lower() else 'skip'
        resultados.append({'nodeid': _nodeid(caso.get('classname', ''), caso.get('name', ''), caso.get('file', '')),
                           'outcome': estado, 'duration': caso.get('time'),
                           'junit': str(ruta.resolve()), 'junit_sha256': sha256(ruta)})
    return resultados


def _asercion(nodo: ast.AST) -> bool:
    # Solo sintaxis ejecutable del test; una función local con assert no cuenta.
    for hijo in ast.iter_child_nodes(nodo):
        if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(hijo, ast.Assert):
            return True
        if isinstance(hijo, ast.Call):
            if isinstance(hijo.func, ast.Attribute) and (hijo.func.attr.startswith('assert') or hijo.func.attr == 'raises'):
                return True
        if _asercion(hijo):
            return True
    return False


def _fuentes_python(raiz: Path, definidos: dict, errores: list[str]) -> tuple[list, list]:
    citas, tests = [], []
    rutas = sorted({p for d in ('tests', 'src', 'tools') for p in (raiz / d).rglob('*.py')
                    if '__pycache__' not in p.parts})
    for ruta in rutas:
        relativo = ruta.relative_to(raiz).as_posix()
        try:
            arbol = ast.parse(ruta.read_text(encoding='utf-8-sig'))
        except (SyntaxError, UnicodeError) as exc:
            errores.append(f'AST ilegible {relativo}: {exc}')
            continue

        for formal in ES.textos_formales_python(ruta.read_text(encoding='utf-8-sig')):
            for n, rfs in ES.citas_en_texto(formal['text'], definidos).items():
                for rf in sorted(rfs, key=ES.clave_rf):
                    citas.append({'requirement': f'{n}:RF-{rf}', 'path': relativo,
                                  **{k: formal[k] for k in ('line', 'scope', 'symbol')},
                                  'evidence': 'cita_formal_no_semantica'})

        def visitar(nodo, padres=()):
            tipo = ('module' if isinstance(nodo, ast.Module) else 'class'
                    if isinstance(nodo, ast.ClassDef) else 'function')
            nombre = getattr(nodo, 'name', '')
            actual = (*padres, nombre) if nombre else padres
            doc = ast.get_docstring(nodo) or ''
            refs = ES.citas_en_texto(doc, definidos)
            es_test = (relativo.startswith('tests/') and tipo == 'function'
                       and nombre.startswith('test_') and all(p.startswith('Test') for p in padres))
            if es_test:
                tests.append({'nodeid': '::'.join([relativo, *actual]), 'path': relativo,
                              'line': nodo.lineno, 'has_assertion': _asercion(nodo),
                              'requirements': [f'{n}:RF-{rf}' for n, rfs in refs.items() for rf in rfs]})
            for hijo in ast.iter_child_nodes(nodo):
                if isinstance(hijo, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    visitar(hijo, actual)
        visitar(arbol)
    return citas, tests


def _indice(raiz: Path, definidos: dict, errores: list[str]) -> list[dict]:
    ruta = raiz / 'CODIGO_FUENTE.md'
    if not ruta.is_file():
        errores.append('Falta CODIGO_FUENTE.md')
        return []
    enlaces = []
    for archivo, columna in re.findall(r'^\| `([^`]+)` \| .* \| ([^|]*) \|\s*$', ruta.read_text(encoding='utf-8'), re.M):
        if Path(archivo).is_absolute() or '..' in Path(archivo).parts:
            errores.append(f'Archivo externo en índice: {archivo}')
            continue
        if not any(raiz.glob(archivo.replace('NNN', '[0-9]' * 3).rstrip('/'))):
            errores.append(f'Archivo inexistente en índice: {archivo}')
        # El índice también permite una atribución a toda la spec: se mantiene separada.
        for m in re.finditer(r'\b(\d{3})\b(?:\s*\(([^)]*)\))?', columna):
            n, contenido = m.groups()
            if n not in definidos:
                errores.append(f'Spec inexistente en índice: {n} ({archivo})')
                continue
            rfs = ES.referencias_rf(contenido or '', {'': definidos[n]}).get('', set())
            enlaces.append({'path': archivo, 'spec': n, 'requirements': [f'{n}:RF-{rf}' for rf in rfs],
                            'kind': 'indice_rf' if rfs else 'indice_spec_no_atribucion_rf',
                            'role': _rol(archivo)})
    return enlaces


def _rol(archivo: str) -> str:
    # El lanzador y los guiones de compilación se ejecutan: implementan 065:RF-2 a RF-4 y no son documentación.
    if archivo.startswith(('src/', 'tools/', 'frontend/src/', 'frontend/scripts/')) or archivo == 'run_gui.bat':
        return 'codigo_no_verificado_semanticamente'
    return 'documentacion_configuracion_no_ejecucion_dominio'


def construir_matriz(raiz: Path, junit_paths=(), manifest_paths=(), vinculos_path=None) -> dict:
    """Reúne evidencia y errores; nunca cambia estados, tareas ni archivos de entrada."""
    raiz = Path(raiz).resolve()
    specs = ES.leer_specs(raiz)
    definidos = {s.numero: s.rf for s in specs}
    requisitos = {f'{s.numero}:RF-{rf}' for s in specs for rf in s.rf}
    errores = []
    digest, inputs = hash_candidato(raiz)
    citas, tests = _fuentes_python(raiz, definidos, errores)
    impl = _indice(raiz, definidos, errores)
    por_test = {t['nodeid']: t for t in tests}
    for test in tests:
        test['executions'] = []
    for item in [*citas, *impl]:
        for req in ([item['requirement']] if 'requirement' in item else item['requirements']):
            if req not in requisitos:
                errores.append(f'Requisito inexistente: {req} en {item.get("path")}')
    if vinculos_path:
        vinculos = json.loads(Path(vinculos_path).read_text(encoding='utf-8'))
        if not isinstance(vinculos, list):
            raise ValueError('Los vínculos deben ser una lista JSON')
        for vinculo in vinculos:
            req, archivo = vinculo['requirement'], vinculo['implementation']
            if req not in requisitos:
                errores.append(f'Requisito inexistente en vínculos: {req}')
            ruta = (raiz / archivo).resolve()
            if not ruta.is_relative_to(raiz) or not ruta.is_file():
                errores.append(f'Implementación inexistente o externa: {archivo}')
            impl.append({'path': archivo, 'spec': req.split(':')[0], 'requirements': [req],
                         'kind': 'vinculo_explicito_no_semantico', 'role': _rol(archivo)})
            for nodeid in vinculo.get('tests', []):
                if nodeid not in por_test:
                    errores.append(f'Prueba sin función existente: {nodeid}')
                else:
                    por_test[nodeid]['requirements'].append(req)
    manifests = []
    actual_revision = revision(raiz)
    manifest_reports = []
    junit_hashes = {sha256(Path(p)) for p in junit_paths}
    for ruta_manifest in manifest_paths:
        manifest = json.loads(Path(ruta_manifest).read_text(encoding='utf-8'))
        if not isinstance(manifest, dict):
            raise ValueError('El manifiesto debe ser un objeto JSON')
        fallos = []
        requeridos = ('candidate_sha256', 'revision', 'command', 'junit_sha256', 'inputs')
        if any(not manifest.get(k) for k in requeridos):
            fallos.append('campos obligatorios ausentes o vacíos')
        if manifest.get('candidate_sha256') != digest or manifest.get('inputs') != inputs:
            fallos.append('entradas o hash distintos del candidato')
        if actual_revision != 'sin_revision_git' and manifest.get('revision') != actual_revision:
            fallos.append('revisión distinta del candidato')
        if manifest.get('junit_sha256') not in junit_hashes:
            fallos.append('JUnit no vinculado por SHA-256')
        # Sin valor por defecto: un manifiesto que no trae las dos observaciones no acredita nada.
        if manifest.get('source_hash_before') != digest or manifest.get('source_hash_after') != digest:
            fallos.append('el código cambió durante la ejecución o falta una observación')
        manifest_reports.append({'path': str(Path(ruta_manifest).resolve()),
                                 'sha256': sha256(Path(ruta_manifest)), 'errors': fallos})
        if fallos:
            errores.append(f'Manifiesto inválido del candidato {ruta_manifest}: {", ".join(fallos)}')
        else:
            manifests.append(manifest)
    ejecuciones = []
    for ruta_xml in junit_paths:
        ruta_xml = Path(ruta_xml)
        xml_hash = sha256(ruta_xml)
        validos = [m for m in manifests if m.get('junit_sha256') == xml_hash]
        for resultado in leer_junit(ruta_xml):
            resultado['verified'] = bool(validos)
            resultado['verification_reason'] = ('identidad_candidato_y_junit_coinciden'
                                                if validos else 'manifiesto_valido_ausente')
            resultado['command'] = validos[0]['command'] if validos else None
            resultado['revision'] = validos[0]['revision'] if validos else None
            ejecuciones.append(resultado)
            base = resultado['nodeid'].split('[', 1)[0]
            if base in por_test:
                por_test[base]['executions'].append(resultado)
    filas = []
    for spec in specs:
        cientifica = spec.numero in {'024', '027', '043', '044', '045', '046', '047', '048', '049', '050', '052', '057', '060'}
        for rf in sorted(spec.rf, key=ES.clave_rf):
            req = f'{spec.numero}:RF-{rf}'
            pruebas = [t for t in tests if req in t['requirements']]
            implementacion = [i for i in impl if req in i['requirements']]
            # Las referencias de código permiten descubrir vínculos ausentes del índice;
            # se etiquetan como formales y requieren la misma revisión semántica.
            implementacion += [{'path': c['path'], 'spec': spec.numero, 'requirements': [req],
                                'kind': 'referencia_formal_no_semantica', 'role': _rol(c['path']),
                                'scope': c['scope'], 'line': c['line'], 'symbol': c['symbol']}
                               for c in citas if c['requirement'] == req
                               and c['path'].startswith(('src/', 'tools/'))]
            generales = [i for i in impl if i['spec'] == spec.numero and not i['requirements']]
            pendientes = ['revision_semantica_pendiente']
            if not any(i['role'] == 'codigo_no_verificado_semanticamente' for i in implementacion):
                pendientes.append('implementacion_rf_sin_vinculo_explicito')
            if not pruebas or not any(t['has_assertion'] for t in pruebas):
                pendientes.append('prueba_con_asercion_ausente')
            resultados = [e for t in pruebas if t['has_assertion'] for e in t['executions']]
            verificado = bool(resultados) and all(e['verified'] and e['outcome'] == 'pass' for e in resultados)
            if not verificado:
                pendientes.append('ejecucion_del_candidato_pendiente_o_no_aprobada')
            tareas = [t for t in spec.tareas if rf in ES.rf_de_texto(t.texto)]
            if any(t.digsilent for t in tareas):
                pendientes.append('aceptacion_nativa_pendiente')
            if cientifica:
                pendientes.append('aceptacion_cientifica_pendiente')
            filas.append({'requirement': req, 'spec_path': (spec.carpeta / 'spec.md').relative_to(raiz).as_posix(),
                          'declared_state': spec.estado, 'implementation': implementacion,
                          'spec_level_implementation': generales, 'tests': pruebas,
                          'test_evidence': 'ejecucion_verificada' if verificado else 'pendiente',
                          'acceptance': 'pendiente_revision_semantica', 'pending': pendientes,
                          'open_tasks': [t.id for t in tareas if not t.hecha]})
    return {'format': FORMATO, 'root': str(raiz), 'candidate': {'sha256': digest, 'inputs': inputs,
             'revision': actual_revision, 'selection': {'directories': DIRECTORIOS, 'fixed': FIJOS,
             'extensions': sorted(EXTENSIONES), 'excluded': sorted(EXCLUIDOS)}},
            'rows': filas, 'formal_citations': citas, 'executions': ejecuciones,
            'execution_manifests': manifest_reports,
            'errors': sorted(set(errores)), 'limitations': [
                'Una cita formal o aserción AST no demuestra semántica.',
                'Documentación, inventarios y dobles no sustituyen ejecución nativa o evaluación científica.',
                'Las aceptaciones conservan pendiente hasta revisión específica del dominio.']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ES.RAIZ, help='checkout candidato a leer')
    parser.add_argument('--output-dir', type=Path, required=True, help='salida externa a todos los checkouts')
    parser.add_argument('--junit', type=Path, action='append', default=[], help='XML JUnit; repetible')
    parser.add_argument('--manifest', type=Path, action='append', default=[], help='manifiesto de ejecución; repetible')
    parser.add_argument('--vinculos', type=Path, help='lista JSON de requirement/implementation/tests')
    parser.add_argument('--comprobar', action='store_true', help='falla si hay referencias inválidas; pendientes siguen visibles')
    args = parser.parse_args(argv)
    try:
        destino = validar_salida(args.output_dir, args.root)
        informe = construir_matriz(args.root, args.junit, args.manifest, args.vinculos)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / 'trazabilidad.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
        with (destino / 'trazabilidad.csv').open('w', encoding='utf-8', newline='') as salida:
            escritor = csv.DictWriter(salida, fieldnames=['requirement', 'implementation', 'tests', 'test_evidence', 'acceptance', 'pending'])
            escritor.writeheader()
            for fila in informe['rows']:
                escritor.writerow({k: json.dumps(fila[k], ensure_ascii=False, separators=(',', ':'))
                                   if isinstance(fila[k], list) else fila[k] for k in escritor.fieldnames})
        fuentes = {str(p.resolve()): sha256(p) for p in [*args.junit, *args.manifest, *([args.vinculos] if args.vinculos else [])]}
        manifiesto = {'format': FORMATO, 'candidate_sha256': informe['candidate']['sha256'],
                      'inputs': informe['candidate']['inputs'], 'evidence_inputs': fuentes,
                      'tool_inputs': {p.name: sha256(p) for p in [Path(__file__), Path(ES.__file__)]},
                      'outputs': {n: sha256(destino / n) for n in ['trazabilidad.json', 'trazabilidad.csv']}}
        (destino / 'manifest.json').write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{len(informe["rows"])} RF; {len(informe["errors"])} errores; aceptación semántica pendiente. {destino}')
        for error in informe['errors']:
            print(error)
        return 1 if args.comprobar and informe['errors'] else 0
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        print(f'Trazabilidad rechazada: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
