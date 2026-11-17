"""Spec 077: el servidor MCP local de solo lectura, con y sin su paquete opcional."""
from __future__ import annotations

import ast
import builtins
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
GUION = RAIZ / 'tools' / 'mcp_conversor.py'


def python_mcp(entorno=None, raiz: Path = RAIZ) -> tuple[str, bool]:
    """El intérprete con el paquete `mcp` y si la prueba real queda exigida (077:RF-76).

    `CSG_MCP_PYTHON` manda; si no, el `.venv_mcp` del repositorio. Con cualquiera de los dos, que falte el paquete es
    un fallo y no una omisión. Sin ninguno, el del proyecto, que no lo lleva: la prueba se omite y la puerta de `main`
    no da la suite por buena.
    """
    entorno = os.environ if entorno is None else entorno
    if entorno.get('CSG_MCP_PYTHON'):
        return entorno['CSG_MCP_PYTHON'], True
    for propio in (raiz / '.venv_mcp' / 'Scripts' / 'python.exe', raiz / '.venv_mcp' / 'bin' / 'python'):
        if propio.is_file():
            return str(propio), True
    return sys.executable, False


PYTHON_MCP, MCP_EXIGIDO = python_mcp()


def _cargar():
    spec = importlib.util.spec_from_file_location('mcp_conversor', GUION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _hay_mcp(python: str | None = None) -> bool:
    try:
        r = subprocess.run([python or PYTHON_MCP, '-c', 'import mcp'], capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def exigir_mcp(python: str | None = None, exigido: bool | None = None) -> None:
    """077:RF-76: con un intérprete configurado, que no tenga `mcp` falla; sin ninguno, se omite con su motivo."""
    python = python or PYTHON_MCP
    exigido = MCP_EXIGIDO if exigido is None else exigido
    if _hay_mcp(python):
        return
    if exigido:
        pytest.fail(f'{python} no tiene el paquete mcp de requirements-mcp.txt: la prueba del servidor real no se omite '
                    '(077:RF-76). Instálelo con la orden de docs/MCP_CONVERSOR.md.')
    pytest.skip('sin CSG_MCP_PYTHON ni .venv_mcp: el servidor MCP real no se prueba (077:RF-76, docs/MCP_CONVERSOR.md)')


def lineas_del_lock(ruta: Path) -> list[str]:
    """Los requisitos de un fichero de pip, con sus continuaciones unidas y sin comentarios."""
    texto = re.sub(r'\\\s*\n', ' ', ruta.read_text(encoding='utf-8'))
    lineas = (re.sub(r'\s+', ' ', linea).strip() for linea in texto.splitlines())
    return [linea for linea in lineas if linea and not linea.startswith('#')]


def test_sin_paquete_lo_dice_y_su_codigo(monkeypatch, capsys):
    """077:RF-39 — sin el paquete explica qué instalar y termina con su código."""
    original = builtins.__import__

    def falta(nombre, *a, **k):
        if nombre == 'mcp' or nombre.startswith('mcp.'):
            raise ImportError(nombre)
        return original(nombre, *a, **k)

    monkeypatch.setattr(builtins, '__import__', falta)
    modulo = _cargar()
    assert modulo.main([]) == modulo.SIN_PAQUETE
    assert 'requirements-mcp.txt' in capsys.readouterr().err


def test_ayuda_sin_el_paquete():
    """077:RF-39 — el --help no pide el paquete, con el intérprete que sea."""
    r = subprocess.run([sys.executable, str(GUION), '--help'], capture_output=True, encoding='utf-8', check=False, timeout=60)
    assert r.returncode == 0 and 'solo lectura' in r.stdout


def test_error_cli_con_entorno_cp1252_conserva_utf8():
    """081: un cliente Windows no debe perder los diagnósticos con acentos."""
    r = subprocess.run(
        [sys.executable, str(GUION), '--opcion-inválida'], capture_output=True,
        check=False, timeout=60, env={**os.environ, 'PYTHONIOENCODING': 'cp1252'},
    )
    assert r.returncode == 2
    assert r.stdout == b''
    assert '--opcion-inválida' in r.stderr.decode('utf-8')


def test_sin_mcp_en_la_web_ni_en_src():
    """077:RF-40 — ni la web ni `src/` importan `mcp`: que falte no puede romperlas."""
    malos = []
    for p in (RAIZ / 'src').rglob('*.py'):
        for n in ast.walk(ast.parse(p.read_text(encoding='utf-8', errors='replace'))):
            nombres = [a.name for a in n.names] if isinstance(n, ast.Import) else [getattr(n, 'module', None) or ''] if isinstance(n, ast.ImportFrom) else []
            if any(x == 'mcp' or x.startswith('mcp.') for x in nombres):
                malos.append(p.name)
    assert not malos
    requisitos = (RAIZ / 'requirements.txt').read_text(encoding='utf-8').casefold()
    assert 'mcp' not in {linea.split('>')[0].split('=')[0].strip() for linea in requisitos.splitlines()}


def test_sin_red_ni_escritura_en_el_guion():
    """077:RF-37 — solo stdio: el guion no menciona transporte HTTP ni escribe en disco."""
    fuente = GUION.read_text(encoding='utf-8')
    arbol = ast.parse(fuente)
    importados = {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    importados |= {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
    assert 'mcp.server.stdio' in importados
    assert not {x for x in importados if 'sse' in x or 'streamable' in x or 'http' in x or x == 'uvicorn'}
    llamadas = {n.func.attr for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not llamadas & {'write_text', 'write_bytes', 'unlink', 'mkdir', 'open'}
    assert 'lectura_proyecto.catalogo()' in fuente and 'lector.ejecutar' in fuente


def test_documentacion():
    """077:RF-41 — está documentado cómo conectarlo, con la orden y el fichero."""
    doc = (RAIZ / 'docs' / 'MCP_CONVERSOR.md').read_text(encoding='utf-8')
    for marca in ('mcpServers', 'tools/mcp_conversor.py', 'requirements-mcp.txt', 'stdio', 'claude mcp add'):
        assert marca in doc


def test_servidor_real_por_stdio():
    """077:RF-37 / 077:RF-38 / 077:RF-75 / 077:RF-76 — con un cliente real por stdio: tres herramientas de solo
    lectura, lo rechazado no sale, y el SDK es el fijado en requirements-mcp.txt."""
    exigir_mcp()
    version = subprocess.run([PYTHON_MCP, '-c', 'import importlib.metadata as m; print(m.version("mcp"))'],
                             capture_output=True, text=True, check=False, timeout=60).stdout.strip()
    assert f'mcp=={version}' in {linea.split()[0] for linea in lineas_del_lock(RAIZ / 'requirements-mcp.txt')}
    guion = r'''
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def principal():
    parametros = StdioServerParameters(command=sys.executable, args=[sys.argv[1]])
    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            herramientas = (await sesion.list_tools()).tools
            salida = {'nombres': sorted(h.name for h in herramientas),
                      'solo_lectura': [h.annotations.read_only_hint for h in herramientas],
                      'destructiva': [h.annotations.destructive_hint for h in herramientas]}
            bueno = await sesion.call_tool('leer_fichero', {'ruta': 'CLAUDE.md', 'desde': 1, 'hasta': 2})
            salida['bueno'] = json.loads(bueno.content[0].text)['fuente']
            api = await sesion.call_tool('consultar_api', {'ruta': '/api/asistente/equipo'})
            salida['api'] = json.loads(api.content[0].text)['existe']
            busca = await sesion.call_tool('buscar_texto', {'texto': 'ConverterSmartGrid', 'tope': 2})
            salida['busca'] = len(json.loads(busca.content[0].text)['coincidencias'])
            for clave, nombre, args in (('negra', 'leer_fichero', {'ruta': 'OUTPUT/x.md'}), ('fuera', 'leer_fichero', {'ruta': '../x.md'}),
                                        ('env', 'leer_fichero', {'ruta': '.env'}), ('otra', 'escribir_fichero', {'ruta': 'x'})):
                r = await sesion.call_tool(nombre, args)
                salida[clave] = [r.is_error, r.content[0].text[:200]]
            print(json.dumps(salida))

asyncio.run(principal())
'''
    r = subprocess.run([PYTHON_MCP, '-c', guion, str(GUION)], capture_output=True, check=False, timeout=120,
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    # Conservar ambos canales antes de decodificar: una excepción del hilo lector
    # de subprocess no puede convertir una bitácora perdida en un test aprobado.
    assert r.returncode == 0, r.stderr[-2000:]
    diagnostico = r.stderr.decode('utf-8')
    assert "lectura fuera del catálogo: 'escribir_fichero'" in diagnostico
    salida = json.loads(r.stdout.decode('utf-8').strip().splitlines()[-1])
    assert salida['nombres'] == ['buscar_texto', 'consultar_api', 'consultar_norma', 'leer_fichero']
    assert all(salida['solo_lectura']) and not any(salida['destructiva'])
    assert salida['bueno'] == 'CLAUDE.md:1' and salida['api'] is True and salida['busca'] == 2
    for clave in ('negra', 'fuera', 'env', 'otra'):
        assert salida[clave][0] is True, clave


@pytest.mark.parametrize('opciones,abierto', [([], False), (['--datos-locales'], True)])
def test_servidor_real_y_sus_datos_locales(opciones, abierto):
    """077:RF-61 / 077:RF-62 / 077:RF-76 / 077:RF-77 — por stdio real: `.gitignore` solo se abre con la opción;
    secretos y sellados, nunca; y con la opción, el aviso del arranque."""
    exigir_mcp()
    guion = r'''
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def principal():
    async with stdio_client(StdioServerParameters(command=sys.executable, args=sys.argv[1:])) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            salida = {}
            for ruta in ('.gitignore', '.env', 'docs/CONJUNTO_ABSTENCION_SELLADO_077.json', 'output/ejemplos.jsonl'):
                r = await sesion.call_tool('leer_fichero', {'ruta': ruta, 'hasta': 1})
                salida[ruta] = r.is_error
            print(json.dumps(salida))

asyncio.run(principal())
'''
    r = subprocess.run([PYTHON_MCP, '-c', guion, str(GUION), *opciones], capture_output=True, check=False, timeout=120,
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert r.returncode == 0, r.stderr[-2000:]
    diagnostico = r.stderr.decode('utf-8')
    assert (AVISO in diagnostico) is abierto
    salida = json.loads(r.stdout.decode('utf-8').strip().splitlines()[-1])
    assert salida['.gitignore'] is (not abierto)
    assert all(salida[x] is True for x in ('.env', 'docs/CONJUNTO_ABSTENCION_SELLADO_077.json', 'output/ejemplos.jsonl'))


def test_herramientas_iguales_a_las_de_la_web():
    """077:RF-37 — el guion no define lecturas: sus funciones son solo el servidor y el registro."""
    arbol = ast.parse(GUION.read_text(encoding='utf-8'))
    assert {n.name for n in arbol.body if isinstance(n, ast.FunctionDef)} == {'_registrar', '_servidor', 'main'}


#: Lo que el arranque con `--datos-locales` dice siempre (077:RF-77).
AVISO = 'solo a un cliente local de confianza'


def test_077_rf75_el_sdk_va_fijado_con_version_exacta_y_huella():
    """077:RF-75 — requirements-mcp.txt fija cada paquete con `==` y su huella, para `pip --require-hashes`."""
    lineas = lineas_del_lock(RAIZ / 'requirements-mcp.txt')
    nombres = {linea.split('==')[0].casefold() for linea in lineas}
    assert {'mcp', 'mcp-types', 'anyio', 'pydantic', 'starlette'} <= nombres
    for linea in lineas:
        assert re.fullmatch(r'[a-z0-9][a-z0-9._-]*==[0-9][^ ]*( --hash=sha256:[0-9a-f]{64})+', linea), linea
    assert 'mcp==2.3.0' in {linea.split()[0] for linea in lineas}
    doc = (RAIZ / 'docs' / 'MCP_CONVERSOR.md').read_text(encoding='utf-8')
    assert '--require-hashes -r requirements-mcp.txt' in doc


def test_077_rf76_un_interprete_configurado_sin_mcp_falla_y_no_se_omite(tmp_path):
    """077:RF-76 — con CSG_MCP_PYTHON o el .venv_mcp, que falte el paquete es un fallo; sin ninguno, una omisión dicha."""
    falso = str(tmp_path / 'no_hay' / 'python.exe')
    assert python_mcp({'CSG_MCP_PYTHON': falso}, tmp_path) == (falso, True)
    with pytest.raises(pytest.fail.Exception, match='077:RF-76'):
        exigir_mcp(falso, True)
    with pytest.raises(pytest.skip.Exception, match='CSG_MCP_PYTHON'):
        exigir_mcp(falso, False)
    assert python_mcp({}, tmp_path) == (sys.executable, False)
    propio = tmp_path / '.venv_mcp' / 'Scripts' / 'python.exe'
    propio.parent.mkdir(parents=True)
    propio.write_bytes(b'')
    assert python_mcp({}, tmp_path) == (str(propio), True)
    assert '.venv_mcp/' in (RAIZ / '.gitignore').read_text(encoding='utf-8').splitlines()
    doc = (RAIZ / 'docs' / 'MCP_CONVERSOR.md').read_text(encoding='utf-8')
    assert '.venv_mcp' in doc and 'CSG_MCP_PYTHON' in doc


def _arrancar_sin_red(monkeypatch, opciones):
    """El arranque del guion hasta antes de servir, con un `mcp` de mentira: sin el paquete ni ningún cliente."""
    import types as tipos

    import anyio

    for nombre in ('mcp', 'mcp.server'):
        monkeypatch.setitem(sys.modules, nombre, tipos.ModuleType(nombre))
    monkeypatch.setitem(sys.modules, 'mcp.server.stdio', tipos.SimpleNamespace(stdio_server=None))
    monkeypatch.setattr(anyio, 'run', lambda _f: None)
    modulo = _cargar()
    monkeypatch.setattr(modulo, '_servidor', lambda _lector: None)
    return modulo.main(opciones)


@pytest.mark.parametrize('opciones,avisa', [([], False), (['--datos-locales'], True)])
def test_077_rf77_datos_locales_avisa_en_el_arranque(monkeypatch, capsys, opciones, avisa):
    """077:RF-77 — con `--datos-locales`, el arranque avisa por stderr de que expone los datos locales solo a un cliente
    local de confianza; sin la opción, no avisa. stdout queda limpio: es el canal del protocolo."""
    assert _arrancar_sin_red(monkeypatch, opciones) == 0
    salida = capsys.readouterr()
    assert (AVISO in salida.err) is avisa and salida.out == ''
    if avisa:
        assert 'sale con él' in salida.err and 'esta máquina' in salida.err
