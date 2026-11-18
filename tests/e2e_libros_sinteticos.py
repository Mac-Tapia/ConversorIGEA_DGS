"""Libros de demanda sintéticos del recorrido F10 (104 T6): los mismos de ``tests/test_libros_nuevos_web.py``.

Uso:
  python tests/e2e_libros_sinteticos.py preparar <carpeta>   → clientes de septiembre 2026, cabecera, medidores y
                                                                suministros, y un JSON con la ruta de cada uno
  python tests/e2e_libros_sinteticos.py octubre <carpeta>    → deja caer el libro nuevo de clientes de octubre 2026

Nombres que no son de ninguna empresa (clientes «111», «222», «333», alimentador «A1», SED «S1», medidor «M1»); ningún
dato real. La web los reconoce sola: el recorrido no pulsa nada para que aparezca el aviso.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_libros_nuevos import _mes_completo  # noqa: E402
from test_pronostico_demanda import _equivalencia, _libro_cabecera, _libro_clientes, _serie, _suministros  # noqa: E402


def preparar(carpeta: Path) -> dict[str, str]:
    cli = carpeta / 'clientes'
    _libro_clientes(cli / '2026/0926clientes.xlsx',
                    {c: _mes_completo(2026, 9, 20., ruido=i) for i, c in enumerate(('111', '222'))})
    sumi = _suministros(carpeta / 'suministros/0926 Clientes_spl.xlsx',
                        [('111', '111', 'S1', 'A1'), ('222', '222', 'S1', 'A1')])
    _libro_cabecera(carpeta / 'cab/2026/s.xlsx', {'M1': _serie(60, 200.0, inicio=_mes_completo(2026, 9)[0][0])})
    eq = _equivalencia(carpeta / 'eq.xlsx', [('A1', 'M1', 10.0, 'S1')])
    return {'clientes': str(cli), 'suministros': str(sumi), 'cabecera': str(carpeta / 'cab'), 'medidores': str(eq)}


def octubre(carpeta: Path) -> str:
    destino = carpeta / 'clientes/2026/1026clientes.xlsx'
    _libro_clientes(destino, {'111': _mes_completo(2026, 10, 20., ruido=7), '222': _mes_completo(2026, 10, 30., ruido=8),
                              '333': _mes_completo(2026, 10, 9., ruido=9)})
    return str(destino)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ('preparar', 'octubre'):
        print(__doc__)
        return 2
    carpeta = Path(argv[1])
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = preparar(carpeta) if argv[0] == 'preparar' else {'octubre': octubre(carpeta)}
    print(json.dumps(salida, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
