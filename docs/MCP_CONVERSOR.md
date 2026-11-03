# Servidor MCP local del conversor

Da a un cliente MCP de esta máquina las mismas tres lecturas que usa el asistente de la web (spec 077). Solo lectura y solo
por stdio: no abre ningún puerto, no llama a la web, no escribe nada y no necesita GPU ni DIgSILENT.

| Herramienta | Qué hace |
| --- | --- |
| `leer_fichero` | Lee un fichero permitido por rango de líneas, 200 como mucho por lectura. |
| `buscar_texto` | Busca un texto literal en los ficheros permitidos, 30 resultados como mucho. |
| `consultar_api` | Consulta una ruta en `docs/asistente/openapi.json`, sin hacer ninguna petición. |

## Instalar

El paquete `mcp` es opcional y va aparte: sin él, la web y el CLI funcionan igual.

```bash
.venv/Scripts/python.exe -m pip install -r requirements-mcp.txt
```

Sin el paquete, `tools/mcp_conversor.py` lo dice y termina con el código 3.

## Conectar

En un cliente que use el formato `mcpServers`, por ejemplo Claude Code en `.mcp.json` en la raíz del repositorio, con las rutas
absolutas de su máquina:

```json
{
  "mcpServers": {
    "conversor": {
      "type": "stdio",
      "command": "D:/ruta/al/repositorio/.venv/Scripts/python.exe",
      "args": ["D:/ruta/al/repositorio/tools/mcp_conversor.py"]
    }
  }
}
```

O con la orden de Claude Code, `claude mcp add conversor -- <python> <repositorio>/tools/mcp_conversor.py`.

## Datos locales

Por defecto el servidor usa la política restringida de abajo, porque un cliente MCP puede estar en la nube y lo que lea sale de
la máquina con él. Si el cliente es local de verdad, se abre con `--datos-locales`, añadido a `args`:

```json
"args": ["D:/ruta/al/repositorio/tools/mcp_conversor.py", "--datos-locales"]
```

Abre lo mismo que el LLM local de la web: todo el árbol del proyecto y las raíces de `CSG_LLM_RAICES`, `CSG_DEMANDA_DIR` y
`raices_llm` del perfil. Nunca abre credenciales ni secretos, conjuntos sellados y sus resultados, `ejemplos.jsonl` ni
`etiquetas*.jsonl`. El servidor no puede comprobar dónde corre su cliente: esa decisión es de quien añade la opción.

## Qué se puede leer con la política restringida

La lista blanca y la lista negra están en `src/convertersmartgrid/asistente/lectura_proyecto.py`, y las publica
`GET /api/asistente/equipo` en `lectura_proyecto`. La lista negra manda sobre la blanca y no distingue mayúsculas.

- Se lee: `src/`, `tools/`, `tests/`, `tests_ml/`, `docs/`, `specs/`, `frontend/src/`, `.claude/skills/`, `CLAUDE.md`, `CODIGO_FUENTE.md`,
  `README*`, `VNR-GIS.md`, `pyproject.toml`, `requirements*.txt`, `constraints-*.txt`, `run_gui.bat`, `frontend/package.json` y los
  ejemplos de `config/`.
- No se lee: `output/`, `input/`, `config/perfil_empresa.json`, `config/perfiles/`, `.env`, credenciales y secretos, `.agents/`,
  `.git/`, `.venv/`, `.worktrees/`, `maestro_real/`, los datos de la distribuidora, los conjuntos sellados y sus resultados.
- Tampoco: nada fuera del repositorio, rutas absolutas, `..`, enlaces que lleven a lo anterior, enlaces duros, nombres cortos de
  Windows y flujos alternativos de NTFS.

La bitácora de cada lectura va a stderr, con el rol `cliente_mcp`; el servidor no guarda nada en disco.

## Comprobar

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_mcp_conversor.py
```
