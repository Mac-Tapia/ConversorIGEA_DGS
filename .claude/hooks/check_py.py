"""Hook PostToolUse: compila el .py recién editado para cazar errores de sintaxis al momento (102:RF-34).

Sale con 2 (el error vuelve a Claude) si un .py del proyecto no compila; en cualquier otro caso, 0. El proyecto es
``CLAUDE_PROJECT_DIR`` (o la carpeta de este hook), y su código está en ``src/``, ``tools/``, ``tests/``, ``tests_ml/`` y
``.claude/hooks/``: una carpeta ``src`` de otro proyecto no se mira. Compila en memoria, sin escribir ``__pycache__``.
No sustituye a la puerta de calidad (102): solo adelanta el aviso. Antes miraba solo ``src`` y ``tests``, y una
herramienta de ``tools/`` rota pasaba (auditoría del 18-11, H10).
"""
import json
import os
import sys
from pathlib import Path

CARPETAS_DE_CODIGO = (('src',), ('tools',), ('tests',), ('tests_ml',), ('.claude', 'hooks'))

try:
    payload = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
tool_input = (payload.get('tool_input') or {}) if isinstance(payload, dict) else {}
texto = (tool_input.get('file_path') or '') if isinstance(tool_input, dict) else ''
if not texto:
    sys.exit(0)
path = Path(texto)
if path.suffix != '.py' or not path.is_file():
    sys.exit(0)
raiz = Path(os.environ.get('CLAUDE_PROJECT_DIR') or Path(__file__).resolve().parents[2])
try:
    relativa = path.resolve().relative_to(raiz.resolve())
except (OSError, ValueError):
    sys.exit(0)                                   # fuera del proyecto
partes = tuple(p.lower() for p in relativa.parts)
if not any(partes[:len(c)] == c for c in CARPETAS_DE_CODIGO):
    sys.exit(0)
try:
    fuente = path.read_bytes()
except OSError:
    sys.exit(0)
try:
    compile(fuente, str(path), 'exec', dont_inherit=True)
except (SyntaxError, ValueError) as exc:
    print(f'Error de sintaxis en {path}:\n{exc}', file=sys.stderr)
    sys.exit(2)
