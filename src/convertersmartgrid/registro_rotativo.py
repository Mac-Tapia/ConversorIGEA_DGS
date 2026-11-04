"""El registro del programa en ficheros rotativos (086:RF-41).

Antes el servidor solo escribía en su consola: al cerrarla no quedaba nada que mirar, y una instalación en
casa de un cliente no tenía cómo explicar un fallo. Los ficheros van con los datos de ejecución, no con el programa,
para que sobrevivan a una actualización y para no escribir en una carpeta que puede ser de solo lectura.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .runtime_paths import rutas_runtime

#: Cinco ficheros de 5 MB: bastan para varios días de trabajo y no llenan un disco en un año.
TAMANO_MAXIMO = 5 * 1024 * 1024
COPIAS = 4
_FORMATO = '%(asctime)s %(levelname)s %(name)s: %(message)s'
#: Los que el servidor escribe además del programa.
_REGISTROS = ('convertersmartgrid', 'vnr_etl', 'uvicorn.error')
_manejadores: dict[Path, RotatingFileHandler] = {}


class _Rotativo(RotatingFileHandler):
    """Si otro proceso tiene abierto el fichero, Windows no deja renombrarlo: se sigue en el mismo.

    Dos webs en dos puertos comparten carpeta; sin esto, cada línea daba un error en la consola al pasar
    del tamaño, y una traza por no poder rotar un registro es peor que un fichero algo más largo.
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            if self.stream is None:
                self.stream = self._open()


def carpeta_de_registros(raiz: Path | None = None) -> Path:
    return rutas_runtime(raiz).runtime / 'registros'


def configurar_registro(nombre: str, *, carpeta: Path | None = None, nivel: int = logging.INFO,
                        tamano: int = TAMANO_MAXIMO, copias: int = COPIAS) -> Path | None:
    """Añade ``<carpeta>/<nombre>.log`` a los registros del programa; devuelve su ruta.

    Sin carpeta donde escribir devuelve None y el programa sigue: quedarse sin registro no impide convertir.
    """
    destino = carpeta_de_registros() if carpeta is None else carpeta
    ruta = (destino / f'{nombre}.log').resolve()
    manejador = _manejadores.get(ruta)
    if manejador is None:
        try:
            destino.mkdir(parents=True, exist_ok=True)
            # delay: sin nada que anotar no se crea el fichero ni queda abierto.
            manejador = _Rotativo(ruta, maxBytes=tamano, backupCount=copias, encoding='utf-8', delay=True)
        except OSError:
            return None
        manejador.setFormatter(logging.Formatter(_FORMATO))
        manejador.setLevel(nivel)
        _manejadores[ruta] = manejador
    # Se puede llamar otra vez: la configuración de uvicorn quita los manejadores de sus registros al crearse.
    for nombre_registro in _REGISTROS:
        registro = logging.getLogger(nombre_registro)
        if manejador not in registro.handlers:
            registro.addHandler(manejador)
        if registro.level == logging.NOTSET or registro.level > nivel:
            registro.setLevel(nivel)
    return ruta
