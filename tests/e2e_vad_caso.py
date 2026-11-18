"""Escribe el caso sintético de dos sistemas del recorrido F06 (108 T30): el mismo de ``tests/test_vad_linea.py``.

Uso: python tests/e2e_vad_caso.py <salida.zip>. Con el registro del TdR real y valores sacados de sus propias
fórmulas, sin datos de ninguna empresa: S1 con resultados, Anexo 2 y explotación; S2 solo con resultados.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_vad_linea import _caso, _registro  # noqa: E402  (las mismas piezas que la prueba por la API)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print('Uso: python tests/e2e_vad_caso.py <salida.zip>')
        return 2
    destino = Path(argv[0])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(_caso(_registro()))
    print(destino)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
