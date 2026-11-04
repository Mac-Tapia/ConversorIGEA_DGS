"""Interfaces por las que un módulo se enchufa al conversor (002:RF-7).

Un módulo, propio o de otro paquete, declara en el grupo de entry points
``convertersmartgrid.modulos`` un objeto :class:`Modulo`. El registro comprueba la versión
mayor (RF-25) y los métodos de su puerto (RF-11) antes de darlo por bueno.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

#: Una versión mayor distinta excluye al módulo; una menor solo añade y no rompe (RF-25).
VERSION_PUERTOS = '1.0'


@runtime_checkable
class LectorDeRed(Protocol):
    """Lee una entrada y entrega el dataset común; es el contrato de ``sources.SourceAdapter``."""

    mode: str

    def load(self, snapshot: Any, *, aliases: dict[str, str]) -> Any:
        ...


@runtime_checkable
class EscritorDeRed(Protocol):
    """Recibe el modelo ya preparado, con las reglas aplicadas y auditado (RF-13)."""

    def escribir(self, modelo: Any, destino: Path, *, auditoria: Mapping[str, Any]) -> Any:
        ...


@runtime_checkable
class Estudio(Protocol):
    """Un estudio corre siempre como trabajo en cola y cancelable (RF-14, RF-30)."""

    usa_powerfactory: bool

    def ejecutar(self, ctx: Any, **parametros: Any) -> Any:
        ...


@runtime_checkable
class SesionPowerFactory(Protocol):
    """Una sesión de PowerFactory corre siempre en el carril único (RF-14)."""

    def ejecutar(self, ctx: Any, **parametros: Any) -> Any:
        ...


#: Puerto → atributos que debe tener la implementación. Se comprueban con nombres, sin crear
#: una instancia: crear un lector real puede abrir ficheros o cargar un driver.
PUERTOS: dict[str, tuple[str, ...]] = {
    'lector': ('mode', 'load'),
    'escritor': ('escribir',),
    'estudio': ('usa_powerfactory', 'ejecutar'),
    'sesion': ('ejecutar',),
}


@dataclass(frozen=True)
class Modulo:
    """Lo que declara un entry point: su nombre, su puerto, su versión y cómo fabricarlo."""

    nombre: str
    puerto: str
    version_puerto: str
    implementacion: Callable[..., Any]


def metodos_que_faltan(modulo: Modulo) -> tuple[str, ...]:
    """Atributos del puerto que la implementación no tiene (RF-11)."""
    return tuple(a for a in PUERTOS.get(modulo.puerto, ()) if not hasattr(modulo.implementacion, a))
