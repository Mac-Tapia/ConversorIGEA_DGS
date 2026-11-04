"""Motor universal de conversión CYMDIST (TXT o Access) a DGS de DIgSILENT."""

# La única versión del programa (086:RF-43): pyproject la lee de aquí, y una prueba compara el resto.
__version__ = '1.0.0rc1'


def notas_de_la_version() -> str:
    """Las notas de esta versión (086:RF-43): van dentro del paquete, para que no se separen de ella."""
    from pathlib import Path

    try:
        return (Path(__file__).resolve().parent / 'recursos' / 'NOTAS_VERSION.md').read_text(encoding='utf-8')
    except OSError:
        return ''
