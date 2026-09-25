"""Hook PostToolUse: compila el .py recién editado para cazar errores de sintaxis al momento.

Sale con 2 (el error vuelve a Claude) si el fichero no compila; en cualquier otro caso, 0.
Solo mira src/ y tests/: el resto no es código del proyecto.
"""
import json
import py_compile
import sys
from pathlib import Path

try:
    payload = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
tool_input = payload.get('tool_input') or {}
path = Path(tool_input.get('file_path') or '')
parts = {p.lower() for p in path.parts}
if path.suffix != '.py' or not ({'src', 'tests'} & parts) or not path.is_file():
    sys.exit(0)
try:
    py_compile.compile(str(path), doraise=True, cfile=None)
except py_compile.PyCompileError as exc:
    print(f'Error de sintaxis en {path}:\n{exc.msg}', file=sys.stderr)
    sys.exit(2)
