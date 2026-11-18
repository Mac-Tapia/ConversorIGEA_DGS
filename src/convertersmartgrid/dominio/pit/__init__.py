"""Plan de Inversiones en Transmisión (PIT) de los sistemas secundario y complementario (spec 107).

Producto aparte del PIDE (107:RF-1): su norma, su horizonte, sus formatos y su expediente se guardan aparte, aunque
comparta con él la red, los motores y los costos. Ningún valor de un área, una empresa o un periodo está en el código
(107:RF-11): van en el perfil (``pit``) o en el registro normativo (``config/normativa``).
"""
from __future__ import annotations


class PitError(ValueError):
    """Un dato del PIT que falta o es imposible; el mensaje nombra la clave, el elemento o el año."""
