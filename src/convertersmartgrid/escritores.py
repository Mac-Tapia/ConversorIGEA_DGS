"""El escritor DGS como un módulo más, y la entrega a cualquier escritor (002:RF-9, RF-13).

Un escritor de otro formato no puede saltarse las reglas del proyecto: recibe el mismo
modelo que el DGS, ya preparado, con las reglas aplicadas y auditado contra la entrada.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .dgs import write_dgs
from .model import build_feeder_model
from .puertos import VERSION_PUERTOS, EscritorDeRed, Modulo
from .reglas import REGLAS_PROYECTO, Reglas, aplicar_reglas, auditar_completitud, preparar_dataset
from .validate import parse_dgs


class EscritorDgs:
    """Escribe el DGS con el perfil de esquema por defecto."""

    def escribir(self, modelo: Any, destino: Path, *, auditoria: Any) -> Any:
        return write_dgs(modelo, destino)


MODULO_DGS = Modulo('escritor-dgs', 'escritor', VERSION_PUERTOS, EscritorDgs)


def entregar_al_escritor(escritor: EscritorDeRed, dataset: Any, red: str, destino: Path | str, *,
                         reglas: Reglas = REGLAS_PROYECTO, catalogo: Path | str | None = None) -> Any:
    """``preparar_dataset`` → modelo → ``aplicar_reglas`` → ``auditar_completitud`` → escritor."""
    preparar_dataset(dataset, catalogo=catalogo)
    modelo = build_feeder_model(dataset, red)
    informe = aplicar_reglas(modelo, reglas)
    # La auditoría compara la entrada con las tablas de un DGS: se escribe uno aparte para
    # que sea la misma comprobación cualquiera que sea el formato de salida.
    with tempfile.TemporaryDirectory(prefix='csg_auditoria_') as carpeta:
        ruta = Path(carpeta) / 'auditoria.dgs'
        write_dgs(modelo, ruta)
        auditoria = auditar_completitud(dataset, [red], modelo, parse_dgs(ruta), [informe])
    return escritor.escribir(modelo, Path(destino), auditoria=auditoria)
