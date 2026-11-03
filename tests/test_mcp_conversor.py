"""Spec 077: el servidor MCP local de solo lectura, con y sin su paquete opcional."""
from __future__ import annotations

import ast
import builtins
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
GUION = RAIZ / 'tools' / 'mcp_conversor.py'
#: Con otro intérprete que sí tenga `mcp`, sin instalarlo en el entorno del proyecto.
PYTHON_MCP = os.environ.get('CSG_MCP_PYTHON') or sys.executable


def _cargar():
    spec = importlib.util.spec_from_file_location('mcp_conversor', GUION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _hay_mcp() -> bool:
    r = subprocess.run([PYTHON_MCP, '-c', 'import mcp'], capture_output=True, check=False)
    return r.returncode == 0


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


@pytest.mark.skipif(not _hay_mcp(), reason='CSG_MCP_PYTHON no apunta a un intérprete con el paquete opcional mcp')
def test_servidor_real_por_stdio():
    """077:RF-37 / 077:RF-38 — con un cliente real por stdio: tres herramientas de solo lectura, y lo rechazado no sale."""
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
    r = subprocess.run([PYTHON_MCP, '-c', guion, str(GUION)], capture_output=True, encoding='utf-8', check=False, timeout=120,
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert r.returncode == 0, r.stderr[-2000:]
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida['nombres'] == ['buscar_texto', 'consultar_api', 'leer_fichero']
    assert all(salida['solo_lectura']) and not any(salida['destructiva'])
    assert salida['bueno'] == 'CLAUDE.md:1' and salida['api'] is True and salida['busca'] == 2
    for clave in ('negra', 'fuera', 'env', 'otra'):
        assert salida[clave][0] is True, clave


def test_herramientas_iguales_a_las_de_la_web():
    """077:RF-37 — el guion no define lecturas: sus funciones son solo el servidor y el registro."""
    arbol = ast.parse(GUION.read_text(encoding='utf-8'))
    assert {n.name for n in arbol.body if isinstance(n, ast.FunctionDef)} == {'_registrar', '_servidor', 'main'}
