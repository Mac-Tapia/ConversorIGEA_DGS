"""La semilla de los seudónimos es secreta: se queda en el equipo de la empresa (112:RF-5, RF-12).

Con el código público y la semilla, quien tenga la lista de códigos originales rehace el mapa entero (plan de la 112,
revisión de privacidad). Por eso la semilla de los seudónimos se guarda solo en la carpeta local de la instalación
(``raiz_local()/benchmarks/<huella del origen>/semilla``), fuera del destino del benchmark, y el manifiesto lleva en su
lugar ``sha256("publica:" + semilla)``: sirve para reconocer que dos benchmarks salen de la misma semilla, y de ella no
se vuelve a la secreta.

Una semilla corta no se admite: sus cifras aparecen en cualquier tabla y el control de reidentificación no podría
distinguir una fuga de un número cualquiera.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from ..runtime_paths import raiz_local

#: Cifras mínimas de una semilla secreta. Las que se sortean tienen 63 bits (hasta 19 cifras).
CIFRAS_MINIMAS = 12


def nueva_semilla() -> int:
    """Una semilla secreta sorteada con el generador del sistema, con las cifras suficientes."""
    while True:
        s = secrets.randbits(63)
        if len(str(s)) >= CIFRAS_MINIMAS:
            return s


def validar_secreta(semilla: int) -> int:
    if not isinstance(semilla, int) or isinstance(semilla, bool) or semilla < 0 or len(str(semilla)) < CIFRAS_MINIMAS:
        raise ValueError(f'la semilla de los seudónimos necesita {CIFRAS_MINIMAS} cifras o más: una corta no se '
                         'distingue de cualquier número del benchmark y el control no vería su fuga')
    return semilla


def semilla_publica(semilla: int) -> str:
    """La derivada de un solo sentido que va al manifiesto en lugar de la secreta."""
    return hashlib.sha256(f'publica:{int(semilla)}'.encode('utf-8')).hexdigest()


def _ruta(huella_origen: str, raiz: Path | None) -> Path:
    if not huella_origen or not all(c in '0123456789abcdef' for c in huella_origen):
        raise ValueError('la huella del origen tiene que ser un SHA-256 en hexadecimal')
    return Path(raiz if raiz is not None else raiz_local()) / 'benchmarks' / huella_origen / 'semilla'


def guardar_secreta(huella_origen: str, semilla: int, *, raiz: Path | None = None) -> Path:
    """Guarda la secreta en el equipo, por la huella del origen. Si ya hay una distinta, no la pisa."""
    ruta = _ruta(huella_origen, raiz)
    validar_secreta(semilla)
    previa = leer_secreta(huella_origen, raiz=raiz)
    if previa is not None:
        if previa != semilla:
            raise FileExistsError('ya hay otra semilla guardada para este origen: se conserva la anterior')
        return ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix('.tmp')
    temporal.write_text(str(semilla), encoding='utf-8')
    os.replace(temporal, ruta)
    return ruta


def leer_secreta(huella_origen: str, *, raiz: Path | None = None) -> int | None:
    ruta = _ruta(huella_origen, raiz)
    try:
        return int(ruta.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return None
