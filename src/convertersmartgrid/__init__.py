"""Motor universal de conversión CYMDIST (TXT o Access) a DGS de DIgSILENT."""

# La única versión del programa (086:RF-43, RF-92): pyproject la lee de aquí, el candidato la pone en el nombre de su rueda
# y el .iss la saca de ese nombre. No se escribe en ningún otro sitio: el rc5 se armó con «--version» y «/DVersion» a mano
# mientras aquí seguía 1.0.0rc1, y su «Acerca de» enseñaba las notas del rc1.
__version__ = '1.0.0rc6'

# 106:RF-18: antes del primer cuInit de cualquier modelo del producto, en este proceso o en un hijo que importe el
# paquete. Con el controlador NVIDIA 560.94, iniciar CUDA dejaba un hilo en una DLL ya descargada y el proceso moría con
# 0xC0000005 a los ~90 s; aquí solo se deja un buscador de módulos que actúa al importar torch.
from .compat_gpu import instalar_antes_de_torch as _instalar_antes_de_torch

_instalar_antes_de_torch()


def seccion_de_notas(texto: str, version: str) -> str | None:
    """El apartado ``## <versión>`` de unas notas, con su título; ``None`` si no lo tienen (086:RF-93)."""
    import re

    apartado = re.search(rf'^## {re.escape(version)}(?=[ (]|$).*?(?=^## |\Z)', texto, flags=re.M | re.S)
    return apartado.group(0).rstrip() + '\n' if apartado else None


def notas_de_la_version() -> str:
    """Las notas de esta versión (086:RF-43): van dentro del paquete, para que no se separen de ella.

    086:RF-93: solo el apartado de esta versión, con el título del fichero; las de versiones anteriores no se enseñan.
    """
    from pathlib import Path

    try:
        texto = (Path(__file__).resolve().parent / 'recursos' / 'NOTAS_VERSION.md').read_text(encoding='utf-8')
    except OSError:
        return ''
    apartado = seccion_de_notas(texto, __version__)
    if apartado is None:
        # Un ensayo con otra versión («construir_candidato --version») no tiene apartado propio: se enseña todo.
        return texto
    titulo = texto.split('\n', 1)[0] if texto.startswith('# ') else '# Notas de la versión'
    return f'{titulo}\n\n{apartado}'
