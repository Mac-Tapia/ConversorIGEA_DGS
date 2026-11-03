#!/usr/bin/env python
"""Servidor MCP local y de solo lectura del proyecto: leer, buscar y consultar la API (spec 077).

Solo por stdio, sin puerto ni red. No tiene lógica propia: cada herramienta es una lectura de
`asistente/lectura_proyecto.py` por `LecturaGobernada`, con el rol `cliente_mcp`, las mismas listas y el mismo tope
que la web. No escribe nada, ni la bitácora: va a stderr (stdout es el canal del protocolo).

Dependencia opcional: `pip install -r requirements-mcp.txt`. Cómo conectarlo: docs/MCP_CONVERSOR.md.
Códigos de salida: 0 correcto, 3 falta el paquete `mcp`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))
SIN_PAQUETE = 3


def _registrar(fila: dict[str, Any]) -> None:
    print(json.dumps(fila, ensure_ascii=False, default=str), file=sys.stderr, flush=True)


def _servidor(lector: Any) -> Any:
    """El servidor con el SDK de bajo nivel, porque así el esquema es el del catálogo y no se escribe dos veces."""
    from mcp import types
    from mcp.server.lowlevel import Server

    from convertersmartgrid.asistente import lectura_proyecto

    async def herramientas(_contexto: Any, _parametros: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(name=h['nombre'], description=h['descripcion'], input_schema=h['esquema'],
                       annotations=types.ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                                                         open_world_hint=False))
            for h in lectura_proyecto.catalogo()])

    async def llamar(_contexto: Any, parametros: types.CallToolRequestParams) -> types.CallToolResult:
        # La validación es la del catálogo, en lector.ejecutar: la misma de la web, también ante un cliente que no la haga.
        try:
            salida = lector.ejecutar(parametros.name, parametros.arguments or {})
        except (ValueError, OSError) as exc:
            return types.CallToolResult(is_error=True, content=[types.TextContent(type='text', text=f'lectura rechazada: {exc}')])
        return types.CallToolResult(content=[types.TextContent(type='text', text=json.dumps(salida, ensure_ascii=False))])

    return Server('conversor-solo-lectura', on_list_tools=herramientas, on_call_tool=llamar)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)
    try:
        import anyio
        from mcp.server.stdio import stdio_server
    except ImportError:
        print('Falta el paquete opcional «mcp»: pip install -r requirements-mcp.txt. La web no lo necesita.', file=sys.stderr)
        return SIN_PAQUETE
    from convertersmartgrid.asistente.equipo import LecturaGobernada

    servidor = _servidor(LecturaGobernada(REPO, rol='cliente_mcp', registrar=_registrar))

    async def correr() -> None:
        async with stdio_server() as (lectura, escritura):
            await servidor.run(lectura, escritura, servidor.create_initialization_options())

    anyio.run(correr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
