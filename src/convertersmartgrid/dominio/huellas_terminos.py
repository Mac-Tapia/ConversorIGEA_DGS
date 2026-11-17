"""La huella de un término (076:RF-6, 086:RF-33): ``sha256('sal:texto normalizado')[:16]``.

Es la forma con la que se versionan sin sus nombres la lista mínima de términos (``config/terminos_huellas.json``) y los
nombres de los elementos del registro normativo (107 T3, PIT-ANON-ELEMENTOS). Un solo cuerpo para la herramienta de
la entrega (``tools/comprobar_entrega.py``) y el producto: la misma huella se calcula igual en los dos.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

__all__ = ['SAL', 'huella', 'normalizar']

#: La sal de la lista mínima de 086:RF-33, también la de los nombres del registro normativo.
SAL = '086'
_TOKEN = re.compile(r'[a-z0-9]+')


def normalizar(texto: Any) -> str:
    """Solo letras y cifras: un guion bajo, una tilde o una mayúscula no esconden un nombre (076:RF-6)."""
    plano = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(_TOKEN.findall(plano))


def huella(termino: str, sal: str = SAL) -> str:
    """La misma forma de 076:RF-6: sha256('sal:texto normalizado')[:16]; la lista se versiona sin los nombres."""
    return hashlib.sha256(f'{sal}:{normalizar(termino)}'.encode()).hexdigest()[:16]
